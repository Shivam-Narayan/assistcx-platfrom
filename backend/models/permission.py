from sqlalchemy import DateTime, String, Integer, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    key: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    module: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    data_filters: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    access_levels: Mapped[Optional[list]] = mapped_column(
        ARRAY(String), nullable=True
    )
    web_routes: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    display_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Deprecated: kept for migration compatibility
    endpoints: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
