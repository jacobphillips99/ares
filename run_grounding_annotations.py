import asyncio
import os
import pickle
import tempfile
import time
from typing import List, Tuple

import numpy as np
from PIL import Image
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from tqdm import tqdm

from ares.configs.base import Rollout
from ares.databases.annotation_database import (
    TEST_ANNOTATION_DB_PATH,
    AnnotationDatabase,
)
from ares.databases.structured_database import get_dataset_rollouts, get_rollout_by_name
from ares.models.base import VLM
from ares.models.grounding import GroundingAnnotator
from ares.models.grounding_utils import get_grounding_nouns_async
from ares.models.shortcuts import get_gemini_2_flash, get_gpt_4o
from ares.utils.image_utils import load_video_frames


async def setup_query(
    dataset_filename: str,
    rollout: Rollout,
    vlm: VLM,
    target_fps: int = 5,
) -> tuple[list[np.ndarray], list[int], str]:
    frames, frame_indices = load_video_frames(
        dataset_filename,
        rollout.filename,
        target_fps,
    )
    label_str = await get_grounding_nouns_async(
        vlm,
        frames[0],
        rollout.task.language_instruction,
    )
    return frames, frame_indices, label_str


def run_local(
    engine: Engine,
    dataset_filename: str,
    rollouts: list[Rollout],
    vlm: VLM,
    target_fps: int = 5,
) -> tuple[int, int, int]:
    total_anns = 0
    total_processed = 0
    total_frames = 0
    pbar = tqdm(total=len(rollouts), desc="Processing videos")

    for rollout in tqdm(rollouts):
        frames, frame_indices, label_str = asyncio.run(
            setup_query(dataset_filename, rollout, vlm, target_fps)
        )
        # Pass description to annotate_video
        video_detection_results = annotator.annotate_video(frames, label_str)
        video_annotations = convert_to_annotations(video_detection_results)
        total_anns += sum(len(anns) for anns in video_annotations)
        total_frames += len(frames)

        video_id = ann_db.add_video_with_annotations(
            dataset_filename=dataset_filename,
            video_path=rollout.filename + ".mp4",
            frames=frames,
            frame_indices=frame_indices,
            annotations=video_annotations,
            label_str=label_str,
        )

        total_processed += 1
        pbar.update(1)
        pbar.set_postfix({"Last file": os.path.basename(rollout.filename)})

    pbar.close()
    return total_anns, total_processed, total_frames


if __name__ == "__main__":
    from ares.databases.structured_database import (
        TEST_ROBOT_DB_PATH,
        RolloutSQLModel,
        get_rollout_by_name,
        setup_database,
        setup_rollouts,
    )

    # Initialize components
    ann_db = AnnotationDatabase(connection_string=TEST_ANNOTATION_DB_PATH)
    annotator = GroundingAnnotator(
        segmenter_id=None,
    )
    engine = setup_database(RolloutSQLModel, path=TEST_ROBOT_DB_PATH)

    # dataset_filename = "cmu_play_fusion"
    # fname = "data/train/episode_208"
    dataset_formalname = "UCSD Kitchen"
    dataset_filename = "ucsd_kitchen_dataset_converted_externally_to_rlds"
    target_fps = 5

    rollouts = setup_rollouts(engine, dataset_formalname)

    # vlm = get_gemini_2_flash()
    vlm = get_gpt_4o()

    # Create progress bar for total files
    tic = time.time()

    total_anns, total_processed, total_frames = run_local(
        engine, dataset_filename, rollouts, vlm, target_fps
    )

    toc = time.time()
    print(f"Total time: {toc - tic:.2f} seconds")
    print(f"Total annotations: {total_anns}")
    print(f"Total processed: {total_processed}")
    print(f"Total frames: {total_frames}")
    breakpoint()
