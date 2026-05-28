from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


class IssueComment(Base):
    __tablename__ = "issue_comments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    comment_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    issue: Mapped["Issue"] = relationship(  # type: ignore
        "Issue", back_populates="comments"
    )


"""
The 'comment_metadata' is an optional JSONB field for storing additional data.

Possible uses:
- attachments: List of attachment references
- mentions: List of mentioned user_ids
- edited: Boolean flag if comment was edited

Example:
comment_metadata = {
    "attachments": [
        {"id": "att_123", "name": "screenshot.png", "type": "image/png"}
    ],
    "mentions": ["usr_abc123", "usr_xyz789"],
    "edited": true
}
"""
