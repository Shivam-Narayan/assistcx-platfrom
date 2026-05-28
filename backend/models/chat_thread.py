from sqlalchemy import String, Boolean, DateTime, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID
from datetime import datetime
from typing import Optional
import uuid
from db_pool import Base


class ChatHistory(Base):
    """Model representing a chat thread/conversation."""

    __tablename__ = "chat_histories"
    # constraints and indexes
    __table_args__ = (Index("idx_chat_history_id_created_at", "id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    external_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    chat_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    chat_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    messages: Mapped[list["ChatMessage"]] = relationship(  # type: ignore
        "ChatMessage", back_populates="chat_history", cascade="all, delete-orphan"
    )
