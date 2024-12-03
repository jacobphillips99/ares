import json
import typing as t
import uuid
from datetime import datetime

import numpy as np
from pydantic import BaseModel, model_validator
from sqlmodel import Field


class BaseConfig(BaseModel):
    def flatten_fields(self, prefix: str = "") -> t.Dict[str, t.Any]:
        flattened = {}
        for field_name, field_value in self.model_dump().items():
            if isinstance(field_value, dict):
                flattened.update(
                    {f"{prefix}{field_name}_{k}": v for k, v in field_value.items()}
                )
            elif isinstance(field_value, list):
                # Convert lists to JSON strings
                flattened[f"{prefix}{field_name}"] = json.dumps(field_value)
            else:
                flattened[f"{prefix}{field_name}"] = field_value
        return flattened


class Robot(BaseConfig):
    embodiment: str
    gripper: str
    morphology: str
    action_space: str
    rgb_cams: int
    depth_cams: int
    wrist_cams: int


class Environment(BaseConfig):
    name: str
    lighting: str
    simulation: bool


class Task(BaseConfig):
    language_instruction: str
    language_instruction_type: str
    success_criteria: str | None
    success: float | None

    @model_validator(mode="after")
    def check_success(self) -> "Task":
        if not 0 <= self.success <= 1:
            raise ValueError("Success must be between 0 and 1, inclusive")
        return self


class Trajectory(BaseConfig):
    actions: str  # JSON string of list[list[float]]
    is_first: int | None  # index of first step
    is_last: int | None  # index of last step
    is_terminal: int | None  # index of terminal step
    states: str | None  # JSON string of list[list[float]]

    @model_validator(mode="before")
    def convert_sequences_to_json(cls, data: dict) -> dict:
        # Convert any list fields to JSON strings
        for field in ["actions", "states"]:
            if isinstance(data.get(field), (list, np.ndarray)):
                # Convert numpy arrays to lists first if needed
                value = data[field]
                if isinstance(value, np.ndarray):
                    value = value.tolist()
                data[field] = json.dumps(value)
        return data

    @property
    def actions_array(self) -> np.ndarray:
        """Get actions as a numpy array instead of JSON string."""
        return np.array(json.loads(self.actions))

    @property
    def states_array(self) -> np.ndarray | None:
        """Get states as a numpy array instead of JSON string."""
        if self.states is None:
            return None
        return np.array(json.loads(self.states))


class Rollout(BaseConfig):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    creation_time: datetime | None
    ingestion_time: datetime
    path: str
    dataset_name: str
    # description: str | None
    length: int
    robot: Robot
    environment: Environment
    task: Task
    trajectory: Trajectory


def pydantic_to_field_instructions(
    model_cls: type[BaseModel], exclude_fields: t.Dict = {}, prefix: str = ""
) -> list[str]:
    field_instructions = []
    for field_name, field in model_cls.model_fields.items():
        # Get the nested exclude_fields dict if it exists
        nested_exclude = (
            exclude_fields.get(field_name, {})
            if isinstance(exclude_fields, dict)
            else {}
        )

        # Skip if this field is excluded (has a non-dict value in exclude_fields)
        if field_name in exclude_fields and not isinstance(
            exclude_fields[field_name], dict
        ):
            continue

        # Handle nested models recursively
        if hasattr(field.annotation, "model_fields"):
            nested_instructions = pydantic_to_field_instructions(
                field.annotation, nested_exclude, prefix=f"{prefix}{field_name}."
            )
            field_instructions.extend(nested_instructions)
        else:
            field_instructions.append(f"    - {prefix}{field_name}: {str(field)}")
    return field_instructions


def pydantic_to_example_dict(
    model_cls: type[BaseModel], exclude_fields: t.Dict = {}
) -> dict:
    example_dict = {}
    for field_name, field in model_cls.model_fields.items():
        # Get the nested exclude_fields dict if it exists
        nested_exclude = (
            exclude_fields.get(field_name, {})
            if isinstance(exclude_fields, dict)
            else {}
        )

        # Skip if this field is excluded (has a non-dict value in exclude_fields)
        if field_name in exclude_fields and not isinstance(
            exclude_fields[field_name], dict
        ):
            continue

        # Handle nested models recursively
        if hasattr(field.annotation, "model_fields"):
            nested_dict = pydantic_to_example_dict(field.annotation, nested_exclude)
            if nested_dict:  # Only add if not empty
                example_dict[field_name] = nested_dict
        else:
            if hasattr(field.annotation, "__args__"):  # For Literal types
                example_dict[field_name] = field.annotation.__args__[0]
            else:
                example_dict[field_name] = "..."
    return example_dict
