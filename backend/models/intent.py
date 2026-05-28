# ---------------------------------------------------------------------------
# Intent ORM model — fully commented out (intents table may still exist in DB).
# Restore when re-enabling intent catalog features.
# ---------------------------------------------------------------------------
from sqlalchemy import String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from typing_extensions import deprecated
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


@deprecated(
    "Intent catalog and intent_class-based routing are deprecated; Table is kept until a migration removes it."
)
class Intent(Base):
    __tablename__ = "intents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    intent_class: Mapped[Optional[str]] = mapped_column(
        String, unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
