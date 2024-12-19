import typing as t
import uuid
from datetime import datetime

import pandas as pd
from sqlalchemy import Column, Engine, MetaData, inspect, text
from sqlmodel import Session, SQLModel, create_engine

from ares.configs.base import Rollout
from ares.configs.pydantic_sql_helpers import create_flattened_model

SQLITE_PREFIX = "sqlite:///"
BASE_ROBOT_DB_PATH = SQLITE_PREFIX + "robot_data.db"
TEST_ROBOT_DB_PATH = SQLITE_PREFIX + "test_robot_data.db"

RolloutSQLModel = create_flattened_model(Rollout)


def setup_database(RolloutSQLModel: SQLModel, path: str = BASE_ROBOT_DB_PATH) -> Engine:
    engine = create_engine(path)
    inspector = inspect(engine)

    if not inspector.has_table("rollout"):
        # If table doesn't exist, create it with all columns
        RolloutSQLModel.metadata.create_all(engine)
    else:
        # Get existing columns
        existing_columns = {col["name"] for col in inspector.get_columns("rollout")}

        # Get new columns from the model
        model_columns = set(RolloutSQLModel.model_fields.keys())

        # Find columns to add
        columns_to_add = model_columns - existing_columns

        if columns_to_add:
            # Create MetaData instance
            metadata = MetaData()
            metadata.reflect(bind=engine)

            # Get the table
            table = metadata.tables["rollout"]

            # Add new columns
            with engine.begin() as conn:
                for col_name in columns_to_add:
                    # Get column definition from model
                    col_type = RolloutSQLModel.model_fields[col_name].annotation
                    conn.execute(
                        text(
                            f"ALTER TABLE rollout ADD COLUMN {col_name} {get_sql_type(col_type)} NULL"
                        )
                    )
                print(f"Added new columns: {columns_to_add}")

    return engine


def get_sql_type(python_type: type) -> str:
    """Convert Python/Pydantic types to SQLite types."""
    type_map = {
        str: "TEXT",
        int: "INTEGER",
        float: "REAL",
        bool: "BOOLEAN",
        datetime: "TIMESTAMP",
        uuid.UUID: "TEXT",
        # Add more type mappings as needed
    }
    # Handle Optional types
    origin = t.get_origin(python_type)
    if origin is t.Union:
        args = t.get_args(python_type)
        # Get the non-None type
        python_type = next(arg for arg in args if arg is not type(None))

    return type_map.get(python_type, "TEXT")


def add_rollout(engine: Engine, rollout: Rollout, RolloutSQLModel: SQLModel) -> None:
    rollout_sql_model = RolloutSQLModel(**rollout.flatten_fields(""))
    with Session(engine) as session:
        session.add(rollout_sql_model)
        session.commit()


def add_rollouts(engine: Engine, rollouts: t.List[Rollout]) -> None:
    # use add_all; potentially update to bulk_save_objects
    with Session(engine) as session:
        session.add_all([RolloutSQLModel(**t.flatten_fields("")) for t in rollouts])
        session.commit()


# query helpers
# Database queries
def get_rollouts(engine: Engine) -> pd.DataFrame:
    """Get all rollouts from the database as a pandas DataFrame."""
    with Session(engine) as session:
        query = text(
            """
            SELECT *
            FROM rollout
            ORDER BY id
            """
        )
        df = pd.read_sql(query, session.connection())

        # Get expected columns from current model
        expected_columns = set(RolloutSQLModel.model_fields.keys())

        # Add missing columns with NaN values
        for col in expected_columns - set(df.columns):
            df[col] = pd.NA

        return df


if __name__ == "__main__":
    from ares.configs.test_configs import ROLL1, ROLL2

    engine = setup_database(RolloutSQLModel, path=TEST_ROBOT_DB_PATH)
    add_rollout(engine, ROLL1, RolloutSQLModel)
    add_rollout(engine, ROLL2, RolloutSQLModel)

    sess = Session(engine)
    res = sess.query(RolloutSQLModel).filter(RolloutSQLModel.task_success > 0.5)
    breakpoint()
