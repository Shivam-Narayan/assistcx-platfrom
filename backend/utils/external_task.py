# Custom libraries
from integrations.office_365.attachment import Attachment
from integrations.aws.aws_s3 import AWSS3
from integrations.file_system.file_system import FileSystem
from utils.document_file import DocumentFile
from utils.task_utils import update_email_status
from utils.email_events import create_email_event, EmailEventType

# Default libraries
from datetime import datetime
from typing import Optional, List
from fastapi import HTTPException
import base64
import os
import requests
import re
import shutil
import sys
import uuid


# Database modules
from logger import configure_logging
from repository.email_repository import EmailRepository
from repository.attachment_repository import AttachmentRepository
from repository.user_repository import UserRepository
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from schemas.email_schema import EmailDetail
from schemas.external_task_schema import ExternalTaskCreate
from schemas.attachment_schema import AttachmentDetail

# Installed libraries
from celery_worker import celery
from dotenv import load_dotenv
from sqlalchemy import func


load_dotenv()
logger = configure_logging(logger_name=__name__)


class ExternalTask:
    """
    A class for interacting with the external system for creating an email task.
    """

    def __init__(self, db: Session, organization_schema: str):
        self.allowed_extensions = [
            "csv",
            "docx",
            "pdf",
            "pptx",
            "xlsx",
        ]
        self.db = db
        self.organization_schema = organization_schema

    # NOTE: _parse_and_save_task is renamed to _create_email_entry
    def _create_task_entry(self, external_task_data: dict) -> Optional[EmailDetail]:
        """Creates a new email record in the database and returns the saved email object."""
        try:
            sender_email_id = external_task_data.get("sender_email_id")
            user_repo = UserRepository(self.db)
            user = (
                user_repo.get_user_by_id(sender_email_id) if sender_email_id else None
            )
            sender_name = "External Sender"
            if user and (user.first_name or user.last_name):
                sender_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

            message_data = {
                "email_id": sender_email_id,
                "message_id": str(uuid.uuid4()),
                "conversation_id": str(uuid.uuid4()),
                "mailbox_email": external_task_data.get("receiver_email"),
                "mailbox_folder": external_task_data.get("receiver_folder"),
                "subject": external_task_data.get("task_title"),
                "received_at": func.now(),
                "sender_name": sender_name,
                "email_body": external_task_data.get("task_body"),
                "records": external_task_data.get("task_records"),
                "agent_id": external_task_data.get("agent_id"),
                "source_type": "external_task",
            }

            # Save to the database using the repository
            email_repository = EmailRepository(self.db)
            saved_email = email_repository.create_email(message_data)
            if saved_email:
                # Create email event
                create_email_event(
                    self.db, saved_email.id, EmailEventType.EMAIL_FETCH_SUCCESSFUL
                )
                logger.info(
                    f"Email data saved in the database. Email UUID: {saved_email.id}"
                )
                return EmailDetail.model_validate(saved_email)
            else:
                logger.error(f"Failed to save email data in the database.")
                return None

        except SQLAlchemyError as e:
            logger.error(f"Error occurred during database operation: {e}")
            return None

    def _extract_attachment(self, file_type, file_path, data_store, task_configs):
        """
        Process an individual attachment file, upload processed files to S3, and return parsed data along with S3 URLs.
        """

        if file_type in self.allowed_extensions:
            attachment = Attachment(self.db)
            parsed = attachment.extract_data(
                file_path=file_path, polling_config=task_configs
            )
            if not parsed:
                return None

            document_file = DocumentFile(organization_schema=self.organization_schema)
            remote_url = document_file.upload_file(
                data_store=data_store,
                file_path=parsed.input_file,
                upload_path=f"{data_store['storage_folder']}/{os.path.basename(parsed.input_file)}",
            )

            return {
                "input_file": parsed.input_file,
                "attachment_content": parsed.extracted_data,
                "remote_url": remote_url,
            }
        else:
            return None

    def _process_and_save_attachments(
        self,
        task_attachments,
        email_uuid,
        message_id,
        conversation_id,
        timestamp,
        data_store,
        task_configs,
    ):
        """
        Downloads, decodes, and processes attachments for a task, then saves them to the database.
        Returns a list of processed attachment details with remote URLs and OCR data.
        """
        try:
            # Create the folder if it doesn't exist
            folder_path = os.path.join("data", conversation_id)
            os.makedirs(folder_path, exist_ok=True)

            downloaded_files = []

            # Iterate through each URL
            for task_attachment in task_attachments:
                logger.info(
                    f"Downloading attachment from {task_attachment['file_name']}"
                )
                # Convert timestamp to custom format "YYYY_MM_DD_HH_MM" and combine with file name
                date_time = timestamp.strftime("%Y%m%d_%H%M%S")
                file_name = re.sub(
                    r"\.(?=\w+\.)", "", task_attachment["file_name"].replace(" ", "_")
                )
                filename = f"{date_time}_{file_name}"
                file_path = os.path.join(folder_path, filename)

                # Check if raw document content is a url or base64 encoded data
                if task_attachment["content"].startswith("https"):
                    try:
                        # Send a GET request to the URL
                        response = requests.get(task_attachment["content"])
                        if response.status_code == 200:
                            # Write the file to the specified folder
                            with open(file_path, "wb") as file:
                                file.write(response.content)

                            # Append the downloaded file path to the list
                            downloaded_files.append(file_path)
                            logger.info(f"Downloaded {filename}")
                        else:
                            logger.error(
                                f"Failed to download file from url {task_attachment['content']}. Status code: {response.status_code}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Failed to download file from url {task_attachment['content']}: {str(e)}"
                        )
                else:
                    try:
                        # Decode and save the attachment data to a file
                        decoded_data = base64.b64decode(task_attachment["content"])
                        with open(file_path, "wb") as file:
                            file.write(decoded_data)

                        # Append the downloaded file path to the list
                        downloaded_files.append(file_path)
                        logger.info(f"Downloaded {filename}")
                    except Exception as e:
                        logger.error(
                            f"Failed to decode base64 data {task_attachment['content']}: {str(e)}"
                        )

            attachment_list = []

            for file in downloaded_files:
                processed_attachment = self._extract_attachment(
                    file_type=file.split(".")[-1].lower(),
                    file_path=file,
                    data_store=data_store,
                    task_configs=task_configs,
                )

                if processed_attachment:
                    attachment_data = {
                        "email_data_id": email_uuid,
                        "external_id": str(uuid.uuid4()),
                        "message_id": message_id,
                        "conversation_id": conversation_id,
                        "file_name": processed_attachment["input_file"].split("/")[-1],
                        "file_type": processed_attachment["input_file"]
                        .split(".")[-1]
                        .lower(),
                        "size": os.path.getsize(processed_attachment["input_file"]),
                        "remote_url": processed_attachment["remote_url"],
                        "content": processed_attachment["attachment_content"],
                    }

                    try:
                        attachment_repository = AttachmentRepository(self.db)
                        saved_attachment = (
                            attachment_repository.create_or_update_attachment(
                                attachment_data
                            )
                        )
                        if saved_attachment:
                            logger.info(
                                f"Attachment data saved for email: {email_uuid}"
                            )
                            attachment_list.append(
                                AttachmentDetail.model_validate(saved_attachment)
                            )
                        else:
                            logger.error(
                                f"Failed to save attachment for email: {email_uuid}"
                            )

                    except SQLAlchemyError as e:
                        logger.error(f"Error in saving attachment data: {e}")

            # Delete local attachment files
            shutil.rmtree(folder_path)
            logger.info("Cleaned attachment files from local folder")
            return attachment_list

        except Exception as e:
            logger.info(
                f"Error downloading file from {task_attachment['content']}: {e}"
            )
            return []

    def process_task(self, external_task_data: dict) -> Optional[EmailDetail]:
        """Processes the incoming task email, saves it to the database, and returns the saved message."""
        try:
            started_at = datetime.now()
            saved_message = self._create_task_entry(external_task_data)

            if not saved_message:
                return None

            logger.info(f"Saved message: {saved_message.id}")

            update_email_status(self.db, saved_message.id, "EXECUTING")

            return saved_message

        except HTTPException:
            # Re-raise HTTPExceptions to preserve error details
            raise
        except Exception as e:
            logger.error(f"Error occurred during email processing: {e}")
            return None

    def process_documents(
        self, external_task_data: dict, saved_message: dict
    ) -> Optional[List[AttachmentDetail]]:
        """
        Processes and downloads attachments for a given task, saving them to the configured data store.
        Returns a list of processed attachment details or None if processing fails.
        """
        try:
            logger.info(f"Starting attachment processing for {saved_message.get('id')}")

            if not external_task_data.get("task_attachments"):
                logger.info(
                    f"Skipping attachment processing for {saved_message.get('id')}"
                )
                return

            if not external_task_data.get("data_store"):
                logger.error(
                    "data_store is required for attachment processing. Please check and retry."
                )
                return None

            started_at = datetime.now()

            attachment_output = self._process_and_save_attachments(
                task_attachments=external_task_data["task_attachments"],
                email_uuid=saved_message.get("id"),
                message_id=saved_message.get("message_id"),
                conversation_id=saved_message.get("conversation_id"),
                timestamp=saved_message.get("created_at"),
                data_store=external_task_data["data_store"],
                task_configs=external_task_data["task_configs"],
            )

            logger.info(
                f"Processed {len(attachment_output)} attachments for email task: {saved_message.get('id')}"
            )

            return attachment_output

        except Exception as e:
            logger.error(f"Error in attachment processing: {e}")
            return None

    def external_task_handler(self, external_task_data: dict) -> dict:
        """
        Process the external task data and send it to the appropriate worker.
        args:
            external_task_data: dict
        returns:
            message: dict
        raises:
            HTTPException: If task processing or worker queueing fails
        """
        try:
            saved_message = self.process_task(external_task_data)

            if not saved_message:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create task entry. Please check logs and retry.",
                )

            if external_task_data.get("task_attachments"):
                worker_data = {
                    "saved_message": saved_message.model_dump(),
                    "external_task_data": external_task_data,
                }
                # Create email event
                create_email_event(
                    self.db,
                    saved_message.id,
                    EmailEventType.ATTACHMENT_PROCESS_QUEUED,
                )
                celery.send_task(
                    "process_task_attachments",
                    args=[self.organization_schema, worker_data],
                    queue="attachment_queue",
                )
            else:
                celery.send_task(
                    "dispatch_task",
                    args=[self.organization_schema, saved_message.model_dump()["id"]],
                    queue="agent_queue",
                )
            return {"message": "New task added to the queue successfully."}
        except HTTPException:
            # Re-raise HTTPExceptions as-is
            raise
        except Exception as e:
            logger.error(f"Error in external_task_handler: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to process external task: {str(e)}"
            )
