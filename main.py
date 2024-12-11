import os
import time
import traceback

import numpy as np
import pandas as pd
import tensorflow_datasets as tfds
from sqlalchemy import Engine, case, func, text
from sqlalchemy.orm import Session
from sqlmodel import SQLModel, select
from tqdm import tqdm

from ares.configs.base import Rollout
from ares.configs.open_x_embodiment_configs import (
    OpenXEmbodimentEpisode,
    OpenXEmbodimentEpisodeMetadata,
    get_dataset_information,
)
from ares.configs.pydantic_sql_helpers import recreate_model
from ares.databases.embedding_database import (
    TEST_EMBEDDING_DB_PATH,
    FaissIndex,
    IndexManager,
    rollout_to_embedding_pack,
)
from ares.databases.structured_database import (
    SQLITE_PREFIX,
    TEST_ROBOT_DB_PATH,
    RolloutSQLModel,
    add_rollout,
    setup_database,
)
from ares.image_utils import ARES_DATASET_VIDEO_PATH, save_video
from ares.models.extractor import RandomInformationExtractor


def build_dataset(
    dataset_name: str, data_dir: str
) -> tuple[tfds.builder, tfds.datasets]:
    builder = tfds.builder(dataset_name, data_dir=data_dir)
    builder.download_and_prepare()
    dataset_dict = builder.as_dataset()
    return builder, dataset_dict


def get_df_from_db(
    engine: Engine, RolloutSQLModel: SQLModel, columns: list[str]
) -> pd.DataFrame:
    df = pd.read_sql(
        select(*[getattr(RolloutSQLModel, col) for col in columns]),
        engine,
    )
    return df


TEST_TIME_STEPS = 100


if __name__ == "__main__":

    from ares.models.llm import NOMIC_EMBEDDER as EMBEDDER

    index_manager = IndexManager(TEST_EMBEDDING_DB_PATH, index_class=FaissIndex)

    hf_base = "jxu124/OpenX-Embodiment"
    # ones that worked
    for dataset_name in [
        # "ucsd_kitchen_dataset_converted_externally_to_rlds",
        # dataset_name = "cmu_play_fusion"
        # "cmu_franka_exploration_dataset_converted_externally_to_rlds",
        # # dataset_name = "utokyo_saytap_converted_externally_to_rlds" --> dont actually want i dont think
        # "asu_table_top_converted_externally_to_rlds",
        # "berkeley_fanuc_manipulation",
        # "cmu_stretch",
        # ones that failed
        "jaco_play",
        # dataset_name = "nyu_rot_dataset_converted_externally_to_rlds"
        # dataset_name = "ucsd_pick_and_place_dataset_converted_externally_to_rlds"
        # dataset_name = "dlr_edan_shared_control_converted_externally_to_rlds"
        # dataset_name = "imperialcollege_sawyer_wrist_cam"
        # dataset_name = "tokyo_u_lsmo_converted_externally_to_rlds"
        # ---> below not found by new oxe-downloader script
        # dataset_name = "conq_hose_manipulation"
        # dataset_name = "tidybot"
        # dataset_name = "plex_robosuite"
    ]:
        # going to try oxe-downloader?
        # oxe-download --dataset "name"

        data_dir = "/workspaces/ares/data/oxe/"
        builder, dataset_dict = build_dataset(dataset_name, data_dir)
        # dataset_info = builder.info
        ds = dataset_dict["train"]
        dataset_info = get_dataset_information(dataset_name)

        random_extractor = RandomInformationExtractor()

        # os.remove(TEST_ROBOT_DB_PATH.replace(SQLITE_PREFIX, ""))
        # engine = setup_database(RolloutSQLModel, path=TEST_ROBOT_DB_PATH)

        rollouts: list[Rollout] = []
        all_times = []
        tic = time.time()
        for i, ep in tqdm(enumerate(ds)):
            try:
                # steps = list(ep["steps"])
                episode = OpenXEmbodimentEpisode(**ep)

                # breakpoint()
                if episode.episode_metadata is None:
                    # construct our own metadata
                    episode.episode_metadata = OpenXEmbodimentEpisodeMetadata(
                        file_path=f"episode_{i}.npy",  # to mock extension
                    )

                # video = [step.observation.image for step in episode.steps]
                # fname = os.path.splitext(episode.episode_metadata.file_path)[0]
                # # check if the file exists
                # if os.path.exists(
                #     os.path.join(
                #         ARES_DATASET_VIDEO_PATH, rollout.dataset_name, fname + ".mp4"
                #     )
                # ):
                #     continue
                # out = save_video(video, dataset_name, fname)

                rollout = random_extractor.extract(
                    episode=episode, dataset_info=dataset_info
                )
                # rollouts.append(rollout)
                # # just track this
                # start_time = time.time()
                # add_rollout(engine, rollout, RolloutSQLModel)
                # all_times.append(time.time() - start_time)

                # add the non-robot specific embeddings
                for name in ["task", "description"]:
                    inp = (
                        rollout.task.language_instruction
                        if name == "description"
                        else rollout.task.success_criteria
                    )
                    if inp is None:
                        continue
                    embedding = EMBEDDER.embed(inp)
                    index_manager.add_vector(name, embedding, str(rollout.id))

                embedding_pack = rollout_to_embedding_pack(rollout)

                for index_name, matrix in embedding_pack.items():
                    if index_name not in index_manager.indices.keys():
                        index_manager.init_index(
                            index_name,
                            matrix.shape[1],
                            TEST_TIME_STEPS,
                            norm_means=None,
                            norm_stds=None,
                        )
                    if not (
                        matrix is None
                        or (isinstance(matrix, list) and all(x is None for x in matrix))
                        or len(matrix.shape) != 2
                    ):
                        index_manager.add_matrix(index_name, matrix, str(rollout.id))

            except Exception as e:
                print(f"Error processing episode {i}: {e}")
                print(traceback.format_exc())
                breakpoint()

        print(f"Total rollouts: {len(rollouts)}")
        print(f"Total time: {time.time() - tic}")
        print(f"Mean time: {np.mean(all_times)}")

        print(index_manager.metadata)
        index_manager.save()

        # sess = Session(engine)
        # # get a df.head() basically
        # # Get first few rows from RolloutSQLModel table
        # first_rows = sess.query(RolloutSQLModel).limit(5).all()
        # last_rows = (
        #     sess.query(RolloutSQLModel).order_by(RolloutSQLModel.id.desc()).limit(5).all()
        # )
        # rows = first_rows + last_rows
        # # breakpoint()
        # # row = rows[0]
        # # rollout = recreate_model(rows[0], Rollout)
        # breakpoint()
        # # Print sample rows
        # # for row in rows:
        # #     print(f"\nRollout {row.id}:")
        # #     print(f"Path: {row.path}")
        # #     print(f"Task Success: {row.task_success}")
        # #     print(f"Language Instruction: {row.task_language_instruction}")
        # #     breakpoint()

        # row_count = sess.execute(
        #     select(func.count()).select_from(RolloutSQLModel)
        # ).scalar_one()
        # print(f"row count: {row_count}")
        # # res = (
        # #     sess.query(RolloutSQLModel)
        # #     .filter(RolloutSQLModel.task_success > 0.5)
        # #     .all()
        # # )
        # # print(f"mean wins: {len(res) / row_count}")
        # res = sess.scalars(sess.query(RolloutSQLModel.task_language_instruction)).all()
        # res = sess.scalars(sess.query(RolloutSQLModel.trajectory_is_last)).all()

        # # get unique dataset_name
        # res = sess.scalars(sess.query(RolloutSQLModel.dataset_name)).unique()
        # print(f"unique dataset_name: {list(res)}")
        # # comparison df
        # comparison_df = pd.read_sql(
        #     select(
        #         RolloutSQLModel.trajectory_is_last,
        #         RolloutSQLModel.trajectory_is_terminal,
        #     ),
        #     engine,
        # )

        # # Print summary statistics
        # print(
        #     (
        #         comparison_df.trajectory_is_last == comparison_df.trajectory_is_terminal
        #     ).mean()
        # )

    breakpoint()
