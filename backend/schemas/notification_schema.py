# Custom libraries

# Default libraries
from datetime import datetime
from typing import Optional, List
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict


class NotificationBase(BaseModel):
    recipient_id: Optional[UUID] = None
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    notification_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    template_key: Optional[str] = None
    channel: Optional[str] = "email"
    status: Optional[str] = "PENDING"
    delivery_info: Optional[dict] = None
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class NotificationCreate(NotificationBase):
    pass


class NotificationUpdate(NotificationBase):
    sent_at: Optional[datetime] = None


class NotificationDetail(NotificationBase):
    id: UUID
    sent_at: Optional[datetime] = None
    created_at: datetime
