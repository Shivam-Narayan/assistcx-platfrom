# Custom libraries
from db_pool import Base

# Default libraries
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime

# Installed libraries
import uuid


class ToolBinding(Base):
    __tablename__ = "tool_bindings"
    __table_args__ = (
        UniqueConstraint("agent_id", "tool_key", name="uq_agent_tool_key"),
    )

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )

    # Foreign Keys
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Tool Identity
    provider_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Denormalized from connection for efficient queries",
    )

    tool_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="References TOOLS registry (e.g., 'outlook.send_email')",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent: Mapped["Agent"] = relationship(  # type: ignore
        "Agent", back_populates="tool_bindings"
    )

    connection: Mapped["Connection"] = relationship(  # type: ignore
        "Connection", back_populates="tool_bindings"
    )
