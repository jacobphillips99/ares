import json
import os
import traceback
import typing as t
from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

from ares.configs.base import Rollout
from ares.constants import ARES_DATA_DIR

EMBEDDING_DB_NAME = "embedding_data"
EMBEDDING_DB_PATH = os.path.join(ARES_DATA_DIR, EMBEDDING_DB_NAME)
STANDARDIZED_TIME_STEPS = 100
META_INDEX_NAMES = ["task_language_instruction", "description_estimate"]
TRAJECTORY_INDEX_NAMES = ["states", "actions"]


def rollout_to_index_name(rollout: Rollout | pd.Series, suffix: str) -> str:
    if isinstance(rollout, pd.Series):
        return f"{rollout['dataset_formalname']}-{rollout['robot_embodiment']}-{suffix}"
    return f"{rollout.dataset_formalname}-{rollout.robot.embodiment}-{suffix}"


def rollout_to_embedding_pack(rollout: Rollout) -> dict[str, np.ndarray | None]:
    pack = dict()
    for key in TRAJECTORY_INDEX_NAMES:
        val = getattr(rollout.trajectory, f"{key}_array", None)
        pack[rollout_to_index_name(rollout, suffix=key)] = val
    return pack


class NormalizationTracker:
    """Tracks mean and standard deviation statistics for online or batch normalization"""

    def __init__(
        self,
        feature_dim: int,
        initial_means: t.Optional[np.ndarray] = None,
        initial_stds: t.Optional[np.ndarray] = None,
    ):
        self.feature_dim = feature_dim
        # For online updates
        self.count = 0
        self.mean = (
            np.zeros(feature_dim) if initial_means is None else initial_means.copy()
        )
        self.M2 = np.zeros(feature_dim)  # For Welford's online algorithm
        # For batch computation
        self._cached_means = initial_means
        self._cached_stds = initial_stds

    def update_online(self, matrix: np.ndarray) -> None:
        """Update statistics using Welford's online algorithm"""
        # Ensure matrix is 2D with features as columns
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        elif matrix.ndim > 2:
            matrix = matrix.reshape(-1, self.feature_dim)

        for x in matrix:
            self.count += 1
            delta = x - self.mean
            self.mean += delta / self.count
            delta2 = x - self.mean
            self.M2 += delta * delta2

    def get_current_stats(self) -> tuple[np.ndarray, np.ndarray]:
        """Get current mean and std estimates"""
        if self.count < 2:
            return self.mean, np.ones_like(self.mean)

        variance = self.M2 / (self.count - 1)
        std = np.sqrt(variance)
        # Prevent division by zero in normalization
        std[std == 0] = 1.0
        return self.mean, std

    def compute_batch_stats(
        self, matrices: list[np.ndarray]
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute statistics from a batch of matrices"""
        # Reshape all matrices to 2D arrays with features as columns
        all_data = np.vstack([m.reshape(-1, self.feature_dim) for m in matrices])

        means = np.mean(all_data, axis=0)
        stds = np.std(all_data, axis=0)
        # Prevent division by zero in normalization
        stds[stds == 0] = 1.0

        self._cached_means = means
        self._cached_stds = stds
        return means, stds


class Index(ABC):
    """Base class for vector indices"""

    @abstractmethod
    def __init__(self, feature_dim: int, time_steps: int, online_norm: bool = False):
        self.feature_dim = feature_dim
        self.time_steps = time_steps
        self.total_dim = feature_dim * time_steps
        self.n_entries = 0

        # Initialize normalization constants to None
        self.norm_means: t.Optional[np.ndarray] = None
        self.norm_stds: t.Optional[np.ndarray] = None

        # t.Optional online normalization
        self.online_norm = online_norm
        if online_norm:
            self.norm_tracker = NormalizationTracker(feature_dim)

    @abstractmethod
    def add_vector(self, vector: np.ndarray, entry_id: str) -> None:
        """Add a single vector to the index"""
        pass

    @abstractmethod
    def search(
        self, query_vector: np.ndarray, k: int
    ) -> tuple[np.ndarray, list[str], np.ndarray]:
        """Search for similar vectors
        Returns:
            - distances: (n_queries, k) array of distances
            - ids: list of string IDs corresponding to the matches
            - vectors: (k, dimension) array of the matched vectors
        """
        pass

    @abstractmethod
    def save(self, path: Path) -> None:
        """Save index to disk"""
        pass

    @abstractmethod
    def load(self, path: Path) -> None:
        """Load index from disk"""
        pass

    @abstractmethod
    def delete(self) -> None:
        """Delete the index"""
        pass

    @abstractmethod
    def get_all_vectors(self) -> np.ndarray:
        """Get all vectors in the index"""
        pass

    @abstractmethod
    def get_all_ids(self) -> list[str]:
        """Get all string IDs in the index, in the same order as get_all_vectors()"""
        pass

    def set_normalization(self, means: np.ndarray, stds: np.ndarray) -> None:
        """Set normalization constants for each channel"""
        if means.shape[0] != self.feature_dim or stds.shape[0] != self.feature_dim:
            raise ValueError(
                f"Normalization constants must have shape ({self.feature_dim},)"
            )
        self.norm_means = means
        self.norm_stds = stds

    def normalize_matrix(self, matrix: np.ndarray) -> np.ndarray:
        """Apply channel-wise normalization if constants are set"""
        if self.norm_means is None or self.norm_stds is None:
            return matrix

        # Broadcasting will automatically align the dimensions
        return (matrix - self.norm_means) / self.norm_stds

    def denormalize_matrix(self, matrix: np.ndarray) -> np.ndarray:
        """Reverse normalization if constants are set"""
        if self.norm_means is None or self.norm_stds is None:
            return matrix
        # Broadcasting will automatically align the dimensions
        return (matrix * self.norm_stds) + self.norm_means

    @abstractmethod
    def get_vector_by_id(self, entry_id: str) -> t.Optional[np.ndarray]:
        """Get a vector by its string ID
        Returns:
            - vector: The vector if found, None otherwise
        """
        pass

    def update_normalization(self, matrix: np.ndarray) -> None:
        """Update normalization statistics if online normalization is enabled"""
        if self.online_norm:
            self.norm_tracker.update_online(matrix)
            self.norm_means, self.norm_stds = self.norm_tracker.get_current_stats()


class FaissIndex(Index):
    def __init__(self, feature_dim: int, time_steps: int, online_norm: bool = False):
        super().__init__(feature_dim, time_steps, online_norm)
        base_index = faiss.IndexFlatL2(self.total_dim)
        self.index = faiss.IndexIDMap2(base_index)
        self.id_map: dict[int, str] = {}
        self.next_id: int = 0

    def add_vector(self, vector: np.ndarray, entry_id: str) -> None:
        internal_id = self.next_id
        self.next_id += 1
        self.id_map[internal_id] = entry_id
        self.index.add_with_ids(vector.reshape(1, -1), np.array([internal_id]))
        self.n_entries += 1

    def search(
        self, query_vector: np.ndarray, k: int
    ) -> tuple[np.ndarray, list[str], np.ndarray]:
        distances, internal_indices = self.index.search(query_vector.reshape(1, -1), k)
        # -1 is the default value for faiss.IndexFlatL2 for no matches
        string_ids = [self.id_map[int(idx)] for idx in internal_indices[0] if idx != -1]
        if len(string_ids) == 0:
            # no matches found, use brute force search
            if self.index.ntotal <= 100:
                return self.brute_force_search(query_vector, k)
            else:
                return np.array([]), [], np.array([])
        else:
            vectors = [
                self.index.reconstruct(int(idx))
                for idx in internal_indices[0]
                if idx != -1
            ]
            vectors = np.vstack(vectors)
            return distances, string_ids, vectors

    def get_all_ids(self) -> np.ndarray:
        """Get all string IDs in the index, in the same order as get_all_vectors()"""
        return np.array([self.id_map[i] for i in range(self.index.ntotal)])

    def save(self, path: Path) -> None:
        self.last_save_path = str(path)  # Track where we last saved
        faiss.write_index(self.index, str(path))
        meta = {
            "feature_dim": self.feature_dim,
            "time_steps": self.time_steps,
            "n_entries": self.n_entries,
            "id_map": self.id_map,
            "next_id": self.next_id,
            "norm_means": (
                self.norm_means.tolist() if self.norm_means is not None else None
            ),
            "norm_stds": (
                self.norm_stds.tolist() if self.norm_stds is not None else None
            ),
        }
        with (path.parent / f"{path.stem}_meta.json").open("w") as f:
            json.dump(meta, f, indent=2)

    def load(self, path: Path) -> None:
        self.index = faiss.read_index(str(path))
        meta_path = path.parent / f"{path.stem}_meta.json"
        if meta_path.exists():
            with meta_path.open() as f:
                meta = json.load(f)
                self.feature_dim = meta["feature_dim"]
                self.time_steps = meta["time_steps"]
                self.total_dim = self.feature_dim * self.time_steps
                self.n_entries = meta["n_entries"]
                self.id_map = {int(k): v for k, v in meta["id_map"].items()}
                self.next_id = meta["next_id"]

                if meta["norm_means"] is not None:
                    self.norm_means = np.array(meta["norm_means"])
                    self.norm_stds = np.array(meta["norm_stds"])

    def get_all_vectors(self) -> np.ndarray:
        return np.vstack([self.index.reconstruct(i) for i in range(self.index.ntotal)])

    def get_vector_by_id(self, entry_id: str) -> t.Optional[np.ndarray]:
        """Get a vector by its string ID"""
        # Find the internal ID corresponding to the string ID
        internal_id = None
        for idx, str_id in self.id_map.items():
            if str_id == entry_id:
                internal_id = idx
                break

        if internal_id is None:
            return None

        return self.index.reconstruct(internal_id)

    def delete(self) -> None:
        """Delete the index from memory and remove associated files from disk"""
        # Reset in-memory state
        base_index = faiss.IndexFlatL2(self.total_dim)
        self.index = faiss.IndexIDMap2(base_index)
        self.id_map = {}
        self.next_id = 0
        self.n_entries = 0

        # Remove files from disk if they exist
        path = Path(self.last_save_path) if hasattr(self, "last_save_path") else None
        if path and path.exists():
            path.unlink()  # Delete the index file
            meta_path = path.parent / f"{path.stem}_meta.json"
            if meta_path.exists():
                meta_path.unlink()  # Delete the metadata file

    def brute_force_search(
        self, query_vector: np.ndarray, k: int, max_brute_force: int = 100
    ) -> tuple[np.ndarray, list[str], np.ndarray]:
        """Search using brute force comparison when index is small enough.
        More reliable than FAISS for small datasets."""
        assert (
            self.index.ntotal <= max_brute_force
        ), f"Index size {self.index.ntotal} is greater than max_brute_force {max_brute_force}"

        # Get all vectors and normalize them
        all_vectors = self.get_all_vectors()
        all_vectors = np.nan_to_num(all_vectors, nan=0.0)
        all_normed_vectors = all_vectors / np.linalg.norm(
            all_vectors, axis=1, keepdims=True
        )
        query_vector = query_vector.reshape(1, -1)
        query_vector = np.nan_to_num(query_vector, nan=0.0)
        query_vector = query_vector / np.linalg.norm(query_vector)

        # Calculate cosine similarities
        similarities = np.dot(all_normed_vectors, query_vector.T).flatten()

        # Get top k indices
        k = min(k, len(similarities))
        top_indices = np.argsort(similarities)[-k:][::-1]

        # Get corresponding distances, ids, and vectors
        distances = 1 - similarities[top_indices]  # Convert to distances
        string_ids = [self.id_map[i] for i in range(len(top_indices))]
        vectors = all_vectors[top_indices]
        return distances.reshape(1, -1), string_ids, vectors


class IndexManager:
    def __init__(
        self,
        base_dir: str,
        index_class: t.Type[Index],
        max_backups: int = 1,
        online_norm: bool = False,
    ):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True, parents=True)
        self.index_class = index_class
        self.max_backups = max_backups
        self.indices: dict[str, Index] = {}
        self.metadata: dict[str, dict] = {}
        self.online_norm = online_norm

        # Load existing indices if they exist
        self.load()

    def init_index(
        self,
        name: str,
        feature_dim: int,
        time_steps: int,
        norm_means: t.Optional[np.ndarray] = None,
        norm_stds: t.Optional[np.ndarray] = None,
        extra_metadata: t.Optional[dict] = None,
    ) -> None:
        if name in self.indices:
            raise ValueError(f"Index {name} already exists")

        index = self.index_class(feature_dim, time_steps, online_norm=self.online_norm)
        if norm_means is not None and norm_stds is not None:
            index.set_normalization(norm_means, norm_stds)

        self.indices[name] = index
        self.update_metadata(
            name,
            feature_dim=feature_dim,
            time_steps=time_steps,
            has_normalization=norm_means is not None,
            online_norm=self.online_norm,
            **(extra_metadata or {}),
        )

    def _interpolate_matrix(
        self, matrix: np.ndarray, target_time_steps: int
    ) -> np.ndarray:
        """Interpolate matrix to target number of time steps"""
        current_steps = matrix.shape[0]
        if current_steps == target_time_steps:
            return matrix

        # Create evenly spaced points for interpolation
        current_times = np.linspace(0, 1, current_steps)
        target_times = np.linspace(0, 1, target_time_steps)

        # Interpolate each feature dimension
        interpolated = np.zeros((target_time_steps, matrix.shape[1]))
        for feature in range(matrix.shape[1]):
            interpolator = interp1d(current_times, matrix[:, feature], kind="linear")
            interpolated[:, feature] = interpolator(target_times)

        return interpolated

    def add_vector(self, name: str, vector: np.ndarray, entry_id: str) -> None:
        """Add a vector directly to the index"""
        if name not in self.indices:
            feature_dim = vector.shape[0]
            self.init_index(name, feature_dim=feature_dim, time_steps=1)

        index = self.indices[name]
        if vector.shape[0] != index.total_dim:
            raise ValueError(
                f"Vector dimension {vector.shape[0]} does not match index dimension {index.total_dim}"
            )

        try:
            index.add_vector(vector, entry_id)
        except Exception as e:
            raise ValueError(f"Error adding vector to index {name}: {e}")
        self.metadata[name]["n_entries"] += 1

    def add_matrix(self, name: str, matrix: np.ndarray, entry_id: str) -> None:
        """Add a matrix to the index, applying interpolation and normalization"""
        if name not in self.indices:
            feature_dim = matrix.shape[1]
            default_time_steps = matrix.shape[0]
            self.init_index(
                name, feature_dim=feature_dim, time_steps=default_time_steps
            )

        index = self.indices[name]
        interpolated = self._interpolate_matrix(matrix, index.time_steps)

        # Update online normalization if enabled
        if self.online_norm:
            index.update_normalization(interpolated)

        normalized = index.normalize_matrix(interpolated)
        vector = normalized.flatten()
        self.add_vector(name, vector, entry_id)

    def load(self) -> None:
        """Load indices and metadata from disk"""
        # Load manager metadata first
        metadata_path = self.base_dir / "manager_metadata.json"
        if metadata_path.exists():
            with metadata_path.open("r") as f:
                self.metadata = json.load(f)

        # Load indices
        for path in self.base_dir.iterdir():
            if path.suffix == ".index":
                name = path.stem
                # Use metadata to get the correct dimensions
                if name in self.metadata:
                    self.init_index(
                        name,
                        feature_dim=self.metadata[name]["feature_dim"],
                        time_steps=self.metadata[name]["time_steps"],
                    )
                    self.load_index(name)

    def load_index(self, name: str) -> None:
        """Load an index from disk"""
        path = self.base_dir / f"{name}.index"
        if path.exists():
            self.indices[name].load(path)
            # Update metadata has_normalization flag based on loaded normalization constants
            self.metadata[name]["has_normalization"] = (
                self.indices[name].norm_means is not None
            )

    def save(self) -> None:
        """Save indices and metadata to disk"""
        # Save all indices
        for name, index in self.indices.items():
            self.save_index(name)

        # Save manager metadata
        metadata_path = self.base_dir / "manager_metadata.json"
        with metadata_path.open("w") as f:
            json.dump(self.metadata, f, indent=2)

    def save_index(self, name: str) -> None:
        """Save an index to disk"""
        path = self.base_dir / f"{name}.index"
        self.indices[name].save(path)

    def update_metadata(self, name: str, **kwargs: t.Any) -> None:
        """Update metadata for an index"""
        if name not in self.metadata:
            self.metadata[name] = {"n_entries": 0}  # Initialize with n_entries
        self.metadata[name].update(kwargs)  # Update with additional metadata

    def get_index_stats(self, name: str) -> dict:
        """Get statistics for an index"""
        return self.metadata[name]

    def get_overall_stats(self) -> dict:
        """Get statistics for all indices"""
        meta = self.metadata
        summary = defaultdict(list)
        for name, index_meta in meta.items():
            for k, v in index_meta.items():
                try:
                    summary[k].append(int(v))
                except:
                    continue
        return {f"avg_{k}": np.mean(v) for k, v in summary.items()}

    def search_matrix(
        self, name: str, query_matrix: np.ndarray, k: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Search for similar matrices, handling normalization"""
        index = self.indices[name]
        interpolated = self._interpolate_matrix(query_matrix, index.time_steps)
        normalized = index.normalize_matrix(interpolated)
        query_vector = normalized.flatten()

        distances, ids, vectors = index.search(query_vector, k)
        distances = distances[0]  # Take first row since only one query

        # Reshape and denormalize the results
        matrices = []
        for v in vectors:
            # Direct reshape using the index dimensions
            matrix = v.reshape(index.time_steps, index.feature_dim)
            denormalized = index.denormalize_matrix(matrix)
            matrices.append(denormalized)
        return distances, np.array(ids), np.array(matrices)

    def set_normalization(self, name: str, means: np.ndarray, stds: np.ndarray) -> None:
        """Set normalization constants for an existing index"""
        if name not in self.indices:
            raise ValueError(f"Index {name} does not exist")

        self.indices[name].set_normalization(means, stds)
        self.metadata[name]["has_normalization"] = True

    def get_all_matrices(
        self, name: str | list[str] | None = None
    ) -> dict[str, dict[str, np.ndarray | None]]:
        """Get all vectors and their IDs from the manager, reshaping vectors to matrices.

        Args:
            name: Index name or list of names to retrieve. None for all indices.

        Returns:
            Dictionary mapping index names to dictionaries containing:
            - 'matrices': (n_entries, time_steps, feature_dim) array or None if empty
            - 'ids': list of string IDs or None if empty
        """
        if isinstance(name, str):
            name = [name]
        elif name is None:
            name = list(self.indices.keys())

        return {
            n: (
                {
                    "arrays": index.get_all_vectors().reshape(
                        -1, index.time_steps, index.feature_dim
                    ),
                    "ids": index.get_all_ids(),
                }
                if index.n_entries > 0
                else {"arrays": None, "ids": None}
            )
            for n, index in self.indices.items()
            if n in name
        }

    def get_matrix_by_id(self, name: str, entry_id: str) -> t.Optional[np.ndarray]:
        """Get a matrix by its ID, handling denormalization

        Args:
            name: Index name
            entry_id: String ID of the entry

        Returns:
            Matrix if found, None otherwise
        """
        if name not in self.indices:
            raise ValueError(f"Index {name} does not exist")

        index = self.indices[name]
        entry_id = str(entry_id)
        vector = index.get_vector_by_id(entry_id)

        if vector is None:
            return None

        # Reshape and denormalize
        matrix = vector.reshape(index.time_steps, index.feature_dim)
        return index.denormalize_matrix(matrix)

    def delete_index(self, name: str) -> None:
        """Delete an index"""
        if name not in self.indices:
            raise ValueError(f"Index {name} does not exist")
        self.indices[name].delete()
        del self.indices[name]
        del self.metadata[name]
        self.save()


if __name__ == "__main__":
    db = IndexManager(EMBEDDING_DB_PATH, FaissIndex)
    print(db.get_overall_stats())
    breakpoint()  # breakpoint to allow exploration of preview statistics
