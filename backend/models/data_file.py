from sqlalchemy import (
    String,
    DateTime,
    ForeignKey,
    Boolean,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid
import enum


class SourceType(enum.Enum):
    LOCAL = "local"
    SHAREPOINT = "sharepoint"
    ONE_DRIVE = "one_drive"
    GOOGLE_DRIVE = "google_drive"


class DataFile(Base):
    __tablename__ = "data_files"
    __table_args__ = (
        UniqueConstraint("collection_id", "name", name="uq_collection_file"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_collections.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)  # Size in bytes
    mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    md5_hash: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # For integrity checks
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )  # Metadata from the source
    file_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )  # File metadata
    acl_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )  # Metadata from the ACL
    last_synced: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    data_folder: Mapped["DataCollection"] = relationship(  # type: ignore
        "DataCollection", back_populates="files"
    )


"""
Comments:
=========
Added columns:
- acl_metadata(JSONB): Metadata from the source ACL
- status(JSONB): Status of the file

Removed columns:
- is_indexed(Boolean): Whether the file has been indexed
- indexed_at(DateTime): Date and time when the file was indexed

modified columns:
- external_metadata -> file_metadata
- source -> source_type

"""


"""
file_metadata(JSONB)
------------------
file_metadata is a JSONB column that will store the keys and values to identify the file in the external source.
The set of keys and values will be different for each source.

Example:
local:
file_metadata = {
    "file_path": "/path/to/file.pdf"
}

sharepoint:
file_metadata = {
    "site_id": "site123",
    "file_id": "file456",
}
"""


"""
acl_metadata(JSONB)
------------------

"""
