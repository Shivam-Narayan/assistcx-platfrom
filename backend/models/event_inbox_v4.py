# Custom libraries
from db_pool import Base

# Default libraries
from sqlalchemy import String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional

# Installed libraries
import uuid


class EventInbox(Base):
    __tablename__ = "event_inbox"
    # Constraints
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_event_inbox_dedupe_key"),)

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )

    # Foreign Keys
    task_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Event Identity
    external_event_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Provider-native event ID (e.g., Graph message ID, S3 ETag)",
    )

    dedupe_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Unique key for deduplication (e.g., task_source_id:external_event_id)",
    )

    # Event Data
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Normalized event payload (what the agent processes)",
    )

    event_inbox_metadata: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Processing context: trace_ids, attempts_history, routing, ingestion_stats",
    )

    # Processing Status
    status: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: {"state": "pending", "attempts": 0},
        nullable=False,
        comment="Processing progress: state, attempts, last_attempt_at, errors, progress, worker_id",
    )

    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the event was successfully processed",
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Last error message (deprecated - use status.last_error instead)",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Relationships
    task_source: Mapped["TaskSource"] = relationship(  # type: ignore
        "TaskSource", back_populates="events"
    )
