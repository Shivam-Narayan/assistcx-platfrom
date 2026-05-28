# Custom libraries
from agents.shared_utils.llm_provider import LLMProvider
from logger import configure_logging
from toolkits.shared_utils import (
    validate_uuid,
    get_attachment,
    get_class_group,
    get_document_images,
    prepare_input_data,
)

# Database modules
from db_pool import DatabasePoolManager
from schemas.class_group_schema import ClassGroupDetail

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


CLASSIFICATION_SYSTEM_PROMPT = """
You are an expert content classifier. Your task is to analyze the given input and classify it into the single most appropriate class based on the provided class definitions.

## Available Classes
The following classes are available for classification. Each class has a name and description:
{% for cls in class_schema -%}
- **{{ cls.class_name }}**: {{ cls.class_description }}
{% endfor %}

## Classification Rules
1. Analyze the input content carefully and match it against the class descriptions
2. Select ONLY ONE class that best matches the content - the most appropriate and accurate match
3. Only select a class where there is clear evidence in the input
4. If no classes match the content, leave class_name empty and provide reasoning explaining why none matched
5. Return the exact class name as provided in the list above
6. Provide specific reasoning explaining why the selected class was chosen (or why no class matched)

## CRITICAL: Accuracy and Precision
- Only classify content when you have high confidence in the match
- Choose the single best matching class, not multiple classes
- If the content is ambiguous or unclear, do not force a classification - return no match with reasoning
"""

CLASSIFICATION_INPUT_PROMPT = """
{% if classification_rules -%}
**IMPORTANT:** Strictly follow these rules during the classification process:
{{ classification_rules }}
{%- endif %}

{% if user_instructions %}
**User instructions:** Follow these instructions strictly during classification:
{{ user_instructions }}
{% endif %}

Here is the raw input for classification:
{% if text_data -%}
<input_text>
{{ text_data }}

{{ additional_data }}
</input_text>
{%- endif %}
"""


class ClassificationResponse(BaseModel):
    """Response model for content classification - returns single best match or no match with reasoning."""

    class_name: Optional[str] = Field(
        default=None,
        description="The name of the single best matching class, or None if no match found",
    )
    reasoning: str = Field(
        description="Explanation for why this class was selected, or why no class matched"
    )


class ContentClassifier:
    """Classifies attachment files and/or inline text into one class from a configured class group."""

    def __init__(self, organization_schema: str):
        """
        Initializes ContentClassifier with organization schema.

        Args:
            organization_schema (str): Schema identifier for the organization
        """
        self.organization_schema = organization_schema
        self.db_pool = DatabasePoolManager()

    def generate_classification(
        self,
        class_group_data: ClassGroupDetail,
        tool_runtime: Dict,
        db: Session,
        attachment_data: Any = None,
        raw_text: Optional[str] = None,
        vision_extraction: bool = False,
        tool_rules: Optional[List[str]] = None,
        user_instructions: Optional[str] = None,
        config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Classify content into matching classes based on the class group schema.

        Args:
            class_group_data (ClassGroupDetail): Class group containing class_schema with class definitions
            tool_runtime (Dict): Tool runtime context
            db (Session): Database session
            attachment_data (any, optional): Attachment data containing content and metadata
            raw_text (str, optional): Inline text (e.g. email subject + body, notes). With
                attachment_data, merged as **Additional context** after attachment-derived text;
                without attachment, used as the sole text source for classification.
            vision_extraction (bool): Flag to enable vision-based classification
            tool_rules (Optional[List[str]]): Additional rules for classification
            user_instructions (Optional[str]): User-provided instructions
            config (Optional[Dict]): Config for LangChain callbacks

        Returns:
            Dict[str, Any]: Classification result with matched_classes and optional no_match_reasoning
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
                        f"[task_id={task_id}] Vision classification enabled but no images extracted, falling back to text"
                    )
                    use_vision = False
                else:
                    logger.info(
                        f"[task_id={task_id}] Vision classification enabled: images={len(image_list)}"
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

            # Get class schema from class_group_data
            class_schema = class_group_data.class_schema
            if not class_schema:
                logger.warning(
                    f"Empty class_schema in class group: {class_group_data.key}"
                )
                return {
                    "error": f"Empty class_schema in class group: {class_group_data.key}."
                }

            # Validate class_schema structure
            valid_class_schema = []
            for cls in class_schema:
                if isinstance(cls, dict) and "class_name" in cls:
                    valid_class_schema.append(
                        {
                            "class_name": cls.get("class_name", ""),
                            "class_description": cls.get(
                                "class_description", cls.get("class_name", "")
                            ),
                        }
                    )

            if not valid_class_schema:
                logger.warning(
                    f"[task_id={task_id}] No valid class definitions found in class_schema"
                )
                return {"error": "No valid class definitions found in class_schema."}

            # Build system prompt with class schema
            system_prompt = Template(CLASSIFICATION_SYSTEM_PROMPT).render(
                class_schema=valid_class_schema,
            )

            classification_rules = (
                "- " + "\n- ".join(tool_rules) if tool_rules else None
            )
            input_prompt = Template(CLASSIFICATION_INPUT_PROMPT).render(
                classification_rules=classification_rules,
                user_instructions=user_instructions,
                text_data=input_data.get("text_data", ""),
                additional_data=input_data.get("metadata", {}),
            )

            # Initialize LLM with ClassificationResponse
            llm_provider = LLMProvider(self.organization_schema, db)
            llm = llm_provider.get_llm().with_structured_output(ClassificationResponse)

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
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=image_content),
                ]
            else:
                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=input_prompt),
                ]

            result = llm.invoke(messages, config=config)

            # Validate the matched class against valid class names
            valid_class_names = [cls["class_name"] for cls in valid_class_schema]

            # Check if a valid class was matched
            if result.class_name and result.class_name in valid_class_names:
                return {
                    "class_name": result.class_name,
                    "reasoning": result.reasoning,
                }
            else:
                # No match or invalid class name
                reasoning = result.reasoning or "No classes matched the input content."
                return {"reasoning": reasoning}

        except Exception as e:
            logger.error(f"Error in content classification: {e}", exc_info=True)
            return {"error": f"Classification error: {str(e)}"}

    def classify_content(
        self,
        tool_runtime: Dict,
        class_group: str,
        attachment_id: Optional[str] = None,
        input_text: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Classify attachment and/or inline text into the single best matching class.
        class_group is the configured class group key. Use attachment_id for file-based
        content; use input_text for email subject + body or other text. At least one of
        attachment_id or input_text is required.
        """
        task_id = tool_runtime.get("task_id", "unknown")

        # Extract config if provided (from LangChain callback injection)
        config = kwargs.get("config")

        try:
            if not class_group or not class_group.strip():
                return json.dumps(
                    {
                        "error": "class_group is required, use a valid key from available class_groups."
                    },
                    ensure_ascii=False,
                )

            class_group = class_group.replace(" ", "_").lower()

            attachment_id = (attachment_id or "").strip()
            input_text = str(input_text).strip() if input_text else ""

            if not input_text and not attachment_id:
                err = (
                    "At least one of attachment_id or input_text must be provided. "
                    "No data source given for classification."
                )
                logger.error(f"[task_id={task_id}] classify_content: {err}")
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
                f"[task_id={task_id}] classification_started: "
                f"tool=classify_content, class_group={class_group}, "
                f"attachment_uuid={attachment_id or None}, has_input_text={bool(input_text)}, "
                f"vision={vision_data_extraction}"
            )

            tool_rules = [
                rule
                for plan in tool_plan or []
                if plan.rules and "classify_content" in (plan.tool or [])
                for rule in plan.rules
            ]

            with self.db_pool.get_session(self.organization_schema) as db:
                class_group_data = get_class_group(db=db, class_group_key=class_group)
                if not class_group_data:
                    raise Exception(f"Class group '{class_group}' not found.")

                # Get attachment data if provided and check vision extraction
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

                classification_result = self.generate_classification(
                    class_group_data=class_group_data,
                    tool_runtime=tool_runtime,
                    db=db,
                    attachment_data=attachment_data,
                    raw_text=input_text or None,
                    vision_extraction=vision_data_extraction,
                    tool_rules=tool_rules,
                    user_instructions=user_instructions,
                    config=config,
                )

                class_name = (
                    classification_result.get("class_name")
                    if classification_result.get("class_name")
                    else ""
                )

                logger.info(
                    f"[task_id={task_id}] classification_completed: "
                    f"tool=classify_content, status=SUCCESS, class_name={class_name}"
                )

                return json.dumps(classification_result, ensure_ascii=False)

        except Exception as e:
            logger.error(
                f"[task_id={task_id}] classification_completed: "
                f'tool=classify_content, status=FAILED, error="{str(e)}"'
            )
            return json.dumps(
                {"error": f"Error in classify_content: {str(e)}"},
                ensure_ascii=False,
            )


if __name__ == "__main__":
    tool_runtime = {
        "organization_schema": "public",
    }

    # Initialize the ContentClassifier
    organization_schema = tool_runtime.get("organization_schema", "public")
    content_classifier = ContentClassifier(organization_schema)

    # Test 1: Classify Text Content
    print("\n --- Testing classify_content (input_text only) ---")
    result = content_classifier.classify_content(
        tool_runtime,
        "hr_class_names",
        input_text="This is a sample text content.",
    )
    print(result)

    # Test 2: Classify Attachment Content
    print("\n --- Testing classify_content (attachment + input_text) ---")
    result = content_classifier.classify_content(
        tool_runtime,
        "hr_class_names",
        attachment_id="01a41722-aaf5-45cc-97fb-c84f2f9284ec",
        input_text="Subject: Application\n\nSee attached resume.",
    )
    print(result)
