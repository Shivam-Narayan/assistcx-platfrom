from typing import List, Tuple, Optional
from dotenv import load_dotenv
from jinja2 import Template
from langchain_core.messages import HumanMessage, SystemMessage
from .model_generator import DataModelGenerator
from .prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACT_INPUT_PROMPT,
)
from logger import configure_logging
from agents.shared_utils.llm_provider import LLMProvider
from sqlalchemy.orm import Session

load_dotenv()
logger = configure_logging(__name__)


class StructuredDataExtractor:

    def __init__(self, llm=None, organization_schema: str = None, vision: bool = False, db: Session = None):
        """
        Initialize StructuredDataExtractor.
        
        Args:
            llm: Pre-configured LLM instance (optional)
            organization_schema: Organization schema name (required if llm not provided)
            vision: Whether to enable vision-based extraction
            db: Database session (required if organization_schema is provided)
        
        Raises:
            ValueError: If neither llm nor organization_schema is provided, or if organization_schema is provided without db
        """
        self.organization_schema = organization_schema
        self.vision = vision
        self.model_generator = DataModelGenerator()
        # Use provided LLM instance or create from organization schema
        if llm is not None:
            self.llm = llm
        elif organization_schema:
            if db is None:
                raise ValueError(
                    "Database session (db) is required when organization_schema is provided"
                )
            self.llm = LLMProvider(organization_schema, db).get_llm()
        else:
            raise ValueError(
                "Either llm instance or both organization_schema and db must be provided"
            )

    def extract_data(
        self,
        data_template: dict,
        text_data: str = "",
        additional_data: dict = {},
        image_list: List[str] = [],
        mime_type: str = "image/jpeg",
        document_metadata: bool = True,
        field_metadata: bool = True,
        extraction_summary: bool = False,
        tool_rules: Optional[List[str]] = None,
        user_instructions: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> Tuple[List[dict], Optional[str]]:
        """
        Extract structured data from input using the output schema.
        Handles both text-only and vision+text extraction.

        Returns:
            tuple: (extracted_data, extraction_summary)
        """
        try:
            template_name = data_template.get("name")
            template_description = data_template.get("description")
            data_schema = data_template.get("data_schema")
            document_instructions = data_template.get("document_instructions")

            # Create model that always expects list output
            request_model = self.model_generator.create_pydantic_model(
                data_schema=data_schema,
                model_name=template_name.lower(),
                document_metadata=document_metadata,
                field_metadata=field_metadata,
                extraction_summary=extraction_summary,
            )

            extraction_prompt = Template(EXTRACTION_SYSTEM_PROMPT).render(
                template_name=template_name,
                template_description=template_description,
                document_metadata=document_metadata,
                field_metadata=field_metadata,
                extraction_summary=extraction_summary,
            )

            instruction_parts = []
            if document_instructions:
                instruction_parts.extend(document_instructions)
            if tool_rules:
                instruction_parts.extend(tool_rules)

            extraction_rules = (
                "- " + "\n- ".join(instruction_parts) if instruction_parts else None
            )

            extraction_input = Template(EXTRACT_INPUT_PROMPT).render(
                extraction_rules=extraction_rules,
                text_data=text_data,
                additional_data=additional_data,
                user_instructions=user_instructions,
            )

            # Format messages based on whether vision is enabled
            if self.vision and image_list:
                # Build content with text and multiple images
                content = [{"type": "text", "text": extraction_input}]
                if len(image_list) > 1:
                    content.append(
                        {
                            "type": "text",
                            "text": f"Following are the {len(image_list)} images from the document.\n\n",
                        }
                    )
                for i, image_data in enumerate(image_list, start=1):
                    if len(image_list) > 1:
                        content.append({"type": "text", "text": f"--- Page {i} ---\n"})
                    content.append(
                        {
                            "type": "image",
                            "source_type": "base64",
                            "data": image_data,
                            "mime_type": mime_type,
                        }
                    )

                messages = [
                    SystemMessage(content=extraction_prompt),
                    HumanMessage(content=content),
                ]
            else:
                messages = [
                    SystemMessage(content=extraction_prompt),
                    HumanMessage(content=extraction_input),
                ]

            # Configure structured output - LLM will return validated Pydantic model
            llm_model = self.llm.with_structured_output(request_model)

            # Invoke the model with config
            response = llm_model.invoke(messages, config=config)

            # Convert Pydantic model to dict
            structured_output = response.model_dump()

            structured_data = structured_output.get("data_records", [])
            summary = (
                structured_output.get("extraction_summary", None)
                if extraction_summary
                else None
            )

            final_data = (
                structured_data
                if isinstance(structured_data, list)
                else [structured_data]
            )

            logger.info(
                f"Data extraction successful: vision_enabled={self.vision}, records_found={len(final_data)}"
            )
            return final_data, summary

        except Exception as e:
            logger.error(f"Data extraction failed: {e}")
            return [], None
