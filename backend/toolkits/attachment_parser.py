# Custom libraries
from logger import configure_logging
from toolkits.shared_utils import validate_uuid, get_attachment
from utils.document_file import DocumentFile

# Database modules
from db_pool import DatabasePoolManager

# Default libraries
from typing import Dict
import asyncio
import json
import os
import tempfile


logger = configure_logging(__name__)


class AttachmentParser:
    """
    Handles attachment parsing using VisionParser.
    """

    def __init__(self, organization_schema: str):
        """
        Initializes AttachmentParser with organization schema.

        Args:
            organization_schema (str): Schema identifier for the organization
        """
        self.organization_schema = organization_schema
        self.db_pool = DatabasePoolManager()

    def vision_parse_attachment(self, tool_runtime: Dict, attachment_id: str) -> str:
        """
        Parse an attachment using VisionParser and return extracted data.

        Args:
            tool_runtime (Dict): Tool runtime context containing task_id, etc
            attachment_id (str): UUID of the attachment to parse

        Returns:
            str: Extracted data wrapped in code block, or error response as JSON string
        """
        task_id = tool_runtime.get("task_id", "unknown")

        logger.info(
            f"[vision_parse_attachment] Started | task_id={task_id}, "
            f"attachment_id={attachment_id}, org_schema={self.organization_schema}"
        )

        try:
            # Validate attachment_id UUID early (before any DB operations)
            attachment_uuid, error = validate_uuid(attachment_id, "attachment_id")
            if error or not attachment_uuid:
                logger.error(f"[task_id={task_id}] Invalid attachment_id: {error}")
                return json.dumps({"error": error}, ensure_ascii=False)

            logger.info(
                f"[task_id={task_id}] vision_parse_attachment_started: "
                f"tool=vision_parse_attachment, attachment_uuid={attachment_id}"
            )

            # Get attachment data
            with self.db_pool.get_session(self.organization_schema) as db:
                attachment_data = get_attachment(db, attachment_uuid)
                if not attachment_data:
                    raise Exception(f"Attachment '{attachment_id}' not found.")

                # Download attachment file
                document_file = DocumentFile(
                    organization_schema=self.organization_schema
                )
                file_content = document_file.download_file(
                    file_path=attachment_data.remote_url
                )
                if not file_content:
                    return json.dumps(
                        {"error": "Failed to download attachment file for parsing."},
                        ensure_ascii=False,
                    )

                # Write attachment file to temp file
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_file_path = os.path.join(temp_dir, attachment_data.file_name)
                    with open(temp_file_path, "wb") as f:
                        f.write(file_content)

                    # Run VisionParser to parse the attachment file
                    from parsers.vision_parser import VisionParser

                    vision_parser = VisionParser(
                        organization_schema=self.organization_schema,
                        db=db,
                        mode="parsing",
                    )
                    parser_output = asyncio.run(
                        vision_parser.parse_file(
                            file_path=temp_file_path,
                        )
                    )
                    if not parser_output:
                        return json.dumps(
                            {"error": "Attachment parsing failed."}, ensure_ascii=False
                        )

                    logger.info(
                        f"[task_id={task_id}] vision_parse_attachment_completed: "
                        f"tool=vision_parse_attachment, status=SUCCESS"
                    )

                    content = "\n\n".join(parser_output.extracted_data) if parser_output.extracted_data else ""
                    return f"```\n{content}\n```"

        except Exception as e:
            logger.error(
                f"[task_id={task_id}] vision_parse_attachment_completed: "
                f"tool=vision_parse_attachment, status=FAILED, error={str(e)}"
            )
            return json.dumps(
                {"error": f"Error while parsing attachment: {str(e)}"},
                ensure_ascii=False,
            )


if __name__ == "__main__":
    tool_runtime = {
        "organization_schema": "public",
    }

    # Initialize the AttachmentParser
    organization_schema = tool_runtime.get("organization_schema", "public")
    attachment_parser = AttachmentParser(organization_schema)

    # Test: Parse Attachment
    print("\n --- Testing vision_parse_attachment ---")
    result = attachment_parser.vision_parse_attachment(
        tool_runtime, "01a41722-aaf5-45cc-97fb-c84f2f9284ec"
    )
    print(result)
