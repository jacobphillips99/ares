import json
import os
import time
import traceback
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st
from sqlalchemy import select

from ares.app.data_analysis import generate_automatic_visualizations
from ares.app.export_data import export_options
from ares.app.filter_helpers import (
    embedding_data_filters_display,
    select_row_from_df_user,
    structured_data_filters_display,
)
from ares.app.init_data import initialize_data
from ares.app.plot_primitives import show_dataframe
from ares.app.viz_helpers import (
    create_tabbed_visualizations,
    display_video_grid,
    generate_robot_array_plot_visualizations,
    generate_success_rate_visualizations,
    generate_time_series_visualizations,
    show_hero_display,
    total_statistics,
)
from ares.clustering import visualize_clusters
from ares.databases.embedding_database import (
    TEST_EMBEDDING_DB_PATH,
    FaissIndex,
    IndexManager,
)
from ares.databases.structured_database import RolloutSQLModel
from ares.task_utils import PI_DEMO_PATH

title = "ARES Dashboard"
video_paths = list(os.listdir(PI_DEMO_PATH))

tmp_dump_dir = "/workspaces/ares/data/tmp/"

# Add at the top level
section_times: dict[str, float] = defaultdict(float)


@contextmanager
def filter_error_context(section_name: str) -> Any:
    """Context manager for handling filter operation errors."""
    try:
        yield
    except Exception as e:
        st.error(f"Error in {section_name}: {str(e)}\n{traceback.format_exc()}")
        # communicate stop to user
        st.write("Stopping execution")
        st.stop()
        return None


@contextmanager
def timer_context(section_name: str) -> Any:
    """Context manager for timing sections."""
    start_time = time.time()
    try:
        yield
    finally:
        elapsed_time = time.time() - start_time
        section_times[section_name] += elapsed_time


def load_data() -> pd.DataFrame:
    # Initialize mock data at the start of the app
    initialize_data(tmp_dump_dir)
    # Initial dataframe
    df = pd.read_sql(select(RolloutSQLModel), st.session_state.ENGINE)
    df = df[[c for c in df.columns if "unnamed" not in c.lower()]]
    return df


# Streamlit app
def main() -> None:
    # Define section names
    section_loading = "loading data"
    with filter_error_context(section_loading), timer_context(section_loading):
        print("\n" + "=" * 100 + "\n")
        st.set_page_config(page_title=title, page_icon="📊", layout="wide")
        st.title(title)
        df = load_data()

        total_statistics(df)
        st.divider()

    section_filters = "data filters"
    with filter_error_context(section_filters), timer_context(section_filters):
        # Structured data filters
        st.header(f"Data Filters")
        value_filtered_df = structured_data_filters_display(df)
        kept_ids = value_filtered_df["id"].apply(str).tolist()
        st.write(
            f"Selected {len(value_filtered_df)} rows out of {len(df)} total via structured data filters"
        )

        # Embedding data filters
        state_key = "description"
        raw_data_key = "task_language_instruction"
        # state_key = "task"
        # raw_data_key = "task_success_criteria"
        # TODO: present SEVERAL embedding filter options
        filtered_df, cluster_fig, selection, selection_flag = (
            embedding_data_filters_display(
                df=df,
                reduced=st.session_state[f"{state_key}_reduced"],
                labels=st.session_state[f"{state_key}_labels"],
                raw_data_key=raw_data_key,
                id_key="id",
                keep_mask=kept_ids,
            )
        )

        if filtered_df.empty:
            st.warning(
                "No data available for the selected points! Try adjusting your selection to receive analytics."
            )
            return

        # Add a button to refresh the sample
        st.button(
            "Get New Random Sample"
        )  # Button press triggers streamlit rerun, triggers new random sample
        show_dataframe(
            filtered_df.sample(min(5, len(filtered_df))), title="Data Sample"
        )
    st.divider()

    section_display = "data distributions"
    with filter_error_context(section_display), timer_context(section_display):
        # Create overview of all data
        st.header("Distribution Analytics")
        general_visualizations = generate_automatic_visualizations(
            filtered_df, time_column="ingestion_time"
        )
        create_tabbed_visualizations(
            general_visualizations, [viz["title"] for viz in general_visualizations]
        )

        st.header("Success Rate Analytics")
        success_visualizations = generate_success_rate_visualizations(filtered_df)
        create_tabbed_visualizations(
            success_visualizations, [viz["title"] for viz in success_visualizations]
        )

        st.header("Time Series Trends")
        time_series_visualizations = generate_time_series_visualizations(
            filtered_df, time_column="ingestion_time"
        )
        create_tabbed_visualizations(
            time_series_visualizations,
            [viz["title"] for viz in time_series_visualizations],
        )

        # show video cards of first 5 rows in a horizontal layout
        display_video_grid(filtered_df)
    st.divider()

    section_plot_hero = "plot hero display"
    with filter_error_context(section_plot_hero), timer_context(section_plot_hero):
        st.header("Rollout Display")

        # Let user select a row from the dataframe using helper function
        row = select_row_from_df_user(df)
        st.write(f"Selected row ID: {row.id}")
        hero_visualizations = show_hero_display(
            df,
            row.name,
            st.session_state.all_vecs,
            show_n=100,
            index_manager=st.session_state.INDEX_MANAGER,
        )
    st.divider()

    # section_plot_robots = "plot robot arrays"
    # with filter_error_context(section_plot_robots), timer_context(section_plot_robots):
    #     st.header("Robot Array Display")
    #     # Number of trajectories to display in plots
    #     robot_array_visualizations = generate_robot_array_plot_visualizations(
    #         row,  # need row to select dataset/robot embodiment of trajectories
    #         st.session_state.all_vecs,
    #         show_n=1000,
    #     )
    # st.divider()

    # section_export = "exporting data"
    # with filter_error_context(section_export), timer_context(section_export):
    #     # Export controls
    #     # Collect all visualizations
    #     # TODO: add structured data filters to export
    #     all_visualizations = [
    #         *general_visualizations,
    #         *success_visualizations,
    #         *time_series_visualizations,
    #         *robot_array_visualizations,
    #         *hero_visualizations,  # Add hero visualizations to export
    #     ]
    #     export_options(filtered_df, all_visualizations, title, cluster_fig=cluster_fig)

    # Print timing report at the end
    print("\n=== Timing Report ===")
    print(f"Total time: {sum(section_times.values()):.2f} seconds")
    for section, elapsed_time in section_times.items():
        print(f"{section}: {elapsed_time:.2f} seconds")
    print("==================\n")


if __name__ == "__main__":
    main()
