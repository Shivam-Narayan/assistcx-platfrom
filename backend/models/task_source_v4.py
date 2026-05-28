# Custom libraries
from db_pool import Base

# Default libraries
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional

# Installed libraries
import uuid


class TaskSource(Base):
    __tablename__ = "task_sources"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )

    # Foreign Keys
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity
    provider_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Denormalized from connection for efficient queries",
    )

    trigger_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="References TRIGGERS registry (e.g., 'outlook.new_email')",
    )

    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="User-visible label"
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Optional description"
    )

    # Configuration (from Trigger template schemas)
    resource_config: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="What to watch: mailbox+folder, bucket+prefix, object+query",
    )

    filter_config: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Event filters: sender domains, attachment types, field conditions",
    )

    schedule_config: Mapped[dict] = mapped_column(
        JSONB, default=dict, comment="Polling interval, cron, jitter, backoff"
    )

    processing_config: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Event processing: include body, download attachments, field selection",
    )

    # Status & Control
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, index=True, comment="User-controlled on/off toggle"
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default="ok",
        index=True,
        comment="Health status: ok, warn, error, auth_error",
    )

    # Runtime State
    cursor: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Polling state: delta_token, timestamp, offset, history_id",
    )

    task_source_metadata: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Operational context: polling_metrics, adapter_version, error_history, rate_limits",
    )

    last_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Last adapter execution time"
    )

    last_success_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful event ingestion",
    )

    error_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="Consecutive errors for exponential backoff"
    )

    last_error: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Last error message for debugging"
    )

    # Metadata
    tags: Mapped[dict] = mapped_column(
        JSONB, default=list, comment="Optional labels for filtering/grouping"
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Soft delete timestamp for audit trail",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent: Mapped["Agent"] = relationship(  # type: ignore
        "Agent", back_populates="task_sources"
    )

    connection: Mapped["Connection"] = relationship(  # type: ignore
        "Connection", back_populates="task_sources"
    )

    events: Mapped[list["EventInbox"]] = relationship(  # type: ignore
        "EventInbox", back_populates="task_source", cascade="all, delete-orphan"
    )
