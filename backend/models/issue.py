from sqlalchemy import String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tag_ids: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    agent_task_ids: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    issue_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    subscribed: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    comments: Mapped[list["IssueComment"]] = relationship(  # type: ignore
        "IssueComment", back_populates="issue", cascade="all, delete-orphan"
    )


"""
The 'status_history' is a JSONB array tracking all status changes.
Every time the status changes, a new entry should be appended.

Fields per entry:
- 'status': 'open', 'in_progress', 'resolved', 'closed', 'reopened'
- 'reason': Why this status was set (required for open/reopen, optional otherwise)
- 'user_id': Who made the change
- 'timestamp': When the change occurred

Example:
status_history = [
    {
        "status": "open",
        "reason": "Customer reported payment gateway timeout errors",
        "user_id": "usr_abc123",
        "timestamp": "2024-12-09 10:30:00.123456"
    },
    {
        "status": "in_progress",
        "reason": "Assigned to backend team",
        "user_id": "usr_xyz789",
        "timestamp": "2024-12-09 11:15:00.654321"
    },
    {
        "status": "resolved",
        "reason": "Fixed retry logic in payment service",
        "user_id": "usr_xyz789",
        "timestamp": "2024-12-10 14:20:00.987654"
    },
    {
        "status": "reopened",
        "reason": "Issue reoccurred after deployment",
        "user_id": "usr_abc123",
        "timestamp": "2024-12-11 09:00:00.111222"
    }
]
"""
