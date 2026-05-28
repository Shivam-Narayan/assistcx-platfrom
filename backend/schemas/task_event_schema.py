# Default libraries
from datetime import datetime
from typing import Optional, Any, Dict
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict


class TaskEventBase(BaseModel):
    name: Optional[str] = None
    key: Optional[str] = None
    count: Optional[int] = None
    description: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None
    event_type: Optional[str] = None


class TaskEventDetail(TaskEventBase):
    id: UUID
    email_data_id: UUID
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
