from typing import Any

import numpy as np
import pandas as pd

from ares.app.plot_primitives import create_bar_plot, create_histogram, create_line_plot


def generate_automatic_visualizations(
    df: pd.DataFrame, time_column: str = "creation_time"
) -> list[dict]:
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


def infer_visualization_type(
    column_name: str,
    data: pd.DataFrame,
    skip_columns: list | None = None,
    max_str_length: int = 500,
) -> dict[str, Any]:
    dtype = str(data[column_name].dtype)
    nunique = data[column_name].nunique()

    result = {"viz_type": None, "dtype": dtype, "nunique": nunique}

    skip_columns = skip_columns or ["path", "id"]
    if column_name.lower() in skip_columns:
        return result

    if pd.api.types.is_string_dtype(data[column_name]):
        if data[column_name].str.len().max() > max_str_length:
            return result

    if pd.api.types.is_datetime64_any_dtype(data[column_name]):
        return result

    if pd.api.types.is_numeric_dtype(data[column_name]):
        if nunique > 20:
            result["viz_type"] = "histogram"
        else:
            result["viz_type"] = "bar"
        return result

    if pd.api.types.is_string_dtype(data[column_name]) or nunique < 20:
        result["viz_type"] = "bar"
        return result

    return result
