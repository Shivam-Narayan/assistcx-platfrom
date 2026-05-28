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


SUMMARIZATION_SYSTEM_PROMPT = """
You are an expert content summarization specialist. Your task is to analyze the given input and create a comprehensive, accurate summary.

## Summarization Guidelines
1. Carefully read and understand the entire input content
2. Identify the main points, key information, and important details
3. Create a concise yet comprehensive summary that captures the essence of the content
4. Maintain accuracy and preserve important facts, dates, names, and numbers
5. Organize the summary in a clear, logical structure
6. Focus on the most relevant and actionable information
7. If the content is technical or domain-specific, preserve the technical accuracy
8. Ensure the summary is coherent and easy to understand

## Output Format
Provide a well-structured summary that includes:
- Main topic or purpose
- Key points and important details
- Any action items, deadlines, or important dates mentioned
- Relevant context or background information
"""

SUMMARIZATION_INPUT_PROMPT = """
{% if summarization_rules -%}
**IMPORTANT:** Strictly follow these rules during the summarization process:
{{ summarization_rules }}
{%- endif %}

{% if user_instructions %}
**User instructions:** Follow these instructions strictly during summarization:
{{ user_instructions }}
{% endif %}

Here is the content to summarize:
{% if text_data -%}
<input_text>
{{ text_data }}

{{ additional_data }}
</input_text>
{%- endif %}
"""


class SummarizationResponse(BaseModel):
    """Response model for content summarization - returns summary text or None if no summary was generated"""

    summary: Optional[str] = Field(
        default=None, description="Comprehensive summary of the input content"
    )


class ContentSummarizer:
    """
    Handles content summarization from attachment files and/or inline text.
    """

    def __init__(self, organization_schema: str):
        """
        Initializes ContentSummarizer with organization schema.

        Args:
            organization_schema (str): Schema identifier for the organization
        """
        self.organization_schema = organization_schema
        self.db_pool = DatabasePoolManager()

    def generate_summary(
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
        Summarize content from email, attachment, or raw text.

        Args:
            tool_runtime (Dict): Tool runtime context
            db (Session): Database session
            attachment_data (any, optional): Attachment data containing content and metadata
            raw_text (str, optional): Inline text to include; merged with email/attachment text
                when those are present, otherwise used alone
            vision_extraction (bool): Flag to enable vision-based summarization
            tool_rules (Optional[List[str]]): Additional rules for summarization
            user_instructions (Optional[str]): User-provided instructions
            config (Optional[Dict]): Config for LangChain callbacks

        Returns:
            str: Summarization result with summary text
        """
        try:
            task_id = tool_runtime.get("task_id", "unknown")

            # Get configurable page limit from tool_runtime (default: 10 for summarization)
            vision_page_limit = tool_runtime.get("vision_page_limit", 10)

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
                        f"[task_id={task_id}] Vision summarization enabled but no images extracted, falling back to text"
                    )
                    use_vision = False
                else:
                    logger.info(
                        f"[task_id={task_id}] Vision summarization enabled: images={len(image_list)}"
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

            # Build system prompt
            system_prompt = SUMMARIZATION_SYSTEM_PROMPT

            # Build summarization rules from tool_rules
            summarization_rules = None
            if tool_rules:
                summarization_rules = "- " + "\n- ".join(tool_rules)

            # Build input prompt
            input_prompt = Template(SUMMARIZATION_INPUT_PROMPT).render(
                summarization_rules=summarization_rules,
                user_instructions=user_instructions,
                text_data=input_data.get("text_data", ""),
                additional_data=input_data.get("metadata", {}),
            )

            # Initialize LLM with SummarizationResponse
            llm_provider = LLMProvider(self.organization_schema, db)
            llm = llm_provider.get_llm().with_structured_output(SummarizationResponse)

            # Build messages
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=input_prompt),
            ]

            # Add images if vision extraction is enabled
            if use_vision and image_list:
                # Build multimodal message with images
                image_content = [{"type": "text", "text": input_prompt}]
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
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=image_content),
                ]

            # Invoke LLM with SummarizationResponse
            result = llm.invoke(messages, config=config)

            return result.summary if result.summary else ""

        except Exception as e:
            logger.error(f"Error in content summarization: {e}", exc_info=True)
            return json.dumps(
                {"error": f"Summarization error: {str(e)}"}, ensure_ascii=False
            )

    def summarize_content(
        self,
        tool_runtime: Dict,
        attachment_id: Optional[str] = None,
        input_text: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Summarize attachment and/or inline text. Use attachment_id for file-based
        content; use input_text for email subject + body, notes, or other text.
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
                    "No data source given for summarization."
                )
                logger.error(f"[task_id={task_id}] summarize_content: {err}")
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
                f"[task_id={task_id}] summarization_started: "
                f"tool=summarize_content, attachment_uuid={attachment_id or None}, "
                f"has_input_text={bool(input_text)}, vision={vision_data_extraction}"
            )

            tool_rules = [
                rule
                for plan in tool_plan or []
                if plan.rules and "summarize_content" in (plan.tool or [])
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

                summarization_result = self.generate_summary(
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
                    f"[task_id={task_id}] summarization_completed: "
                    f"tool=summarize_content, status=SUCCESS, "
                    f"summary_length={len(summarization_result)}"
                )

                return summarization_result

        except Exception as e:
            logger.error(
                f"[task_id={task_id}] summarization_completed: "
                f'tool=summarize_content, status=FAILED, error="{str(e)}"'
            )
            return json.dumps(
                {"error": f"Error in summarize_content: {str(e)}"},
                ensure_ascii=False,
            )


if __name__ == "__main__":
    tool_runtime = {
        "organization_schema": "public",
    }

    # Initialize the ContentSummarizer
    organization_schema = tool_runtime.get("organization_schema", "public")
    content_summarizer = ContentSummarizer(organization_schema)

    # Test 1: attachment + inline context
    print("\n --- Testing summarize_content (attachment + input_text) ---")
    result = content_summarizer.summarize_content(
        tool_runtime,
        attachment_id="01a41722-aaf5-45cc-97fb-c84f2f9284ec",
        input_text="Subject: Re: invoice\n\nPlease summarize with this context.",
    )
    print(result)

    # Test 2: inline text only
    print("\n --- Testing summarize_content (input_text only) ---")
    result = content_summarizer.summarize_content(
        tool_runtime,
        input_text="This is a sample text content that needs to be summarized.",
    )
    print(result)
