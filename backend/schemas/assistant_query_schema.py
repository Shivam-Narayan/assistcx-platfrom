# Default libraries
from typing import Any, Dict, List, Literal, Optional

# Installed libraries
from pydantic import BaseModel, Field, field_validator, model_validator


class AssistantQueryRequest(BaseModel):
    """Enhanced request model for a Assistant query with validation."""

    query: str = Field(
        ..., min_length=1, max_length=2000, description="The query to execute"
    )
    chat_id: Optional[str] = Field(
        default=None,
        min_length=5,
        max_length=100,
        description="Chat Thread ID for conversation history",
    )
    mode: Literal["research", "agent"] = Field(
        default="research",
        description="Execution mode: 'research' for deep research, 'agent' for custom agent",
    )
    collections: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        max_items=10,
        description="Knowledge collections to use (optional), contain id, name, and description",
    )
    attachments: Optional[List[Dict[str, str]]] = Field(
        default=None,
        max_items=50,
        description="List of file attachments (each with 'id' and 'name') from user's private collection (mutually exclusive with collections)",
    )
    user_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="User context for the query",
    )
    timeout: Optional[int] = Field(
        default=120, ge=10, le=300, description="Query timeout in seconds"
    )
    web_search_enabled: Optional[bool] = Field(
        default=True, description="Whether to enable web search functionality"
    )
    agent_id: Optional[str] = Field(
        default=None,
        description="Agent UUID — required when mode='agent'.",
    )

    @model_validator(mode="after")
    def validate_agent_mode(self):
        if self.mode == "agent" and not self.agent_id:
            raise ValueError("agent_id is required when mode='agent'")
        return self

    @field_validator("query")
    @classmethod
    def validate_query(cls, v):
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace only")
        return v.strip()

    @field_validator("attachments")
    @classmethod
    def validate_attachments_mutual_exclusive(cls, v, info):
        if v is not None:
            if info.data.get("collections") is not None:
                raise ValueError("Cannot provide both collections and attachments")
            if info.data.get("web_search_enabled") is True:
                raise ValueError(
                    "Cannot enable web search when using attachments - file-based search should focus only on selected files"
                )
        return v


class AssistantQueryResponse(BaseModel):
    """Enhanced response model returned from the Assistant agent."""

    chat_id: str = Field(description="The unique identifier for the chat.")
    thread_id: str = Field(description="The unique identifier for the execution.")
    question: str = Field(description="The original question asked by the user.")
    answer: str = Field(description="The generated answer to the user's question.")

    # Core response data
    sources: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Sources referenced in the answer.",
        max_items=50,
    )
    citations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Citations for information sources used in the answer.",
        max_items=50,
    )
    suggested_queries: List[str] = Field(
        default_factory=list,
        description="Suggested queries for follow up questions.",
        max_items=10,
    )

    # Execution metadata
    execution_time: float = Field(
        description="Total execution time in seconds.", ge=0.0
    )

    # Plan and tasks
    plan: Optional[Dict[str, Any]] = Field(
        default=None, description="The execution plan for this query."
    )
    tasks: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Tasks executed to generate the answer.", max_items=20
    )

    # Status information
    status: str = Field(
        default="completed", description="Status of the query execution"
    )
    timestamp: Optional[str] = Field(
        default=None, description="Timestamp when the response was generated"
    )
