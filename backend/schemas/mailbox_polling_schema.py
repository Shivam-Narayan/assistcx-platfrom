# Default libraries
from datetime import datetime
from typing import Optional, List
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
)


class DataStore(BaseModel):
    storage_type: Annotated[str, StringConstraints(strip_whitespace=True)]
    storage_bucket: Annotated[str, StringConstraints(strip_whitespace=True)]
    storage_folder: Optional[
        Annotated[str, StringConstraints(strip_whitespace=True)]
    ] = "files"
    storage_region: Optional[
        Annotated[str, StringConstraints(strip_whitespace=True)]
    ] = ""


class PollingConfig(BaseModel):
    data_parsing: Optional[bool] = False
    ocr_parser: Optional[bool] = True
    pdf_parsing: Optional[str] = "local"
    max_pdf_pages: Optional[int] = 50
    ocr_page_limit: Optional[int] = None
    split_pdf_pages: Optional[bool] = False
    fix_page_rotation: Optional[bool] = False
    preserve_page_layout: Optional[bool] = False
    # vision_correction: Optional[bool] = False
    copy_email_data: Optional[bool] = False
    send_notifications: Optional[bool] = False
    notification_recipients: Optional[List] = []
    mailbox_priority: int = Field(
        default=0,
        ge=0,
        le=9,
        description="Task priority: 0=highest priority (default), 9=lowest priority. Lower numbers are processed first.",
    )

    @field_validator("notification_recipients", mode="before")
    def lowercase_notification_recipients(cls, v: Optional[List]) -> Optional[List]:
        if v:
            return [
                recipient.strip().lower() if isinstance(recipient, str) else recipient
                for recipient in v
                if recipient
            ]
        return v


class MailboxPollingBase(BaseModel):
    email_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6)]  # type: ignore
    folder: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    frequency: Optional[float] = None
    description: Optional[str] = None
    data_store: Optional[DataStore] = None
    polling_config: Optional[PollingConfig] = None
    status: Optional[str] = None

    @field_validator("email_id", mode="before")
    def lowercase_email_id(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return v.strip().lower()
        return v


class MailboxPollingCreate(MailboxPollingBase):
    data_store: DataStore
    polling_config: Optional[PollingConfig] = PollingConfig()
    status: Optional[str] = "CREATED"


class MailboxPollingUpdate(MailboxPollingBase):
    email_id: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=6)]] = None  # type: ignore
    folder: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore

    @field_serializer("email_id", "folder")
    def remove_email_id_and_folder(self, value):
        return None


class MailboxPollingDetail(MailboxPollingBase):
    id: UUID
    task_name: Optional[str] = None
    delta_link: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class MailboxPollingResponse(BaseModel):
    mailbox_pollings: List[MailboxPollingDetail]
    total: int
