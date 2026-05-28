from sqlalchemy import String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


class DataTemplate(Base):
    __tablename__ = "data_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    template_class: Mapped[Optional[str]] = mapped_column(
        String, unique=True, nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    document_instructions: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    data_schema: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


"""
The 'data_schema' defines the name and description of various fields required for a data template.


Each entry in the 'data_schema' array is a dictionary containing the following keys:
- 'name': A string representing the field name (e.g., 'document_type', 'shipper').
- 'description': A string providing an explanation of the field, including any extra details when needed.

Example:
data_schema = [
    {
        'name': 'document_type',
        'description': 'Type of document, typically found on top',
    },
    {
        'name': 'shipper',
        'description': 'Shipper name found in the data',
    },
    # More field descriptions here
]
"""
