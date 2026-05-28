# Custom libraries
from builders.data_schema_builder.schemas import DataSchemaBuilderInput, GeneratedDataSchema
from builders.data_schema_builder.prompts import DATA_SCHEMA_BUILDER_PROMPT
from agents.shared_utils.llm_provider import LLMProvider
from logger import configure_logging

# Database modules
from sqlalchemy.orm import Session

# Default libraries
from jinja2 import Template
from typing import Dict, Any
import json


logger = configure_logging(__name__)


class DataSchemaBuilderService:
    """
    Service for generating the data schema for a data template based on its name and description.
    """

    def __init__(self, organization_schema: str, db: Session):
        self.organization_schema = organization_schema
        self.llm_provider = LLMProvider(organization_schema, db)
        self.llm = self.llm_provider.get_llm()

    async def generate_data_schema(
        self, input_data: DataSchemaBuilderInput
    ) -> Dict[str, Any]:
        """
        Generates the data schema for a data template based on its name and description.

        Args:
            input_data: Input containing the data template name, description, previous schema, and user instructions

        Returns:
            Dict[str, Any]: Dictionary containing name, description, and generated list of data schema fields
        """
        try:
            prompt_content = Template(DATA_SCHEMA_BUILDER_PROMPT).render(
                name=input_data.name,
                description=input_data.description,
                previous_schema=(
                    json.dumps(input_data.previous_schema, indent=2)
                    if input_data.previous_schema
                    else "None"
                ),
                user_instructions=input_data.user_instructions or "None",
            )

            llm_with_structure = self.llm.with_structured_output(
                GeneratedDataSchema, method="function_calling"
            )

            generated_schema = await llm_with_structure.ainvoke(
                [{"role": "user", "content": prompt_content}]
            )

            logger.info(
                f"Generated data schema for data template '{input_data.name}' successfully"
            )

            result = generated_schema.model_dump()
            result["name"] = input_data.name
            result["description"] = input_data.description

            field_count = len(result.get("data_schema", []))
            logger.info(
                f"Generated {field_count} fields for data template '{input_data.name}'"
            )

            return result

        except Exception as e:
            logger.error(
                f"Failed to generate data schema for data template '{input_data.name}': {e}",
                exc_info=True,
            )
            raise Exception(f"Data schema generation failed: {str(e)}")
