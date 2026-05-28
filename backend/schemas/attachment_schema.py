# Default libraries
from datetime import datetime
from typing import Optional, Union, Dict, List, Any
from uuid import UUID
import json

# Installed libraries
from pydantic import BaseModel, ConfigDict, field_serializer, field_validator


class AttachmentBase(BaseModel):
    external_id: Optional[str] = None
    message_id: Optional[str] = None
    conversation_id: Optional[str] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    size: Optional[int] = None
    remote_url: Optional[str] = None


class AttachmentPreview(AttachmentBase):
    id: UUID
    email_data_id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class AttachmentPreviewResponse(BaseModel):
    attachments: List[AttachmentPreview]
    total: int


class AttachmentView(AttachmentBase):
    id: UUID
    email_data_id: UUID
    content: Optional[List[str]] = None
    # ocr_content: Optional[List[str]] = None
    template_class: Optional[str] = None
    # ai_output: Optional[Union[str, List[Dict]]] = None
    additional_data: Optional[Dict[str, Any]] = None
    attachment_metadata: Optional[Dict[str, Any]] = None
    structured_output: Optional[Union[str, List[Dict]]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    @field_validator("structured_output", mode="before")
    @classmethod
    def parse_json(cls, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON string")
        return value


class AttachmentDetail(AttachmentBase):
    id: UUID
    email_data_id: UUID
    content: Optional[List[str]] = None
    # ocr_content: Optional[List[str]] = None
    # ocr_json: Optional[List[dict]] = None
    template_class: Optional[str] = None
    # ai_output: Optional[Union[str, List[Dict]]] = None
    # mapping_data: Optional[Union[str, List[Dict]]] = None
    structured_output: Optional[Union[str, List[Dict]]] = None
    additional_data: Optional[Dict[str, Any]] = None
    attachment_metadata: Optional[Dict[str, Any]] = None
    # ocr_corrections: Optional[str] = None
    document_pages: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    @field_validator("structured_output", mode="before")
    @classmethod
    def parse_json(cls, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON string")
        return value


class AttachmentDetail(AttachmentBase):
    id: UUID
    email_data_id: UUID
    content: Optional[List[str]] = None
    # ocr_content: Optional[List[str]] = None
    # ocr_json: Optional[List[dict]] = None
    template_class: Optional[str] = None
    # ai_output: Optional[Union[str, List[Dict]]] = None
    # mapping_data: Optional[Union[str, List[Dict]]] = None
    structured_output: Optional[Union[str, List[Dict]]] = None
    attachment_metadata: Optional[Dict[str, Any]] = None
    # ocr_corrections: Optional[str] = None
    document_pages: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    @field_validator("structured_output", mode="before")
    @classmethod
    def parse_json(cls, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON string")
        return value


class AttachmentResponse(BaseModel):
    attachments: List[AttachmentDetail]
    total: int


class AttachmentURL(BaseModel):
    attachment_url: Optional[str] = None


class AttachmentDownload(BaseModel):
    mime_type: str
    file_name: str
    content: str


class AttachmentReprocess(BaseModel):
    instructions: Optional[str] = None
