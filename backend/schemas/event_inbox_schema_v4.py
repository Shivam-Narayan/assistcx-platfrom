# Default libraries
from datetime import datetime
from typing import Optional, Dict, Any, List
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints, Field, field_validator


class EventInboxBase(BaseModel):
    task_source_id: UUID
    external_event_id: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=4, max_length=255)
    ]
    dedupe_key: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=4, max_length=255)
    ]
    payload: Annotated[Dict[str, Any], Field(min_length=1)]
    event_inbox_metadata: Optional[Dict[str, Any]] = None
    status: Annotated[
        Dict[str, Any], Field(default={"state": "pending", "attempts": 0})
    ]
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class EventInboxCreate(EventInboxBase):
    pass


class EventInboxUpdate(EventInboxBase):
    task_source_id: Optional[UUID] = None
    external_event_id: Optional[
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=4, max_length=255)
        ]
    ] = None
    dedupe_key: Optional[
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=4, max_length=255)
        ]
    ] = None
    payload: Optional[Annotated[Dict[str, Any], Field(min_length=1)]] = None


class EventInboxDetail(EventInboxBase):
    id: UUID
    created_at: Optional[datetime] = None


class EventInboxResponse(BaseModel):
    event_inboxes: List[EventInboxDetail]
