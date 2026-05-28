# Installed libraries
from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional
import uuid
from db_pool import Base


class Configuration(Base):
    __tablename__ = "configurations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    preferences: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    auth_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


"""
Comments:
=========
Removed columns:
- environment
"""
"""

The `environment` column contains a JSONB dictionary with API keys and their corresponding values. This dictionary is used to store and manage environment-specific configuration settings.

Structure:
- API Key Name: A string representing the name or identifier of the API key.
- API Key Value: A string representing the actual value of the API key.

Example:
{
  "google_api_key": "AIzaSyA-ExampleKey1234567890",
  "aws_secret_key": "AKIAExampleSecretKey1234567890",
  "database_password": "my_secure_password"
}

### STALE ###
The 'preferences' configuration defines various preferences for handling tasks and processing documents within the system.

The 'preferences' dictionary contains the following keys:
- 'routing_task': A string indicating the criteria for routing tasks, such as 'based_on_intent'.
- 'pdf_parsing': A string specifying the method for parsing PDF documents, e.g., 'local' or other methods.
- 'max_pdf_pages': An integer representing the limit of maximum pages, after which the PDF document will be strip.
- 'split_pdf_pages': A boolean indicating whether to split PDF documents (True) or not (False).

Example:
preferences = {
    'routing_task': 'based_on_intent',
    'pdf_parsing': 'local',
    'max_pdf_pages': 10,
    'split_pdf_pages': True
}
"""
