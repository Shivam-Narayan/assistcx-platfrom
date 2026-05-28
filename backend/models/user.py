# Installed libraries
from sqlalchemy import String, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional
import uuid
from db_pool import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    email: Mapped[Optional[str]] = mapped_column(
        String, unique=True, index=True, nullable=True
    )
    first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        String, unique=True, index=True, nullable=True
    )
    hashed_password: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    salt: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    account_status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    user_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # ADD

    # Relationship with Authentication model
    authentications: Mapped[list["Authentication"]] = relationship(  # type: ignore
        "Authentication", back_populates="user", cascade="all, delete, delete-orphan"
    )
    user_access: Mapped[list["UserAccess"]] = relationship(  # type: ignore
        "UserAccess", back_populates="user", cascade="all, delete, delete-orphan"
    )
