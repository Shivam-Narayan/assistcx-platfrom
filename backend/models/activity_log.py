"""
will be planned along with notifications
"""

from sqlalchemy import String, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid
import enum


class ActivityType(enum.Enum):
    TASK_STATUS_CHANGE = "task_status_change"
    TASK_RETRY = "task_retry"
    TASK_REVIEW = "task_review"
    TASK_ARCHIVED = "task_archived"
    TASK_CREATED = "task_created"


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    __table_args__ = (
        Index("idx_entity_activity", "entity_type", "entity_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    user_id: Mapped[str] = mapped_column(String, nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # "agent_task", "agent", etc.
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    activity_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    previous_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activity_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


"""
Change log:
=========
New table

"""

"""
previous_state and new_state:
Store only the changed fields, not the entire row
Example: {"status": "QUEUED"} → {"status": "EXECUTING"}

metadata:
Store additional context about the action
Example: {"reason": "User requested a retry"}
"""
