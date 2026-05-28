# Installed libraries
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional
import uuid
from db_pool import Base


class Authentication(Base):
    __tablename__ = "authentications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    user_uuid: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True
    )
    access_token: Mapped[Optional[str]] = mapped_column(
        String, index=True, nullable=True
    )
    refresh_token: Mapped[Optional[str]] = mapped_column(
        String, index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship with User model
    user: Mapped[Optional["User"]] = relationship(  # type: ignore
        "User", back_populates="authentications"
    )
