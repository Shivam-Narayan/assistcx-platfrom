# Custom libraries
from schemas.chat_message_schema import ChatMessageDetail

# Default libraries
from datetime import datetime
from typing import Dict, List, Literal, Optional
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints


class ChatHistoryBase(BaseModel):
    title: Optional[str] = None  # type: ignore
    chat_metadata: Optional[Dict] = None
    parent_id: Optional[UUID] = None
    chat_type: Optional[Literal["chat", "task"]] = "chat"

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ChatHistoryCreate(ChatHistoryBase):
    pass


class ChatHistoryUpdate(ChatHistoryBase):
    title: Optional[str] = None  # type: ignore


class ChatHistoryDetail(ChatHistoryBase):
    id: UUID
    user_id: UUID
    is_archived: Optional[bool] = False
    parent_id: Optional[UUID] = None
    chat_messages: Optional[List[ChatMessageDetail]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChatHistoryResponse(BaseModel):
    chat_threads: List[ChatHistoryDetail]
    total: int
