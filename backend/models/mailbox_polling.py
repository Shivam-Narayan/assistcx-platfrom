from sqlalchemy import String, DateTime, Text, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


class MailboxPolling(Base):
    __tablename__ = "mailbox_polling"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    email_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    folder: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    task_name: Mapped[Optional[str]] = mapped_column(
        String, unique=True, index=True, nullable=True
    )
    frequency: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delta_link: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_store: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    polling_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String, default="CREATED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


"""
The 'data_store' configuration defines the storage settings for data storage with mailbox pollings.

The 'data_store' dictionary contains the following keys:
- 'storage_type': A string indicating the type of storage used (e.g., 'remote' or 'local').
- 'storage_bucket': A string specifying the name of the storage bucket where data is stored.
- 'storage_folder': A string representing the folder or directory within the bucket where data files are organized.
- 'storage_region': A string denoting the region where the storage is located.

Example:
data_store = {
    "storage_type": "remote",
    "storage_bucket": "assistcx-data",
    "storage_folder": "files",
    "storage_region": "ap-south-1"
}

---------------------------------------------------------------------------------------------------------

The 'polling_config' configuration defines the polling settings for mailbox pollings.

The 'polling_config' dictionary contains the following keys:
- 'pdf_parsing': A string specifying the method for parsing PDF documents ('local' or 'remote').
- 'max_pdf_pages': An integer representing the limit of maximum pages, after which the PDF document will be strip.
- 'split_pdf_pages': A boolean indicating whether to split PDF documents (True) or not (False).
- 'copy_email_data': A boolean value indicating whether the email data is to be copied (True) or not (False).

Example:

polling_config = {
    "pdf_parsing": "local",
    "max_pdf_pages": 20,
    "split_pdf_pages": false,
    "copy_email_data": false
}
"""
