"""
Agent Builder Package - Utility for generating agent configurations from business use cases.

This package provides tools to automatically generate comprehensive agent configurations
based on business use case descriptions and available tool lists.

Main Components:
- AgentBuilderService: Core service for generating agent configurations
- AgentBuilderInput: Input schema for business use case and tools
- GeneratedAgentConfig: Output schema for complete agent configuration
- ToolInfo: Schema for individual tool information

Usage:
    from builders.agent_builder import AgentBuilderService, AgentBuilderInput, ToolInfo
    
    # Create input
    input_data = AgentBuilderInput(
        business_usecase="Your business use case description...",
        tools=[ToolInfo(icon="...", name="...", action="...", description="...")]
    )
    
    # Generate configuration
    service = AgentBuilderService("public")
    config = await service.generate_agent_config(input_data)
"""

from .service import AgentBuilderService
from .schemas import AgentBuilderInput, GeneratedAgentConfig
from .prompts import AGENT_BUILDER_PROMPT, SIMPLE_AGENT_BUILDER_PROMPT

__all__ = [
    "AgentBuilderService",
    "AgentBuilderInput", 
    "GeneratedAgentConfig",
    "AGENT_BUILDER_PROMPT",
    "SIMPLE_AGENT_BUILDER_PROMPT"
]

__version__ = "1.0.0"
__author__ = "AssistCX Team"
__description__ = "Agent Builder utility for generating agent configurations from business use cases"