"""
Errors happen! We want a service to self-heal -- that is, ensure that our databases are synced.
"""

import os
from datetime import datetime
from pathlib import Path

import click
import pandas as pd

from ares.databases.annotation_database import (
    TEST_ANNOTATION_DB_PATH,
    AnnotationDatabase,
)
from ares.databases.embedding_database import (
    META_INDEX_NAMES,
    TEST_EMBEDDING_DB_PATH_2,
    FaissIndex,
    IndexManager,
    rollout_to_embedding_pack,
    rollout_to_index_name,
)
from ares.databases.structured_database import (
    TEST_ROBOT_DB_PATH,
    RolloutSQLModel,
    get_partial_df,
    get_rollout_by_name,
    setup_database,
)
from scripts.run_trajectory_embedding_ingestion import (
    main as run_embedding_database_ingestion_main,
)

HEALING_EXCEPTIONS = {"Saytap": ["grounding"]}
HEAL_INFO_DIR = "/workspaces/ares/data/heal_info"


@click.command("find-heal")
def find_heal_opportunities(heal_info_dir: str = HEAL_INFO_DIR) -> str:
    engine = setup_database(RolloutSQLModel, path=TEST_ROBOT_DB_PATH)
    ann_db = AnnotationDatabase(connection_string=TEST_ANNOTATION_DB_PATH)
    embedding_db = IndexManager(TEST_EMBEDDING_DB_PATH_2, FaissIndex)
    time_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    heal_dir = os.path.join(heal_info_dir, time_str)
    os.makedirs(heal_dir, exist_ok=True)

    # collect all rollout IDs from structured database (engine)
    id_cols = ["id", "dataset_filename", "dataset_formalname", "filename"]
    rollout_df = get_partial_df(engine, id_cols)
    dataset_formalname_to_df = {
        k: v for k, v in rollout_df.groupby("dataset_formalname")
    }

    # check embedding database
    to_update_embedding_index_ids = []
    for dataset_formalname, id_df in dataset_formalname_to_df.items():
        if "embedding" in HEALING_EXCEPTIONS.get(dataset_formalname, []):
            continue
        example_rollout = get_rollout_by_name(
            engine, dataset_formalname, id_df["filename"].iloc[0]
        )
        potential_index_names = [
            rollout_to_index_name(example_rollout, suffix)
            for suffix in ["states", "actions"]
        ] + META_INDEX_NAMES  # description, task
        for index_name in potential_index_names:
            if index_name not in embedding_db.indices:
                to_update_embedding_index_ids.extend(id_df["id"].tolist())
                print(
                    f"Index {index_name} not found in embedding database; adding {len(to_update_embedding_index_ids)} ids to update list"
                )
            else:
                existing_index = embedding_db.indices[index_name]
                existing_index_ids = existing_index.get_all_ids()
                # add any missing ids to update list
                missing_ids = set(id_df["id"].astype(str).tolist()) - set(
                    existing_index_ids.tolist()
                )
                if len(missing_ids) > 0:
                    print(
                        f"Found {len(missing_ids)} missing ids for index {index_name} out of {len(existing_index_ids)} existing ids; {len(missing_ids) / len(existing_index_ids) * 100:.2f}% missing"
                    )
                    to_update_embedding_index_ids.extend(missing_ids)

    update_embedding_ids_path = os.path.join(heal_dir, "update_embedding_ids.txt")
    with open(update_embedding_ids_path, "w") as f:
        for id in to_update_embedding_index_ids:
            f.write(f"{id}\n")
    print(
        f"Found {len(to_update_embedding_index_ids)} ids to update in embedding database; saving to disk at {update_embedding_ids_path}"
    )

    print("\n\n" + "=" * 100 + "\n\n")
    # to update grounding
    to_update_grounding_video_ids = []
    to_update_grounding_annotation_ids = []
    for dataset_formalname, id_df in dataset_formalname_to_df.items():
        if "grounding" in HEALING_EXCEPTIONS.get(dataset_formalname, []):
            to_update_grounding_video_ids.extend(id_df["id"].tolist())
        # check if videos exists -- if not, add to list (will add video and grounding)
        existing_video_ids = pd.Series(ann_db.get_video_ids())
        found_video_ids = (id_df["dataset_filename"] + "/" + id_df["filename"]).apply(
            lambda x: str(Path(x).with_suffix(".mp4"))
        )
        mask = ~found_video_ids.isin(existing_video_ids)
        if mask.any():
            print(f"Found {len(mask)} missing videos for dataset {dataset_formalname}")
            to_update_grounding_video_ids.extend(id_df[mask]["id"].astype(str).tolist())

        # Handle videos that exist but are missing annotations
        has_video_mask = found_video_ids.isin(existing_video_ids)
        videos_with_annotations = pd.Series(ann_db.get_annotation_ids())
        missing_annotations_mask = ~found_video_ids[has_video_mask].isin(
            videos_with_annotations
        )
        if missing_annotations_mask.any():
            print(
                f"Found {missing_annotations_mask.sum()} videos missing annotations for dataset {dataset_formalname}"
            )
            to_update_grounding_annotation_ids.extend(
                id_df[has_video_mask][missing_annotations_mask]["id"]
                .astype(str)
                .tolist()
            )

    update_grounding_video_ids_path = os.path.join(
        heal_dir, "update_grounding_video_ids.txt"
    )
    with open(update_grounding_video_ids_path, "w") as f:
        for id in to_update_grounding_video_ids:
            f.write(f"{id}\n")
    print(
        f"Found {len(to_update_grounding_video_ids)} ids to update in grounding database; saving to disk at {update_grounding_video_ids_path}"
    )

    update_grounding_annotation_ids_path = os.path.join(
        heal_dir, "update_grounding_annotation_ids.txt"
    )
    with open(update_grounding_annotation_ids_path, "w") as f:
        for id in to_update_grounding_annotation_ids:
            f.write(f"{id}\n")
    print(
        f"Found {len(to_update_grounding_annotation_ids)} ids to update in grounding database; saving to disk at {update_grounding_annotation_ids_path}"
    )
    print(f"TIME DIR STR: {time_str}")
    return time_str


@click.command("execute-heal")
@click.option("--time-dir", type=str, required=True)
def execute_heal(time_dir: str):
    heal_dir = os.path.join(HEAL_INFO_DIR, time_dir)
    update_embedding_ids_path = os.path.join(heal_dir, "update_embedding_ids.txt")
    # run embedding ingestion
    run_embedding_database_ingestion_main(
        engine_url=TEST_ROBOT_DB_PATH,
        from_id_file=update_embedding_ids_path,
    )
    # update_grounding_video_ids_path = os.path.join(
    #     heal_dir, "update_grounding_video_ids.txt"
    # )
    # update_grounding_annotation_ids_path = os.path.join(
    #     heal_dir, "update_grounding_annotation_ids.txt"
    # )
    breakpoint()
    pass


@click.group()
def cli():
    """Self-healing utilities for database synchronization"""
    pass


cli.add_command(find_heal_opportunities)
cli.add_command(execute_heal)

if __name__ == "__main__":
    cli()
