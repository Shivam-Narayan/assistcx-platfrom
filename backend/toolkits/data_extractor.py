# Custom libraries
from agents.data_extractor import StructuredDataExtractor
from logger import configure_logging
from parsers.ocr_mapper import OCRBlockMapper
from toolkits.shared_utils import (
    validate_uuid,
    get_attachment,
    get_data_template,
    get_document_images,
)

# Default libraries
from typing import Any, List, Dict, Optional
import json

# Database modules
from db_pool import DatabasePoolManager
from repository.attachment_repository import AttachmentRepository

# Installed libraries
from dotenv import load_dotenv
from sqlalchemy.orm import Session


load_dotenv()

logger = configure_logging(__name__)

IMAGE_MIME_TYPES = "image/jpeg"


class DataExtractor:
    """
    Handles structured data extraction from emails, attachments, and raw text.
    """

    def __init__(self, organization_schema: str):
        """
        Initializes DataExtractor with organization schema.

        Args:
            organization_schema (str): Schema identifier for the organization
        """
        self.organization_schema = organization_schema
        self.db_pool = DatabasePoolManager()

    def _cleanup_metadata(self, ai_output: Any) -> Any:
        """
        Recursively remove 'meta__document' and 'meta__fields' keys from the data structure.

        Args:
            ai_output (Any): The data structure to clean

        Returns:
            Any: Cleaned data structure without metadata keys
        """
        if isinstance(ai_output, list):
            return [self._cleanup_metadata(item) for item in ai_output]
        if isinstance(ai_output, dict):
            return {
                key: self._cleanup_metadata(value)
                for key, value in ai_output.items()
                if key not in ["meta__document", "meta__fields"]
            }
        return ai_output

    def _perform_ocr_mapping(
        self,
        attachment_id: str,
        line_json: dict,
        extracted_data: list,
        template_class: str,
    ):
        """
        Perform OCR geometry mapping and update attachment table.

        Args:
            attachment_id (str): The attachment identifier
            line_json (dict): OCR line JSON data
            extracted_data (list): Extracted data from AI
            template_class (str): Template class name
        """
        try:
            ocr_block_geometry = OCRBlockMapper()

            transformed_data = ocr_block_geometry.apply_ocr_mapping(
                ai_data=extracted_data, ocr_pages=line_json or []
            )
            attachment_data = {
                "structured_output": transformed_data,
                "template_class": template_class,
            }

            with self.db_pool.get_session(self.organization_schema) as db:
                attachment_repo = AttachmentRepository(db=db)
                attachment_repo.update_attachment(
                    identifier=attachment_id, update_data=attachment_data
                )

            logger.info(
                f"OCR mapping completed: attachment_id={attachment_id}, records={len(extracted_data)}"
            )

        except Exception as e:
            logger.error(f"Failed to perform OCR mapping: {e}")

    def _extract_data(
        self,
        data_template: Any,
        tool_runtime: Dict,
        db: Session,
        input_text: Optional[str] = None,
        attachment_data: Any = None,
        vision_extraction: bool = False,
        tool_rules: Optional[List[str]] = None,
        user_instructions: Optional[str] = None,
        config: Optional[Dict] = None,
    ) -> tuple[Optional[List[Dict]], Optional[str]]:
        """
        Core extraction method. Combines input_text and/or attachment content,
        then runs the AI data extractor.

        Args:
            data_template (Any): Template containing extraction rules and schema
            tool_runtime (Dict): Tool runtime context
            db (Session): Database session
            input_text (str, optional): Text input for extraction (email body, raw text, etc.)
            attachment_data (Any, optional): Attachment data containing content and metadata
            vision_extraction (bool): Flag to enable vision-based extraction
            tool_rules (Optional[List[str]]): Additional rules for extraction
            user_instructions (Optional[str]): User-provided instructions
            config (Optional[Dict]): Config for LangChain callbacks

        Returns:
            tuple[Optional[List[Dict]], Optional[str]]: (extracted_data, extraction_summary)
        """
        try:
            vision_page_limit = (
                tool_runtime.get("vision_page_limit", 50) if tool_runtime else 50
            )

            image_list: List[Any] = []
            use_vision = vision_extraction

            if vision_extraction and attachment_data:
                image_list = get_document_images(
                    organization_schema=self.organization_schema,
                    attachment_data=attachment_data,
                    page_count=vision_page_limit,
                )
                if not image_list:
                    logger.warning(
                        "Vision extraction enabled but no images extracted, falling back to text extraction"
                    )
                    use_vision = False
                else:
                    logger.info(
                        f"Vision extraction enabled: images={len(image_list)}, "
                        f"file_type={attachment_data.file_type if attachment_data else 'N/A'}"
                    )

            # Build text_data from input_text + attachment content
            attachment_content = ""
            if attachment_data and attachment_data.content and not use_vision:
                attachment_content = attachment_data.content[0].strip()
            # TODO: consider leaving this on LLM rahter then complicating it just treast it as text.
            parts = [p for p in [attachment_content, input_text] if p]
            text_data = "\n\n".join(parts)

            task_context = tool_runtime.get("task_context", {})
            additional_data = {
                "sender_email": task_context.get("sender_email", ""),
                "mailbox_email": task_context.get("mailbox_email", ""),
                "email_subject": tool_runtime.get("email_subject", ""),
                "email_received_at": task_context.get("email_received_at"),
                "email_created_at": task_context.get("email_created_at"),
                "email_file_url": tool_runtime.get("email_file_url", ""),
                "attachment_file_url": (
                    attachment_data.remote_url if attachment_data else ""
                ),
                "task_id": tool_runtime.get("task_id", ""),
                "email_uuid": tool_runtime.get("email_uuid", ""),
                "agent_id": tool_runtime.get("agent_id", ""),
            }

            data_extractor = StructuredDataExtractor(
                organization_schema=self.organization_schema,
                vision=use_vision,
                db=db,
            )

            raw_extracted_data, extraction_summary = data_extractor.extract_data(
                data_template=data_template.model_dump(),
                text_data=text_data,
                additional_data=additional_data,
                image_list=image_list,
                mime_type=IMAGE_MIME_TYPES,
                extraction_summary=True,
                tool_rules=tool_rules,
                user_instructions=user_instructions,
                config=config,
            )

            if attachment_data:
                self._perform_ocr_mapping(
                    attachment_id=attachment_data.id,
                    line_json=[],
                    extracted_data=raw_extracted_data,
                    template_class=data_template.template_class,
                )

            clean_extracted_data = self._cleanup_metadata(raw_extracted_data)

            return (
                clean_extracted_data if clean_extracted_data else []
            ), extraction_summary

        except Exception as e:
            logger.error(f"Error in data extraction: {e}")
            return [], None

    def extract_structured_data(
        self,
        tool_runtime: Dict,
        data_template: str,
        attachment_id: Optional[str] = None,
        input_text: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Extract structured data using a data template from attachment and/or input text.
        At least one of attachment_id or input_text must be provided.

        Args:
            tool_runtime (Dict): Tool runtime context containing plan, task_id, etc
            data_template (str): The template class to use for extraction
            attachment_id (str, optional): UUID of the attachment to extract data from
            input_text (str, optional): Text input for extraction (email body, raw text, etc.)
            **kwargs: Additional kwargs including config from LangChain

        Returns:
            str: JSON string of extracted structured data
        """
        task_id = tool_runtime.get("task_id", "unknown")
        config = kwargs.get("config")

        try:
            if not data_template or not data_template.strip():
                return json.dumps(
                    [
                        {
                            "error": "data_template is required, use a valid template_class from available data_templates."
                        }
                    ],
                    ensure_ascii=False,
                )

            input_text = str(input_text).strip() if input_text else ""

            if not input_text and not (attachment_id and attachment_id.strip()):
                err = (
                    "At least one of attachment_id or input_text must be provided. "
                    "No data source given for extraction."
                )
                logger.error(f"[task_id={task_id}] extract_structured_data: {err}")
                return json.dumps([{"error": err}], ensure_ascii=False)

            data_template = data_template.replace(" ", "_").lower()
            user_instructions = tool_runtime.get("user_instructions")
            tool_plan = tool_runtime.get("plan")
            tool_rules = [
                rule
                for plan in tool_plan or []
                if plan.rules
                and (
                    "extract_structured_data" in (plan.tool or [])
                    or "extract_data" in (plan.tool or [])
                )
                for rule in plan.rules
            ]

            with self.db_pool.get_session(self.organization_schema) as db:
                template_data = get_data_template(db=db, template_class=data_template)
                if not template_data:
                    raise Exception(f"Data template {data_template} not found.")

                attachment_data = None
                vision_data_extraction = False

                if attachment_id and attachment_id.strip():
                    attachment_uuid, error = validate_uuid(
                        attachment_id, "attachment_id"
                    )
                    if error:
                        logger.error(
                            f"[task_id={task_id}] UUID validation failed: {error}"
                        )
                        return json.dumps([{"error": error}], ensure_ascii=False)

                    attachment_data = get_attachment(
                        db=db, attachment_data_id=attachment_uuid
                    )
                    if not attachment_data:
                        raise Exception(f"Attachment {attachment_id} not found.")

                    vision_data_extraction = tool_runtime.get(
                        "vision_data_extraction", False
                    )
                    if vision_data_extraction:
                        file_type = attachment_data.file_type.lower()
                        if file_type not in ["pdf", "jpg", "png", "jpeg"]:
                            logger.info(
                                f"Vision extraction disabled for unsupported file type: {file_type}"
                            )
                            vision_data_extraction = False

                logger.info(
                    f"[task_id={task_id}] data_extraction_started: "
                    f"tool=extract_structured_data, attachment_uuid={attachment_id}, "
                    f"template={data_template}, vision={vision_data_extraction}, "
                    f"has_input_text={bool(input_text)}"
                )

                extracted_data, extraction_summary = self._extract_data(
                    data_template=template_data,
                    tool_runtime=tool_runtime,
                    db=db,
                    input_text=input_text or None,
                    attachment_data=attachment_data,
                    vision_extraction=vision_data_extraction,
                    tool_rules=tool_rules,
                    user_instructions=user_instructions,
                    config=config,
                )

            if extracted_data:
                logger.info(
                    f"[task_id={task_id}] data_extraction_completed: "
                    f"tool=extract_structured_data, status=SUCCESS, records_found={len(extracted_data)}"
                )
                return json.dumps(extracted_data, ensure_ascii=False)

            message = (
                extraction_summary if extraction_summary else "Could not extract data"
            )
            logger.warning(
                f"[task_id={task_id}] data_extraction_completed: "
                f'tool=extract_structured_data, status=FAILED, error="{message}"'
            )
            return json.dumps([{"error": message}], ensure_ascii=False)

        except Exception as e:
            logger.error(
                f"[task_id={task_id}] data_extraction_completed: "
                f'tool=extract_structured_data, status=FAILED, error="{str(e)}"'
            )
            return json.dumps(
                [{"error": f"Error in extract_structured_data: {str(e)}"}],
                ensure_ascii=False,
            )


if __name__ == "__main__":
    organization_schema = "public"
    data_template = "vendor_invoice"

    tool_runtime = {
        "organization_schema": organization_schema,
        "task_id": "local-test",
        "plan": [],
    }

    data_extractor = DataExtractor(organization_schema)

    # Test 1 — extract_structured_data: attachment_id only
    print("\n --- extract_structured_data: attachment only ---")
    print(
        data_extractor.extract_structured_data(
            tool_runtime,
            data_template,
            attachment_id="673aedd5-0fd5-467d-a750-f6b2981dacb5",
        )
    )

    # Test 2 — extract_structured_data: input_text only
    print("\n --- extract_structured_data: input_text only ---")
    print(
        data_extractor.extract_structured_data(
            tool_runtime,
            data_template,
            input_text="This is a sample text content that needs to be extracted.",
        )
    )

    # Test 3 — extract_structured_data: attachment_id + input_text
    print("\n --- extract_structured_data: attachment + input_text ---")
    print(
        data_extractor.extract_structured_data(
            tool_runtime,
            data_template,
            attachment_id="673aedd5-0fd5-467d-a750-f6b2981dacb5",
            input_text="Additional context for the extraction.",
        )
    )
