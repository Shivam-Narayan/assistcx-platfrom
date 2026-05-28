from sqlalchemy import String, DateTime, ForeignKey, Text, ARRAY, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    email_data_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("emails.id"), nullable=True
    )
    external_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    message_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    remote_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    content: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), nullable=True
    )  # Corrected content
    # ocr_content = Column(ARRAY(Text))  # original OCR content
    ocr_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    template_class: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # ai_output = Column(
    #     JSONB
    # )  # Move away from this, but keeping the fields for backward compatibility
    # mapping_data = Column(
    #     JSONB
    # )  # Move away from this, but keeping the fields for backward compatibility
    structured_output: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # Combinted structure of ai_output and mapping_data
    # ocr_corrections = Column(Text)
    attachment_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    email: Mapped[Optional["Email"]] = relationship(  # type: ignore
        "Email", back_populates="attachments"
    )


"""
Comments:
=========
Added columns:
- ocr_content
- structured_output
- ocr_corrections
- size

Removed columns:
- content_id
"""

"""
The 'content' field contains the textual content of an attachment, typically extracted from documents like invoices or reports.

Structure:
- text: A list of strings, each representing a line or block of text from the attachment.

Example:
[
  "Page 1 of 1",
  "Invoice No: INV-2024-001",
  "Date: 25/06/2024",
  "Vendor: ABC Company Ltd."
]

The 'mapping_data' field stores key-value pairs that map specific data points or metadata related to the attachment's content.

Structure:
- key: A string representing a specific data point or metadata field.
- value: The corresponding value for the key, typically a string or number.

Example:
{
  "invoice_number": "INV-2024-001",
  "vendor_name": "ABC Company Ltd."
}

The 'ai_output' field contains AI-generated data related to the attachment, typically resulting from data extraction or analysis processes.

Structure:
- key: A string representing a specific data point or analysis result.
- value: A string containing the extracted data along with its context in double angle brackets.

Example:
{
  "invoice_number": "INV-2024-001<<Invoice No.\nINV-2024-001>>",
  "total_amount": "Total: $1,265.00<<Total: $1,265.00>>"
}

The 'ocr_json' field stores the OCR (Optical Character Recognition) data extracted from the attachment in a structured JSON format.

Structure:
- page_number: A string key representing each page of the document (e.g., "page_1").
- text_blocks: An array of objects, each containing:
  - text: A string with the extracted text.
  - geometry: An array of coordinate pairs representing the bounding box of the text.

Example:
{
  "page_1": [
    {"text": "Invoice No: INV-2024-001", "geometry": [[0, 0], [100, 20]]},
    {"text": "Date: 25/06/2024", "geometry": [[0, 25], [100, 45]]}
  ]
}
"""
