import os
import time

import datasets
import numpy as np
import tensorflow_datasets as tfds
from sqlalchemy.orm import Session
from tqdm import tqdm

from ares.configs.base import Environment, Robot, Rollout, Task
from ares.configs.open_x_embodiment_configs import OpenXEmbodimentEpisode
from ares.database import (  # RolloutSQLModel,
    SQLITE_PREFIX,
    TEST_ROBOT_DB_PATH,
    add_rollout,
    add_rollouts,
    create_flattened_model,
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

    os.remove(TEST_ROBOT_DB_PATH.replace(SQLITE_PREFIX, ""))
    engine = setup_database(path=TEST_ROBOT_DB_PATH)

    rollouts: list[Rollout] = []
    add_and_commit_times: list[float] = []

    for i, ep in tqdm(enumerate(ds)):
        episode = OpenXEmbodimentEpisode(**ep)
        steps = episode.steps
        dataset_info_dict = hard_coded_dataset_info_extraction(dataset_info)
        episode_info_dict = hard_coded_episode_info_extraction(episode)
        hardcoded_info = merge_dicts(dataset_info_dict, episode_info_dict)
        traj = hardcoded_info["trajectory"]
        print(traj["is_first"], traj["is_last"], traj["is_terminal"])

        breakpoint()
        # rollout = random_extractor.extract(
        #     episode=episode, dataset_info=dataset_info
        # )
        # rollouts.append(rollout)
        # # just track this
        # start_time = time.time()
        # add_rollout(engine, rollout)
        # add_and_commit_times.append(time.time() - start_time)
        # if i > 50:
        #     break

    print(
        f"mean (sum) --> add and commit time: {np.mean(add_and_commit_times), np.sum(add_and_commit_times)}"
    )

    os.remove(TEST_ROBOT_DB_PATH.replace(SQLITE_PREFIX, ""))
    engine = setup_database(path=TEST_ROBOT_DB_PATH)

    tic = time.time()
    add_rollouts(engine, rollouts)
    bunch_time = time.time() - tic

    print(f"time to add all rollouts: {np.mean(bunch_time), np.sum(bunch_time)}")

    sess = Session(engine)
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
