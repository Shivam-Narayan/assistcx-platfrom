from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


class UserAccess(Base):
    __tablename__ = "user_access"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    role_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_roles.id"), nullable=True
    )
    data_access: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    app_access: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    user_group_ids: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(  # type: ignore
        "User", back_populates="user_access"
    )
    user_role: Mapped[Optional["UserRole"]] = relationship(  # type: ignore
        "UserRole", back_populates="user_access"
    )


"""
The 'data_access' configuration defines dynamic user access control for various system modules.

The 'data_access' dictionary is structured as follows:
- Each key represents a permission key (e.g., 'view_agents', 'view_task_inbox').
- The corresponding value is a dictionary defining the data filters for that permission.
    - The keys within this dictionary represent the data filter columns (e.g., 'name', 'mailbox_email').
    - The values are a list of strings representing the associated data filter values for the column.

Example:
data_access = {
    "view_agents": {
        "name": [
            "Invoice Data Agent"
        ]
    },
    "view_task_inbox": {
        "mailbox_email": [
            "assist@aexonic.com"
        ]
    }
}
"""
