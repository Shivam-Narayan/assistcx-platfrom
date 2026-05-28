# Custom libraries
from db_pool import Base

# Default libraries
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional

# Installed libraries
import uuid


class Connection(Base):
    __tablename__ = "connections"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )

    # Foreign Keys
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Connection Identity
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    provider_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Validated against ALL_INTEGRATIONS registry at runtime",
    )

    auth_schema_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="References AUTH_SCHEMAS registry (e.g., 'msft.oauth2.app_only')",
    )

    # Credentials (Fernet encrypted)
    encrypted_credentials: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Fernet-encrypted user inputs: client_id, client_secret, api_keys, etc.",
    )

    encrypted_token: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Fernet-encrypted OAuth tokens: access_token, refresh_token, expires_at",
    )

    # Non-Sensitive Config
    connection_config: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Provider-specific non-sensitive config: region, tenant_id, instance_url",
    )

    connection_metadata: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Operational context: validation_attempts, error_details, reauth_history",
    )

    # Status & Health
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        index=True,
        comment="User-controlled enable/disable toggle",
    )

    auth_status: Mapped[str] = mapped_column(
        String(32),
        default="valid",
        index=True,
        comment="System-managed: valid, expired, invalid, reauth_required",
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Soft delete timestamp for audit trail",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last TaskSource poll or ToolBinding invocation",
    )

    last_validated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful authentication check",
    )

    # Relationships
    created_by_user: Mapped[Optional["User"]] = relationship(  # type: ignore
        "User", foreign_keys=[created_by]
    )

    task_sources: Mapped[list["TaskSource"]] = relationship(  # type: ignore
        "TaskSource", back_populates="connection", cascade="all, delete-orphan"
    )

    tool_bindings: Mapped[list["ToolBinding"]] = relationship(  # type: ignore
        "ToolBinding", back_populates="connection", cascade="all, delete-orphan"
    )
