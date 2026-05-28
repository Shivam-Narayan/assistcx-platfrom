# Custom libraries
from schemas.attachment_schema import AttachmentPreviewResponse

# Default libraries
from datetime import datetime
from typing import Optional, Dict, List
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, field_validator


class EmailTag(BaseModel):
    id: UUID
    name: str
    color: Optional[str] = None


class EmailBase(BaseModel):
    email_id: Optional[str] = None
    message_id: Optional[str] = None
    conversation_id: Optional[str] = None
    tag_ids: Optional[List[str]] = None
    mailbox_email: Optional[str] = None
    mailbox_folder: Optional[str] = None
    sender_name: Optional[str] = None
    web_link: Optional[str] = None
    subject: Optional[str] = None
    email_body: Optional[str] = None
    data_template: Optional[str] = None
    records: Optional[List[Dict]] = None
    additional_data: Optional[Dict] = None
    # events: Optional[List[Dict]] = None
    source_type: Optional[str] = "Mailbox"
    status: Optional[str] = "QUEUED"
    notes: Optional[str] = None
    credits_used: Optional[int] = None
    received_at: Optional[datetime] = None

    @field_validator("email_id", "mailbox_email", mode="before")
    def lowercase_email_id(cls, v: str) -> str:
        if v:
            return v.strip().lower()
        return v


class EmailDetail(EmailBase):
    id: UUID
    agent_id: Optional[UUID] = None
    email_tags: Optional[List[EmailTag]] = None
    agent_task_counts: Optional[Dict] = None
    attachment_details: Optional[AttachmentPreviewResponse] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class EmailResponse(BaseModel):
    emails: List[EmailDetail]
    total: int


class EmailMailboxFilters(BaseModel):
    mailbox_emails: List[str]
    agents: List[str]


class EmailRetryTask(BaseModel):
    note: Optional[str] = None


class EmailExport(BaseModel):
    email_ids: Optional[List[UUID]] = None


class EmailExportResponse(BaseModel):
    mime_type: str
    file_name: str
    content: str


class EmailArchive(BaseModel):
    email_ids: List[UUID]


class EmailTagsUpdate(BaseModel):
    tag_ids: Optional[List[UUID]] = []


class EmailDelete(BaseModel):
    email_ids: List[UUID]
