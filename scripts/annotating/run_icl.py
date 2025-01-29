"""
Inspired by `InstantPolicy` and `R+X: Retrieval and Execution from Everyday Human Videos`, we demonstrate creating rollout annotations for 
in-context learning by retrieving similar rollouts from the dataset. We can do this for several keys, such as the task, the text
description of the rollout, or the state and action trajectories of the robot. 
"""

import asyncio
import os
import traceback

from sqlalchemy import Engine

from ares.annotating.annotating_base import ErrorResult, ResultTracker
from ares.annotating.annotating_fn import APIAnnotatingFn
from ares.annotating.orchestration import orchestrate_annotating
from ares.configs.annotations import Annotation
from ares.configs.base import Rollout
from ares.constants import ANNOTATION_OUTER_BATCH_SIZE, ARES_DATA_DIR, DATASET_NAMES
from ares.databases.annotation_database import ANNOTATION_DB_PATH, AnnotationDatabase
from ares.databases.embedding_database import (
    EMBEDDING_DB_PATH,
    META_INDEX_NAMES,
    TRAJECTORY_INDEX_NAMES,
    FaissIndex,
    IndexManager,
    rollout_to_index_name,
)
from ares.databases.structured_database import (
    ROBOT_DB_PATH,
    RolloutSQLModel,
    create_engine,
    get_rollouts_by_ids,
    setup_database,
)
from ares.models.base import VLM, parse_response
from ares.models.shortcuts import get_vlm
from ares.utils.image_utils import load_video_frames


class ICLAnnotatingFn(APIAnnotatingFn):
    """
    Object to orchestrate the retrieval of similar rollouts (per key) to facilitate ICL.
    Given the databases, we can retrieve similar rollouts for each key and then pull their example_field to use as context.

    For example, we can retrieve similar rollouts for the `task` key and `states` key and then pull their `description_estimate` to use as context.
    """

    def __init__(
        self,
        index_manager: IndexManager,
        engine: Engine,
        keys: list[str],
        n_examples_per_key: int = 1,
        example_field: str = "description_estimate",
    ):
        super().__init__(annotation_key="string", annotation_type="icl")
        self.index_manager = index_manager
        self.engine = engine
        self.keys = keys
        self.n_examples_per_key = n_examples_per_key
        self.example_field = example_field

    def construct_example_values(self, rollout: Rollout) -> dict[str, list[str]]:
        output_vals = dict()
        for key in self.keys:
            if key not in META_INDEX_NAMES:
                index_name = rollout_to_index_name(rollout, suffix=key)
            else:
                index_name = key
            value = index_manager.get_matrix_by_id(index_name, str(rollout.id))
            dists, ids, _ = index_manager.search_matrix(
                index_name, value, k=self.n_examples_per_key + 1
            )
            ids = [_id for _id in ids if _id != str(rollout.id)][
                : self.n_examples_per_key
            ]
            example_rollouts = get_rollouts_by_ids(self.engine, ids)
            example_vals = [
                rollout.get_nested_attr(self.example_field)
                for rollout in example_rollouts
            ]
            output_vals[key] = example_vals
        return output_vals

    async def run_query(self, vlm: VLM, rollout: Rollout, ann_db: AnnotationDatabase):
        try:
            frames, frame_indices = load_video_frames(
                rollout.dataset_filename,
                rollout.filename,
                target_fps=0,
            )
        except Exception as e:
            return ErrorResult(
                rollout_id=rollout.id,
                error_pattern="loading_video_failure",
                error=traceback.format_exc(),
            )
        try:
            example_values = self.construct_example_values(rollout)
            info = {
                "task": rollout.get_nested_attr("task_language_instruction"),
                "examples": example_values,
            }
            messages, res = await vlm.ask_async(
                info=info,
                prompt_filename="icl.jinja2",
                images=[frames[0]],
            )
            icl_str = parse_response(res.choices[0], load_json=False)
        except Exception as e:
            return ErrorResult(
                rollout_id=rollout.id,
                error_pattern="icl_parsing_failure",
                error=traceback.format_exc(),
            )
        return icl_str


if __name__ == "__main__":
    from ares.databases.structured_database import db_to_df

    index_manager = IndexManager(EMBEDDING_DB_PATH, FaissIndex)
    engine = setup_database(RolloutSQLModel, path=ROBOT_DB_PATH)

    # dont use description estimate
    keys = META_INDEX_NAMES + TRAJECTORY_INDEX_NAMES
    keys = [key for key in keys if key != "description_estimate"]
    n_examples_per_key = 5
    overall_tracker = ResultTracker()
    overall_failures = []

    df = db_to_df(engine)
    first_rollout_id = df.iloc[-1].id
    first_rollout = get_rollouts_by_ids(engine, [first_rollout_id])[0]

    vlm = get_vlm("gpt-4o-mini")
    icl_annotating_fn = ICLAnnotatingFn(
        index_manager=index_manager,
        engine=engine,
        keys=keys,
        n_examples_per_key=n_examples_per_key,
        example_field="description_estimate",
    )
    out = asyncio.run(
        icl_annotating_fn.run_query(vlm=vlm, rollout=first_rollout, ann_db=None)
    )

    # for dataset_info in DATASET_NAMES:
    #     print(f"Processing {dataset_info['dataset_formalname']}")
    #     dataset_filename = dataset_info["dataset_filename"]
    #     tracker, failures = orchestrate_annotating(
    #         engine_path=ROBOT_DB_PATH,
    #         ann_db_path=ANNOTATION_DB_PATH,
    #         annotating_fn=ICLAnnotatingFn(index_manager=index_manager, keys=keys, n_examples_per_key=n_examples_per_key),
    #         dataset_filename=dataset_filename,
    #         outer_batch_size=ANNOTATION_OUTER_BATCH_SIZE,
    #         failures_path=os.path.join(
    #             ARES_DATA_DIR,
    #             "annotating_failures",
    #             f"icl_failures_{dataset_filename}.pkl",
    #         ),
    #     )
    #     overall_tracker.update_tracker(tracker)
    #     overall_failures.extend(failures)

    # print(f"OVERALL STATS")
    # overall_tracker.print_stats()
    # print(f"Number of failures: {len(overall_failures)}")
    # breakpoint()
