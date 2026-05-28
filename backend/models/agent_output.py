from sqlalchemy import Integer, ForeignKey, DateTime, Text, String
from sqlalchemy.dialects.postgresql import JSONB, UUID, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


class AgentOutput(Base):
    __tablename__ = "agent_outputs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    agent_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_tasks.id"), nullable=True
    )
    thread_id: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_actions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    execution_log: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    credits_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    token_usage: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent: Mapped[Optional["Agent"]] = relationship(  # type: ignore
        "Agent", back_populates="agent_outputs"
    )
    agent_task: Mapped[Optional["AgentTask"]] = relationship(  # type: ignore
        "AgentTask", back_populates="agent_outputs"
    )


"""
Comments:
=========
Added columns:
- thread_id
- execution_log

Removed columns:
- email_data_id
- agent_environment
- agent_memory

"""

"""
The 'agent_actions' column contains a JSONB array of action objects performed by an agent. Each object includes details about the action, its input, and any relevant thoughts or outputs.

Structure:
- action: An action proposed by LLM to be performed by the agent (e.g., `"upload_to_s3"`).
- input: Action input sent by an LLM to be passed fo given action, usually resembles the function signature.
  - file_name: Name of the file to be processed or uploaded.
- thought: A string detailing the agent's reasoning or plan related to the action.
- output: A string representing the result of the action taken by the agent(e.g., API response).

Example:
[
  {
    "action": "upload_to_s3",
    "input": {
      "upload_data": {
        "message_id": "AA",
        "mailbox_email": "test1@test1.com",
        "sender_email": "test@test.com",
        "email_subject": "Fw: Post invoice",
        "received_date": "yyyy/mm/ddd",
        "received_time": "hh:mm:ss"
      },
      "file_name": "{file_name}.{extension}"
    },
    "thought": "Thought: ",
    "output": "https://{bucket_name}.s3.amazonaws.com/{folder_name}/{file_name}.{extension}"
  }
]

----------------------------------------------------------
The 'agent_environment' contains dynamic information dictionary added by agents which usually contains system level info, which agent keeps in environment for execution.

The 'agent_environment' dictionary includes the following keys:
- 'message_id': A string representing the unique identifier of the email message.
- 'mailbox_email': A string containing the email address of the mailbox where the email was received.
- 'sender_email': A string indicating the email address of the sender.
- 'email_subject': A string representing the subject of the email.
- 'email_received_at': A string representing the date and time when the email was received.

Example:
agent_environment = {
    'message_id': 'AAAtryjkt4o3r5trghjryyyhggrrty543e457',
    'mailbox_email': 'mailbox@email.com',
    'sender_email': 'sender@email.com',
    'email_subject': 'Email Subject',
    'email_received_at': '2024-07-25 14:23:45.123456',
}
----------------------------------------------------------
The 'agent_memory' : PENDING
"""
