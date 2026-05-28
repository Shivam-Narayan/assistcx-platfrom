# Default libraries
from datetime import datetime
from typing import Optional
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator


class ApiKeyBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    @field_validator("name")
    def validate_name(cls, v):
        # Check if contains only letters, numbers, underscores, hyphens, and periods
        if v and not all(c.isalnum() or c in ("_", "-", ".", " ") for c in v):
            raise ValueError(
                "Name can only contain letters, numbers, underscores, hyphens, and periods"
            )
        return v


class ApiKeyCreate(ApiKeyBase):
    pass


class ApiKeyUpdate(ApiKeyBase):
    name: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore


class ApiKeyDetail(ApiKeyBase):
    id: UUID
    user_id: Optional[UUID] = None
    user_name: Optional[str] = None
    key_hint: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    api_key: Optional[str] = None
    last_used_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
