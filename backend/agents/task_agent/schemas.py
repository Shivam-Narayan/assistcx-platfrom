"""This file contains the graph schema for the application."""

from datetime import datetime, timezone
from operator import add
from typing import Annotated, List, Literal, Optional, Any, Dict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field, model_validator


# Defining valid human actions for HITL
HITL_ACTION = Literal["approve", "reject", "edit"]


# Modeling human input for tool call review
class HumanInput(BaseModel):
    """Represents the human's response to a tool call review request."""

    action: HITL_ACTION = Field(
        description="The action taken by the human (approve, reject, edit)."
    )
    feedback: Optional[str] = Field(
        default=None,
        description="Feedback provided by the human, used for reject action.",
    )
    edited_params: Optional[Dict[str, Any]] = Field(
        default=None, description="Edited tool call parameters, if action is edit."
    )
    user_id: Optional[str] = Field(
        default=None,
        description="ID of the user who performed this review action.",
    )

    @model_validator(mode="after")
    def validate_action_fields(self) -> "HumanInput":
        if self.action == "edit" and not self.edited_params:
            raise ValueError("edited_params is required when action is 'edit'")
        return self


# Human Review Record for audit trail
class HumanReviewRecord(BaseModel):
    """A single entry in the human review history, capturing the human input and tool call context."""

    tool_name: str = Field(description="The name of the tool that was reviewed.")
    tool_call_id: str = Field(
        description="The unique ID of the tool call for reference in message history."
    )
    action_taken: HITL_ACTION = Field(
        description="The action taken by the human (approve, reject, edit)."
    )
    question: Optional[str] = Field(
        default=None,
        description="The LLM-generated question shown to the reviewer when this record was created.",
    )
    feedback: Optional[str] = Field(
        default=None, description="Feedback provided by the human."
    )
    original_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Original tool call parameters before edit (only populated for edit action).",
    )
    edited_params: Optional[Dict[str, Any]] = Field(
        default=None, description="Edited tool call parameters, if action is edit."
    )
    user_id: Optional[str] = Field(
        default=None,
        description="ID of the user who performed this review action.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO format UTC timestamp when the human review was recorded.",
    )


# --- Graph State Schema ---
class GraphState(BaseModel):
    """State definition for the LangGraph Agent/Workflow."""

    messages: Annotated[list, add_messages] = Field(
        default_factory=list, description="The messages in the task execution thread"
    )
    # Task and agent identifiers
    task_id: Optional[str] = Field(
        default=None, description="The unique identifier for the task being executed"
    )
    agent_id: Optional[str] = Field(
        default=None,
        description="The unique identifier for the agent executing the task",
    )
    # Stores the structured output from the agent
    structured_output: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured output from the agent after processing the task",
    )
    # Human review audit trail (accumulates via add reducer, same pattern as token_usage)
    review_history: Annotated[List[HumanReviewRecord], add] = Field(
        default_factory=list,
        description="History of human reviews for the current task.",
    )
    # Token consumption tracking (accumulates across multiple LLM calls)
    token_usage: Annotated[List[Dict[str, Any]], add] = Field(
        default_factory=list,
        description="List of token usage records for each LLM call in this task execution. Each record contains node name, tool call, input/output tokens, and timestamp.",
    )
