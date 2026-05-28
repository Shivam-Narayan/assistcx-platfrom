from sqlalchemy import Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid
import enum


class SourceType(enum.Enum):
    MAILBOX = "mailbox"
    API = "api"
    FORM = "form"
    WEB = "web"
    OTHER = "other"


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    email_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    message_id: Mapped[Optional[str]] = mapped_column(
        String, unique=True, index=True, nullable=True
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    tag_ids: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    mailbox_email: Mapped[Optional[str]] = mapped_column(
        String, index=True, nullable=True
    )
    mailbox_folder: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sender_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    web_link: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_template: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    records: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    credits_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="QUEUED")
    source_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    additional_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )

    # Relationships
    agent: Mapped[Optional["Agent"]] = relationship(  # type: ignore
        "Agent", back_populates="emails"
    )
    agent_tasks: Mapped[list["AgentTask"]] = relationship(  # type: ignore
        "AgentTask", back_populates="email", cascade="all, delete, delete-orphan"
    )
    attachments: Mapped[list["Attachment"]] = relationship(  # type: ignore
        "Attachment", back_populates="email", cascade="all, delete, delete-orphan"
    )
    task_events: Mapped[list["TaskEvent"]] = relationship(  # type: ignore
        "TaskEvent", back_populates="email", cascade="all, delete, delete-orphan"
    )


"""
Comments:
=========
Added columns:
- source_type (mailbox, api, form, etc)
- additional_data (JSONB): Additional data for the email
- notes (Text): Notes for the email

Removed columns:
- sent_at
- sender_email
- intent_class
- remote_url: Move to additional_data

Modified columns:
- task_status -> status
"""

"""

The `records` column contains a JSONB object that holds email-specific information. This includes metadata about records sent by external system for agentic processing.

Structure:

- records: (Optional) A list of dictionaries, where each dictionary represents a record associated with the task.

Example:
"records": [
    {
        "field1": "value1",
        "field2": "value2"
    },
    {
        "field1": "value3",
        "field2": "value4"
    }
]

"""
