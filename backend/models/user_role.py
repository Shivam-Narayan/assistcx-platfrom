from sqlalchemy import DateTime, String, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    role_key: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    default_role: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    role_permissions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user_access: Mapped[list["UserAccess"]] = relationship(  # type: ignore
        "UserAccess", back_populates="user_role", cascade="all, delete, delete-orphan"
    )


"""
The 'role_permissions' data contains an array of dictionaries, 
each representing a permission configuration for a specific module and feature within the system.

Each role permission has the following keys:
- 'module': A string indicating the module name (e.g., 'agents_and_tools', 'dashboards').
- 'feature': A string specifying the particular feature within the module that the permission relates to (e.g., 'view_agents', 'view_dashboards').
- 'enabled': A boolean value indicating whether the permission is granted (True) or denied (False).

Example:
role_permissions = [
    {
        'module': 'agents_and_tools',
        'feature': 'view_agents',
        'enabled': True
    },
    {
        'module': 'dashboards',
        'feature': 'view_dashboards',
        'enabled': True
    },
    # More permissions here
]
"""
