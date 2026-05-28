"""Schemas for live agent execution in assistant chat."""

from operator import add
from typing import Annotated, Any, Dict, List, Literal, Optional

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field, model_validator


class LiveAgentState(BaseModel):
    """Minimal state for live agent execution in assistant chat.

    Only contains fields relevant to conversational agent execution:
    - messages: Core conversation history (auto-appends via add_messages)
    - agent_id: Tracks which agent is executing
    - token_usage: Accumulates token metrics across LLM calls (auto-appends via add)
    """

    messages: Annotated[list, add_messages] = Field(
        default_factory=list, description="The messages in the conversation"
    )
    agent_id: Optional[str] = Field(
        default=None, description="The agent executing this conversation"
    )
    token_usage: Annotated[List[Dict[str, Any]], add] = Field(
        default_factory=list,
        description="Token usage records accumulated across LLM calls",
    )


class GenerateFinalAnswer(BaseModel):
    """Provide the final answer to the user's question.

    Use this when you have all the information needed to respond.
    """

    answer: str = Field(
        description="The complete answer to provide to the user in markdown format."
    )


class HumanReviewInput(BaseModel):
    """Request body for POST /assistant/stream/resume.

    Two actions:
    - approve: Execute the tool call as proposed
    - reject: Skip the tool call, optionally provide feedback to guide the agent
    """

    chat_id: str = Field(
        ..., min_length=5, description="Chat thread ID"
    )
    agent_id: str = Field(
        ..., description="Agent UUID"
    )
    graph_thread_id: str = Field(
        ...,
        min_length=10,
        description="LangGraph thread_id returned in the review_required event",
    )
    action: Literal["approve", "reject"] = Field(
        ..., description="Human review action"
    )
    feedback: Optional[str] = Field(
        default=None,
        description="Feedback when rejecting — guides the agent to adjust its approach",
    )
