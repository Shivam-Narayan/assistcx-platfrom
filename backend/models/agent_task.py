# Installed libraries
from sqlalchemy import ARRAY, ForeignKey, DateTime, String, Text, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional
import uuid
from db_pool import Base


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    email_data_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emails.id"), nullable=True
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    thread_id: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    tag_ids: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attachments: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    additional_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    task_order: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    progress: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    credits_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    email: Mapped[Optional["Email"]] = relationship(  # type: ignore
        "Email", back_populates="agent_tasks"
    )
    agent: Mapped[Optional["Agent"]] = relationship(  # type: ignore
        "Agent", back_populates="agent_tasks"
    )
    agent_outputs: Mapped[list["AgentOutput"]] = relationship(  # type: ignore
        "AgentOutput", back_populates="agent_task"
    )


"""
Comments:
=========
Added columns:
- thread_id: for storing the thread id of the task
- attachments
- task_order
- tags
- notes

Modified columns:
- data -> additional_data
- executed_at -> completed_at
"""

"""
attachments:
attachments is a JSONB object that holds task-specific attachments. It's a list of dictionaries, each with following keys: id, name, type, size (optional).
Example:
attachments = [
    {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "name": "attachment.pdf",
        "type": "pdf",
        "size": 123456
    }
]





The `data` column contains a JSONB object that holds task-specific information. This includes metadata about attachments, records, and additional data relevant to the task.

Structure:
- task_order: A string indicating the order of the task, often used when multiple tasks are generated (e.g., "1 of 5").
- attachment_id: (Optional) A list of UUIDs representing the IDs of attachments related to the task.
- records: (Optional) A list of dictionaries, where each dictionary represents a record associated with the task.

Example:
{
  "task_order": "1 of 3",
  "attachment_id": [
    "b3b1e0d4-7f83-4b3c-92d1-3e7d21b7e6a3"
  ],
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
}

----------------------------------------------------------

The 'progress' is a JSON object containing an array of dictionaries, each with two keys: 'status' and 'timestamp'.
Every time the progress status changes, a new dictionary should be appended to this array.

- 'status': 'QUEUED', 'EXECUTING', 'PAUSED','SUCCESSFUL', or 'FAILED', 'ARCHIVED'.
- 'timestamp': {datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")}.

Example:
progress = [
    {
        'status': 'QUEUED',
        'timestamp': '2024-07-25 14:23:45.123456'
    }, 
    {        
        'status': 'EXECUTING',
        'timestamp': '2024-07-25 14:23:45.123456'
    }, 
    #More objects here
]
"""
