# Custom libraries
from logger import configure_logging
from integrations.office_365.outlook import Outlook
from parsers.pdf_parser import PDFParser
from parsers.csv_parser import CSVParser
from parsers.rotation_handler import RotationHandler
from schemas.parsed_document_schema import ParsedDocument
from utils.common_utils import generate_short_id
from utils.document_file import DocumentFile
from utils.schema_utils import get_current_schema

# Database modules
from repository.attachment_repository import AttachmentRepository
from schemas.attachment_schema import AttachmentDetail

# Default libraries
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
from typing_extensions import deprecated
from uuid import UUID
import base64
import io
import os
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import shutil
import time
import tempfile
import json

# Installed libraries
from dotenv import load_dotenv
from fastapi import HTTPException
from pdf2image import convert_from_bytes
from PIL import Image
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import fitz

logger = configure_logging(__name__)

load_dotenv()


class Attachment:
    """
    A class to handle processing of attachments, supporting file types
    such as PDF, DOC, and DOCX.

    Attributes:
        db (Session, optional): Database session used for storing or querying attachment-related data.
        scope (str): The OAuth2 scope required for accessing Microsoft Graph API.
        allowed_extensions (list): A list of permitted file extensions for attachments.
        graph_api_url (str): URL template for fetching attachments via Microsoft Graph API.
    """

    def __init__(self, db: Session = None):
        self.db = db
        self.scope = "https://graph.microsoft.com/.default"
        self.allowed_extensions = [
            "pdf",
            "doc",
            "docx",
        ]
        self.graph_api_url = (
            "https://graph.microsoft.com/v1.0/users/{}/messages/{}/attachments"
        )
        self.organization_schema = get_current_schema(self.db)
        self.document_file = DocumentFile(organization_schema=self.organization_schema)

    def _clean_up(self, local_path: str) -> bool:
        """
        Remove the specified local file or folder.

        Args:
            local_path (str): Path to file or folder to clean up

        Returns:
            bool: True if cleanup was successful, False otherwise
        """
        try:
            if os.path.exists(local_path):
                if os.path.isfile(local_path):
                    os.remove(local_path)
                elif os.path.isdir(local_path):
                    shutil.rmtree(local_path)
                return True
            return True
        except Exception as e:
            logger.error(f"Failed to clean up {local_path}: {e}")
            return False

    def _download_single_attachment(
        self, attachment: dict, local_dir: str
    ) -> Optional[str]:
        """
        Downloads a single attachment from the message and saves it locally.
        This method ensures only allowed file types and saves them to the specified directory
        with a unique filename to ensure uniqueness.

        Args:
            attachment (dict): A dictionary containing the attachment metadata returned by MS Graph API.
            local_dir (str): The local directory path where the attachment should be saved.

        Returns:
            Optional[str]: The local file path where the attachment was saved, or `None`
            if the file type is not allowed or already exists.
        """
        # Generate unique filename using os.path
        file_name, file_ext = os.path.splitext(attachment["name"])
        file_type = file_ext.lower().lstrip(".")
        clean_name = re.sub(r"[^A-Za-z0-9]+", "_", file_name).strip("_")
        clean_name = clean_name[:50]  # Limit to 50 characters
        attachment["name"] = f"{clean_name}_{generate_short_id(5)}.{file_type}"
        attachment_path = os.path.join(local_dir, attachment["name"])

        # Save if the file has an allowed file type and doesn't already exist
        if file_type in self.allowed_extensions and not os.path.exists(attachment_path):
            decoded_data = base64.b64decode(attachment["contentBytes"])
            with open(attachment_path, "wb") as file:
                file.write(decoded_data)
            return attachment_path

        return None

    def _format_data(
        self,
        message_data: dict,
        attachment_data: dict,
        parsed: Optional[ParsedDocument] = None,
    ) -> dict:
        """
        Prepares and structures extracted attachment data for database insertion.

        Args:
            message_data (dict): Email metadata (email_uuid, message_id, conversation_id).
            attachment_data (dict): Attachment metadata (attachment_id/id, file_name, file_type, size, remote_url).
            parsed (ParsedDocument, optional): Parsed content from the file parser.

        Returns:
            dict: Structured dictionary for database insertion.
        """
        attachment_data = attachment_data or {}

        return {
            "email_data_id": message_data.get("email_uuid"),
            "external_id": attachment_data.get("attachment_id")
            or attachment_data.get("id"),
            "message_id": message_data.get("message_id"),
            "conversation_id": message_data.get("conversation_id"),
            "file_name": attachment_data.get("file_name"),
            "file_type": attachment_data.get("file_type"),
            "size": attachment_data.get("size"),
            "remote_url": attachment_data.get("remote_url"),
            "content": parsed.extracted_data if parsed else None,
        }

    def _get_attachment_items(self, message_data: dict) -> List[dict]:
        """
        Retrieves the list of attachment metadata for a given email message using Microsoft Graph API
        with automatic retry for transient failures.

        Args:
            message_data (dict): A dictionary containing required metadata for the email including:
                - mailbox_email (str): The email address of the mailbox.
                - message_id (str): The ID of the email message in Microsoft Outlook.

        Returns:
            List[dict]: A list of dictionaries, each representing metadata for an attachment
            (e.g., name, size, contentType, id).

        Raises:
            requests.exceptions.HTTPError: If the API request fails after retries.
            KeyError: If expected keys like "mailbox_email" or "message_id" are missing from message_data.
        """
        outlook = Outlook(self.db)
        outlook_token = outlook.get_outlook_token()

        # Create session with retry strategy
        session = requests.Session()
        retry_strategy = Retry(
            total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)

        response = session.get(
            self.graph_api_url.format(
                message_data["mailbox_email"], message_data["message_id"]
            ),
            headers={"Authorization": f"Bearer {outlook_token}"},
        )
        response.raise_for_status()
        return response.json()["value"]

    def extract_data(
        self, file_path: str, polling_config: dict
    ) -> Optional[ParsedDocument]:
        """
        Extracts data from an attachment file based on its file extension.

        Args:
            file_path (str): The full path to the file to be processed.
            polling_config: Configuration object used during parsing.

        Returns:
            Optional[ParsedDocument]: Parsed content, or None on failure.
        """
        try:
            extension = file_path.split(".")[-1].lower()

            if (
                extension == "pdf"
                and os.environ.get("SERVICE_TYPE") == "attachment-worker"
            ):
                from parsers.pdf_parser import PDFParser

                return PDFParser(
                    file_path,
                    self.organization_schema,
                    db=self.db,
                    polling_config=polling_config,
                ).extract_pdf_data()

            elif extension == "md":
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return ParsedDocument(
                    input_file=file_path,
                    extracted_data=[content],
                )

            elif extension == "csv":
                return CSVParser(file_path).extract_csv_data()

            elif (
                extension in ("docx", "pptx", "xlsx")
                and os.environ.get("SERVICE_TYPE") == "attachment-worker"
            ):
                from parsers.office_365_parser import Office365Parser

                return Office365Parser(file_path).extract_office_data()

            else:
                return ParsedDocument(
                    input_file=file_path,
                    extracted_data=[f"Unsupported file format '{extension}'"],
                )

        except Exception as e:
            logger.error(f"Data extraction error {file_path}: {e}")
            return ParsedDocument(
                input_file=file_path,
                extracted_data=[f"Error: {e}"],
            )

    def get_attachment_details(
        self, db: Session, attachment_identifier: Union[UUID, str]
    ) -> Optional[AttachmentDetail]:
        """
        Retrieve and return details of a saved attachment from the database.
        If the file is a PDF and stored remotely, it will be temporarily downloaded
        to generate page previews as base64-encoded images.

        Args:
            db (Session): SQLAlchemy database session.
            attachment_identifier (Union[UUID, str]): The unique identifier for the attachment.

        Returns:
            Optional[AttachmentDetail]: An object containing metadata and content
            of the attachment, including base64-encoded pages for PDFs.

        Raises:
            HTTPException: If the attachment does not exist in the database.
        """
        attachment_repository = AttachmentRepository(db)
        existing_attachment = attachment_repository.get_attachment_by_id(
            attachment_identifier
        )
        if not existing_attachment:
            raise HTTPException(
                status_code=404, detail="Attachment not found. Please check and retry."
            )

        # Generate base64-encoded images for PDF attachments
        if existing_attachment.file_type == "pdf" and existing_attachment.remote_url:
            file_content = self.document_file.download_file(
                file_path=existing_attachment.remote_url
            )

            if file_content:
                document_pages = self.get_pdf_images_from_bytes(file_content)
                attachment_details = AttachmentDetail.model_validate(
                    existing_attachment
                )
                attachment_details.document_pages = document_pages
                return attachment_details
            else:
                logger.error(
                    f"Failed to download PDF file: {existing_attachment.remote_url}"
                )

        return AttachmentDetail.model_validate(existing_attachment)

    def get_pdf_images_from_bytes(
        self, pdf_bytes: bytes, max_pages: int = 100
    ) -> List[str]:
        """
        Convert PDF pages into base64-encoded JPEG images using pdf2image for better performance.

        Args:
            pdf_bytes (bytes): PDF file content as bytes.
            max_pages (int): Maximum number of pages to convert.

        Returns:
            List[str]: A list of base64-encoded image strings, one for each page.
        """
        logger.info("Converting PDF to images from bytes using pdf2image")

        try:
            # Convert PDF to images with optimized settings
            images = convert_from_bytes(
                pdf_bytes,
                first_page=1,
                last_page=max_pages,  # Limit pages for performance
                fmt="jpeg",  # JPEG is smaller than PNG
                dpi=200,  # Balanced quality/performance
                thread_count=4,  # Parallel processing
                use_pdftocairo=True,  # Faster backend if available
            )

            base64_list = []
            for img in images:
                # Convert PIL image to base64 with compression
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85, optimize=True)
                img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
                base64_list.append(img_base64)

                # Clean up immediately to save memory
                buffer.close()

            logger.info(f"Converted {len(base64_list)} pages to images")
            return base64_list

        except Exception as e:
            logger.error(f"Error converting PDF to images: {e}")
            # Fallback to empty list rather than crashing
            return []

    def has_attachments(self, message_data: dict) -> dict:
        """
        Checks whether a specified email message has any allowed attachments using Microsoft Graph API.

        Args:
            message_data (dict): A dictionary containing the following required keys:
                - email_uuid (str): Internal unique identifier for the email.
                - mailbox_email (str): The email address of the mailbox.
                - message_id (str): The ID of the email message in Microsoft Outlook.
                - conversation_id (str): Identifier for the email thread in Microsoft Outlook.

        Returns:
            dict: A dictionary containing:
                - has_attachments (bool): True if allowed attachments are found, False otherwise.
                - count (int): Number of allowed attachments.
                - total_size (int): Total size of allowed attachments in bytes.

        Raises:
            ValueError: If any of the required keys are missing from the input dictionary.
            Logs errors in case of request or API issues and safely returns a dict with False/0 values.
        """
        required_keys = ["email_uuid", "mailbox_email", "message_id", "conversation_id"]
        missing_keys = [key for key in required_keys if key not in message_data]
        if missing_keys:
            raise ValueError(f"Missing required data: {', '.join(missing_keys)}")

        outlook = Outlook(self.db)
        outlook_token = outlook.get_outlook_token()
        try:
            response = requests.get(
                self.graph_api_url.format(
                    message_data["mailbox_email"], message_data["message_id"]
                ),
                headers={"Authorization": f"Bearer {outlook_token}"},
            )
            response.raise_for_status()
            attachments = response.json()["value"]
            if not attachments:
                return {"has_attachments": False, "count": 0, "total_size": 0}

            allowed_attachments = []
            total_size = 0
            for attachment in attachments:
                file_name, file_ext = os.path.splitext(attachment["name"])
                file_type = file_ext.lower().lstrip(".")
                if file_type in self.allowed_extensions:
                    total_size += attachment.get("size", 0)
                    allowed_attachments.append(file_name)

            return {
                "has_attachments": bool(allowed_attachments),
                "count": len(allowed_attachments),
                "total_size": total_size,
            }
        except Exception as e:
            logger.error(f"Error checking attachments: {e}")
            return {"has_attachments": False, "count": 0, "total_size": 0}

    def stage_attachments(self, message_data: dict) -> list[str]:
        """
        Stage attachments for parsing: download, enforce PDF page limits, split PDFs, upload each part,
        and create/update a DB row per part (without parsed content). Returns list of staged attachment IDs.

        This moves heavy orchestration out of the Celery worker to keep tasks thin and testable.
        """
        required_keys = [
            "email_uuid",
            "mailbox_email",
            "message_id",
            "conversation_id",
            "timestamp",
            "data_store",
            "polling_config",
        ]
        missing_keys = [key for key in required_keys if key not in message_data]
        if missing_keys:
            raise ValueError(f"Missing required data: {', '.join(missing_keys)}")

        staged_ids: list[str] = []
        total_parts = 0
        polling_config = message_data.get("polling_config", {})
        start_time = time.time()

        # Create local directory for downloads before try block
        local_dir = os.path.join("/data/emails", str(message_data["email_uuid"]))
        os.makedirs(local_dir, exist_ok=True)

        try:
            # Fetch attachment items from Outlook
            attachment_items = self._get_attachment_items(message_data)
            if not attachment_items:
                return staged_ids

            attachment_repo = AttachmentRepository(self.db)

            for idx, item in enumerate(attachment_items, 1):
                file_size_kb = item.get("size", 0) / 1024
                logger.info(
                    f"Staging attachment {idx}/{len(attachment_items)}: file={item.get('name', 'unknown')}, size={file_size_kb:.0f}KB, type={item.get('contentType', 'unknown')}, pages=unknown"
                )

            for item in attachment_items:
                # Download original locally (respects allowed extensions)
                local_path = self._download_single_attachment(item, local_dir)
                if not local_path:
                    continue

                file_name = os.path.basename(local_path)
                ext = file_name.split(".")[-1].lower()

                part_paths = [local_path]
                if ext == "pdf":
                    try:
                        # Validate PDF structure first (always check, not conditional)
                        with fitz.open(local_path) as doc:
                            page_count = len(doc)

                        # Skip invalid/empty PDFs
                        if page_count == 0:
                            logger.error(
                                f"Skipping invalid PDF (0 pages): {file_name}, size={os.path.getsize(local_path)}B"
                            )
                            continue  # Skip to next attachment

                        logger.info(
                            f"PDF validated: file={file_name}, pages={page_count}"
                        )

                        pdf_parser = PDFParser(
                            local_path,
                            self.organization_schema,
                            db=self.db,
                            polling_config=polling_config,
                        )
                        max_pages = polling_config.get("max_pdf_pages", 0)

                        # Strip PDF if max_pdf_pages is configured
                        if max_pages and max_pages > 0:
                            stripped_path = (
                                pdf_parser.strip_pdf_file(local_path, max_pages)
                                or local_path
                            )

                            with fitz.open(stripped_path) as doc:
                                kept_pages = len(doc)

                            stripped = page_count > kept_pages
                            logger.info(
                                f"PDF stripping: file={file_name}, original_pages={page_count}, max_pages={max_pages}, stripped={str(stripped).lower()}{f', kept_pages={kept_pages}' if stripped else ''}"
                            )
                        else:
                            stripped_path = local_path

                        # Apply rotation correction BEFORE splitting
                        processed_path = stripped_path
                        if polling_config.get("fix_page_rotation", True):
                            rotation_handler = RotationHandler()
                            ocr_page_limit = polling_config.get("ocr_page_limit")

                            success = rotation_handler.handle_pdf_rotation(
                                stripped_path, page_limit=ocr_page_limit
                            )

                            if not success:
                                logger.warning(
                                    f"Rotation correction failed for {file_name}, continuing with original"
                                )

                        # Split PDF only if split_pdf_pages is enabled
                        if polling_config.get("split_pdf_pages", False):
                            part_paths = pdf_parser.split_pdf_file(processed_path)
                            blank_count = (
                                len(part_paths) - 1 if len(part_paths) > 1 else 0
                            )
                            logger.info(
                                f"PDF splitting: file={file_name}, blank_pages_found={blank_count}, split_parts={len(part_paths)}"
                            )
                        else:
                            part_paths = [processed_path]
                    except Exception as e:
                        logger.error(f"Cannot process PDF {file_name}: {e}")
                        continue  # Skip corrupted PDFs instead of staging them

                parts_count = len(part_paths)
                for idx, part in enumerate(part_paths, start=1):
                    # Upload to configured data store
                    upload_name = os.path.basename(part)
                    upload_path = os.path.join(
                        message_data["data_store"]["storage_folder"],
                        upload_name,
                    )
                    remote_url = self.document_file.upload_file(
                        data_store=message_data["data_store"],
                        file_path=part,
                        upload_path=upload_path,
                    )

                    # External id and part suffix
                    part_suffix = f"_{idx}" if parts_count > 1 else ""
                    external_id = f"{item.get('id')}{part_suffix}"

                    # Stage DB row (no parsed content yet) using unified formatter
                    staged_size = (
                        os.path.getsize(part)
                        if os.path.exists(part)
                        else item.get("size", 0)
                    )
                    # Use unified formatter with optional fields (no extracted content at staging)
                    attachment_info = {
                        "attachment_id": external_id,
                        "file_name": os.path.basename(part),
                        "file_type": ext,
                        "size": staged_size,
                        "remote_url": remote_url,
                    }
                    formatted_data = self._format_data(
                        message_data, attachment_info, None
                    )
                    saved_attachment = attachment_repo.create_or_update_attachment(
                        formatted_data
                    )

                    if saved_attachment:
                        # Collect DB UUID for downstream parse task
                        staged_ids.append(str(saved_attachment.id))
                        total_parts += 1
                        logger.info(
                            f"Attachment saved: file={os.path.basename(part)}, attachment_id={saved_attachment.id}"
                        )

            # Clean up conversation folder
            self._clean_up(local_dir)

            # Staging completed summary
            elapsed_time = time.time() - start_time
            total_size_kb = sum(item.get("size", 0) for item in attachment_items) / 1024
            logger.info(
                f"Staging completed: total_attachments={len(attachment_items)}, total_parts={total_parts}, total_size={total_size_kb:.0f}KB, time={elapsed_time:.2f}s"
            )

            return staged_ids
        except Exception as e:
            logger.error(f"Error staging attachments: {e}")
            # Clean up partial work on complete failure
            self._clean_up(local_dir)
            return []

    def parse_attachment(
        self, attachment_uuid: UUID, polling_config: Optional[dict] = None
    ) -> dict:
        """
        Parse a single staged attachment (by id or attachment_id). Downloads from remote storage,
        runs extraction pipeline and updates the DB row with parsed content.

        Returns dict with file_name and email_uuid on success, raises Exception on failure.
        """
        # Accept UUIDs passed either as objects or strings to handle Celery serialization.
        if isinstance(attachment_uuid, str):
            try:
                attachment_uuid = UUID(attachment_uuid)
            except ValueError:
                pass

        attachment_repo = AttachmentRepository(self.db)
        attachment_data = attachment_repo.get_attachment_by_id(attachment_uuid)
        if not attachment_data:
            raise Exception("attachment_not_found")

        file_name = attachment_data.file_name
        remote_url = attachment_data.remote_url

        logger.info(
            f"Parsing attachment: attachment_id={attachment_uuid}, file={file_name}"
        )

        # Download content and write to a temp file
        file_bytes = self.document_file.download_file(file_path=remote_url)
        if not file_bytes:
            raise Exception("download_failed")

        # Standardized temp path: /data/attachments/{attachment_uuid}
        local_dir = os.path.join("/data/attachments", str(attachment_uuid))
        os.makedirs(local_dir, exist_ok=True)
        temp_path = os.path.join(local_dir, file_name)

        try:
            with open(temp_path, "wb") as f:
                f.write(file_bytes)

            # Disable re-splitting
            effective_config = dict(polling_config or {})
            effective_config["split_pdf_pages"] = False

            # Extract data from document
            parsed_result = self.extract_data(temp_path, effective_config)
            if not parsed_result:
                raise Exception("no_parsed_output")

            update_payload = {
                "content": parsed_result.extracted_data,
            }
            updated_attachment = attachment_repo.update_attachment(
                attachment_uuid, update_payload
            )
            if not updated_attachment:
                raise Exception("update_failed")

            # Success case - return only what's needed
            return {
                "status": "SUCCESS",
                "attachment_uuid": updated_attachment.id,
            }
        finally:
            # Cleanup temp folder for this attachment
            self._clean_up(local_dir)

    async def stream_pdf_pages(
        self, pdf_bytes: bytes, max_pages: int = 100
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streams PDF pages as base64-encoded JPEG images one at a time.

        Args:
            pdf_bytes (bytes): PDF file content as bytes.
            max_pages (int): Maximum number of pages to convert.

        Yields:
            Dict: Dict containing page number, total_pages and base64-encoded image.
        """
        try:
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            total_pages = (
                pdf_document.page_count
                if pdf_document.page_count <= max_pages
                else max_pages
            )

            for page_number in range(total_pages):
                page = pdf_document.load_page(page_number)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85, optimize=True)
                img_bytes = buffer.getvalue()
                img_base64 = base64.b64encode(img_bytes).decode("utf-8")

                # Construct streaming payload
                yield {
                    "page_number": page_number + 1,
                    "total_pages": total_pages,
                    "image": img_base64,
                }

            pdf_document.close()
            logger.info(f"Completed streaming {total_pages} pages")

        except Exception as e:
            logger.error(f"Error in stream_pdf_pages: {e}")
            yield {"type": "error", "message": f"Error converting PDF: {str(e)}"}
