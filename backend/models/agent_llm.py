from sqlalchemy import String, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


class AgentLLM(Base):
    __tablename__ = "agent_llms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    llm_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


"""
data(JSONB)
-----------
The data column stores all LLM configuration as JSON.

Example:
data = {
    "name": "OpenAI GPT-4.1",
    "description": "OpenAI GPT-4.1 is an advanced large language model.",
    "model_name": "gpt-4.1",
    "provider": "openai",
    "integration_key": "openai",
    "llm_config": {
        "temperature": 0.7,
    "system_prompt": true,
    "tool_calling": true,
        "multi_modal": true
    }
}
"""
