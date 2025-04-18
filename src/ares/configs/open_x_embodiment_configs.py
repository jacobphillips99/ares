import os
import typing as t

import numpy as np
import pandas as pd
import tensorflow as tf
from pydantic import BaseModel, model_validator

from ares.constants import ARES_OXE_DIR


class TensorConverterMixin(BaseModel):
    """
    TFDS returns tensors; we want everything in numpy arrays or
    base python types to work with other parts of the codebase.
    """

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="before")
    @classmethod
    def convert_tensors_to_python(cls, data: dict) -> dict:
        def convert_value(value: t.Any) -> t.Any:
            if isinstance(value, tf.Tensor):
                # Convert to numpy first
                value = value.numpy()
                # Convert to base Python type if it's a scalar
                if np.isscalar(value):
                    if isinstance(value, (np.bool_)):
                        return bool(value)
                    elif isinstance(value, np.floating):
                        return float(value)
                    elif isinstance(value, np.integer):
                        return int(value)
            elif isinstance(value, dict):
                return {k: convert_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [convert_value(v) for v in value]
            return value

        return {k: convert_value(v) for k, v in data.items()}


class OpenXEmbodimentEpisodeMetadata(TensorConverterMixin, BaseModel):
    file_path: str
    success: bool | None = None


class OpenXEmbodimentStepObservation(TensorConverterMixin, BaseModel):
    image: np.ndarray
    state: np.ndarray | None = None
    depth: np.ndarray | None = None
    wrist_image: np.ndarray | None = None
    end_effector_state: np.ndarray | None = None

    @model_validator(mode="before")
    def get_image(cls, data: dict) -> "dict":
        if "highres_image" in data:
            data["image"] = data.pop("highres_image")
        elif "hand_image" in data and "image" not in data:
            data["image"] = data.pop("hand_image")
        elif "agentview_rgb" in data:
            data["image"] = data.pop("agentview_rgb")

        if "eye_in_hand_rgb" in data:
            data["wrist_image"] = data.pop("eye_in_hand_rgb")
        return data

    @model_validator(mode="before")
    def get_state(cls, data: dict) -> dict:
        if "state" not in data:
            extra_state_keys = [
                "gripper",
                "gripper_states",
                "end_effector_cartesian_pos",
                "end_effector_cartesian_velocity",
                "joint_pos",
                "joint_states",
                "pose",
            ]
            state_arrays = []
            for k in extra_state_keys:
                if k in data:
                    value = data[k]
                    if isinstance(value, bool):
                        state_arrays.append(np.array([float(value)]))
                    elif hasattr(value, "shape"):
                        if value.shape == ():
                            state_arrays.append(value.numpy().reshape(1))
                        else:
                            state_arrays.append(value)
            if state_arrays:
                data["state"] = np.concatenate(state_arrays)
            else:
                data["state"] = None
        if "end_effector_state" not in data:
            if "ee_state" in data:
                data["end_effector_state"] = data.pop("ee_state")
        return data


class OpenXEmbodimentStep(TensorConverterMixin, BaseModel):
    action: np.ndarray | None
    discount: float | None = None
    is_first: bool
    is_last: bool
    is_terminal: bool
    language_embedding: np.ndarray | None = None
    language_instruction: str | None = None
    observation: OpenXEmbodimentStepObservation
    reward: float | None = None

    @model_validator(mode="before")
    @classmethod
    def remap_fields(cls, data: dict) -> dict:
        # Handle observation field remapping
        if "observation" in data and isinstance(data["observation"], dict):
            obs = data["observation"]

            # Move natural_language_instruction if it exists in observation
            if "natural_language_instruction" in obs:
                data["language_instruction"] = obs.pop("natural_language_instruction")
            if "natural_language_embedding" in obs:
                data["language_embedding"] = obs.pop("natural_language_embedding")

            # Add more field remapping here as needed
            action = data["action"]
            if isinstance(action, dict):
                extra_action_keys = [
                    "rotation_delta",
                    "world_vector",
                    "gripper_closedness_action",
                    "terminate_episode",
                ]
                action_arrays = []
                for k in extra_action_keys:
                    if k in action:
                        value = action[k]
                        if isinstance(value, (int, float)):
                            action_arrays.append(np.array([float(value)]))
                        elif hasattr(value, "shape"):
                            if value.shape == ():
                                action_arrays.append(value.numpy().reshape(1))
                            else:
                                action_arrays.append(value)

                if action_arrays:
                    data["action"] = np.concatenate(action_arrays)
                else:
                    data["action"] = None
        return data


class OpenXEmbodimentEpisode(TensorConverterMixin, BaseModel):
    episode_metadata: OpenXEmbodimentEpisodeMetadata
    steps: list[OpenXEmbodimentStep]


# hardcoded path to OXE spreadsheet
# see original version at https://docs.google.com/spreadsheets/d/1rPBD77tk60AEIGZrGSODwyyzs5FgCU9Uz3h-3_t2A9g/edit?gid=0#gid=0
PATH_TO_OXE_SPREADSHEET = "/workspaces/ares/src/ares/extras/oxe.csv"
HEADER_ROW = 16


def get_oxe_dataframe() -> pd.DataFrame:
    return pd.read_csv(PATH_TO_OXE_SPREADSHEET, header=HEADER_ROW)


def get_dataset_information(dataset_filename: str) -> pd.DataFrame:
    df = get_oxe_dataframe()
    return dict(df[df["Registered Dataset Name"] == dataset_filename].iloc[0])


def construct_openxembodiment_episode(ep: dict, i: int) -> OpenXEmbodimentEpisode:
    if "episode_metadata" not in ep:
        ep["episode_metadata"] = dict(file_path=f"episode_{i}.npy")
    episode = OpenXEmbodimentEpisode(**ep)
    return episode
