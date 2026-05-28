from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


class UserGroup(Base):
    __tablename__ = "user_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    data_access: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    app_access: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


"""
The UserGroup model represents groups that define common access patterns for users.
Each group has its own data_access and app_access configurations that can be applied
to multiple UserAccess records.

The 'data_access' and 'app_access' fields follow the same structure as defined in
the UserAccess model, allowing groups to define common permission patterns.

Example usage:
- Create a "Sales Team" group with specific agent and dashboard access
- Assign multiple users to this group through UserAccess relationships
- Users inherit the group's access permissions along with their individual permissions
"""
