# Custom libraries
from schemas.issue_comment_schema import IssueCommentDetail
from schemas.agent_task_schema import AgentTaskBase

# Default libraries
from datetime import datetime
from typing import Any, Dict, List, Optional
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class IssueProgress(BaseModel):
    status: Optional[str] = None
    reason: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    timestamp: Optional[str] = None


class IssueProgressUpdate(BaseModel):
    status: str
    reason: Optional[str] = None


class IssueBase(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    tag_ids: Optional[List[UUID]] = None
    agent_task_ids: List[UUID] = Field(..., min_length=1)
    issue_metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class IssueCreate(IssueBase):
    pass


class IssueUpdate(IssueBase):
    title: Optional[str] = None  # type: ignore
    description: Optional[str] = None  # type: ignore
    agent_task_ids: Optional[List[UUID]] = None  # type: ignore


class IssueDetail(IssueBase):
    id: UUID
    tag_ids: Optional[List[UUID]] = None 
    agent_task_ids: Optional[List[UUID]] = None
    created_by: Optional[UUID] = None
    user_name: Optional[str] = None
    progress: Optional[List[IssueProgress]] = None
    comments: Optional[List[IssueCommentDetail]] = None
    subscribed: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class IssueUserFilter(BaseModel):
    user_id: UUID
    user_name: Optional[str] = None
    issue_count: int


class IssueFilters(BaseModel):
    users: Optional[List[IssueUserFilter]] = []


class AgentTaskPreview(AgentTaskBase):
    id: UUID
    email_data_id: Optional[UUID] = None
    agent_id: Optional[UUID] = None
    agent_name: Optional[str] = None
    agent_icon: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
