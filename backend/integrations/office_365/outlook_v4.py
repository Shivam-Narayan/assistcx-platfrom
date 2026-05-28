# Custom libraries
from configs.auth_schemas_v4 import AUTH_SCHEMAS
from logger import configure_logging
from models.connection_v4 import Connection
from utils.crypto_utils import decrypt_string, encrypt_string

# Database modules
from utils.schema_utils import async_db_pool
from repository.connection_repository_v4 import ConnectionRepository
from repository.email_repository import EmailRepository
from repository.attachment_repository import AttachmentRepository
from sqlalchemy.orm import Session

# Default libraries
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import asyncio
import base64
import json

# Utils
from utils.document_file import DocumentFile

# Installed libraries
from requests.exceptions import HTTPError
import jwt
import requests


logger = configure_logging(__name__)


class OutlookV4:
    """
    Handles Outlook integration for email and Microsoft Graph API operations.
    """

    def __init__(self, db: Session):
        """
        Initializes OutlookV4 with database session.

        Args:
            db: Database session
        """
        self.db = db
        self.graph_url = "https://graph.microsoft.com/v1.0"

    async def resolve_connection(self, tool_runtime: dict) -> Optional[Connection]:
        """
        Resolves connection from tool runtime.

        Args:
            tool_runtime: Runtime configuration containing tool_action

        Returns:
            Optional[Connection]: Resolved connection or None if not found
        """
        try:
            # Get the tool action from the tool runtime
            tool_action = tool_runtime.get("tool_action")

            # Get the tool connections from the tool runtime
            tool_connections = tool_runtime.get("tool_connections", {})

            # Get the connection id from the tool connections for the tool action
            connection_id = tool_connections.get(tool_action) if tool_action else None

            # Get the connection id from the tool runtime if not found in the tool connections
            if not connection_id:
                connection_id = tool_runtime.get("connection_id")

            # If no connection id is found, return None
            if not connection_id:
                return None

            # Get the connection data from the database
            connection_repository = ConnectionRepository(self.db)
            connection = await connection_repository.get_connection_by_id(
                UUID(connection_id)
            )

            # Return the connection if it is active and the auth status is valid else return None
            if (
                connection
                and connection.is_active
                and connection.auth_status == "valid"
            ):
                return connection
            return None

        except Exception as e:
            logger.error(f"Error resolving connection: {e}")
            return None

    async def _refresh_token(self, connection: Connection) -> Optional[str]:
        """
        Refreshes the token for a connection.

        Args:
            connection: Connection object containing encrypted credentials

        Returns:
            Optional[str]: Refreshed token or None if failed to refresh
        """
        try:
            # Get the raw encrypted credentials from the connection
            raw_credentials = json.loads(connection.encrypted_credentials)

            # Get the auth schema from the connection
            auth_schema = AUTH_SCHEMAS.get(connection.auth_schema_key)
            if not auth_schema:
                logger.warning(f"Unknown auth_schema_key: {connection.auth_schema_key}")
                return None

            # Get input_fields from the auth schema and build decrypted credentials for each
            input_fields = auth_schema["input_fields"]
            credentials = {}
            for field_key in input_fields:
                raw_value = raw_credentials.get(field_key)
                credentials[field_key] = (
                    decrypt_string(raw_value) if raw_value else None
                )

            # Get the preset from the auth schema and build the token URL
            preset = auth_schema["preset"]
            token_url = preset.get("token_url", "").format(
                tenant_id=credentials.get("tenant_id")
            )

            # Build the headers for the token request
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
            }

            # Build the data for the token request
            data = {
                "client_id": credentials.get("client_id"),
                "client_secret": credentials.get("client_secret"),
                "grant_type": preset.get("grant_type"),
                "scope": preset.get("scope"),
            }

            # Make the token request
            response = requests.post(token_url, headers=headers, data=data)
            response.raise_for_status()

            # Get the access token from the response
            outlook_token = response.json().get("access_token")

            # Update the connection with the new token
            connection_repository = ConnectionRepository(self.db)
            await connection_repository.update_connection(
                {
                    "connection_id": connection.id,
                    "encrypted_token": encrypt_string(outlook_token),
                }
            )

            return outlook_token

        except HTTPError as e:
            logger.error(f"Token refresh failed for connection {connection.id}: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Error refreshing token for connection {connection.id}: {e}",
                exc_info=True,
            )
            return None

    async def _get_token(self, connection: Connection) -> Optional[str]:
        """
        Retrieves the token for a connection.

        Args:
            connection: Connection object containing encrypted token andcredentials

        Returns:
            Optional[str]: Token for the connection or None if not found
        """
        try:
            # If encrypted_token is present, check if valid and return it
            if connection.encrypted_token:
                try:
                    outlook_token = decrypt_string(connection.encrypted_token)
                    alg = jwt.get_unverified_header(outlook_token)["alg"]
                    decoded_token = jwt.decode(
                        outlook_token,
                        algorithms=[alg],
                        options={"verify_signature": False},
                    )

                    if int(datetime.now().timestamp()) < decoded_token["exp"]:
                        return outlook_token

                except Exception as e:
                    logger.debug(f"Stored token invalid or expired: {e}")

            # No token or invalid/expired: refresh using connection credentials
            return await self._refresh_token(connection)
        except Exception as e:
            logger.error(
                f"Error getting token for connection {connection.id}: {e}",
                exc_info=True,
            )
            return None

    async def _prepare_connection(
        self, tool_runtime: dict
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Resolves connection and obtains an Outlook token from tool_runtime.

        Returns:
            tuple: (outlook_token, None) on success, or (None, error_json) on failure.
        """
        connection = await self.resolve_connection(tool_runtime)
        if not connection:
            return None, json.dumps(
                {
                    "status_code": 400,
                    "message": "No connection bound for this tool. Create a tool binding for this agent or ensure task has connection context.",
                }
            )

        outlook_token = await self._get_token(connection)
        if not outlook_token:
            return None, json.dumps(
                {
                    "status_code": 401,
                    "message": "Failed to obtain outlook token. Please check the connection credentials.",
                }
            )

        return outlook_token, None

    async def _get_folder_id(
        self,
        outlook_token: str,
        email_id: str,
        folder_name: str,
    ) -> Optional[str]:
        """
        Get the ID of the specified folder for a user email address.

        Args:
            outlook_token: Access token for Microsoft Graph.
            email_id: Email address of the mailbox.
            folder_name: Name of the folder to get the ID for.

        Returns:
            Optional[str]: ID of the specified folder, or None if not found.
        """
        try:
            url = f"{self.graph_url}/users/{email_id}/mailFolders"

            headers = {
                "Authorization": f"Bearer {outlook_token}",
                "Content-Type": "application/json",
            }

            response = requests.get(url, headers=headers)
            response.raise_for_status()
            folders = response.json().get("value", [])

            for folder in folders:
                if folder.get("displayName", "").lower() == folder_name.lower():
                    return folder.get("id")

            return None

        except Exception as e:
            logger.error(
                f"Error in _get_folder_id for {email_id}, folder {folder_name}: {e}"
            )
            return None

    async def _process_attachments(
        self, attachment_ids: Optional[List[str]], organization_schema: str
    ) -> List:
        """
        Process attachment IDs and return formatted attachments for email.

        Args:
            attachment_ids: List of attachment UUID strings
            organization_schema: Organization schema for DocumentFile

        Returns:
            List: List of processed attachment objects if successful, empty list otherwise
        """
        if not attachment_ids:
            return []

        try:
            attachments = []
            attachment_repository = AttachmentRepository(self.db)
            document_file = DocumentFile(organization_schema, self.db)

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

    async def _get_user_profile(
        self, outlook_token: str, email_id: str
    ) -> Optional[dict]:
        """
        Retrieve user profile details for a given user email address.

        Args:
            outlook_token: Access token for Microsoft Graph.
            email_id: Email address of the user

        Returns:
            Optional[dict]: Dictionary containing user profile details if successful, None otherwise
        """
        try:
            # Request additional company-related fields using $select
            select_fields = "id,businessPhones,displayName,givenName,surname,userPrincipalName,jobTitle,mail,mobilePhone,officeLocation,preferredLanguage,companyName,department,usageLocation,streetAddress,city,state,country,postalCode"
            url = f"{self.graph_url}/users/{email_id}?$select={select_fields}"

            headers = {
                "Authorization": f"Bearer {outlook_token}",
                "Content-Type": "application/json",
            }

            response = requests.get(url, headers=headers)
            response.raise_for_status()
            user_data = response.json()

            # Strip OData metadata keys; $select already limits the fields
            return {k: v for k, v in user_data.items() if not k.startswith("@odata")}

        except requests.RequestException as e:
            logger.warning(f"Error fetching user profile for {email_id}: {str(e)}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error in _get_user_profile: {str(e)}")
            return None

    async def forward_email(
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
        if any(v is None for v in [tool_runtime, from_email, message_id, forward_to]):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, from_email, message_id, and forward_to are required",
                }
            )

        if not isinstance(forward_to, list) or not forward_to:
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "forward_to must be a non-empty list of email addresses",
                }
            )

        # Resolve connection and obtain token
        outlook_token, error = await self._prepare_connection(tool_runtime)
        if error:
            return error

        try:
            # Define the API endpoint - createForward is called on the original message
            url = f"{self.graph_url}/users/{from_email}/messages/{message_id}/createForward"

            # Define the headers
            headers = {
                "Authorization": f"Bearer {outlook_token}",
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

                patch_response = requests.patch(
                    update_url, headers=headers, json=update_data
                )
                patch_response.raise_for_status()
                logger.info(
                    f"Updated forward draft with CC: {cc_recipients}, BCC: {bcc_recipients}"
                )

            # Send the forward draft
            send_url = f"{self.graph_url}/users/{from_email}/messages/{draft_id}/send"
            send_response = requests.post(send_url, headers=headers)
            send_response.raise_for_status()

            recipients_str = ", ".join(forward_to)
            logger.info(
                f"Email forwarded successfully to {recipients_str} for message: {message_id}"
            )
            return json.dumps(
                {
                    "status_code": 200,
                    "message": f"Email forwarded to {recipients_str} successfully",
                }
            )

        except requests.HTTPError as e:
            logger.error(f"HTTP error forwarding email: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps(
                {
                    "status_code": status_code,
                    "message": f"HTTP error forwarding email: {status_code}",
                }
            )
        except Exception as e:
            logger.error(f"Failed to forward email: {str(e)}")
            return json.dumps(
                {"status_code": 500, "message": f"Failed to forward email: {str(e)}"}
            )

    async def archive_email(
        self,
        tool_runtime: dict,
        mailbox_email: str,
        message_id: str,
    ) -> str:
        """
        Archive an email message by moving it to the Archive folder (v4 / connection-based).

        Args:
            tool_runtime: Runtime configuration containing tool_action / tool_connections.
            mailbox_email: Email address of the mailbox.
            message_id: ID of the message to archive.

        Returns:
            str: JSON response with status_code and message.
        """
        # Input validation
        if any(v is None for v in [tool_runtime, mailbox_email, message_id]):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, mailbox_email and message_id are required",
                }
            )

        # Resolve connection and obtain token
        outlook_token, error = await self._prepare_connection(tool_runtime)
        if error:
            return error

        try:
            # Get Archive folder ID
            archive_folder_id = await self._get_folder_id(
                outlook_token=outlook_token,
                email_id=mailbox_email,
                folder_name="Archive",
            )

            if not archive_folder_id:
                logger.error(f"Could not find Archive folder for {mailbox_email}")
                return json.dumps(
                    {
                        "status_code": 404,
                        "message": f"Could not find Archive folder for {mailbox_email}",
                    }
                )

            # Define the API endpoint for moving email
            url = f"{self.graph_url}/users/{mailbox_email}/messages/{message_id}/move"

            # Define the headers
            headers = {
                "Authorization": f"Bearer {outlook_token}",
                "Content-Type": "application/json",
            }

            # Prepare the move data
            move_data = {
                "destinationId": archive_folder_id,
            }

            # Make the archive request
            response = requests.post(url, headers=headers, json=move_data)
            response.raise_for_status()

            # Update the message_id for the archived email in DB (if present)
            try:
                new_message_id = response.json().get("id")
                if new_message_id:
                    email_repository = EmailRepository(self.db)
                    email_repository.update_email(
                        identifier=message_id,
                        update_data={"message_id": new_message_id},
                    )
            except Exception as e:
                # Log but don't fail the archive operation if DB update fails
                logger.error(
                    f"Failed to update archived email message_id in DB for {message_id}: {e}"
                )

            logger.info(f"Email archived successfully: {message_id}")
            return json.dumps(
                {
                    "status_code": 200,
                    "message": f"Email archived successfully for message: {message_id}",
                }
            )

        except requests.HTTPError as e:
            logger.error(f"HTTP error archiving email: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps(
                {
                    "status_code": status_code,
                    "message": f"HTTP error archiving email: {status_code}",
                }
            )
        except Exception as e:
            logger.error(f"Failed to archive email: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to archive email: {str(e)}",
                }
            )

    async def delete_email(
        self,
        tool_runtime: dict,
        mailbox_email: str,
        message_id: str,
    ) -> str:
        """
        Delete an email message by moving it to the Deleted Items folder (v4 / connection-based).

        Args:
            tool_runtime: Runtime configuration containing tool_action / tool_connections.
            mailbox_email: Email address of the mailbox.
            message_id: ID of the message to delete.

        Returns:
            str: JSON response with status_code and message.
        """
        # Input validation
        if any(v is None for v in [tool_runtime, mailbox_email, message_id]):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, mailbox_email and message_id are required",
                }
            )

        # Resolve connection and obtain token
        outlook_token, error = await self._prepare_connection(tool_runtime)
        if error:
            return error

        try:
            # Define the API endpoint for deleting email
            url = f"{self.graph_url}/users/{mailbox_email}/messages/{message_id}"

            # Define the headers
            headers = {
                "Authorization": f"Bearer {outlook_token}",
                "Content-Type": "application/json",
            }

            # Make the delete request
            response = requests.delete(url, headers=headers)
            response.raise_for_status()

            logger.info(f"Email deleted successfully: {message_id}")
            return json.dumps(
                {
                    "status_code": 200,
                    "message": f"Email deleted successfully for message: {message_id}",
                }
            )

        except requests.HTTPError as e:
            logger.error(f"HTTP error deleting email: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps(
                {
                    "status_code": status_code,
                    "message": f"HTTP error deleting email: {status_code}",
                }
            )
        except Exception as e:
            logger.error(f"Failed to delete email: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to delete email: {str(e)}",
                }
            )

    async def _create_reply_draft(
        self,
        outlook_token: str,
        from_email: str,
        message_id: str,
        email_reply: str,
        attachment_ids: Optional[List[str]],
        organization_schema: str,
    ) -> tuple[Optional[str], Optional[dict]]:
        """
        Creates a reply-all draft and uploads attachments.

        Returns:
            tuple: (draft_id, headers) on success. Raises on failure.
        """
        # Prepare email data
        email_data = {
            "comment": email_reply.replace("\n", "<br>"),
            "contentType": "html",
        }

        # Process attachments
        attachments = await self._process_attachments(
            attachment_ids, organization_schema
        )

        # Create the reply-all draft
        url = (
            f"{self.graph_url}/users/{from_email}/messages/{message_id}/createReplyAll"
        )
        headers = {
            "Authorization": f"Bearer {outlook_token}",
            "Content-Type": "application/json",
        }

        email_data_json = json.dumps(email_data)
        response = requests.post(url, headers=headers, data=email_data_json)
        logger.info(f"Draft response: {response}")
        response.raise_for_status()
        draft_message = response.json()
        draft_id = draft_message.get("id")

        # Upload attachments to the draft
        if attachments:
            attachment_url = (
                f"{self.graph_url}/users/{from_email}/messages/{draft_id}/attachments"
            )
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
                    continue

        return draft_id, headers

    async def draft_email_reply(
        self,
        tool_runtime: dict,
        from_email: str,
        message_id: str,
        email_reply: str,
        attachment_ids: Optional[List[str]] = None,
    ) -> str:
        """
        Create a draft reply for a specific email message (v4 / connection-based).

        Args:
            tool_runtime: Runtime configuration containing tool_action / tool_connections.
            from_email: Email address of the mailbox.
            message_id: ID of the message to reply to.
            email_reply: Content of the reply email.
            attachment_ids: List of attachment UUIDs to download and attach.

        Returns:
            str: JSON response with status_code and message.
        """
        # Input validation
        if any(v is None for v in [tool_runtime, from_email, message_id, email_reply]):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, from_email, message_id, and email_reply are required",
                }
            )

        if not email_reply.strip():
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Email reply cannot be empty",
                }
            )

        # Resolve connection and obtain token
        outlook_token, error = await self._prepare_connection(tool_runtime)
        if error:
            return error

        try:
            organization_schema = tool_runtime.get("organization_schema", "public")
            await self._create_reply_draft(
                outlook_token,
                from_email,
                message_id,
                email_reply,
                attachment_ids,
                organization_schema,
            )

            logger.info(f"Email reply drafted successfully for message: {message_id}")
            return json.dumps(
                {
                    "status_code": 200,
                    "message": f"Email reply drafted successfully for message: {message_id}",
                }
            )

        except requests.HTTPError as e:
            logger.error(f"HTTP error drafting email reply: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps(
                {
                    "status_code": status_code,
                    "message": f"HTTP error drafting email reply: {status_code}",
                }
            )
        except Exception as e:
            logger.error(f"Failed to draft email reply: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to draft email reply: {str(e)}",
                }
            )

    async def flag_email(
        self,
        tool_runtime: dict,
        mailbox_email: str,
        message_id: str,
    ) -> str:
        """
        Flag an email message (v4 / connection-based).

        Args:
            tool_runtime: Runtime configuration containing tool_action / tool_connections.
            mailbox_email: Email address of the mailbox.
            message_id: ID of the message to flag.

        Returns:
            str: JSON response with status_code and message.
        """
        # Input validation
        if any(v is None for v in [tool_runtime, mailbox_email, message_id]):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, mailbox_email and message_id are required",
                }
            )

        # Resolve connection and obtain token
        outlook_token, error = await self._prepare_connection(tool_runtime)
        if error:
            return error

        try:
            # Graph API endpoint for the message
            url = f"{self.graph_url}/users/{mailbox_email}/messages/{message_id}"

            # Headers
            headers = {
                "Authorization": f"Bearer {outlook_token}",
                "Content-Type": "application/json",
            }

            # JSON payload to flag the message
            payload = {"flag": {"flagStatus": "flagged"}}

            # Make the PATCH request
            response = requests.patch(url, headers=headers, json=payload)
            response.raise_for_status()

            logger.info(f"Email flagged successfully for message: {message_id}")
            return json.dumps(
                {
                    "status_code": 200,
                    "message": f"Email flagged successfully for message: {message_id}",
                }
            )

        except requests.HTTPError as e:
            logger.error(f"HTTP error flagging email: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps(
                {
                    "status_code": status_code,
                    "message": f"HTTP error flagging email: {status_code}",
                }
            )
        except Exception as e:
            logger.error(f"Failed to flag email: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to flag email: {str(e)}",
                }
            )

    async def move_email(
        self,
        tool_runtime: dict,
        mailbox_email: str,
        message_id: str,
        target_folder: str,
    ) -> str:
        """
        Move an email to the specified folder (v4 / connection-based).

        Args:
            tool_runtime: Runtime configuration containing tool_action / tool_connections.
            mailbox_email: Email address of the mailbox.
            message_id: ID of the message to move.
            target_folder: Name of the target folder.

        Returns:
            str: JSON response with status_code and message.
        """
        # Input validation
        if any(
            v is None for v in [tool_runtime, mailbox_email, message_id, target_folder]
        ):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, mailbox_email, message_id, and target_folder are required",
                }
            )

        # Resolve connection and obtain token
        outlook_token, error = await self._prepare_connection(tool_runtime)
        if error:
            return error

        try:
            # Get target folder ID
            target_folder_id = await self._get_folder_id(
                outlook_token, mailbox_email, target_folder
            )

            if not target_folder_id:
                logger.error(f"Could not find folder ID for {target_folder}")
                return json.dumps(
                    {
                        "status_code": 404,
                        "message": f"Could not find folder: {target_folder}",
                    }
                )

            # Define the API endpoint
            url = f"{self.graph_url}/users/{mailbox_email}/messages/{message_id}/move"

            # Define the headers
            headers = {
                "Authorization": f"Bearer {outlook_token}",
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
            try:
                new_message_id = response.json().get("id")
                if new_message_id:
                    email_repository = EmailRepository(self.db)
                    email_repository.update_email(
                        identifier=message_id,
                        update_data={"message_id": new_message_id},
                    )
            except Exception as e:
                # Log but don't fail the move operation if DB update fails
                logger.error(
                    f"Failed to update moved email message_id in DB for {message_id}: {e}"
                )

            logger.info(
                f"Email moved successfully to {target_folder} for message: {message_id}"
            )
            return json.dumps(
                {
                    "status_code": 200,
                    "message": f"Email moved to {target_folder} successfully",
                }
            )

        except requests.HTTPError as e:
            logger.error(f"HTTP error moving email: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps(
                {
                    "status_code": status_code,
                    "message": f"HTTP error moving email: {status_code}",
                }
            )
        except Exception as e:
            logger.error(f"Failed to move email: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to move email: {str(e)}",
                }
            )

    async def send_bulk_email(
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
        Send individual emails to each recipient (v4 / connection-based).

        Args:
            tool_runtime: Runtime configuration containing tool_action / tool_connections.
            from_email: Sender's email address.
            subject: Subject of the email.
            email_body: Body content of the email.
            to_recipients: List of recipient email addresses.
            cc_recipients: List of CC recipient email addresses (optional).
            bcc_recipients: List of BCC recipient email addresses (optional).
            attachment_ids: List of attachment UUIDs to download and attach.

        Returns:
            str: JSON response with status_code and message.
        """
        # Input validation
        if any(
            v is None
            for v in [tool_runtime, from_email, subject, email_body, to_recipients]
        ):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, from_email, subject, email_body and to_recipients are required",
                }
            )

        if not isinstance(to_recipients, list) or not to_recipients:
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "to_recipients must be a non-empty list of email addresses",
                }
            )

        # Resolve connection and obtain token
        outlook_token, error = await self._prepare_connection(tool_runtime)
        if error:
            return error

        try:
            # Get organization_schema from tool_runtime
            organization_schema = tool_runtime.get("organization_schema", "public")

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
            attachments = await self._process_attachments(
                attachment_ids, organization_schema
            )
            if attachments:
                message_template["attachments"] = attachments

            # Define the API endpoint
            url = f"{self.graph_url}/users/{from_email}/sendMail"

            # Define the headers
            headers = {
                "Authorization": f"Bearer {outlook_token}",
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
                message = f"Individual emails sent from {from_email} successfully"
                logger.info(f"{message}: {success_count}/{total_recipients}")
                return json.dumps(
                    {
                        "status_code": 202,
                        "message": message,
                    }
                )
            elif success_count > 0:
                message = f"Partially sent emails from {from_email}: {success_count}/{total_recipients} successful"
                logger.warning(f"{message}. Failed recipients: {failed_recipients}")
                return json.dumps(
                    {
                        "status_code": 207,
                        "message": message,
                    }
                )
            else:
                message = f"Failed to send any emails from {from_email}"
                logger.error(message)
                return json.dumps(
                    {
                        "status_code": 500,
                        "message": message,
                    }
                )

        except requests.HTTPError as e:
            logger.error(f"HTTP error sending bulk emails: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps(
                {
                    "status_code": status_code,
                    "message": f"HTTP error sending bulk emails: {status_code}",
                }
            )
        except Exception as e:
            logger.error(f"Failed to send bulk emails: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to send bulk emails: {str(e)}",
                }
            )

    async def send_email_reply(
        self,
        tool_runtime: dict,
        from_email: str,
        message_id: str,
        email_reply: str,
        attachment_ids: Optional[List[str]] = None,
    ) -> str:
        """
        Send an email reply for a specific email message (v4 / connection-based).

        Args:
            tool_runtime: Runtime configuration containing tool_action / tool_connections.
            from_email: Email address of the mailbox.
            message_id: ID of the message to reply to.
            email_reply: Content of the reply email.
            attachment_ids: List of attachment UUIDs to download and attach.

        Returns:
            str: JSON response with status_code and message.
        """
        # Input validation
        if any(v is None for v in [tool_runtime, from_email, message_id, email_reply]):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, from_email, message_id, and email_reply are required",
                }
            )

        if not email_reply.strip():
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Email reply cannot be empty",
                }
            )

        # Resolve connection and obtain token
        outlook_token, error = await self._prepare_connection(tool_runtime)
        if error:
            return error

        try:
            organization_schema = tool_runtime.get("organization_schema", "public")
            draft_id, headers = await self._create_reply_draft(
                outlook_token,
                from_email,
                message_id,
                email_reply,
                attachment_ids,
                organization_schema,
            )

            # Send the draft message
            send_url = f"{self.graph_url}/users/{from_email}/messages/{draft_id}/send"
            response = requests.post(send_url, headers=headers)
            logger.info(f"Send email response: {response}")
            response.raise_for_status()

            logger.info(f"Email reply sent successfully for message: {message_id}")
            return json.dumps(
                {
                    "status_code": 200,
                    "message": f"Email reply sent successfully for message: {message_id}",
                }
            )

        except requests.HTTPError as e:
            logger.error(f"HTTP error sending email reply: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps(
                {
                    "status_code": status_code,
                    "message": f"HTTP error sending email reply: {status_code}",
                }
            )
        except Exception as e:
            logger.error(f"Failed to send email reply: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to send email reply: {str(e)}",
                }
            )

    async def send_new_email(
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
        Send a new email to all recipients (v4 / connection-based).

        Args:
            tool_runtime: Runtime configuration containing tool_action / tool_connections.
            from_email: Sender's email address.
            subject: Subject of the email.
            email_body: Body content of the email.
            to_recipients: List of recipient email addresses.
            cc_recipients: List of CC recipient email addresses (optional).
            bcc_recipients: List of BCC recipient email addresses (optional).
            attachment_ids: List of attachment UUIDs to download and attach.

        Returns:
            str: JSON response with status_code and message.
        """
        # Input validation
        if any(
            v is None
            for v in [tool_runtime, from_email, subject, email_body, to_recipients]
        ):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime, from_email, subject, email_body and to_recipients are required",
                }
            )

        if not isinstance(to_recipients, list) or not to_recipients:
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "to_recipients must be a non-empty list of email addresses",
                }
            )

        # Resolve connection and obtain token
        outlook_token, error = await self._prepare_connection(tool_runtime)
        if error:
            return error

        try:
            # Get organization_schema from tool_runtime
            organization_schema = tool_runtime.get("organization_schema", "public")

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
            attachments = await self._process_attachments(
                attachment_ids, organization_schema
            )
            if attachments:
                message["attachments"] = attachments

            # Define the API endpoint
            url = f"{self.graph_url}/users/{from_email}/sendMail"

            # Define the headers
            headers = {
                "Authorization": f"Bearer {outlook_token}",
                "Content-Type": "application/json",
            }

            # Prepare the payload
            payload = {"message": message, "saveToSentItems": True}

            # Make the request
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()

            status_code = response.status_code if response.status_code else 202
            message_text = f"New email sent from {from_email} successfully"
            logger.info(f"{message_text}: {status_code}")
            return json.dumps(
                {
                    "status_code": status_code,
                    "message": message_text,
                }
            )

        except requests.HTTPError as e:
            logger.error(f"HTTP error sending new email: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps(
                {
                    "status_code": status_code,
                    "message": f"HTTP error sending new email: {status_code}",
                }
            )
        except Exception as e:
            logger.error(f"Failed to send new email: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to send new email: {str(e)}",
                }
            )

    async def tool_get_user_profile(
        self,
        tool_runtime: dict,
        mailbox_email: str,
    ) -> str:
        """
        Tool wrapper for getting user profile (v4 / connection-based).

        Args:
            tool_runtime: Runtime configuration containing tool_action / tool_connections.
            mailbox_email: Email address of the mailbox to retrieve user profile.

        Returns:
            str: JSON response with user profile data or error message.
        """
        # Input validation
        if any(v is None for v in [tool_runtime, mailbox_email]):
            return json.dumps(
                {
                    "status_code": 400,
                    "message": "Missing required parameters: tool_runtime and mailbox_email are required",
                }
            )

        # Resolve connection and obtain token
        outlook_token, error = await self._prepare_connection(tool_runtime)
        if error:
            return error

        try:
            profile = await self._get_user_profile(outlook_token, mailbox_email)

            if profile:
                return json.dumps(
                    {
                        "status_code": 200,
                        "message": f"User profile fetched successfully for {mailbox_email}",
                        "data": profile,
                    }
                )
            else:
                return json.dumps(
                    {
                        "status_code": 404,
                        "message": f"User profile not found for {mailbox_email}",
                    }
                )

        except requests.HTTPError as e:
            logger.error(f"HTTP error fetching user profile: {e}")
            status_code = e.response.status_code if e.response else 500
            return json.dumps(
                {
                    "status_code": status_code,
                    "message": f"HTTP error fetching user profile: {status_code}",
                }
            )
        except Exception as e:
            logger.error(f"Failed to fetch user profile: {str(e)}")
            return json.dumps(
                {
                    "status_code": 500,
                    "message": f"Failed to fetch user profile: {str(e)}",
                }
            )


class OutlookValidatorV4:
    def __init__(self, preset: Dict = None):
        self.preset = preset or {}
        self.token_url_template = self.preset.get(
            "token_url",
            "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        )
        self.default_scope = self.preset.get(
            "scope", "https://graph.microsoft.com/.default"
        )

    async def validate_credentials(
        self, credentials: Dict
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates Outlook credentials by attempting to get an access token.
        Returns a tuple of (is_valid, error_message).
        """
        required_fields = ["client_id", "client_secret", "tenant_id"]

        # Check if all required fields are present (lowercase, v4 schema)
        for field in required_fields:
            if field not in credentials:
                return False, f"Missing required field: {field}"

        try:
            # Format the token URL with the tenant ID
            token_url = self.token_url_template.format(
                tenant_id=credentials["tenant_id"]
            )

            # Prepare the token request payload
            token_data = {
                "grant_type": "client_credentials",
                "client_id": credentials["client_id"],
                "client_secret": credentials["client_secret"],
                "scope": self.default_scope,
            }

            # Make the token request (requests is sync; run in thread)
            def _post():
                return requests.post(token_url, data=token_data)

            response = await asyncio.to_thread(_post)

            if response.status_code == 200:
                return True, None
            else:
                error_detail = response.json().get(
                    "error_description", "Unknown error"
                )
                return False, f"Failed to validate credentials: {error_detail}"

        except Exception as e:
            return False, f"Error validating credentials: {str(e)}"


if __name__ == "__main__":

    async def test_outlook():
        tool_runtime = {"organization_schema": "public"}

        async with async_db_pool.get_session("public") as db_session:

            # Initialize the OutlookV4
            outlook = OutlookV4(db=db_session)

            # Test 1: Forward Email
            print("\n --- Testing outlook_forward_email ---")
            result_forward_email = await outlook.forward_email(
                tool_runtime={
                    **tool_runtime,
                    "tool_action": "outlook_forward_email",
                    "tool_connections": {
                        "outlook_forward_email": "cab0cf0f-7141-47e0-86e6-ecb667a71804"
                    },
                },
                from_email="agent@aexonic.com",
                message_id="AAMkAGU3Y2JiMDdmLTljNWMtNDJkMC05OWQ3LWQ5NGZkMThhZTRjMgBGAAAAAAA4N3HQCLPnSJSfgNV-891dBwBOzTuI0WmRRpVedJJNVNi6AAAAAAEMAABOzTuI0WmRRpVedJJNVNi6AAF_JJKvAAA=",
                forward_to=["a.chauhan@aexonic.com"],
            )
            print(result_forward_email)

            # Test 2: Archive Email
            print("\n --- Testing outlook_archive_email ---")
            result_archive_email = await outlook.archive_email(
                tool_runtime={
                    **tool_runtime,
                    "tool_action": "outlook_archive_email",
                    "tool_connections": {
                        "outlook_archive_email": "e376c152-48e8-4e77-b940-83ac941be89d"
                    },
                },
                mailbox_email="agent@aexonic.com",
                message_id="AAMkAGU3Y2JiMDdmLTljNWMtNDJkMC05OWQ3LWQ5NGZkMThhZTRjMgBGAAAAAAA4N3HQCLPnSJSfgNV-891dBwBOzTuI0WmRRpVedJJNVNi6AAAAAAEMAABOzTuI0WmRRpVedJJNVNi6AAF_JJKvAAA=",
            )
            print(result_archive_email)

            # Test 3: Send New Email
            print("\n --- Testing outlook_send_new_email ---")
            result_send_new_email = await outlook.send_new_email(
                tool_runtime={
                    **tool_runtime,
                    "tool_action": "outlook_send_new_email",
                    "tool_connections": {
                        "outlook_send_new_email": "e376c152-48e8-4e77-b940-83ac941be89d"
                    },
                },
                from_email="agent@aexonic.com",
                subject="Test Email from OutlookV4",
                email_body="<p>This is a test email sent from the OutlookV4 integration.</p>",
                to_recipients=["a.chauhan@aexonic.com"],
                cc_recipients=[],
                bcc_recipients=None,
                attachment_ids=None,
            )
            print(result_send_new_email)

            # Test 4: Get User Profile
            print("\n --- Testing outlook_get_user_profile ---")
            result_get_user_profile = await outlook.tool_get_user_profile(
                tool_runtime={
                    **tool_runtime,
                    "tool_action": "outlook_get_user_profile",
                    "tool_connections": {
                        "outlook_get_user_profile": "e376c152-48e8-4e77-b940-83ac941be89d"
                    },
                },
                mailbox_email="agent@aexonic.com",
            )
            print(result_get_user_profile)

            # Test 5: Delete Email
            print("\n --- Testing outlook_delete_email ---")
            result_delete_email = await outlook.delete_email(
                tool_runtime={
                    **tool_runtime,
                    "tool_action": "outlook_delete_email",
                    "tool_connections": {
                        "outlook_delete_email": "e376c152-48e8-4e77-b940-83ac941be89d"
                    },
                },
                mailbox_email="agent@aexonic.com",
                message_id="AAMkAGU3Y2JiMDdmLTljNWMtNDJkMC05OWQ3LWQ5NGZkMThhZTRjMgBGAAAAAAA4N3HQCLPnSJSfgNV-891dBwBOzTuI0WmRRpVedJJNVNi6AAAAAAEMAABOzTuI0WmRRpVedJJNVNi6AAF_JJKvAAA=",
            )
            print(result_delete_email)

            # Test 6: Draft Email Reply
            print("\n --- Testing outlook_draft_email_reply ---")
            result_draft_email_reply = await outlook.draft_email_reply(
                tool_runtime={
                    **tool_runtime,
                    "tool_action": "outlook_draft_email_reply",
                    "tool_connections": {
                        "outlook_draft_email_reply": "e376c152-48e8-4e77-b940-83ac941be89d"
                    },
                },
                from_email="agent@aexonic.com",
                message_id="AAMkAGU3Y2JiMDdmLTljNWMtNDJkMC05OWQ3LWQ5NGZkMThhZTRjMgBGAAAAAAA4N3HQCLPnSJSfgNV-891dBwBOzTuI0WmRRpVedJJNVNi6AAAAAAEMAABOzTuI0WmRRpVedJJNVNi6AAF_JJKvAAA=",
                email_reply="<p>This is a test draft reply from OutlookV4 integration.</p>",
                attachment_ids=None,
            )
            print(result_draft_email_reply)

            # Test 7: Flag Email
            print("\n --- Testing outlook_flag_email ---")
            result_flag_email = await outlook.flag_email(
                tool_runtime={
                    **tool_runtime,
                    "tool_action": "outlook_flag_email",
                    "tool_connections": {
                        "outlook_flag_email": "e376c152-48e8-4e77-b940-83ac941be89d"
                    },
                },
                mailbox_email="agent@aexonic.com",
                message_id="AAMkAGU3Y2JiMDdmLTljNWMtNDJkMC05OWQ3LWQ5NGZkMThhZTRjMgBGAAAAAAA4N3HQCLPnSJSfgNV-891dBwBOzTuI0WmRRpVedJJNVNi6AAAAAAEMAABOzTuI0WmRRpVedJJNVNi6AAF_JJKvAAA=",
            )
            print(result_flag_email)

            # Test 8: Move Email
            print("\n --- Testing outlook_move_email ---")
            result_move_email = await outlook.move_email(
                tool_runtime={
                    **tool_runtime,
                    "tool_action": "outlook_move_email",
                    "tool_connections": {
                        "outlook_move_email": "e376c152-48e8-4e77-b940-83ac941be89d"
                    },
                },
                mailbox_email="agent@aexonic.com",
                message_id="AAMkAGU3Y2JiMDdmLTljNWMtNDJkMC05OWQ3LWQ5NGZkMThhZTRjMgBGAAAAAAA4N3HQCLPnSJSfgNV-891dBwBOzTuI0WmRRpVedJJNVNi6AAAAAAEMAABOzTuI0WmRRpVedJJNVNi6AAF_JJKvAAA=",
                target_folder="Archive",
            )
            print(result_move_email)

            # Test 9: Send Bulk Email
            print("\n --- Testing outlook_send_bulk_email ---")
            result_send_bulk_email = await outlook.send_bulk_email(
                tool_runtime={
                    **tool_runtime,
                    "tool_action": "outlook_send_bulk_email",
                    "tool_connections": {
                        "outlook_send_bulk_email": "e376c152-48e8-4e77-b940-83ac941be89d"
                    },
                },
                from_email="agent@aexonic.com",
                subject="Test Bulk Email from OutlookV4",
                email_body="<p>This is a test bulk email sent from the OutlookV4 integration.</p>",
                to_recipients=["a.chauhan@aexonic.com"],
                cc_recipients=None,
                bcc_recipients=None,
                attachment_ids=None,
            )
            print(result_send_bulk_email)

            # Test 10: Send Email Reply
            print("\n --- Testing outlook_send_email_reply ---")
            result_send_email_reply = await outlook.send_email_reply(
                tool_runtime={
                    **tool_runtime,
                    "tool_action": "outlook_send_email_reply",
                    "tool_connections": {
                        "outlook_send_email_reply": "e376c152-48e8-4e77-b940-83ac941be89d"
                    },
                },
                from_email="agent@aexonic.com",
                message_id="AAMkAGU3Y2JiMDdmLTljNWMtNDJkMC05OWQ3LWQ5NGZkMThhZTRjMgBGAAAAAAA4N3HQCLPnSJSfgNV-891dBwBOzTuI0WmRRpVedJJNVNi6AAAAAAEMAABOzTuI0WmRRpVedJJNVNi6AAF_JJKvAAA=",
                email_reply="<p>This is a test email reply from OutlookV4 integration.</p>",
                attachment_ids=None,
            )
            print(result_send_email_reply)

    asyncio.run(test_outlook())
