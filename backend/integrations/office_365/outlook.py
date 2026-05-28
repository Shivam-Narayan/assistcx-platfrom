# Custom libraries
from logger import configure_logging
from schemas.email_schema import EmailDetail
from utils.crypto_utils import decrypt_string, encrypt_string
from utils.document_file import DocumentFile
from utils.environment import environment
from utils.schema_utils import get_current_schema

# Database modules
from repository.attachment_repository import AttachmentRepository
from repository.email_repository import EmailRepository
from repository.integration_repository import IntegrationRepository
from repository.mailbox_polling_repository import MailboxPollingRepository
from sqlalchemy.orm import Session

# Default libraries
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import base64
import json
import os

# Installed libraries
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import HTTPException
from requests.exceptions import HTTPError
from requests.structures import CaseInsensitiveDict
from sqlalchemy.exc import SQLAlchemyError
import fitz
import jwt
import html2text
import requests


load_dotenv()

logger = configure_logging(logger_name=__name__)


class Outlook:
    """
    Microsoft Outlook Integration Class for Email Operations

    Manages authentication, email retrieval, parsing, and manipulation
    using Microsoft Graph API with comprehensive error handling and logging.
    """

    def __init__(self, db: Session = None):
        """
        Initializes Outlook with db session configurations.

        Args:
            db (Session, optional): Database session for persistent operations. Defaults to None.
        """
        self.graph_url = "https://graph.microsoft.com/v1.0"
        self.db = db
        self.organization_schema = get_current_schema(self.db) if self.db else "public"
        self.outlook_token = self.get_outlook_token()

    def _clean_email_content(self, html_content: str):
        """
        Return clean and well formatted email content in text format.

        Args:
            html_content: HTML content to clean

        Returns:
            str: Clean and well formatted email content in text format
        """
        try:
            h = html2text.HTML2Text()
            h.body_width = 0
            h.ignore_images = True
            h.ignore_links = True
            h.single_line_break = True
            text = h.handle(html_content).strip()
            # Remove trailing spaces from each line
            return "\n".join(line.rstrip() for line in text.split("\n"))
        except Exception:
            # Fallback: use BeautifulSoup with manual line break handling
            soup = BeautifulSoup(html_content, "html.parser")
            # Replace <br> tags with \n before extracting text
            for br in soup.find_all("br"):
                br.replace_with("\n")
            return soup.get_text().strip()

    def _convert_html_to_pdf(self, html_content: str, output_path: str) -> None:
        """
        Convert HTML content to a PDF file using PyMuPDF.

        Args:
            html_content: HTML content to convert to PDF
            output_path: Path to save the PDF file
        """
        try:
            # Create a Story object from the HTML content
            story = fitz.Story(html=html_content)

            mediabox = fitz.paper_rect("a4")
            where = mediabox + (36, 36, -36, -36)
            writer = fitz.DocumentWriter(output_path)

            more = 1
            page_count = 0

            while more:
                # Begin a new page and draw the content
                device = writer.begin_page(mediabox)
                more, _ = story.place(where)
                story.draw(device)

                # Finish the page
                writer.end_page()

                # Safety check to prevent infinite loops
                page_count += 1
                if page_count > 100:  # Max 100 pages
                    logger.warning(f"PDF conversion stopped at max pages: {page_count}")
                    break

            # Close the writer to finalize the PDF
            writer.close()

            logger.info(f"Email PDF created successfully at {output_path}")

        except Exception as e:
            logger.error(f"Error in converting HTML to PDF: {e}")
            raise

    def _get_folder_id(self, email_id: str, folder_name: str) -> str:
        """
        Get the ID of the specified folder for a user email address.

        Args:
            email_id: Email address of the mailbox
            folder_name: Name of the folder to get the ID for

        Returns:
            str: ID of the specified folder for the user email address
        """
        try:
            # Define the API endpoint
            url = f"{self.graph_url}/users/{email_id}/mailFolders"

            # Define the headers
            headers = {
                "Authorization": f"Bearer {self.outlook_token}",
                "Content-Type": "application/json",
            }

            # Send a GET request to fetch the folders
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            folders = response.json().get("value", [])

            return next(
                (
                    folder.get("id")
                    for folder in folders
                    if folder.get("displayName").lower() == folder_name.lower()
                ),
                "",
            )

        except Exception as e:
            logger.error(f"Error in _get_folder_id: {e}")
            return ""

    def _refresh_outlook_token(self) -> Optional[str]:
        """
        Retrieves a new Outlook access token using stored integration credentials.

        Returns:
            Optional[str]: Outlook access token if successful, None otherwise
        """
        try:
            # Fetch environment data and Outlook credentials
            env = environment.get_environment(
                organization_schema=self.organization_schema
            )
            credentials = env.get("OUTLOOK")
            client_id = decrypt_string(credentials.get("CLIENT_ID"))
            client_secret = decrypt_string(credentials.get("CLIENT_SECRET"))
            tenant_id = decrypt_string(credentials.get("TENANT_ID"))

            # Retrieve integration details and authorization schema fields
            integration_repository = IntegrationRepository(self.db)
            integration = integration_repository.get_integration("outlook")
            auth_schema_fields = integration.auth_schema_fields
            headers = CaseInsensitiveDict(
                {"Content-Type": "application/x-www-form-urlencoded"}
            )

            # Prepare data for the token request
            data = (
                f"client_id={client_id}"
                f"&scope={auth_schema_fields['preset']['scope']}"
                f"&client_secret={client_secret}"
                f"&grant_type=client_credentials"
            )

            # Format the token URL with the tenant ID
            token_url = auth_schema_fields["preset"]["token_url"].format(
                tenant_id=tenant_id
            )
            response = requests.post(token_url, headers=headers, data=data)
            response.raise_for_status()

            if response.status_code == 200:
                # Extract and encrypt the new access token
                outlook_token = response.json().get("access_token")
                env["OUTLOOK"]["OUTLOOK_TOKEN"] = encrypt_string(outlook_token)

                # Update environment data in Redis
                environment.set_environment(
                    environment_data=env, organization_schema=self.organization_schema
                )
                logger.info("Outlook token updated successfully")
                return outlook_token
            else:
                logger.error("Failed to retrieve Outlook Token")
                return None

        except requests.exceptions.RequestException as e:
            # Log the error if the token request fails
            logger.error(f"Error while requesting Outlook token: {e}")
            return None

    def _save_email_pdf(
        self, email_data: dict, email_body: str, data_store: Optional[dict] = None
    ) -> Optional[str]:
        """
        Save the email data as a PDF file and upload it to data storage.

        Args:
            email_data: Dictionary containing email data
            email_body: HTML content of the email
            data_store: Dictionary containing data store configuration

        Returns:
            Optional[str]: Remote URL of the uploaded PDF file, None if failed
        """
        try:
            # Extract and clean the body content
            soup = BeautifulSoup(email_body, "html.parser")
            email_content = str(soup.body) if soup.body else str(soup)

            # Extract any existing styles
            existing_styles = soup.find_all("style")
            style_content = "\n".join(
                [style.string for style in existing_styles if style.string]
            )

            # Construct the email content for the PDF
            email_content = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; line-height: 1.6; }}
                    .email-header {{ background-color: #f0f0f0; padding: 20px; margin-bottom: 20px; border-bottom: 1px solid #ddd; }}
                    .email-header h1 {{ margin: 0; color: #333; font-size: 24px; }}
                    .email-metadata {{ margin-bottom: 20px; font-size: 14px; }}
                    .email-metadata p {{ margin: 5px 0; }}
                    .email-body {{ border-top: 1px solid #ddd; padding-top: 20px; }}
                    .label {{ font-weight: bold; color: #555; }}
                </style>
            </head>
            <body>
                <div class="email-metadata">
                    <p><span class="label">From:</span> {email_data['sender_name']} &lt;{email_data['email_id']}&gt;</p>
                    <p><span class="label">To:</span> {email_data['mailbox_email']}</p>
                    <p><span class="label">Date:</span> {email_data['received_at'].strftime("%Y-%m-%d %H:%M:%S")}</p>
                    <p><span class="label">Subject:</span> {email_data['subject']}</p>
                </div>
                <div class="email-body">
                    {email_content}
                </div>
            </body>
            </html>
            """

            # Define the local file path for the PDF file
            datetime = email_data["received_at"].strftime("%Y%m%d_%H%M%S_%f")
            sanitized_email = email_data["email_id"].replace("@", "_").replace(".", "_")
            file_name = f"{datetime}_{sanitized_email}.pdf"
            folder = "data"
            os.makedirs(folder, exist_ok=True)
            pdf_path = os.path.join(folder, file_name)

            # Create and save PDF from email content
            self._convert_html_to_pdf(email_content, pdf_path)

            # Upload the PDF file to the data_store and get the remote_url
            document_file = DocumentFile(organization_schema=self.organization_schema)
            remote_url = document_file.upload_file(
                data_store=data_store,
                file_path=pdf_path,
                upload_path=f"{data_store['storage_folder']}/{file_name}",
            )

            # Remove the local PDF file after uploading
            os.remove(pdf_path)

            # Return the S3 URL where the PDF is stored
            return remote_url

        except Exception as e:
            # General exception handler for unexpected errors
            logger.error(f"An error occurred in copy_email_data: {e}")
            return None

    def _write_delta_link(self, email_id: str, folder: str, delta_link: str) -> None:
        """
        Update the delta link in the mailbox_polling table for future delta queries.

        Args:
            email_id: Email address of the mailbox
            folder: Name of the folder to update the delta link for
            delta_link: Delta link to update
        """
        task_name = f"{email_id}|{folder}"
        update_data = {"task_name": task_name, "delta_link": delta_link}

        # Use the repository to create or update the mailbox polling entry
        mailbox_polling_repo = MailboxPollingRepository(self.db)
        polling_entry = mailbox_polling_repo.create_or_update_polling(
            task_name, update_data
        )

        if polling_entry is None:
            logger.error(f"Failed to update delta link for: {task_name}")
        else:
            logger.info(f"Delta link updated successfully for: {task_name}")

    def get_outlook_token(self) -> Optional[str]:
        """
        Retrieves the existing Outlook token, refreshing it if missing or expired.

        Returns:
            Optional[str]: Outlook token if successful, None otherwise
        """
        try:
            # Fetch Outlook credentials from the environment
            credentials = environment.get_environment_key(
                key="OUTLOOK", organization_schema=self.organization_schema
            )
            if credentials is None:
                logger.error("Outlook integration is not configured")

            # Retrieve the current token from credentials
            current_token = credentials.get("OUTLOOK_TOKEN")
            if not current_token:
                # Refresh the token if it is missing
                logger.info("Missing Outlook token, refreshing token")
                return self._refresh_outlook_token()

            # Decrypt and decode the token
            outlook_token = decrypt_string(current_token)
            alg = jwt.get_unverified_header(outlook_token)["alg"]
            decoded_token = jwt.decode(
                outlook_token, algorithms=[alg], options={"verify_signature": False}
            )

            # Check if the token is still valid
            if int(datetime.now().timestamp()) < decoded_token["exp"]:
                return outlook_token

            # Refresh the token if it has expired
            logger.info("Outlook token has expired, refreshing token")
            return self._refresh_outlook_token()

        except Exception as e:
            logger.error(f"Error in getting Outlook token: {e}")

    def get_user_profile(self, email_id: str) -> Optional[dict]:
        """
        Retrieve user profile details for a given user email address.

        Args:
            email_id: Email address of the user

        Returns:
            Optional[dict]: Dictionary containing user profile details if successful, None otherwise
        """
        try:
            # Request additional company-related fields using $select
            select_fields = "id,businessPhones,displayName,givenName,surname,userPrincipalName,jobTitle,mail,mobilePhone,officeLocation,preferredLanguage,companyName,department,usageLocation,streetAddress,city,state,country,postalCode"
            url = f"{self.graph_url}/users/{email_id}?$select={select_fields}"

            headers = {
                "Authorization": f"Bearer {self.outlook_token}",
                "Content-Type": "application/json",
            }

            response = requests.get(url, headers=headers)
            response.raise_for_status()
            user_data = response.json()

            return {
                "id": user_data.get("id"),
                "businessPhones": user_data.get("businessPhones"),
                "displayName": user_data.get("displayName"),
                "givenName": user_data.get("givenName"),
                "surname": user_data.get("surname"),
                "userPrincipalName": user_data.get("userPrincipalName"),
                "jobTitle": user_data.get("jobTitle"),
                "mail": user_data.get("mail"),
                "mobilePhone": user_data.get("mobilePhone"),
                "officeLocation": user_data.get("officeLocation"),
                "preferredLanguage": user_data.get("preferredLanguage"),
                "companyName": user_data.get("companyName"),
                "department": user_data.get("department"),
                "usageLocation": user_data.get("usageLocation"),
                "streetAddress": user_data.get("streetAddress"),
                "city": user_data.get("city"),
                "state": user_data.get("state"),
                "country": user_data.get("country"),
                "postalCode": user_data.get("postalCode"),
            }

        except requests.RequestException as e:
            logger.warning(f"Error fetching user profile for {email_id}: {str(e)}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error in get_user_profile: {str(e)}")
            return None

    def parse_and_save_email(
        self,
        mailbox_email: str,
        email_data: dict,
        polled_folder: str,
        polling_config: dict,
        data_store: dict = None,
    ) -> Optional[EmailDetail]:
        """
        Parse and save email data for a given mailbox email address.

        Args:
            mailbox_email: Email address of the mailbox
            email_data: Dictionary containing email data
            polled_folder: Name of the folder polled
            polling_config: Dictionary containing polling configuration
            data_store: Dictionary containing data store configuration

        Returns:
            Optional[EmailDetail]: EmailDetail object if successful, None otherwise
        """
        message_id = email_data.get("id")
        if not message_id:
            logger.warning("No email ID found in the email data.")
            return None

        # Check if email already exists to prevent duplicates
        try:
            email_repo = EmailRepository(self.db)
            existing_email = email_repo.get_email_by_id(message_id)
            if existing_email:
                logger.info(
                    f"Email with message_id {message_id} already exists, skipping duplicate"
                )
                return None
        except Exception as e:
            logger.error(f"Error checking for existing email: {e}")
            # Continue with processing in case of error

        # Clean email content
        email_body_content = email_data.get("body", {}).get("content", "")
        email_content = self._clean_email_content(email_body_content)
        sender_email = (
            email_data.get("sender", {}).get("emailAddress", {}).get("address").lower()
        )
        sender_name = email_data.get("sender", {}).get("emailAddress", {}).get("name")

        # Prepare data for database
        message_data = {
            "email_id": sender_email,
            "message_id": message_id,
            "conversation_id": email_data.get("conversationId"),
            "mailbox_email": mailbox_email,
            "mailbox_folder": polled_folder,
            "subject": email_data.get("subject"),
            "received_at": email_data.get("receivedDateTime"),
            "sender_name": sender_name,
            "web_link": email_data.get("webLink"),
            "email_body": email_content,
        }

        # Save to the database using the repository
        try:
            saved_email = email_repo.create_or_update_email(message_data)
            if saved_email:
                # Copy email data to S3 if polling_config has copy_email_data set to true
                email = EmailDetail.model_validate(saved_email)
                if polling_config and polling_config["copy_email_data"]:
                    remote_url = self._save_email_pdf(
                        email.model_dump(), email_body_content, data_store
                    )
                    if remote_url:  # Only update if PDF was successful
                        email_repo.update_email(
                            identifier=saved_email.id,
                            update_data={"additional_data": {"remote_url": remote_url}},
                        )
                return email
            else:
                logger.error(f"Failed to save email data in the database: {message_id}")
                return None
        except SQLAlchemyError as e:
            logger.error(f"Error occurred during database operation: {e}")
            return None

    def poll_mailbox(self, email_id: str, folder: str, date_time: str):
        """
        Poll the mailbox for new emails.

        Args:
            email_id: Email address of the mailbox
            folder: Name of the folder to poll
            date_time: Date and time to start polling from

        Returns:
            tuple: Tuple containing email data, polling configuration, and data store
        """
        task_name = f"{email_id}|{folder}"

        # Retrieve the mailbox polling entry from the database
        mailbox_polling_repo = MailboxPollingRepository(self.db)

        polling_entry = mailbox_polling_repo.get_mailbox_polling(task_name)
        saved_delta_link = polling_entry.delta_link if polling_entry else ""

        folder_id = self._get_folder_id(email_id=email_id, folder_name=folder)

        # Determine the request URL based on saved_delta_link
        # Using changeType=created,updated to track both new emails and moved emails (including within same mailbox)
        request_url = (
            saved_delta_link
            if saved_delta_link
            else f"{self.graph_url}/Users/{email_id}/mailFolders/{folder_id}/messages/delta?changeType=created&$filter=receivedDateTime+ge+{date_time}"
        )

        try:
            response = requests.get(
                request_url,
                headers={"Authorization": f"Bearer {self.outlook_token}"},
            )
            response.raise_for_status()
            response_dict = response.json()

            # Get delta_link and update it in the database
            new_delta_link = response_dict.get("@odata.deltaLink") or response_dict.get(
                "@odata.nextLink"
            )

            # Only update delta link if we received a valid new one from the API
            if new_delta_link and new_delta_link.strip():
                self._write_delta_link(email_id, folder, new_delta_link)
            else:
                logger.warning(
                    f"No valid delta link received for {email_id}|{folder}, preserving existing delta link"
                )

            email_data = response_dict.get("value", [])
            logger.info(
                f"Mailbox polling complete and {len(email_data)} emails fetched"
            )

            return email_data, polling_entry.polling_config, polling_entry.data_store
        except HTTPError as http_err:
            logger.error(
                f"HTTP error occurred: {http_err.response.status_code} - {http_err.response.reason} - {http_err.response.url}"
            )
        except Exception as e:
            logger.error(f"Error occurred during notification processing: {e}")
            raise HTTPException(
                status_code=500,
                detail="An error occurred during notification processing.",
            )

    def process_attachments(self, attachment_ids: List) -> List:
        """
        Process attachment IDs and return formatted attachments for email.

        Args:
            attachment_ids: List of attachment UUID strings

        Returns:
            List: List of processed attachment objects if successful, empty list otherwise
        """
        if not attachment_ids:
            return []

        try:
            attachments = []
            attachment_repository = AttachmentRepository(self.db)
            document_file = DocumentFile(self.organization_schema, self.db)

            for uuid in attachment_ids:
                try:
                    # Get file information from database
                    attachment = attachment_repository.get_attachment_by_id(UUID(uuid))
                    if not attachment:
                        logger.warning(f"Data file not found for UUID: {uuid}")
                        continue

                    # Download file content using DocumentFile.download_file
                    logger.debug(
                        f"Downloading file with path {attachment.remote_url}, type {attachment.file_type}"
                    )
                    file_content = document_file.download_file(
                        file_path=attachment.remote_url
                    )

                    if file_content:
                        # Encode file content to base64 for email attachment
                        encoded_content = base64.b64encode(file_content).decode("utf-8")

                        attachments.append(
                            {
                                "@odata.type": "#microsoft.graph.fileAttachment",
                                "name": attachment.file_name,
                                "contentType": attachment.file_type
                                or "application/octet-stream",
                                "contentBytes": encoded_content,
                            }
                        )
                    else:
                        logger.error(
                            f"Failed to download file content for UUID: {uuid}"
                        )

                except Exception as e:
                    logger.error(f"Error processing attachment {uuid}: {str(e)}")
                    continue

            return attachments

        except Exception as e:
            logger.error(f"Error in attachment processing: {str(e)}")
            return []

    def send_email(
        self, mailbox_email: str, notification_recipients: list, email_data: dict
    ) -> bool:
        """
        Send an email to a list of recipients for a given mailbox email address.

        Args:
            mailbox_email: Email address of the mailbox
            notification_recipients: List of recipient email addresses
            email_data: Dictionary containing email details (recipients, subject, body)
            
        Returns:
            bool: True if the email was sent successfully, False otherwise
        """
        try:
            # Define the API endpoint
            url = f"{self.graph_url}/users/{mailbox_email}/sendMail"

            # Define the headers
            headers = {
                "Authorization": f"Bearer {self.outlook_token}",
                "Content-Type": "application/json",
            }

            # Prepare the email data
            message = {
                "message": {
                    "subject": email_data.get("subject", ""),
                    "body": {
                        "contentType": "HTML",
                        "content": email_data.get("body", ""),
                    },
                    "toRecipients": [
                        {"emailAddress": {"address": recipient}}
                        for recipient in notification_recipients
                    ],
                },
                "saveToSentItems": "true",
            }

            # Convert email data to JSON and call API
            response = requests.post(url, headers=headers, json=message)

            # Raise an exception if the request was unsuccessful
            response.raise_for_status()

            # Check the response status code
            if response.status_code == 202:
                logger.info(
                    f'Successfully sent email {email_data.get("subject", "")} successfully from {mailbox_email}'
                )
                return True
            else:
                # If the status code is not 202, log the error details
                logger.error(
                    f"Failed to send email. Status code: {response.status_code}. Response: {response.text}"
                )
                return False

        except requests.RequestException as e:
            logger.error(
                f"Network error when sending email from {mailbox_email}: {str(e)}"
            )
            return False

        except Exception as e:
            logger.error(
                f"Unexpected error when sending email from {mailbox_email}: {str(e)}"
            )
            return False

    def verify_polling_request(self, email_id: str, folder: str) -> bool:
        """
        Verify the polling request for a given email and folder.

        Args:
            email_id: Email address of the mailbox
            folder: Name of the folder to poll

        Returns:
            bool: True if the polling request is valid, False otherwise
        """
        try:
            # Define the API endpoint
            url = f"{self.graph_url}/users/{email_id}/mailFolders"

            # Define the headers
            headers = {
                "Authorization": f"Bearer {self.outlook_token}",
                "Content-Type": "application/json",
            }

            # Send a GET request to fetch the folders
            response = requests.get(url, headers=headers)

            # Handle non-200 status codes
            if response.status_code != 200:
                error = response.json().get("error", {})
                error_code = error.get("code", "UnknownError")
                error_message = error.get("message", "An unexpected error occurred")
                # Raise an exception if the email ID is invalid
                if error_code == "ErrorInvalidUser":
                    logger.error(f"Invalid email ID {email_id}")
                    raise HTTPException(
                        status_code=422,
                        detail=f"Invalid email ID {email_id}. Please check and retry.",
                    )
                logger.error(f"Error fetching folders: {error_code} - {error_message}")
                return False

            # Extract the list of folders from the response and search for the folder
            folders = response.json().get("value", [])
            folder_id = next(
                (
                    f.get("id")
                    for f in folders
                    if f.get("displayName").lower() == folder.lower()
                ),
                None,
            )

            # Raise an exception if the folder is not found
            if not folder_id:
                logger.error(f"Folder {folder} not found for email: {email_id}")
                raise HTTPException(
                    status_code=422,
                    detail=f"Folder {folder} not found for email {email_id}. Please check and retry.",
                )

            # If the response status code is 200 OK, the polling request is valid
            if response.status_code == 200:
                logger.info(f"Polling verified successfully: {email_id}|{folder}")
                return True

        except requests.RequestException as e:
            logger.error(f"Error in verify_polling_request: {e}")
            return False

    def archive_email(
        self,
        tool_runtime: dict,
        mailbox_email: str,
        message_id: str,
    ) -> str:
        """
        Archive an email message by moving it to the Archive folder.

        Args:
            tool_runtime: Runtime configuration containing db
            mailbox_email: Email address of the mailbox
            message_id: ID of the message to archive
            
        Returns:
            str: JSON response with status_code and message
        """
        # Input validation
        if not all([tool_runtime, mailbox_email, message_id]):
            return json.dumps({
                "status_code": 400,
                "message": "Missing required parameters: tool_runtime, mailbox_email and message_id are required."
            })
        
        try:
            # Get Archive folder ID
            archive_folder_id = self._get_folder_id(mailbox_email, "Archive")
            
            if not archive_folder_id:
                logger.error(f"Could not find Archive folder for {mailbox_email}")
                return json.dumps({
                    "status_code": 404,
                    "message": f"Could not find Archive folder for {mailbox_email}."
                })
            
            # Define the API endpoint for moving email
            url = f"{self.graph_url}/users/{mailbox_email}/messages/{message_id}/move"
            
            # Define the headers
            headers = {
                "Authorization": f"Bearer {self.outlook_token}",
                "Content-Type": "application/json",
            }
            
            # Prepare the move data
            move_data = {
                "destinationId": archive_folder_id,
            }
            
            # Make the archive request
            response = requests.post(url, headers=headers, json=move_data)
            response.raise_for_status()
            
            # Update the message_id for the archived email
            new_message_id = response.json().get("id")
            email_repository = EmailRepository(self.db)
            email_repository.update_email(
                identifier=message_id, update_data={"message_id": new_message_id}
            )
            
            logger.info(f"Email archived successfully: {message_id}")
            return json.dumps({
                "status_code": 200,
                "message": f"Email archived successfully for message: {message_id}."
            })
        
        except requests.HTTPError as e:
            logger.error(f"HTTP error archiving email: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps({
                "status_code": status_code,
                "message": f"HTTP error archiving email: {status_code}."
            })
        except Exception as e:
            logger.error(f"Failed to archive email: {str(e)}")
            return json.dumps({
                "status_code": 500,
                "message": f"Failed to archive email: {str(e)}"
            })

    def delete_email(
        self,
        tool_runtime: dict,
        mailbox_email: str,
        message_id: str,
    ) -> str:
        """
        Delete an email message by moving it to the Deleted Items folder.

        Args:
            tool_runtime: Runtime configuration containing db
            mailbox_email: Email address of the mailbox
            message_id: ID of the message to delete
            
        Returns:
            str: JSON response with status_code and message
        """
        # Input validation
        if not all([tool_runtime, mailbox_email, message_id]):
            return json.dumps({
                "status_code": 400,
                "message": "Missing required parameters: tool_runtime, mailbox_email and message_id are required."
            })
        
        try:
            # Define the API endpoint for deleting email
            url = f"{self.graph_url}/users/{mailbox_email}/messages/{message_id}"
            
            # Define the headers
            headers = {
                "Authorization": f"Bearer {self.outlook_token}",
                "Content-Type": "application/json",
            }
            
            # Make the delete request
            response = requests.delete(url, headers=headers)
            response.raise_for_status()
            
            logger.info(f"Email deleted successfully: {message_id}")
            return json.dumps({
                "status_code": 200,
                "message": f"Email deleted successfully for message: {message_id}."
            })
        
        except requests.HTTPError as e:
            logger.error(f"HTTP error deleting email: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps({
                "status_code": status_code,
                "message": f"HTTP error deleting email: {status_code}."
            })
        except Exception as e:
            logger.error(f"Failed to delete email: {str(e)}")
            return json.dumps({
                "status_code": 500,
                "message": f"Failed to delete email: {str(e)}"
            })

    def draft_email_reply(
        self,
        tool_runtime: dict,
        from_email: str,
        message_id: str,
        email_reply: str,
        attachment_ids: Optional[List[str]] = None,
    ) -> str:
        """
        Create a draft reply for a specific email message.

        Args:
            tool_runtime: Runtime configuration containing db
            from_email: Email address of the mailbox
            message_id: ID of the message to reply to
            email_reply: Content of the reply email
            attachment_ids: List of attachment UUIDs to download and attach
            
        Returns:
            str: JSON response with status_code and message
        """
        # Input validation
        if not all([tool_runtime, from_email, message_id, email_reply]):
            return json.dumps({
                "status_code": 400,
                "message": "Missing required parameters: tool_runtime, from_email, message_id, and email_reply are required."
            })
        
        if not email_reply.strip():
            return json.dumps({
                "status_code": 400,
                "message": "Email reply cannot be empty."
            })
        
        try:
            # Prepare email data for drafting reply
            email_data = {
                "comment": email_reply.replace("\n", "<br>"),
                "contentType": "html",
            }
            
            # Process attachments
            attachments = self.process_attachments(attachment_ids)
            
            # Define the API endpoint - createReplyAll is called on the original message
            url = f"{self.graph_url}/users/{from_email}/messages/{message_id}/createReplyAll"
            
            # Define the headers
            headers = {
                "Authorization": f"Bearer {self.outlook_token}",
                "Content-Type": "application/json",
            }
            
            # Convert email data to JSON and call API
            email_data_json = json.dumps(email_data)
            response = requests.post(url, headers=headers, data=email_data_json)
            logger.info(f"Draft response: {response}")
            response.raise_for_status()
            draft_message = response.json()
            
            # If there are attachments, upload them to the draft message
            if attachments:
                draft_id = draft_message.get("id")
                attachment_url = f"{self.graph_url}/users/{from_email}/messages/{draft_id}/attachments"
                
                for attachment in attachments:
                    try:
                        response = requests.post(
                            attachment_url, headers=headers, json=attachment
                        )
                        logger.info(f"Attachment upload response: {response}")
                        response.raise_for_status()
                    except requests.RequestException as e:
                        logger.error(
                            f"Failed to upload attachment {attachment.get('name', 'unknown')}: {str(e)}"
                        )
                        # Continue with other attachments even if one fails
                        continue
            
            logger.info(f"Email reply drafted successfully for message: {message_id}")
            return json.dumps({
                "status_code": 200,
                "message": f"Email reply drafted successfully for message: {message_id}."
            })
        
        except requests.HTTPError as e:
            logger.error(f"HTTP error drafting email reply: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps({
                "status_code": status_code,
                "message": f"HTTP error drafting email reply: {status_code}."
            })
        except Exception as e:
            logger.error(f"Failed to draft email reply: {str(e)}")
            return json.dumps({
                "status_code": 500,
                "message": f"Failed to draft email reply: {str(e)}"
            })

    def flag_email(
        self,
        tool_runtime: dict,
        mailbox_email: str,
        message_id: str,
    ) -> str:
        """
        Flag an email message.

        Args:
            tool_runtime: Runtime configuration containing db
            mailbox_email: Email address of the mailbox
            message_id: ID of the message to flag
            
        Returns:
            str: JSON response with status_code and message
        """
        # Input validation
        if not all([tool_runtime, mailbox_email, message_id]):
            return json.dumps({
                "status_code": 400,
                "message": "Missing required parameters: tool_runtime, mailbox_email and message_id are required."
            })
        
        try:
            # Graph API endpoint for the message
            url = f"{self.graph_url}/users/{mailbox_email}/messages/{message_id}"
            
            # Headers
            headers = {
                "Authorization": f"Bearer {self.outlook_token}",
                "Content-Type": "application/json",
            }
            
            # JSON payload to flag the message
            payload = {"flag": {"flagStatus": "flagged"}}
            
            # Make the PATCH request
            response = requests.patch(url, headers=headers, json=payload)
            response.raise_for_status()
            
            logger.info(f"Email flagged successfully for message: {message_id}")
            return json.dumps({
                "status_code": 200,
                "message": f"Email flagged successfully for message: {message_id}."
            })
        
        except requests.HTTPError as e:
            logger.error(f"HTTP error flagging email: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps({
                "status_code": status_code,
                "message": f"HTTP error flagging email: {status_code}."
            })
        except Exception as e:
            logger.error(f"Failed to flag email: {str(e)}")
            return json.dumps({
                "status_code": 500,
                "message": f"Failed to flag email: {str(e)}"
            })

    def forward_email(
        self,
        tool_runtime: dict,
        from_email: str,
        message_id: str,
        forward_to: List[str],
        cc_recipients: Optional[List[str]] = None,
        bcc_recipients: Optional[List[str]] = None,
    ) -> str:
        """
        Forward a specific email message to the specified recipients.

        Args:
            tool_runtime: Runtime configuration containing db
            from_email: Email address of the mailbox
            message_id: ID of the message to forward
            forward_to: List of email addresses to forward to
            cc_recipients: Optional list of CC recipient email addresses
            bcc_recipients: Optional list of BCC recipient email addresses
            
        Returns:
            str: JSON response with status_code and message
        """
        # Input validation
        if not all([tool_runtime, from_email, message_id, forward_to]):
            return json.dumps({
                "status_code": 400,
                "message": "Missing required parameters: tool_runtime, from_email, message_id, and forward_to are required."
            })
        
        if not isinstance(forward_to, list) or not forward_to:
            return json.dumps({
                "status_code": 400,
                "message": "forward_to must be a non-empty list of email addresses."
            })
        
        try:
            # Define the API endpoint - createForward is called on the original message
            url = f"{self.graph_url}/users/{from_email}/messages/{message_id}/createForward"
            
            # Define the headers
            headers = {
                "Authorization": f"Bearer {self.outlook_token}",
                "Content-Type": "application/json",
            }
            
            # Create list of recipient objects
            recipients = [{"emailAddress": {"address": email}} for email in forward_to]
            
            # Prepare forward data with CC and BCC if provided
            forward_data = {"toRecipients": recipients}
            
            # Create the forward draft
            response = requests.post(
                url,
                headers=headers,
                json=forward_data,
            )
            response.raise_for_status()
            draft_message = response.json()
            draft_id = draft_message.get("id")
            
            # Update draft with CC/BCC recipients via PATCH (createForward doesn't support these)
            if cc_recipients or bcc_recipients:
                update_url = f"{self.graph_url}/users/{from_email}/messages/{draft_id}"
                update_data = {}
                
                if cc_recipients:
                    update_data["ccRecipients"] = [
                        {"emailAddress": {"address": email}} for email in cc_recipients
                    ]
                
                if bcc_recipients:
                    update_data["bccRecipients"] = [
                        {"emailAddress": {"address": email}} for email in bcc_recipients
                    ]
                
                patch_response = requests.patch(update_url, headers=headers, json=update_data)
                patch_response.raise_for_status()
                logger.info(f"Updated forward draft with CC: {cc_recipients}, BCC: {bcc_recipients}")
            
            # Send the forward draft
            send_url = (
                f"{self.graph_url}/users/{from_email}/messages/{draft_id}/send"
            )
            send_response = requests.post(send_url, headers=headers)
            send_response.raise_for_status()
            
            recipients_str = ", ".join(forward_to)
            logger.info(f"Email forwarded successfully to {recipients_str} for message: {message_id}")
            return json.dumps({
                "status_code": 200,
                "message": f"Email forwarded to {recipients_str} successfully for message: {message_id}."
            })
        
        except requests.HTTPError as e:
            logger.error(f"HTTP error forwarding email: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps({
                "status_code": status_code,
                "message": f"HTTP error forwarding email: {status_code}."
            })
        except Exception as e:
            logger.error(f"Failed to forward email: {str(e)}")
            return json.dumps({
                "status_code": 500,
                "message": f"Failed to forward email: {str(e)}"
            })

    def move_email(
        self,
        tool_runtime: dict,
        mailbox_email: str,
        message_id: str,
        source_folder: str,
        target_folder: str,
    ) -> str:
        """
        Move an email from one folder to another.

        Args:
            tool_runtime: Runtime configuration containing db
            mailbox_email: Email address of the mailbox
            message_id: ID of the message to move
            source_folder: Name of the source folder
            target_folder: Name of the target folder
            
        Returns:
            str: JSON response with status_code and message
        """
        # Input validation
        if not all([tool_runtime, mailbox_email, message_id, source_folder, target_folder]):
            return json.dumps({
                "status_code": 400,
                "message": "Missing required parameters: tool_runtime, mailbox_email, message_id, source_folder, and target_folder are required."
            })
        
        try:
            # Get folder IDs
            source_folder_id = self._get_folder_id(mailbox_email, source_folder)
            target_folder_id = self._get_folder_id(mailbox_email, target_folder)
            
            if not source_folder_id or not target_folder_id:
                logger.error(
                    f"Could not find folder IDs for {source_folder} or {target_folder}"
                )
                return json.dumps({
                    "status_code": 404,
                    "message": f"Could not find folder IDs for {source_folder} or {target_folder}."
                })
            
            # Define the API endpoint
            url = f"{self.graph_url}/users/{mailbox_email}/mailFolders/{source_folder_id}/messages/{message_id}/move"
            
            # Define the headers
            headers = {
                "Authorization": f"Bearer {self.outlook_token}",
                "Content-Type": "application/json",
            }
            
            # Prepare the move data
            move_data = {
                "destinationId": target_folder_id,
            }
            
            # Make the move request
            response = requests.post(url, headers=headers, json=move_data)
            response.raise_for_status()
            
            # Update the message_id for the moved email
            new_message_id = response.json().get("id")
            email_repository = EmailRepository(self.db)
            email_repository.update_email(
                identifier=message_id, update_data={"message_id": new_message_id}
            )
            
            logger.info(f"Email moved successfully from {source_folder} to {target_folder} for message: {message_id}")
            return json.dumps({
                "status_code": 200,
                "message": f"Email moved from {source_folder} to {target_folder} successfully for message: {message_id}."
            })
        
        except requests.HTTPError as e:
            logger.error(f"HTTP error moving email: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps({
                "status_code": status_code,
                "message": f"HTTP error moving email: {status_code}."
            })
        except Exception as e:
            logger.error(f"Failed to move email: {str(e)}")
            return json.dumps({
                "status_code": 500,
                "message": f"Failed to move email: {str(e)}"
            })

    def send_bulk_email(
        self,
        tool_runtime: dict,
        from_email: str,
        subject: str,
        email_body: str,
        to_recipients: List[str],
        cc_recipients: Optional[List[str]] = None,
        bcc_recipients: Optional[List[str]] = None,
        attachment_ids: Optional[List[str]] = None,
    ) -> str:
        """
        Send individual emails to each recipient.

        Args:
            tool_runtime: Runtime configuration containing db
            from_email: Sender's email address
            subject: Subject of the email
            email_body: Body content of the email
            to_recipients: List of recipient email addresses
            cc_recipients: List of CC recipient email addresses (optional)
            bcc_recipients: List of BCC recipient email addresses (optional)
            attachment_ids: List of attachment UUIDs to download and attach
            
        Returns:
            str: JSON response with status_code and message
        """
        # Input validation
        if not all([tool_runtime, from_email, subject, email_body, to_recipients]):
            return json.dumps({
                "status_code": 400,
                "message": "Missing required parameters: tool_runtime, from_email, subject, email_body and to_recipients are required."
            })
        
        if not isinstance(to_recipients, list) or not to_recipients:
            return json.dumps({
                "status_code": 400,
                "message": "to_recipients must be a non-empty list of email addresses."
            })
        
        try:
            # Prepare email message structure
            message_template = {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": email_body.replace("\n", "<br>"),
                },
            }
            
            # Add CC recipients if provided
            if cc_recipients:
                message_template["ccRecipients"] = [
                    {"emailAddress": {"address": recipient}}
                    for recipient in cc_recipients
                ]
            
            # Add BCC recipients if provided
            if bcc_recipients:
                message_template["bccRecipients"] = [
                    {"emailAddress": {"address": recipient}}
                    for recipient in bcc_recipients
                ]
            
            # Process attachments
            attachments = self.process_attachments(attachment_ids)
            if attachments:
                message_template["attachments"] = attachments
            
            # Define the API endpoint
            url = f"{self.graph_url}/users/{from_email}/sendMail"

            # Define the headers
            headers = {
                "Authorization": f"Bearer {self.outlook_token}",
                "Content-Type": "application/json",
            }

            success_count = 0
            failed_recipients = []

            # Send individual emails to each recipient
            for recipient in to_recipients:
                try:
                    # Create message for this specific recipient
                    message = message_template.copy()
                    message["toRecipients"] = [{"emailAddress": {"address": recipient}}]

                    # Prepare the payload
                    payload = {"message": message, "saveToSentItems": True}

                    # Make the request
                    response = requests.post(url, headers=headers, json=payload)
                    response.raise_for_status()

                    success_count += 1
                    logger.info(f"Email sent successfully to {recipient}")

                except Exception as e:
                    failed_recipients.append(recipient)
                    logger.error(f"Failed to send email to {recipient}: {str(e)}")

            # Return appropriate response
            total_recipients = len(to_recipients)
            if success_count == total_recipients:
                message = f"Individual emails sent from {from_email} successfully."
                logger.info(f"{message}: {success_count}/{total_recipients}")
                return json.dumps({
                    "status_code": 202,
                    "message": message
                })
            elif success_count > 0:
                message = f"Partially sent emails from {from_email}: {success_count}/{total_recipients} successful."
                logger.warning(f"{message}. Failed recipients: {failed_recipients}")
                return json.dumps({
                    "status_code": 207,
                    "message": message
                })
            else:
                message = f"Failed to send any emails from {from_email}."
                logger.error(message)
                return json.dumps({
                    "status_code": 500,
                    "message": message
                })
        
        except requests.HTTPError as e:
            logger.error(f"HTTP error sending bulk emails: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps({
                "status_code": status_code,
                "message": f"HTTP error sending bulk emails: {status_code}."
            })
        except Exception as e:
            logger.error(f"Failed to send bulk emails: {str(e)}")
            return json.dumps({
                "status_code": 500,
                "message": f"Failed to send bulk emails: {str(e)}"
            })

    def send_email_reply(
        self,
        tool_runtime: dict,
        from_email: str,
        message_id: str,
        email_reply: str,
        attachment_ids: Optional[List[str]] = None,
    ) -> str:
        """
        Send an email reply for a specific email message.

        Args:
            tool_runtime: Runtime configuration containing db
            from_email: Email address of the mailbox
            message_id: ID of the message to reply to
            email_reply: Content of the reply email
            attachment_ids: List of attachment UUIDs to download and attach
            
        Returns:
            str: JSON response with status_code and message
        """
        # Input validation
        if not all([tool_runtime, from_email, message_id, email_reply]):
            return json.dumps({
                "status_code": 400,
                "message": "Missing required parameters: tool_runtime, from_email, message_id, and email_reply are required."
            })
        
        if not email_reply.strip():
            return json.dumps({
                "status_code": 400,
                "message": "Email reply cannot be empty."
            })
        
        try:
            # Prepare email data for reply
            email_data = {
                "comment": email_reply.replace("\n", "<br>"),
                "contentType": "html",
            }
            
            # Process attachments
            attachments = self.process_attachments(attachment_ids)
            
            # Define the API endpoint - createReplyAll is called on the original message
            draft_url = f"{self.graph_url}/users/{from_email}/messages/{message_id}/createReplyAll"

            # Define the headers
            headers = {
                "Authorization": f"Bearer {self.outlook_token}",
                "Content-Type": "application/json",
            }

            # Convert email data to JSON and call API
            email_data_json = json.dumps(email_data)
            response = requests.post(draft_url, headers=headers, data=email_data_json)
            logger.info(f"Draft response: {response}")
            response.raise_for_status()
            draft_message = response.json()
            draft_id = draft_message.get("id")

            # If there are attachments, upload them to the draft message
            if attachments:
                attachment_url = f"{self.graph_url}/users/{from_email}/messages/{draft_id}/attachments"

                for attachment in attachments:
                    try:
                        response = requests.post(
                            attachment_url, headers=headers, json=attachment
                        )
                        logger.info(f"Attachment upload response: {response}")
                        response.raise_for_status()
                    except requests.RequestException as e:
                        logger.error(
                            f"Failed to upload attachment {attachment.get('name', 'unknown')}: {str(e)}"
                        )
                        # Continue with other attachments even if one fails
                        continue

            # Send the draft message
            send_url = (
                f"{self.graph_url}/users/{from_email}/messages/{draft_id}/send"
            )
            response = requests.post(send_url, headers=headers)
            logger.info(f"Send email response: {response}")
            response.raise_for_status()

            logger.info(f"Email reply sent successfully for message: {message_id}")
            return json.dumps({
                "status_code": 200,
                "message": f"Email reply sent successfully for message: {message_id}."
            })
    
        except requests.HTTPError as e:
            logger.error(f"HTTP error sending email reply: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps({
                "status_code": status_code,
                "message": f"HTTP error sending email reply: {status_code}."
            })
        except Exception as e:
            logger.error(f"Failed to send email reply: {str(e)}")
            return json.dumps({
                "status_code": 500,
                "message": f"Failed to send email reply: {str(e)}"
            })

    def send_new_email(
        self,
        tool_runtime: dict,
        from_email: str,
        subject: str,
        email_body: str,
        to_recipients: List[str],
        cc_recipients: Optional[List[str]] = None,
        bcc_recipients: Optional[List[str]] = None,
        attachment_ids: Optional[List[str]] = None,
    ) -> str:
        """
        Send a new email to all recipients.

        Args:
            tool_runtime: Runtime configuration containing db
            from_email: Sender's email address
            subject: Subject of the email
            email_body: Body content of the email
            to_recipients: List of recipient email addresses
            cc_recipients: List of CC recipient email addresses (optional)
            bcc_recipients: List of BCC recipient email addresses (optional)
            attachment_ids: List of attachment UUIDs to download and attach
            
        Returns:
            str: JSON response with status_code and message
        """
        # Input validation
        if not all([tool_runtime, from_email, subject, email_body, to_recipients]):
            return json.dumps({
                "status_code": 400,
                "message": "Missing required parameters: tool_runtime, from_email, subject, email_body and to_recipients are required."
            })
        
        if not isinstance(to_recipients, list) or not to_recipients:
            return json.dumps({
                "status_code": 400,
                "message": "to_recipients must be a non-empty list of email addresses."
            })
        
        try:
            # Prepare email message structure
            message = {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": email_body.replace("\n", "<br>"),
                },
                "toRecipients": [
                    {"emailAddress": {"address": email}} for email in to_recipients
                ],
            }
            
            # Add CC recipients if provided
            if cc_recipients:
                message["ccRecipients"] = [
                    {"emailAddress": {"address": recipient}}
                    for recipient in cc_recipients
                ]
            
            # Add BCC recipients if provided
            if bcc_recipients:
                message["bccRecipients"] = [
                    {"emailAddress": {"address": recipient}}
                    for recipient in bcc_recipients
                ]
            
            # Process attachments
            attachments = self.process_attachments(attachment_ids)
            if attachments:
                message["attachments"] = attachments
            
            # Define the API endpoint
            url = f"{self.graph_url}/users/{from_email}/sendMail"

            # Define the headers
            headers = {
                "Authorization": f"Bearer {self.outlook_token}",
                "Content-Type": "application/json",
            }

            # Prepare the payload
            payload = {"message": message, "saveToSentItems": True}

            # Make the request
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()

            status_code = response.status_code if response.status_code else 202
            message_text = f"New email sent from {from_email} successfully."
            logger.info(f"{message_text}: {status_code}")
            return json.dumps({
                "status_code": status_code,
                "message": message_text
            })
        
        except requests.HTTPError as e:
            logger.error(f"HTTP error sending new email: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps({
                "status_code": status_code,
                "message": f"HTTP error sending new email: {status_code}."
            })
        except Exception as e:
            logger.error(f"Failed to send new email: {str(e)}")
            return json.dumps({
                "status_code": 500,
                "message": f"Failed to send new email: {str(e)}"
            })

    def tool_get_user_profile(
        self,
        tool_runtime: dict,
        mailbox_email: str,
    ) -> str:
        """
        Tool wrapper for getting user profile.
        
        Args:
            tool_runtime: Runtime configuration containing db
            mailbox_email: Email address of the mailbox to retrieve user profile
            
        Returns:
            str: JSON response with user profile data or error message
        """
        # Input validation
        if not all([tool_runtime, mailbox_email]):
            return json.dumps({
                "status_code": 400,
                "message": "Missing required parameters: tool_runtime and mailbox_email are required."
            })
        
        try:
            profile = self.get_user_profile(email_id=mailbox_email)
            
            if profile:
                return json.dumps({
                    "status_code": 200,
                    "message": f"User profile fetched successfully for {mailbox_email}.",
                    "data": profile
                })
            else:
                return json.dumps({
                    "status_code": 404,
                    "message": f"User profile not found for {mailbox_email}."
                })
        
        except requests.HTTPError as e:
            logger.error(f"HTTP error fetching user profile: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps({
                "status_code": status_code,
                "message": f"HTTP error fetching user profile: {status_code}."
            })
        except Exception as e:
            logger.error(f"Failed to fetch user profile: {str(e)}")
            return json.dumps({
                "status_code": 500,
                "message": f"Failed to fetch user profile: {str(e)}"
            })


class OutlookValidator:
    def __init__(self, preset: Dict = None):
        self.preset = preset or {}
        self.token_url_template = self.preset.get(
            "token_url",
            "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        )
        self.default_scope = self.preset.get(
            "scope", "https://graph.microsoft.com/.default"
        )

    def validate_credentials(self, credentials: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validates Outlook credentials by attempting to get an access token.
        Returns a tuple of (is_valid, error_message).
        """
        required_fields = ["CLIENT_ID", "CLIENT_SECRET", "TENANT_ID"]

        # Check if all required fields are present
        for field in required_fields:
            if field not in credentials:
                return False, f"Missing required field: {field}"

        try:
            # Format the token URL with the tenant ID
            token_url = self.token_url_template.format(
                tenant_id=credentials["TENANT_ID"]
            )

            # Prepare the token request payload
            token_data = {
                "grant_type": "client_credentials",
                "client_id": credentials["CLIENT_ID"],
                "client_secret": credentials["CLIENT_SECRET"],
                "scope": self.default_scope,
            }

            # Make the token request
            response = requests.post(token_url, data=token_data)

            if response.status_code == 200:
                return True, None
            else:
                error_detail = response.json().get("error_description", "Unknown error")
                return False, f"Failed to validate credentials: {error_detail}"

        except Exception as e:
            return False, f"Error validating credentials: {str(e)}"
