# Default libraries
from typing_extensions import deprecated

# Installed libraries
from pydantic import BaseModel, Field


# @deprecated("Use AgentSelectionResponse instead")
# class IntentClassificationResponse(BaseModel):
#     """Schema for the response from the input classification LLM."""
#
#     intent_class: str = Field(
#         description="The most accurate intent class relevent to this email and attachment data."
#     )


class AgentSelectionResponse(BaseModel):
    """Schema for the response from the agent selection LLM."""

    agent_name: str = Field(
        description="The exact name of the most suitable agent for this email and attachment data."
    )
