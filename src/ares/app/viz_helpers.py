import os
from typing import Any

import numpy as np
import pandas as pd
import plotly
import plotly.express as px
import streamlit as st

from ares.task_utils import PI_DEMO_PATH  # hack


def create_line_plot(
    df: pd.DataFrame,
    x: str,
    y: list[str],
    title: str,
    labels: dict[str, str],
    colors: list[str],
    y_format: str | None = None,
) -> plotly.graph_objects.Figure:
    fig = px.line(
        df,
        x=x,
        y=y,
        title=title,
        labels=labels,
        color_discrete_sequence=colors,
    )
    layout_args = {
        "yaxis_title": labels.get("value", "Value"),
        "showlegend": True,
        "legend_title_text": "",
    }
    if y_format:
        layout_args["yaxis_tickformat"] = y_format
    fig.update_layout(**layout_args)
    return fig


def create_histogram(
    df: pd.DataFrame,
    x: str,
    title: str,
    labels: dict[str, str],
    color: str,
    nbins: int = 30,
) -> plotly.graph_objects.Figure:
    fig = px.histogram(
        df,
        x=x,
        nbins=nbins,
        title=title,
        labels=labels,
        color_discrete_sequence=[color],
        barmode="overlay",
        marginal="box",
    )
    fig.update_layout(
        xaxis_title=labels.get(x, x),
        yaxis_title="count",
        showlegend=False,
        bargap=0.1,
    )
    fig.update_traces(marker_line_width=1, marker_line_color="black")
    return fig


def create_bar_plot(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str,
    labels: dict[str, str],
    color: str,
) -> plotly.graph_objects.Figure:
    fig = px.bar(
        df,
        x=x,
        y=y,
        title=title,
        labels=labels,
        color_discrete_sequence=[color],
    )
    fig.update_layout(
        xaxis_title=labels.get(x, x),
        yaxis_title=labels.get(y, y),
        showlegend=False,
    )
    return fig


def display_video_card(video: pd.Series) -> None:
    if not pd.isna(video["video_path"]) and video["video_path"].endswith(
        (".mp4", ".avi", ".mov")
    ):
        st.video(video["video_path"])
        st.write(f"**{video['id']}**")
        st.write(f"Task: {video['task_language_instruction']}")
        st.write(f"Upload Date: {video['ingestion_time'].strftime('%Y-%m-%d')}")
    else:
        st.warning(f"Invalid video path for {video['id'], video['video_path']}")


def show_dataframe(
    df: pd.DataFrame,
    title: str,
    show_columns: list[str] = None,
    hide_columns: list[str] = None,
) -> None:
    """Helper function to display DataFrames with consistent styling.

    Args:
        df: DataFrame to display
        title: Subheader title for the table
        show_columns: List of column names to show (exclusive with hide_columns)
        hide_columns: List of column names to hide (exclusive with show_columns)
    """
    if show_columns and hide_columns:
        raise ValueError("Cannot specify both show_columns and hide_columns")

    st.subheader(title)

    # Create copy and filter columns
    display_df = df.copy()
    if show_columns:
        display_df = display_df[show_columns]
    elif hide_columns:
        display_df = display_df.drop(hide_columns, axis=1)

    # Auto-generate column configs based on data types
    column_config = {}
    for col in display_df.columns:
        if pd.api.types.is_datetime64_any_dtype(display_df[col]):
            column_config[col] = st.column_config.DateColumn(
                col.replace("_", " ").title()
            )
        elif pd.api.types.is_numeric_dtype(display_df[col]):
            if "rate" in col.lower() or "percent" in col.lower():
                column_config[col] = st.column_config.NumberColumn(
                    col.replace("_", " ").title(), format="%.2%"
                )
            else:
                column_config[col] = st.column_config.NumberColumn(
                    col.replace("_", " ").title(), format="%g"
                )
        else:
            column_config[col] = st.column_config.TextColumn(
                col.replace("_", " ").title()
            )

    st.dataframe(
        display_df,
        column_config=column_config,
        hide_index=True,
    )


def infer_visualization_type(
    column_name: str,
    data: pd.DataFrame,
    skip_columns: list | None = None,
    max_str_length: int = 500,
) -> dict[str, Any]:
    """Infer the appropriate visualization type based on column characteristics.

    Args:
        column_name: Name of the column to analyze
        data: DataFrame containing the data
        skip_columns: List of column names to skip
        max_str_length: Maximum string length allowed for categorical plots. Longer strings will be skipped.

    Returns:
        dict containing:
            - viz_type: Type of visualization ('line', 'bar', 'histogram', etc.) or None if should be skipped
            - dtype: Data type as string
            - nunique: Number of unique values
    """
    # Get column data type and unique count
    dtype = str(data[column_name].dtype)
    nunique = data[column_name].nunique()

    result = {"viz_type": None, "dtype": dtype, "nunique": nunique}

    # Skip certain columns that shouldn't be plotted
    skip_columns = skip_columns or ["path", "id"]
    if column_name.lower() in skip_columns:
        return result

    # Skip columns with long string values
    if pd.api.types.is_string_dtype(data[column_name]):
        if data[column_name].str.len().max() > max_str_length:
            return result

    # Time series data (look for time/date columns)
    if pd.api.types.is_datetime64_any_dtype(data[column_name]):
        return result  # We'll use this as an x-axis instead

    # Numeric continuous data
    if pd.api.types.is_numeric_dtype(data[column_name]):
        if nunique > 20:  # Arbitrary threshold for continuous vs discrete
            result["viz_type"] = "histogram"
        else:
            result["viz_type"] = "bar"
        return result

    # Categorical data
    if pd.api.types.is_string_dtype(data[column_name]) or nunique < 20:
        result["viz_type"] = "bar"
        return result

    print(
        f"Skipping column {column_name} with dtype {dtype} and nunique {nunique} -- didn't fit into any graph types"
    )
    print(data[column_name].value_counts())
    return result


def generate_success_rate_visualizations(df: pd.DataFrame) -> list[dict]:
    """Generate success rate visualizations for categorical columns."""
    visualizations = []
    categorical_cols = sorted(
        [
            col
            for col in df.columns
            if infer_visualization_type(col, df)["viz_type"] == "bar"
        ]
    )

    for col in categorical_cols:
        # Create new DataFrame with success rates by category
        success_rates = pd.DataFrame(
            {
                col: df[col].unique(),
                "success_rate": [
                    df[df[col] == val]["task_success"].mean()
                    for val in df[col].unique()
                ],
            }
        )

        col_title = col.replace("_", " ").replace("-", " ").title()

        visualizations.append(
            {
                "figure": create_bar_plot(
                    success_rates,
                    x=col,
                    y="success_rate",
                    color="#2ecc71",
                    title=f"Success Rate by {col_title}",
                    labels={col: col_title, "success_rate": "Success Rate"},
                ),
                "title": f"{col_title} Success Rate",
            }
        )

    return visualizations


def generate_automatic_visualizations(
    df: pd.DataFrame, time_column: str = "creation_time"
) -> list[dict]:
    """Generate visualizations automatically based on data types."""
    visualizations = []
    columns = sorted(df.columns)

    for col in columns:
        viz_info = infer_visualization_type(col, df)
        if col == time_column or viz_info["viz_type"] is None:
            continue

        col_title = col.replace("_", " ").replace("-", " ").title()
        viz_type = viz_info["viz_type"]

        if viz_type == "histogram":
            visualizations.append(
                {
                    "figure": create_histogram(
                        df,
                        x=col,
                        color="#1f77b4",
                        title=f"Distribution of {col_title}",
                        labels={col: col_title, "count": "Count"},
                    ),
                    "title": f"{col_title} Distribution",
                }
            )
        elif viz_type == "bar":
            agg_data = df.groupby(col).agg({time_column: "count"}).reset_index()
            visualizations.append(
                {
                    "figure": create_bar_plot(
                        agg_data,
                        x=col,
                        y=time_column,
                        color="#1f77b4",
                        title=f"Count by {col_title}",
                        labels={col: col_title, time_column: "Count"},
                    ),
                    "title": f"{col_title} Distribution",
                }
            )

    return visualizations


def generate_time_series_visualizations(
    df: pd.DataFrame, time_column: str = "creation_time"
) -> list[dict]:
    """Generate time series visualizations for numeric columns."""
    visualizations: list[dict] = []
    numeric_cols = sorted(df.select_dtypes(include=["int64", "float64"]).columns)

    for col in numeric_cols:
        viz_info = infer_visualization_type(col, df)
        if col == time_column or viz_info["viz_type"] is None:
            continue

        col_title = col.replace("_", " ").replace("-", " ").title()
        visualizations.append(
            {
                "figure": create_line_plot(
                    df,
                    x=time_column,
                    y=[col],
                    colors=["#1f77b4"],
                    title=f"{col_title} Over Time",
                    labels={
                        col: col_title,
                        time_column: time_column.title(),
                        "value": col_title,
                    },
                    y_format=".0%" if "task_success" in col.lower() else None,
                ),
                "title": f"{col_title} Trends",
            }
        )

    return visualizations


def create_tabbed_visualizations(
    visualizations: list[dict], tab_names: list[str]
) -> None:
    """Create tabs for each visualization."""
    tabs = st.tabs(tab_names)
    for tab, viz in zip(tabs, visualizations):
        with tab:
            st.plotly_chart(viz["figure"], use_container_width=True)


def display_video_grid(filtered_df: pd.DataFrame, max_videos: int = 5) -> None:
    """Display a grid of video cards for the first N rows of the dataframe.

    Args:
        filtered_df: DataFrame containing rollout data
        max_videos: Maximum number of videos to display in the grid
    """
    st.header("Rollout Examples")
    n_videos = min(max_videos, len(filtered_df))
    video_cols = st.columns(n_videos)

    video_paths = [
        os.path.join(PI_DEMO_PATH, path)
        for path in os.listdir(PI_DEMO_PATH)
        if "ds_store" not in path.lower()
    ]

    for i, (_, row) in enumerate(filtered_df.head(n_videos).iterrows()):
        with video_cols[i]:
            video_path = video_paths[i % len(video_paths)]
            inp = {**row.to_dict(), "video_path": video_path}
            display_video_card(inp)


# make a object to show all the information in a given row
def show_one_row(df: pd.DataFrame, idx: int) -> None:
    row = df.iloc[idx]
    # video card
    st.video(row["video_path"])
    with st.expander("Row Details", expanded=False):
        for col, val in row.items():
            st.write(f"{col}: {val}")


def plot_robot_array(
    robot_array: np.ndarray, title_base: str, highlight_idx: int | None = None
) -> plotly.graph_objects.Figure:
    """Plot a 3D array with dimensions (trajectory, timestep, robot_state_dim).
    Note that the "time sequence" is already aligned, so "timestep" is actually relative.
    """
    assert (
        robot_array.ndim == 3
    ), f"robot_array must have 3 dimensions; received shape: {robot_array.shape}"

    # Calculate grid dimensions - try to make it as square as possible
    n_dims = robot_array.shape[2]
    grid_size = int(np.ceil(np.sqrt(n_dims)))

    # Create a grid of columns
    cols = st.columns(grid_size)

    # Create a figure for each dimension of the robot state
    for dim in range(robot_array.shape[2]):
        # Calculate row and column position
        row = dim // grid_size
        col = dim % grid_size

        # If we need a new row of columns
        if col == 0 and dim != 0:
            cols = st.columns(grid_size)

        with cols[col]:
            fig = px.line(
                title=title_base + f" - Dimension {dim}",
                labels={
                    "x": "Relative Timestep",
                    "y": "Value",
                    "color": "Trajectory",
                },
            )

            # Plot each trajectory
            for traj in range(robot_array.shape[0]):
                color = "red" if traj == highlight_idx else "blue"
                width = 3 if traj == highlight_idx else 1
                opacity = 1.0 if traj == highlight_idx else 0.3

                fig.add_scatter(
                    x=list(range(robot_array.shape[1])),
                    y=robot_array[traj, :, dim],
                    mode="lines",
                    name=f"Trajectory {traj}",
                    line=dict(color=color, width=width),
                    opacity=opacity,
                )

            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    return fig
