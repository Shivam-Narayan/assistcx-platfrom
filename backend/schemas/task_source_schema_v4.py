# Default libraries
from datetime import datetime
from typing import Optional, Dict, Any, List
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, Field

# Custom libraries
from configs.integrations_v4 import INTEGRATIONS
from configs.triggers_v4 import ALL_TRIGGERS


class TaskSourceBase(BaseModel):
    agent_id: UUID
    connection_id: UUID
    provider_key: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=4, max_length=64)
    ]
    trigger_key: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=4, max_length=128)
    ]
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=4, max_length=255)
    ]
    description: Optional[str] = None
    resource_config: Optional[Dict[str, Any]] = None
    filter_config: Optional[Dict[str, Any]] = None
    schedule_config: Optional[Dict[str, Any]] = None
    processing_config: Optional[Dict[str, Any]] = None
    enabled: bool = True
    status: str = Field(default="ok", max_length=32)
    cursor: Optional[Dict[str, Any]] = None
    task_source_metadata: Optional[Dict[str, Any]] = None
    tags: Optional[Dict[str, Any]] = None

    @field_validator("provider_key")
    @classmethod
    def validate_provider_key(cls, v: str) -> str:
        """Validate provider_key against INTEGRATIONS config."""
        provider_keys = [integration.get("key") for integration in INTEGRATIONS]
        if v not in provider_keys:
            raise ValueError(
                f"Invalid provider_key. Must be one of: {', '.join(provider_keys)}"
            )
        return v

    # @field_validator('trigger_key')
    # @classmethod
    # def validate_trigger_key(cls, v: str) -> str:
    #     """Validate trigger_key against ALL_TRIGGERS config."""
    #     trigger_slugs = [trigger.get("slug") for trigger in ALL_TRIGGERS]
    #     if v not in trigger_slugs:
    #         raise ValueError(f"Invalid trigger_key. Must be one of: {', '.join(trigger_slugs)}")
    #     return v

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class TaskSourceCreate(TaskSourceBase):
    pass


class TaskSourceUpdate(TaskSourceBase):
    agent_id: Optional[UUID] = None
    connection_id: Optional[UUID] = None
    name: Optional[
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=4, max_length=255)
        ]
    ] = None
    provider_key: Optional[
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=4, max_length=64)
        ]
    ] = None
    trigger_key: Optional[
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=4, max_length=128)
        ]
    ] = None

    @field_validator("provider_key")
    @classmethod
    def validate_provider_key(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        provider_keys = [integration.get("key") for integration in INTEGRATIONS]
        if v not in provider_keys:
            raise ValueError(
                f"Invalid provider_key. Must be one of: {', '.join(provider_keys)}"
            )
        return v

    @field_validator("trigger_key")
    @classmethod
    def validate_trigger_key(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        trigger_slugs = [trigger.get("slug") for trigger in ALL_TRIGGERS]
        if v not in trigger_slugs:
            raise ValueError(
                f"Invalid trigger_key. Must be one of: {', '.join(trigger_slugs)}"
            )
        return v

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class TaskSourceDetail(TaskSourceBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    last_checked_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class TaskSourceResponse(BaseModel):
    task_sources: List[TaskSourceDetail]
