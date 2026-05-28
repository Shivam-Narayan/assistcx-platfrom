"""
Pydantic schemas for Agent Builder utility.
Defines input and output models for agent configuration generation.
"""

from typing import List, Dict, Any, Literal, Optional
from pydantic import BaseModel, Field


class AgentBuilderInput(BaseModel):
    """Input for agent builder generation."""

    name: str = Field(description="Name of the agent to be created", min_length=4)
    business_usecase: str = Field(
        description="Business use case description explaining what the agent should accomplish"
    )
    tools: List[Dict[str, str]] = Field(
        description="List of available tools with name, action, and description"
    )
    previous_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Previous agent configuration to reference or improve upon",
    )
    user_instructions: Optional[str] = Field(
        default="",
        description="Additional instructions or constraints from the user",
    )

    # this class method is for POC only. In production pydantic to dict should be handeled at API layer.
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentBuilderInput":
        """Create AgentBuilderInput from dictionary for API usage."""
        return cls(**data)


class GeneratedAgentConfig(BaseModel):
    """Generated agent configuration"""

    description: str = Field(description="Agent purpose and capabilities")
    style: Literal[
        "formal", "informal", "friendly", "empathetic", "creative", "analytical"
    ] = Field(description="Communication style")
    goal: str = Field(description="Agent goal statement")
    instructions: str = Field(description="Step-by-step execution instructions")
    rules: List[str] = Field(description="Operational rules and constraints")
    tools: Optional[List[Dict[str, str]]] = Field(
        default = None,
        description="List of tools with name, action, and description that the agent will need"
    )
    success_criteria: str = Field(description="Success criteria")
    plan: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Optional execution plan with sequential steps (only for tool count > 2)",
    )
    response_schema: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Optional response schema defining expected output structure",
    )
