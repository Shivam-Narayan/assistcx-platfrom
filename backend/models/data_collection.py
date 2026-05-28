from sqlalchemy import String, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


class DataCollection(Base):
    __tablename__ = "data_collections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    index_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_root: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    collection_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    smart_fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    knowledge_topics: Mapped[dict] = mapped_column(JSONB, default=dict)
    owner_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    availability: Mapped[str] = mapped_column(String, default="UNLISTED")
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_collections.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    parent: Mapped[Optional["DataCollection"]] = relationship(  # type: ignore
        "DataCollection", back_populates="subfolders", remote_side=[id]
    )
    subfolders: Mapped[list["DataCollection"]] = relationship(  # type: ignore
        "DataCollection", back_populates="parent"
    )
    files: Mapped[list["DataFile"]] = relationship(  # type: ignore
        "DataFile", back_populates="data_folder"
    )


"""
Comments:
=========
Added columns:
owner_id: string of owner id
availability: string of PUBLISHED, PRIVATE, UNLISTED
index_name: milvus collection name
status: string of "active", "archived", "deleted"
collection_config: jsonb of collection config
"""
