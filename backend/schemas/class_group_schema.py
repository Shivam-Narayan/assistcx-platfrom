# Default libraries
from datetime import datetime
from typing import Dict, Optional, List
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator


class ClassGroupBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    description: Optional[str] = None
    class_schema: List[Dict]

    @field_validator("class_schema")
    def not_empty(cls, v):
        if not v:
            raise ValueError("Class schema cannot be empty")
        return v


class ClassGroupCreate(ClassGroupBase):
    pass


class ClassGroupUpdate(ClassGroupBase):
    name: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore
    key: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore
    class_schema: Optional[List[Dict]] = None

    @field_validator("key", mode="before")
    def force_key_none(cls, v):
        # Always set key to None to avoid updating it
        return None


class ClassGroupDetail(ClassGroupBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
