# Custom libraries
from schemas.attachment_schema import AttachmentPreviewResponse

# Default libraries
from datetime import datetime
from typing import Optional, Any, Dict, List, Literal
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict

AgentTaskStatusType = Literal["SUCCESSFUL", "INCOMPLETE", "ARCHIVED", "RESOLVED"]


class Progress(BaseModel):
    status: str
    timestamp: str


class AgentTaskTag(BaseModel):
    id: UUID
    name: str
    color: Optional[str] = None


class AgentTaskBase(BaseModel):
    thread_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    tag_ids: Optional[List[str]] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    task_order: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None
    progress: Optional[List[Progress]] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    credits_used: Optional[int] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class AgentTaskDetail(AgentTaskBase):
    id: UUID
    email_data_id: Optional[UUID] = None
    agent_id: Optional[UUID] = None
    agent_task_tags: Optional[List[AgentTaskTag]] = None
    agent_name: Optional[str] = None
    agent_icon: Optional[str] = None
    attachment_details: Optional[AttachmentPreviewResponse] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AgentTaskResponse(BaseModel):
    agent_tasks: List[AgentTaskDetail]
    agent_task_counts: Dict
    total: int


class AgentTaskExport(BaseModel):
    email_ids: Optional[List[UUID]] = None


class AgentTaskExportResponse(BaseModel):
    mime_type: str
    file_name: str
    content: str


class AgentTaskRetry(BaseModel):
    agent_uuid: Optional[UUID] = None
    instructions: Optional[str] = None


class AgentTaskStatusUpdate(BaseModel):
    agent_task_ids: List[UUID]
    status: AgentTaskStatusType
    note: Optional[str] = None


class AgentTaskTagsUpdate(BaseModel):
    tag_ids: Optional[List[UUID]] = []


class AgentTaskContinue(BaseModel):
    message: str


class AgentTaskResume(BaseModel):
    action: Literal["approve", "reject", "edit", "respond"]
    feedback: Optional[str] = None
    edited_params: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
