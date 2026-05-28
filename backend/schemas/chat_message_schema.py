# Default libraries
from datetime import datetime
from typing import Dict, List, Optional
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints, field_serializer

# Reuse existing schemas from research agent
from agents.research_agent.schemas import ResearchKnowledge, SourceDocument


class ChatMessageBase(BaseModel):
    role: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]  # type: ignore
    context: Optional[Dict] = None
    feedback: Optional[Dict] = None
    message_metadata: Optional[Dict] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ChatMessageCreate(ChatMessageBase):
    chat_history_id: UUID


class ChatMessageUpdate(ChatMessageBase):
    role: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore
    content: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] = None  # type: ignore

    @field_serializer("role")
    def remove_role(self, value):
        return None


class GraphStateContext(BaseModel):
    """Graph state context attached to assistant messages."""

    graph_thread_id: Optional[str] = None
    original_query: Optional[str] = None
    relevant_sources: Optional[List[SourceDocument]] = None
    research_knowledge: Optional[List[ResearchKnowledge]] = None
    suggested_queries: Optional[List[str]] = None
    query_type: Optional[str] = None
    title: Optional[str] = None
    messages: Optional[List[Dict]] = None  # Tool calls represent the "plan"
    metadata: Optional[Dict] = None
    research_complete: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class ChatMessageDetail(ChatMessageBase):
    id: UUID
    chat_history_id: UUID
    graph_state: Optional[GraphStateContext] = (
        None  # Optional - populated for assistant messages
    )
    token_usage: Optional[Dict] = None  # Token usage metrics for assistant messages
    credits_used: Optional[int] = None  # Credits consumed for this message
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChatMessageResponse(BaseModel):
    chat_messages: List[ChatMessageDetail]
    total: int


class ChatThreadMessage(BaseModel):
    role: str
    content: str
    timestamp: datetime
