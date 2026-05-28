# Default libraries
from datetime import datetime
from typing import Optional, Any, Dict
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints


class ActivityLogBase(BaseModel):
    entity_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    entity_id: UUID
    activity_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    previous_state: Optional[Dict[str, Any]] = None
    new_state: Optional[Dict[str, Any]] = None
    note: Optional[str] = None
    activity_metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ActivityLogCreate(ActivityLogBase):
    pass


class ActivityLogDetail(ActivityLogBase):
    id: UUID
    user_id: Optional[UUID] = None
    user_name: Optional[str] = None
    created_at: Optional[datetime] = None
