# Custom libraries
from schemas.chat_message_schema import ChatMessageDetail

# Default libraries
from datetime import datetime
from typing import Any, Dict, Optional, List, Literal
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssistantTaskBase(BaseModel):
    title: str = Field(..., description="Title of the Assistant task")
    schedule: str = Field(
        ...,
        description="Schedule for task execution. Formats: Cron expression (e.g., '0 9 * * *' for daily at 9 AM) or Unix timestamp (e.g., '1738353600' for one-time execution)",
        examples=["0 9 * * *", "1738353600"],
    )
    task_prompt: str = Field(..., description="Query/prompt for the Assistant task execution")
    chat_type: Literal["task"] = Field("task", description="Thread type of Assistant task")
    collections: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        max_items=10,
        description="Knowledge collections behavior: null=no knowledge search, []=use all user collections, [{...}]=use specified collections. Contains id, name, index_name, and description",
    )
    notification_recipients: Optional[List[str]] = Field(
        default=None,
        description="List of email ids to notify upon task execution. If not provided, no notifications will be sent.",
    )
    web_search_enabled: Optional[bool] = Field(
        default=True, description="Whether to enable web search functionality"
    )

    @field_validator("notification_recipients", mode="before")
    def lowercase_notification_recipients(
        cls, v: Optional[List[str]]
    ) -> Optional[List[str]]:
        if v:
            return [recipient.strip().lower() for recipient in v if recipient]
        return v

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class AssistantTaskCreate(AssistantTaskBase):
    pass


class AssistantTaskUpdate(AssistantTaskBase):
    title: Optional[str] = Field(None, description="Title of the Assistant task")
    schedule: Optional[str] = Field(
        None,
        description="Schedule for task execution. Formats: Cron expression or Unix timestamp",
    )
    task_prompt: Optional[str] = Field(
        None, description="Query/prompt for the Assistant task execution"
    )


class AssistantTaskDetail(AssistantTaskBase):
    id: UUID
    user_id: UUID
    schedule: Optional[str] = None
    status: Optional[str] = None
    is_archived: bool = False
    chat_messages: Optional[List[ChatMessageDetail]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_chat_thread(cls, chat_thread):
        """Convert ChatThread with task metadata to AssistantTaskDetail"""
        metadata = chat_thread.chat_metadata or {}
        return cls(
            id=chat_thread.id,
            user_id=chat_thread.user_id,
            title=chat_thread.title or "",
            chat_type=chat_thread.chat_type or "task",
            task_prompt=metadata.get("task_prompt", ""),
            collections=metadata.get("collections"),
            schedule=metadata.get("schedule", ""),
            status=metadata.get("status", ""),
            notification_recipients=metadata.get("notification_recipients", None),
            web_search_enabled=metadata.get("web_search_enabled", True),
            is_archived=chat_thread.is_archived,
            chat_messages=getattr(chat_thread, "chat_messages", None),
            created_at=chat_thread.created_at,
            updated_at=chat_thread.updated_at,
        )


class AssistantTaskStatusResponse(BaseModel):
    chat_thread_id: UUID
    status: str
    message: str
