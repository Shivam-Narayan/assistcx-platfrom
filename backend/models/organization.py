# Custom libraries
from db_pool import Base

# Default libraries
import uuid
from datetime import datetime
from typing import Optional

# Installed libraries
from sqlalchemy import String, DateTime, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    tenant_code: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    address: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    contact_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    db_schema: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


"""
Comments:
=========
Removed columns:
- city
- state
- postal_code
- country

Added columns:
- db_schema

Modified columns:
- address
- contact_info
"""

"""
Combine all of address to a new column called address which will be a JSONB object.
Combine all of phone_number, email, website, industry to a new column called contact_info which will be a JSONB object.
"""
