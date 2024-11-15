"""
Cluster embeddings using UMAP for dimensionality reduction and HDBSCAN for clustering.
"""

import json
import os
from typing import Optional, Tuple, Union

import hdbscan
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import umap

# At the top with other imports
SELECTION_FILE = "/tmp/selected_points.json"


def cluster_embeddings(
    embeddings: np.ndarray,
    n_neighbors: int = 15,
    min_cluster_size: int = 50,
    min_samples: int = 5,
    random_state: int = 42,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Cluster embeddings using UMAP for dimensionality reduction and HDBSCAN for clustering.

    Args:
        embeddings: Input embeddings array of shape (n_samples, n_dimensions)
        n_neighbors: UMAP parameter for local neighborhood size
        min_cluster_size: Minimum cluster size for HDBSCAN
        min_samples: Minimum samples for HDBSCAN
        random_state: Random seed for reproducibility

    Returns:
        reduced_embeddings: UMAP-reduced embeddings (3D)
        cluster_labels: Cluster assignments for each embedding
        probabilities: Cluster membership probabilities
    """
    # Reduce dimensionality to 2D for visualization
    reducer = umap.UMAP(
        n_components=2, n_neighbors=n_neighbors, random_state=random_state
    )
    reduced_embeddings = reducer.fit_transform(embeddings)

    # Perform clustering
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size, min_samples=min_samples, prediction_data=True
    )
    cluster_labels = clusterer.fit_predict(reduced_embeddings)
    probabilities = clusterer.probabilities_
    return reduced_embeddings, cluster_labels, probabilities


def visualize_clusters(
    reduced_embeddings: np.ndarray,
    cluster_labels: np.ndarray,
    probabilities: Optional[np.ndarray] = None,
    title: str = "Embedding Clusters",
) -> Tuple[go.Figure, pd.DataFrame]:
    """
    Create an interactive 2D visualization of the clustered embeddings.
    Returns figure and dataframe for selection tracking.
    """
    df = pd.DataFrame(
        {
            "x": reduced_embeddings[:, 0],
            "y": reduced_embeddings[:, 1],
            "cluster": cluster_labels,
            "probability": (
                probabilities
                if probabilities is not None
                else np.ones(len(cluster_labels))
            ),
            "point_index": range(
                len(cluster_labels)
            ),  # Add index for selection tracking
        }
    )

    # Create a color map
    n_clusters = len(np.unique(cluster_labels))
    colors = px.colors.qualitative.Dark24[:n_clusters]

    fig = px.scatter(
        df,
        x="x",
        y="y",
        color="cluster",
        title=title,
        labels={"cluster": "Cluster"},
        color_discrete_sequence={i: colors[i] for i in (np.unique(cluster_labels))},
        template="plotly_white",
    )

    # Update traces and layout
    fig.update_traces(
        marker_size=3,
        selectedpoints=[],
        mode="markers",
        selected=dict(marker=dict(color="red")),
        selector=dict(type="scatter"),
    )

    fig.update_layout(
        xaxis_title="UMAP 1",
        yaxis_title="UMAP 2",
        showlegend=True,
        coloraxis_colorbar=dict(
            tickmode="array",
            ticktext=[str(i) for i in sorted(df["cluster"].unique())],
            tickvals=list(range(len(df["cluster"].unique()))),
            yanchor="top",
            y=1,
            x=1.2,
        ),
        # Update selection behavior
        dragmode="select",
        clickmode="event+select",
        selectionrevision=True,  # This helps persist selections
    )

    # Add centroids
    for cluster in np.unique(cluster_labels):
        if cluster != -1:  # Skip noise points
            mask = cluster_labels == cluster
            if mask.any():  # Only add centroid if cluster has points
                centroid = reduced_embeddings[mask].mean(axis=0)
                fig.add_trace(
                    go.Scatter(
                        x=[centroid[0]],
                        y=[centroid[1]],
                        mode="markers",
                        marker=dict(
                            symbol="triangle-up",
                            color=colors[cluster],
                            size=25,
                            line=dict(color="white", width=2),
                        ),
                        name=f"Centroid {cluster}",
                        legendgroup="centroids",
                        legendgrouptitle_text="Centroids",
                    )
                )

    # Add this after all traces are added
    fig.update_layout(
        legend=dict(
            yanchor="top",
            y=-0.1,  # Moves legend below the plot
            xanchor="left",
            x=0,
            orientation="h",  # Makes legend horizontal
        )
    )

    return fig, df


if __name__ == "__main__":
    import json
    import os

    import streamlit as st

    # Initialize session state for selections
    if "selected_indices" not in st.session_state:
        st.session_state.selected_indices = []

    embeddings = np.random.rand(1000, 2)
    for i in range(3):
        embeddings[i * 200 : (i + 1) * 200] += i
    reduced, labels, probs = cluster_embeddings(embeddings)

    # Create the visualization
    fig, df = visualize_clusters(reduced, labels, probs)

    # Create columns for controls and info
    col1, col2 = st.columns([3, 1])

    with col1:
        # Display the plot
        selected_points = st.plotly_chart(
            fig, use_container_width=True, key="cluster_plot"
        )

    with col2:
        st.write("### Selection Controls")

        if st.button("Save Selection"):
            # Get the currently selected points from the figure's selectedpoints
            selected = fig.data[0].selectedpoints
            if selected:
                with open(SELECTION_FILE, "w") as f:
                    json.dump({"selected": selected}, f)
                st.session_state.selected_indices = selected
                st.success("Selection saved!")

        if st.button("Load Selection"):
            if os.path.exists(SELECTION_FILE):
                with open(SELECTION_FILE, "r") as f:
                    data = json.load(f)
                    st.session_state.selected_indices = data["selected"]
                    # Update figure with loaded selection
                    fig.update_traces(selectedpoints=st.session_state.selected_indices)
                st.success("Selection loaded!")

        if st.button("Clear Selection"):
            if os.path.exists(SELECTION_FILE):
                os.remove(SELECTION_FILE)
            st.session_state.selected_indices = []
            st.rerun()

        # Display selection information
        if st.session_state.selected_indices:
            selected_df = df.iloc[st.session_state.selected_indices]
            st.write("### Selection Info")
            st.write(f"Points selected: {len(st.session_state.selected_indices)}")
            st.write("Cluster distribution:")
            st.write(selected_df["cluster"].value_counts())
            st.write(f"Avg probability: {selected_df['probability'].mean():.3f}")
