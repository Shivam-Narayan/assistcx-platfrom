# Custom libraries
from agents.shared_utils.llm_provider import LLMProvider
from logger import configure_logging
from toolkits.shared_utils import (
    validate_uuid,
    get_attachment,
    get_document_images,
    prepare_input_data,
)

# Database modules
from db_pool import DatabasePoolManager

# Default libraries
from typing import Any, List, Dict, Optional
import json

# Installed libraries
from dotenv import load_dotenv
from jinja2 import Template
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session


load_dotenv()

logger = configure_logging(__name__)

IMAGE_MIME_TYPES = "image/jpeg"


EXTRACTION_SYSTEM_PROMPT = """
You are an expert information extraction specialist. Your task is to analyze the given input and extract key information in a structured format.

## Extraction Guidelines
1. Carefully analyze the input content to identify all relevant key information
2. Extract information accurately and completely
3. Structure the extracted information in a clear, organized manner
4. Focus on extracting factual, actionable information
5. Maintain accuracy and avoid making assumptions beyond what is stated in the input
6. No metadata should be included in the extracted information
7. If certain information is explicitly specified to be extracted but not available in the input, indicate that clearly

## Output Format
Return the extracted information as a valid JSON object string with clear fields and values. 
The JSON must be properly formatted and parseable. Use an empty object {} if no information can be extracted.
"""

EXTRACTION_INPUT_PROMPT = """
{% if extraction_rules -%}
**IMPORTANT:** Strictly follow these rules during the extraction process:
{{ extraction_rules }}
{%- endif %}

{% if user_instructions %}
**User instructions:** Follow these instructions strictly during extraction:
{{ user_instructions }}
{% endif %}

Here is the raw input for extraction:
{% if text_data -%}
<input_text>
{{ text_data }}

{{ additional_data }}
</input_text>
{%- endif %}
"""


class KeyInformationExtractionResponse(BaseModel):
    """Response model for key information extraction - returns structured extracted data as JSON string."""

    key_information_data: str = Field(
        default="{}",
        description="JSON string containing the extracted key information with structured fields, must be valid JSON",
    )


class KeyInformationExtractor:
    """Extracts key information from attachment files and/or inline text via the LLM."""

    def __init__(self, organization_schema: str):
        """
        Initializes KeyInformationExtractor with organization schema.

        Args:
            organization_schema (str): Schema identifier for the organization
        """
        self.organization_schema = organization_schema
        self.db_pool = DatabasePoolManager()

    def _cleanup_metadata(self, ai_output: Any) -> Any:
        """Recursively remove meta__document and meta__fields keys (parity with DataExtractor)."""
        if isinstance(ai_output, list):
            return [self._cleanup_metadata(item) for item in ai_output]
        if isinstance(ai_output, dict):
            return {
                key: self._cleanup_metadata(value)
                for key, value in ai_output.items()
                if key not in ["meta__document", "meta__fields"]
            }
        return ai_output

    def generate_key_information(
        self,
        tool_runtime: Dict,
        db: Session,
        attachment_data: Any = None,
        raw_text: Optional[str] = None,
        vision_extraction: bool = False,
        tool_rules: Optional[List[str]] = None,
        user_instructions: Optional[str] = None,
        config: Optional[Dict] = None,
    ) -> str:
        """
        Extract key information from email, attachment, or raw text.

        Args:
            tool_runtime (Dict): Tool runtime context
            db (Session): Database session
            attachment_data (any, optional): Attachment data containing content and metadata
            raw_text (str, optional): Inline text (e.g. email subject + body, notes). With
                attachment_data, merged as **Additional context** after attachment-derived text;
                without attachment, used as the sole text source for extraction.
            vision_extraction (bool): Flag to enable vision-based extraction
            tool_rules (Optional[List[str]]): Additional rules for extraction
            user_instructions (Optional[str]): User-provided instructions
            config (Optional[Dict]): Config for LangChain callbacks

        Returns:
            str: JSON string of extraction result with key information extracted data
        """
        try:
            task_id = tool_runtime.get("task_id", "unknown")

            # Align default with DataExtractor for multi-page documents
            vision_page_limit = (
                tool_runtime.get("vision_page_limit", 50) if tool_runtime else 50
            )

            # Get image data if vision extraction requested
            image_list = []
            use_vision = vision_extraction

            if vision_extraction and attachment_data:
                image_list = get_document_images(
                    organization_schema=self.organization_schema,
                    attachment_data=attachment_data,
                    page_count=vision_page_limit,
                )
                # Fallback to text if no images available
                if not image_list:
                    logger.warning(
                        f"[task_id={task_id}] Vision extraction enabled but no images extracted, falling back to text"
                    )
                    use_vision = False
                else:
                    logger.info(
                        f"[task_id={task_id}] Vision extraction enabled: images={len(image_list)}"
                    )

            supplementary = (raw_text or "").strip()
            has_attachment = attachment_data is not None

            if has_attachment:
                input_data = prepare_input_data(
                    None, attachment_data, tool_runtime, use_vision
                )
                if supplementary:
                    base = (input_data.get("text_data") or "").strip()
                    extra = f"\n\n**Additional context:**\n{supplementary}"
                    input_data["text_data"] = f"{base}{extra}" if base else supplementary
            elif supplementary:
                input_data = {"text_data": supplementary, "metadata": {}}
            else:
                input_data = {"text_data": "", "metadata": {}}

            extraction_rules = (
                "- " + "\n- ".join(tool_rules) if tool_rules else None
            )
            input_prompt = Template(EXTRACTION_INPUT_PROMPT).render(
                extraction_rules=extraction_rules,
                user_instructions=user_instructions,
                text_data=input_data.get("text_data", ""),
                additional_data=input_data.get("metadata", {}),
            )

            # Initialize LLM with KeyInformationExtractionResponse
            llm_provider = LLMProvider(self.organization_schema, db)
            llm = llm_provider.get_llm().with_structured_output(
                KeyInformationExtractionResponse
            )

            if use_vision and image_list:
                image_content: List[Dict[str, Any]] = [
                    {"type": "text", "text": input_prompt}
                ]
                for img_base64 in image_list:
                    image_content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{IMAGE_MIME_TYPES};base64,{img_base64}"
                            },
                        }
                    )
                messages = [
                    SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
                    HumanMessage(content=image_content),
                ]
            else:
                messages = [
                    SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
                    HumanMessage(content=input_prompt),
                ]

            result = llm.invoke(messages, config=config)

            raw = (result.key_information_data or "").strip()
            if not raw:
                return ""
            parsed = json.loads(raw)
            clean_key_information = self._cleanup_metadata(parsed)
            return json.dumps(clean_key_information, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Error in key information extraction: {e}", exc_info=True)
            return json.dumps(
                {"error": f"Key information extraction error: {str(e)}"},
                ensure_ascii=False,
            )

    def extract_key_information(
        self,
        tool_runtime: Dict,
        attachment_id: Optional[str] = None,
        input_text: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Extract key information from attachment and/or inline text. Use attachment_id
        for file-based content; use input_text for email subject + body, notes, etc.
        At least one of attachment_id or input_text is required.
        """
        task_id = tool_runtime.get("task_id", "unknown")

        # Extract config if provided (from LangChain callback injection)
        config = kwargs.get("config")

        attachment_id = (attachment_id or "").strip()
        input_text = str(input_text).strip() if input_text else ""

        try:
            if not input_text and not attachment_id:
                err = (
                    "At least one of attachment_id or input_text must be provided. "
                    "No data source given for key information extraction."
                )
                logger.error(f"[task_id={task_id}] extract_key_information: {err}")
                return json.dumps({"error": err}, ensure_ascii=False)

            attachment_uuid = None
            if attachment_id:
                attachment_uuid, error = validate_uuid(attachment_id, "attachment_id")
                if error:
                    logger.error(f"[task_id={task_id}] UUID validation failed: {error}")
                    return json.dumps({"error": error}, ensure_ascii=False)

            # Get tool runtime data
            vision_data_extraction = tool_runtime.get("vision_data_extraction", False)
            user_instructions = tool_runtime.get("user_instructions")
            tool_plan = tool_runtime.get("plan")

            logger.info(
                f"[task_id={task_id}] key_information_extraction_started: "
                f"tool=extract_key_information, attachment_uuid={attachment_id or None}, "
                f"has_input_text={bool(input_text)}, vision={vision_data_extraction}"
            )

            tool_rules = [
                rule
                for plan in tool_plan or []
                if plan.rules and "extract_key_information" in (plan.tool or [])
                for rule in plan.rules
            ]

            with self.db_pool.get_session(self.organization_schema) as db:
                attachment_data = None
                if attachment_uuid:
                    attachment_data = get_attachment(
                        db=db, attachment_data_id=attachment_uuid
                    )
                    if not attachment_data:
                        raise Exception(f"Attachment {attachment_id} not found.")
                    # Vision extraction only works for visual file types
                    if attachment_data and vision_data_extraction:
                        file_type = attachment_data.file_type.lower()
                        if file_type not in ["pdf", "jpg", "png", "jpeg"]:
                            logger.info(
                                f"Vision extraction disabled for unsupported file type: {file_type}"
                            )
                            vision_data_extraction = False

                extraction_result = self.generate_key_information(
                    tool_runtime=tool_runtime,
                    db=db,
                    attachment_data=attachment_data,
                    raw_text=input_text or None,
                    vision_extraction=vision_data_extraction,
                    tool_rules=tool_rules,
                    user_instructions=user_instructions,
                    config=config,
                )

                logger.info(
                    f"[task_id={task_id}] key_information_extraction_completed: "
                    f"tool=extract_key_information, status=SUCCESS"
                )

                return extraction_result

        except Exception as e:
            logger.error(
                f"[task_id={task_id}] key_information_extraction_completed: "
                f'tool=extract_key_information, status=FAILED, error="{str(e)}"'
            )
            return json.dumps(
                {"error": f"Error in extract_key_information: {str(e)}"},
                ensure_ascii=False,
            )


if __name__ == "__main__":
    tool_runtime = {
        "organization_schema": "public",
    }

    # Initialize the KeyInformationExtractor
    organization_schema = tool_runtime.get("organization_schema", "public")
    key_extractor = KeyInformationExtractor(organization_schema)

    # Test 1: Extract Email Key Information
    print("\n --- Testing extract_key_information (attachment + input_text) ---")
    result = key_extractor.extract_key_information(
        tool_runtime,
        attachment_id="01a41722-aaf5-45cc-97fb-c84f2f9284ec",
        input_text="Subject: Re: vendor\n\nContext for extraction.",
    )
    print(result)

    # Test 2: Extract Text Key Information
    print("\n --- Testing extract_key_information (input_text only) ---")
    result = key_extractor.extract_key_information(
        tool_runtime,
        input_text="Invoice #INV-2024-001, amount $250, due 2024-12-01.",
    )
    print(result)
