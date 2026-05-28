# Default libraries
from typing import Any, Dict, List, Optional

# Installed libraries
from pydantic import BaseModel, Field, field_validator


class ResearchQueryRequest(BaseModel):
    """Enhanced request model for a Research query with validation."""

    query: str = Field(
        ..., min_length=1, max_length=2000, description="The query to execute"
    )
    chat_id: Optional[str] = Field(
        default=None,
        min_length=5,
        max_length=100,
        description="Chat Thread ID for conversation history",
    )
    collections: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        max_items=10,
        description="Knowledge collections to use (optional), contain id, name, and description",
    )
    file_ids: Optional[List[str]] = Field(
        default=None,
        max_items=10,
        description="List of file IDs from user's private collection to use for Research (mutually exclusive with collections)",
    )
    user_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="User context for the query",
    )
    web_search_enabled: Optional[bool] = Field(
        default=True, description="Whether to enable web search functionality"
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v):
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace only")
        return v.strip()

    @field_validator("file_ids")
    @classmethod
    def validate_file_collections_mutual_exclusive(cls, v, info):
        if v is not None:
            if info.data.get("collections") is not None:
                raise ValueError("Cannot provide both collections and file_ids")
            if info.data.get("web_search_enabled") is True:
                raise ValueError(
                    "Cannot enable web search when using file_ids - file-based search should focus only on selected files"
                )
        return v
