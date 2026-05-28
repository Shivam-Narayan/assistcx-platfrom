# Default libraries
from typing import Optional, Dict, List
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, StringConstraints, field_validator


class DataStore(BaseModel):
    storage_type: Annotated[str, StringConstraints(strip_whitespace=True)]
    storage_bucket: Annotated[str, StringConstraints(strip_whitespace=True)]
    storage_folder: Optional[
        Annotated[str, StringConstraints(strip_whitespace=True)]
    ] = "files"
    storage_region: Optional[
        Annotated[str, StringConstraints(strip_whitespace=True)]
    ] = ""


class TaskConfigs(BaseModel):
    data_parsing: Optional[bool] = True
    ocr_parser: Optional[bool] = True
    pdf_parsing: Optional[str] = "local"
    max_pdf_pages: Optional[int] = 50
    ocr_page_limit: Optional[int] = None
    split_pdf_pages: Optional[bool] = False
    fix_page_rotation: Optional[bool] = False
    preserve_page_layout: Optional[bool] = True
    # vision_correction: Optional[bool] = True
    copy_email_data: bool = False
    send_notifications: Optional[bool] = False
    notification_recipients: Optional[List] = []

    @field_validator("notification_recipients", mode="before")
    def lowercase_notification_recipients(
        cls, v: Optional[List[str]]
    ) -> Optional[List[str]]:
        if v:
            return [recipient.strip().lower() for recipient in v if recipient]
        return v


class ExternalTaskCreate(BaseModel):
    sender_email_id: str = None
    receiver_email: Optional[str] = None  # type: ignore
    receiver_folder: str = "inbox"
    task_title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    task_body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6)]  # type: ignore
    agent_id: UUID
    task_records: Optional[List[Dict]] = None
    data_store: Optional[DataStore] = None
    task_configs: Optional[TaskConfigs] = TaskConfigs()
