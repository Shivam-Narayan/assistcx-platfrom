"""
Agent Builder Service - Main implementation for generating agent configurations.
Orchestrates the generation of complete agent configurations from business use cases and tools.
"""

import asyncio
import json
from typing import Dict, Any, List
from datetime import datetime
from jinja2 import Template

from logger import configure_logging
from agents.shared_utils.llm_provider import LLMProvider
from sqlalchemy.orm import Session

from .schemas import AgentBuilderInput, GeneratedAgentConfig
from .prompts import AGENT_BUILDER_PROMPT

logger = configure_logging(__name__)


class AgentBuilderService:
    """
    Service for generating complete agent configurations from business use cases and tools.

    Uses LLM with structured output to generate comprehensive agent configurations
    that effectively utilize the provided tools to accomplish business objectives.

    Methods:
    - generate_agent_config(): Returns Pydantic object (for internal use)
    - generate_agent_json(): Returns JSON dictionary (for API use)
    """

    def __init__(self, organization_schema: str, db: Session):
        """
        Initialize the AgentBuilderService.

        Args:
            organization_schema: The organization schema for LLM provider
            db: Database session (required)
        """
        self.organization_schema = organization_schema
        self.llm_provider = LLMProvider(organization_schema, db)
        self.llm = self.llm_provider.get_llm()

        logger.info(
            f"AgentBuilderService initialized for schema: {organization_schema}"
        )

    def _format_tools_for_prompt(self, tools: List[Dict[str, str]]) -> str:
        """Format tools for LLM prompt consumption."""
        if not tools:
            return "No tools available."

        formatted_tools = []
        for i, tool in enumerate(tools, 1):
            tool_section = f"{i}. Tool: {tool['name']}\n   Action: {tool['action']}\n   Description: {tool['description']}"
            formatted_tools.append(tool_section)

        return "\n\n".join(formatted_tools)

    async def generate_agent_config(
        self, input_data: AgentBuilderInput
    ) -> Dict[str, Any]:
        """
        Generate a complete agent configuration from business use case and tools.

        Args:
            input_data: Input containing business use case and tools list

        Returns:
            Complete agent configuration as JSON dictionary

        Raises:
            Exception: If generation fails
        """
        try:
            # 1. Format tools for prompt context
            formatted_tools = self._format_tools_for_prompt(input_data.tools)

            # 2. Calculate tool count for conditional plan generation
            # tool_count = len(input_data.tools)

            # 3. Build generation prompt
            prompt_content = Template(AGENT_BUILDER_PROMPT).render(
                business_usecase=input_data.business_usecase,
                formatted_tools=formatted_tools,
                # tool_count=tool_count,
                previous_config=(
                    json.dumps(input_data.previous_config, indent=2)
                    if input_data.previous_config
                    else "None"
                ),
                user_instructions=input_data.user_instructions or "None",
            )

            # 4. Generate with structured output using function calling method
            llm_with_structure = self.llm.with_structured_output(
                GeneratedAgentConfig, method="function_calling"
            )

            generated_config = await llm_with_structure.ainvoke(
                [{"role": "user", "content": prompt_content}]
            )

            logger.info(f"Generated agent: '{input_data.name}' configuration successfully")

            # 5. Combine generated config with name for JSON output
            result = generated_config.model_dump()
            result["name"] = input_data.name

            tool_count = len(result.get("tools", []))

            # 5. Log plan generation
            if tool_count > 2:
                plan_steps = len(generated_config.plan) if generated_config.plan else 0
                logger.info(f"Generated execution plan with {plan_steps} steps")
            else:
                logger.info("Skipped plan generation (tool count <= 2)")

            # 7. Validate plan based on tool count
            if tool_count > 2 and not result.get("plan"):
                logger.warning(
                    f"Expected plan for {tool_count} tools but none generated"
                )
            elif tool_count <= 2 and result.get("plan"):
                logger.warning(
                    f"Unexpected plan generated for {tool_count} tools, removing it"
                )
                result["plan"] = None  # Ensure no plan for simple agents

            return result

        except Exception as e:
            logger.error(f"Failed to generate agent configuration: {e}", exc_info=True)
            raise Exception(f"Agent configuration generation failed: {str(e)}")


async def main():
    """Test the AgentBuilderService with sample data."""
    business_usecase = """
    I need an agent that can process vendor invoices received via email. The agent should:
    1. Extract invoice data from email attachments (PDF invoices)
    2. Structure the data according to our vendor invoice template
    3. Upload the processed data to our file system for further processing
    4. Handle multiple invoices in a single email
    5. Ensure data quality and provide execution summaries
    
    The agent should be professional, thorough, and handle errors gracefully.
    """

    sample_tools = [
        {
            "name": "Extract Structured Data",
            "action": "extract_structured_data",
            "description": "Extracts structured data using a data template: provide input_text (supplementary text) and/or attachment_id; at least one is required.",
        },
        {
            "name": "Create Structured File in Filesystem",
            "action": "filesystem_create_structured_file",
            "description": "Creates a structured file in JSON or CSV format from structured data (a dictionary or a list of dictionaries) in a local or network filesystem. Requires the data, a file name, and an optional format (json or csv). Defaults to json if no format is provided. The file will be stored at the designated mount path using the specified folder structure. Supports batch operations for multiple records.",
        },
    ]

    input_data = AgentBuilderInput(
        business_usecase=business_usecase, tools=sample_tools
    )
    service = AgentBuilderService("public")
    result = await service.generate_agent_config(input_data)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    """
    Run the test when executed directly.
    Usage: python -m builders.agent_builder.service
    """
    asyncio.run(main())
