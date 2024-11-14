import os
import time

import datasets
import numpy as np
import tensorflow_datasets as tfds
from sqlalchemy.orm import Session
from tqdm import tqdm

from ares.configs.base import Environment, Robot, Rollout, Task
from ares.configs.open_x_embodiment_configs import OpenXEmbodimentEpisode
from ares.databases.structured_database import (
    SQLITE_PREFIX,
    TEST_ROBOT_DB_PATH,
    add_rollout,
    add_rollouts,
    create_flattened_model,
    recreate_model,
    setup_database,
)
from ares.extractor import (
    LLMInformationExtractor,
    RandomInformationExtractor,
    hard_coded_dataset_info_extraction,
    hard_coded_episode_info_extraction,
    merge_dicts,
)


def build_dataset(
    dataset_name: str, data_dir: str
) -> tuple[tfds.builder, tfds.datasets]:
    builder = tfds.builder(dataset_name, data_dir=data_dir)
    builder.download_and_prepare()
    datasets = builder.as_dataset()
    return builder, datasets


if __name__ == "__main__":
    hf_base = "jxu124/OpenX-Embodiment"
    dataset_name = "ucsd_kitchen_dataset_converted_externally_to_rlds"
    # dataset_name = "cmu_play_fusion"
    data_dir = "/workspaces/ares/data"

    builder, datasets = build_dataset(dataset_name, data_dir)
    dataset_info = builder.info
    ds = datasets["train"]

    random_extractor = RandomInformationExtractor()

    # os.remove(TEST_ROBOT_DB_PATH.replace(SQLITE_PREFIX, ""))
    RolloutSQLModel = create_flattened_model(Rollout)
    engine = setup_database(RolloutSQLModel, path=TEST_ROBOT_DB_PATH)

    # rollouts: list[Rollout] = []
    # for i, ep in tqdm(enumerate(ds)):
    #     episode = OpenXEmbodimentEpisode(**ep)
    #     steps = episode.steps
    #     dataset_info_dict = hard_coded_dataset_info_extraction(dataset_info)
    #     episode_info_dict = hard_coded_episode_info_extraction(episode)
    #     hardcoded_info = merge_dicts(dataset_info_dict, episode_info_dict)
    #     traj = hardcoded_info["trajectory"]
    #     print(traj["is_first"], traj["is_last"], traj["is_terminal"])

    #     rollout = random_extractor.extract(episode=episode, dataset_info=dataset_info)
    #     rollouts.append(rollout)
    #     # just track this
    #     start_time = time.time()
    #     add_rollout(engine, rollout, RolloutSQLModel)

    sess = Session(engine)
    # get a df.head() basically
    # Get first few rows from RolloutSQLModel table
    rows = sess.query(RolloutSQLModel).limit(5).all()
    # breakpoint()
    row = rows[0]
    rollout = recreate_model(rows[0], Rollout)
    breakpoint()
    # Print sample rows
    for row in rows:
        print(f"\nRollout {row.id}:")
        print(f"Path: {row.path}")
        print(f"Task Success: {row.task_success}")
        print(f"Language Instruction: {row.task_language_instruction}")
        breakpoint()
    # RolloutSQLModel = create_flattened_model(Rollout, non_nullable_fields=["id", "path"])

    # row_count = sess.execute(
    #     select(func.count()).select_from(RolloutSQLModel)
    # ).scalar_one()
    # res = (
    #     sess.query(RolloutSQLModel)
    #     .filter(RolloutSQLModel.task_success > 0.5)
    #     .all()
    # )
    # print(f"mean wins: {len(res) / row_count}")
    #  res = sess.scalars(sess.query(RolloutSQLModel.task_language_instruction)).all()
    breakpoint()
