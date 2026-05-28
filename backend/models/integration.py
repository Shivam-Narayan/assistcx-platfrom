from sqlalchemy import ARRAY, String, DateTime, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    key: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tags: Mapped[list] = mapped_column(ARRAY(String), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auth_type: Mapped[str] = mapped_column(String, nullable=False)
    auth_schema: Mapped[str] = mapped_column(String, nullable=False)
    credentials: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    integration_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    service_types: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


"""
Comments:
=========
Added columns:
- is_active: boolean to indicate if the integration is active
- service_types: array of service types (llm, data, tools, etc)
"""
