import hashlib

import cv2
import numpy as np
import streamlit as st

from ares.configs.annotations import Annotation
from ares.utils.image_utils import choose_and_preprocess_frames, get_video_frames


def get_color_mapping(category_str: str) -> tuple[int, int, int]:
    """
    Create a consistent color mapping based on hash of a string.
    This way, the same strings are mapped to the same colors.
    """
    hash_str = hashlib.sha256(category_str.encode()).hexdigest()[:6]
    # Convert pairs of hex digits to RGB values (0-255)
    r = int(hash_str[0:2], 16)
    g = int(hash_str[2:4], 16)
    b = int(hash_str[4:6], 16)
    return (r, g, b)


def draw_legend(
    canvas: np.ndarray,
    unique_categories: dict,
    start_y: int,
    legend_spacing: int = 25,
    legend_x: int = 10,
) -> None:
    """Draw category legend on the canvas.

    Args:
        canvas: Image to draw legend on
        unique_categories: Dictionary mapping category names to colors
        start_y: Y coordinate to start drawing legend
        legend_spacing: Vertical spacing between legend items
        legend_x: X coordinate to start drawing legend
    """
    for idx, (category, color) in enumerate(unique_categories.items()):
        # Draw color box
        cv2.rectangle(
            canvas,
            (legend_x, start_y + idx * legend_spacing - 15),
            (legend_x + 20, start_y + idx * legend_spacing),
            color,
            -1,
        )
        # Draw category text
        cv2.putText(
            canvas,
            category,
            (legend_x + 30, start_y + idx * legend_spacing - 3),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )


def draw_box(
    annotation: Annotation,
    annotated_image: np.ndarray,
    image: np.ndarray,
    overlay: np.ndarray,
    color: tuple[int, int, int],
    label: str,
    show_scores: bool,
) -> np.ndarray:
    if not annotation.bbox:
        return annotated_image
    x1, y1, x2, y2 = map(int, annotation.bbox)

    cv2.rectangle(annotated_image, (x1, y1), (x2, y2), color, 2)  # Border
    # Draw rectangle with transparency
    if not annotation.segmentation:
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)  # Filled box for overlay

    # Prepare label text
    if show_scores and annotation.score is not None:
        label_text = f"{label} {annotation.score:.2f}"
    else:
        label_text = label

    # Get text size
    (text_w, text_h), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)

    # Adjust label position to ensure it's within image bounds
    text_x = min(max(x1, 0), image.shape[1] - text_w)
    text_y = max(y1 - 2, text_h + 4)  # Ensure there's room for text

    # Draw label background and text
    cv2.rectangle(
        annotated_image,
        (text_x, text_y - text_h - 4),
        (text_x + text_w, text_y),
        color,
        -1,
    )
    cv2.putText(
        annotated_image,
        label_text,
        (text_x, text_y - 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 0, 0),
        1,
        cv2.LINE_AA,
    )
    return annotated_image


# Draw annotations
def draw_annotations(
    image: np.ndarray,
    annotations: list[Annotation],
    show_scores: bool = True,
    alpha: float = 0.25,
) -> np.ndarray:
    """
    Create quick-and-easy visualizations of annotations.
    """
    annotated_image = image.copy()
    overlay = image.copy()

    # Track unique categories for legend
    unique_categories = {}

    for annotation in annotations:
        label = annotation.category_name or "unknown"
        color = get_color_mapping(label)
        unique_categories[label] = color

        # Draw bounding box
        if annotation.bbox:
            annotated_image = draw_box(
                annotation, annotated_image, image, overlay, color, label, show_scores
            )

        # Draw segmentation mask
        if annotation.segmentation:
            colored_mask = np.zeros_like(image, dtype=np.uint8)
            colored_mask[annotation.mask == 1] = color
            overlay = cv2.addWeighted(overlay, 1, colored_mask, alpha, 0)

    # Calculate legend dimensions
    legend_spacing = 25  # Vertical spacing between legend items
    legend_height = len(unique_categories) * legend_spacing + 10
    legend_padding = 20  # Padding around legend

    # Create extended canvas for image + legend
    canvas = np.full(
        (image.shape[0] + legend_height + legend_padding, image.shape[1], 3),
        255,  # White background
        dtype=np.uint8,
    )

    # Place the annotated image at the top
    canvas[: image.shape[0]] = cv2.addWeighted(
        overlay, alpha, annotated_image, 1 - alpha, 0
    )

    # Draw legend using helper function
    legend_y = image.shape[0] + legend_padding
    draw_legend(canvas, unique_categories, legend_y)
    return canvas


def draw_detection_data(detection_data: dict, dataset: str, fname: str) -> None:
    # given detection data, lets display the frames and annotations
    frame_inds = list(detection_data.keys())
    all_frame_paths = get_video_frames(dataset, fname, n_frames=None, just_path=True)
    selected_frames = choose_and_preprocess_frames(
        all_frame_paths,
        specified_frames=frame_inds,
    )
    annotated_frames = [
        draw_annotations(frame, anns)
        for frame, anns in zip(selected_frames, detection_data.values())
    ]
    # use an expander for visual clarity
    with st.expander("Annotated Frames", expanded=False):
        max_cols = 3
        cols = st.columns(max_cols)
        for i, (frame_ind, frame) in enumerate(zip(frame_inds, annotated_frames)):
            with cols[i % max_cols]:
                st.write(f"Frame {frame_ind}")
                st.image(frame)
