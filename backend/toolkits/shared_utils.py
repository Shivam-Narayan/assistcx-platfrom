# Custom libraries
from logger import configure_logging
from schemas.email_schema import EmailDetail
from schemas.attachment_schema import AttachmentDetail
from schemas.class_group_schema import ClassGroupDetail
from schemas.data_template_schema import DataTemplateDetail
from utils.document_file import DocumentFile

# Default libraries
from datetime import datetime
from pdf2image import convert_from_bytes
from typing import Any, Dict, List, Optional
from uuid import UUID
import base64
import io

# Database modules
from db_pool import DatabasePoolManager
from repository.email_repository import EmailRepository
from repository.attachment_repository import AttachmentRepository
from repository.class_group_repository import ClassGroupRepository
from repository.data_template_repository import DataTemplateRepository

# Installed libraries
from dotenv import load_dotenv


load_dotenv()

logger = configure_logging(__name__)

db_pool = DatabasePoolManager()

IMAGE_MIME_TYPES = "image/jpeg"
IMAGE_FILE_TYPE = "jpeg"


def validate_uuid(value: str, param_name: str) -> tuple:
    """
    Validate UUID string and return UUID object or error message.

    Args:
        value: The UUID string to validate
        param_name: Parameter name for error messages

    Returns:
        (UUID object, None) if valid
        (None, error_message) if invalid
    """
    if not value:
        return None, f"Missing required parameter '{param_name}'"

    try:
        uuid_obj = UUID(value.strip())
        return uuid_obj, None
    except (ValueError, AttributeError) as e:
        error_msg = (
            f"Invalid UUID input for '{param_name}': {str(e)}\n"
            f"Expected format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (36 chars with hyphens)\n"
            f"Received: '{value}' (length={len(value)})\n"
            f"The provided input may be truncated or incorrect. Make sure to use the correct value for {param_name} from the task data."
        )
        return None, error_msg


def get_attachment(db, attachment_data_id) -> Optional[AttachmentDetail]:
    """
    Get attachment data from DB using attachment UUID.

    Args:
        db: Database session
        attachment_data_id: UUID object (already validated)

    Returns:
        AttachmentDetail if found, None otherwise
    """
    try:
        # Query to find the attachment for the given UUID
        attachment_repo = AttachmentRepository(db=db)
        attachment = attachment_repo.get_attachment_by_id(identifier=attachment_data_id)

        if attachment:
            return AttachmentDetail.model_validate(attachment)
        return None

    except Exception as e:
        logger.error(f"Error in fetching attachment: {e}")
        return None


def get_email(db, email_uuid) -> Optional[EmailDetail]:
    """
    Get email data from DB using email UUID.

    Args:
        db: Database session
        email_uuid: UUID object (already validated)

    Returns:
        EmailDetail if found, None otherwise
    """
    try:
        email_repo = EmailRepository(db=db)
        email_data = email_repo.get_email_by_id(email_uuid)
        if email_data:
            return EmailDetail.model_validate(email_data)
        return None

    except Exception as e:
        logger.error(f"Error in fetching email with uuid {email_uuid}: {e}")
        return None


def get_data_template(db, template_class: str) -> Optional[DataTemplateDetail]:
    """
    Get data template information using template class.

    Args:
        db: Database session
        template_class: Template class string

    Returns:
        DataTemplateDetail if found, None otherwise
    """
    try:
        data_template_repo = DataTemplateRepository(db=db)
        data_template = data_template_repo.get_template(template_class)
        if data_template:
            return DataTemplateDetail.model_validate(data_template)
        return None

    except Exception as e:
        logger.error(f"Error in fetching data template: {e}")
        return None


def get_class_group(db, class_group_key: str) -> Optional[ClassGroupDetail]:
    """
    Get class group information using class group key.

    Args:
        db: Database session
        class_group_key: Class group key string

    Returns:
        ClassGroupDetail if found, None otherwise
    """
    try:
        class_group_repo = ClassGroupRepository(db=db)
        class_group = class_group_repo.get_class_group_by_id(class_group_key)
        if class_group:
            return ClassGroupDetail.model_validate(class_group)
        return None

    except Exception as e:
        logger.error(f"Error in fetching class group: {e}")
        return None


def get_document_images(
    organization_schema,
    attachment_data: any,
    page_count: int = 10,
) -> List[str]:
    """
    Convert document to images and return as list of base64 strings.
    Supports PDF (converted to images) and direct image files (JPG, PNG, JPEG).

    Args:
        organization_schema: Organization schema for S3 utility
        attachment_data: Attachment information containing file_type and remote_url
        page_count: Number of pages to convert for PDFs (default: 10)

    Returns:
        List[str]: List of base64 encoded image strings, empty list if conversion fails
    """
    if not attachment_data:
        return []

    file_type = attachment_data.file_type.lower()

    try:
        document_file = DocumentFile(organization_schema=organization_schema)
        file_content = document_file.download_file(file_path=attachment_data.remote_url)
        if not file_content:
            logger.warning(f"Failed to download file: {attachment_data.remote_url}")
            return []

        # Handle PDF files - convert to images
        if file_type == "pdf":
            images = convert_from_bytes(
                file_content, first_page=1, last_page=page_count
            )

            # Convert each image to base64
            image_list = []
            for img in images:
                buffer = io.BytesIO()
                img.save(buffer, format=IMAGE_FILE_TYPE, optimize=True)
                image_list.append(base64.b64encode(buffer.getvalue()).decode())

            logger.info(
                f"PDF converted to {len(image_list)} images (page_limit={page_count})"
            )
            return image_list

        # Handle direct image files (JPG, PNG, JPEG)
        elif file_type in ["jpg", "jpeg", "png"]:
            # Already an image, just encode to base64
            image_base64 = base64.b64encode(file_content).decode()
            logger.info(f"Image file ({file_type}) encoded directly")
            return [image_base64]

        else:
            logger.warning(f"Unsupported file type for vision extraction: {file_type}")
            return []

    except Exception as e:
        logger.error(f"Document image processing error (type={file_type}): {str(e)}")
        return []


def prepare_input_data(
    email_data: any, attachment_data: any, tool_runtime: dict, use_vision: bool = False
) -> Dict[str, Any]:
    """
    Prepare input data for extraction by formatting email and attachment content.

    Args:
        email_data (any): Email data containing subject, body, and metadata
        attachment_data (any): Attachment data containing content and metadata
        tool_runtime (dict): Tool runtime context
        use_vision (bool): If True, excludes attachment content (images will be used instead)

    Returns:
        Dict[str, Any]: Formatted input data with extraction text and metadata
    """
    # Extract email fields with fallbacks
    email_subject = (
        f"**Email Subject:**\n{email_data.subject}"
        if email_data and email_data.subject
        else ""
    )
    email_body = (
        f"**Email Body:**\n{email_data.email_body}"
        if email_data and email_data.email_body
        else ""
    )

    # Format attachment content (exclude if using vision - images will be sent instead)
    attachment_content = ""
    if attachment_data and attachment_data.content and not use_vision:
        attachment_content = (
            f"**Attachment Content:**\n```\n{attachment_data.content[0].strip()}\n```"
        )

    # Combine all fields
    text_data = f"{email_subject}\n\n{email_body}\n\n{attachment_content}"

    # Build metadata dictionary
    metadata = {
        "sender_email": email_data.email_id if email_data else "",
        "mailbox_email": email_data.mailbox_email if email_data else "",
        "mailbox_folder": email_data.mailbox_folder if email_data else "",
        "email_subject": email_data.subject if email_data else "",
        "email_received_at": email_data.received_at if email_data else None,
        "email_created_at": email_data.created_at if email_data else None,
        "email_file_url": (
            email_data.additional_data.get("remote_url", "")
            if email_data and email_data.additional_data is not None
            else ""
        ),
        "attachment_file_url": attachment_data.remote_url if attachment_data else "",
        "current_utc_datetime": datetime.now().isoformat(),
        "task_id": tool_runtime.get("task_id", ""),
        "email_uuid": tool_runtime.get("email_uuid", ""),
        "agent_id": tool_runtime.get("agent_id", ""),
    }
    return {"text_data": text_data, "metadata": metadata}
