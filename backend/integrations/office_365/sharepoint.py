# Custom libraries
from celery_worker import celery
from dotenv import load_dotenv
from logger import configure_logging

# from integrations.aws.s3utility import S3Utility
from utils.environment import environment
from utils.crypto_utils import encrypt_string, decrypt_string
from utils.schema_utils import get_current_schema

# Database modules
from repository.data_collection_repository import DataCollectionRepository
from repository.data_file_repository import DataFileRepository
from repository.integration_repository import IntegrationRepository
from schemas.data_file_schema import DataFileDetail
from sqlalchemy.orm import Session

# Default libraries
from datetime import datetime
from typing import Optional, Tuple, Dict, List
from urllib.parse import urlparse
from uuid import UUID
import os
import requests

# Installed libraries
from fastapi import HTTPException
from requests.structures import CaseInsensitiveDict
import redis
import jwt


load_dotenv()

logger = configure_logging(logger_name=__name__)


class Sharepoint:
    """All functions for authentication and making requests to the SharePoint API."""

    GRAPH_API_BASE_URL = "https://graph.microsoft.com/v1.0"
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

    def __init__(self, db: Session = None):
        """Initialize Sharepoint client with necessary dependencies."""
        self.redis_client = redis.from_url(self.REDIS_URL)
        self.scope = "https://graph.microsoft.com/.default"
        self.db = db
        self.organization_schema = get_current_schema(self.db) if self.db else "public"
        self._init_repositories()
        self.sharepoint_token = self._get_sharepoint_token()
        # self.data_store = self.get_data_store()
        self.allowed_extensions = ["pdf", "md", "docx", "pptx"]

    def _init_repositories(self) -> None:
        """Initialize repository instances."""
        self.data_file_repository = DataFileRepository(self.db)
        self.data_collection_repository = DataCollectionRepository(self.db)
        self.integration_repository = IntegrationRepository(self.db)

    def _get_integration_credentials(self) -> Tuple[str, str, str]:
        """Get and decrypt SharePoint integration credentials."""
        # Retrieve encrypted SharePoint credentials from the environment
        credentials = environment.get_environment_key(
            key="SHAREPOINT", organization_schema=self.organization_schema
        )
        if credentials is None:
            # Raise an error if credentials are missing or not configured
            raise HTTPException(
                status_code=400,
                detail="SharePoint integration is either not configured or lacks proper credentials.",
            )

        # Decrypt individual credentials
        client_id = decrypt_string(credentials.get("CLIENT_ID"))
        client_secret = decrypt_string(credentials.get("CLIENT_SECRET"))
        tenant_id = decrypt_string(credentials.get("TENANT_ID"))

        # Validate that all required credentials are present
        if not all([client_id, client_secret, tenant_id]):
            raise HTTPException(
                status_code=400, detail="Missing required SharePoint credentials."
            )

        # Return decrypted credentials
        return client_id, client_secret, tenant_id

    def _refresh_sharepoint_token(self) -> Optional[str]:
        """Retrieve a new SharePoint access token using stored integration credentials."""
        try:
            # Fetch environment data and SharePoint credentials
            env = environment.get_environment(
                organization_schema=self.organization_schema
            )
            credentials = env.get("SHAREPOINT")
            client_id = decrypt_string(credentials.get("CLIENT_ID"))
            client_secret = decrypt_string(credentials.get("CLIENT_SECRET"))
            tenant_id = decrypt_string(credentials.get("TENANT_ID"))

            # Retrieve integration details and authorization schema fields
            integration = self.integration_repository.get_integration("sharepoint")
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
                sharepoint_token = response.json().get("access_token")
                env["SHAREPOINT"]["SHAREPOINT_TOKEN"] = encrypt_string(sharepoint_token)

                # Update environment data in Redis
                environment.set_environment(
                    environment_data=env, organization_schema=self.organization_schema
                )
                logger.info("SharePoint token updated successfully")
                return sharepoint_token

            # Raise an exception if token retrieval fails
            raise HTTPException(
                status_code=400, detail="Failed to retrieve SharePoint Token."
            )

        except requests.exceptions.RequestException as e:
            # Log the error if the token request fails
            logger.error(f"Error while requesting SharePoint token: {e}")
            return None

    def _get_sharepoint_token(self) -> Optional[str]:
        """Retrieve the existing SharePoint token, refreshing it if missing or expired."""
        try:
            # Fetch SharePoint credentials from the environment
            credentials = environment.get_environment_key(
                key="SHAREPOINT", organization_schema=self.organization_schema
            )
            if credentials is None:
                # Raise an error if integration is not configured
                raise HTTPException(
                    status_code=400, detail="SharePoint integration is not configured."
                )

            # Retrieve the current token from credentials
            current_token = credentials.get("SHAREPOINT_TOKEN")
            if not current_token:
                # Refresh the token if it is missing
                logger.info("Missing SharePoint token, refreshing token")
                return self._refresh_sharepoint_token()

            # Decrypt and decode the token
            sharepoint_token = decrypt_string(current_token)
            alg = jwt.get_unverified_header(sharepoint_token)["alg"]
            decoded_token = jwt.decode(
                sharepoint_token, algorithms=[alg], options={"verify_signature": False}
            )

            # Check if the token is still valid
            if int(datetime.now().timestamp()) < decoded_token["exp"]:
                return sharepoint_token

            # Refresh the token if it has expired
            logger.info("SharePoint token has expired, refreshing token")
            return self._refresh_sharepoint_token()

        except Exception as e:
            # Log and raise an HTTP exception in case of an error
            logger.error(f"Error in getting SharePoint token: {e}")
            raise HTTPException(
                status_code=400, detail=f"Error retrieving SharePoint token: {str(e)}"
            )

    # def get_data_store(self) -> Dict:
    #     """Retrieve the data store preferences stored in Redis for a specific organization."""
    #     try:
    #         # Fetch organization preferences from the environment
    #         org_preferences = (
    #             environment.get_preferences(self.organization_schema) or {}
    #         )

    #         # Return the data store preferences, or defaults if not specified
    #         return org_preferences.get(
    #             "data_store",
    #             {
    #                 "storage_type": "local",
    #                 "storage_bucket": "",
    #                 "storage_folder": "files",
    #                 "storage_region": "",
    #             },
    #         )

    #     except Exception as e:
    #         # Log the error and propagate the exception
    #         logger.error(
    #             f"Error in getting data store for {self.organization_schema}: {e}"
    #         )
    #         raise

    def _make_graph_api_request(
        self, endpoint: str, method: str = "GET", **kwargs
    ) -> Dict:
        """Make a request to the Microsoft Graph API."""
        try:
            # Prepare headers and URL for the API request
            headers = {
                "Authorization": f"Bearer {self.sharepoint_token}",
                "Accept": "application/json",
            }
            url = f"{self.GRAPH_API_BASE_URL}/{endpoint}"

            # Make the API request
            response = requests.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            # Log and raise an error for any request-related exceptions
            logger.error(f"Error in Graph API request to endpoint {endpoint}: {e}")
            raise

    def _verify_site_accessibility(self, site_url: str) -> Dict:
        """
        Verify accessibility of a SharePoint site using the site URL.

        Args:
            site_url (str): The SharePoint site URL to check.

        Returns:
            Dict: A dictionary with site details if accessible, or error information if not.
        """
        try:
            logger.info(f"Verifying SharePoint site: {site_url}")

            # Parse the site URL to extract hostname and path and validate it
            parsed = urlparse(site_url)
            hostname, path = parsed.hostname, parsed.path
            if not hostname or not path:
                return {"url": site_url, "error": "Invalid URL."}

            # Ensure path starts with "/"
            if not path.startswith("/"):
                path = f"/{path}"

            # Make API request to get site details
            try:
                endpoint = f"sites/{hostname}:{path}"
                response = self._make_graph_api_request(endpoint)
            except requests.exceptions.RequestException as e:
                logger.warning(f"SharePoint site not found: {site_url}")
                return {"url": site_url, "error": "Site not found."}

            if not response or not all(k in response for k in ("id", "name", "webUrl")):
                logger.warning(f"SharePoint site not found: {site_url}")
                return {"url": site_url, "error": "Site not found."}

            logger.info(f"SharePoint site verified: {site_url}")
            return {
                "id": response["id"],
                "url": response["webUrl"],
                "name": response["name"],
            }

        except Exception as e:
            logger.error(f"Error verifying SharePoint site {site_url}: {e}")
            return {"url": site_url, "error": str(e)}

    def list_all_sites(self) -> List[Dict]:
        """List all SharePoint sites for the organization."""
        try:
            response = self._make_graph_api_request("sites?search=*")
            return response.get("value", [])
        except requests.exceptions.RequestException as e:
            # Log and raise an error if the request fails
            logger.error(f"Error listing SharePoint sites: {e}")
            raise

    def list_objects_in_site(self, site_id: str) -> List[Dict]:
        """List all files in a SharePoint site."""
        try:
            response = self._make_graph_api_request(
                f"sites/{site_id}/drive/root/children"
            )
            return response.get("value", [])
        except requests.exceptions.RequestException as e:
            # Log and raise an error if the request fails
            logger.error(f"Error listing files in SharePoint site {site_id}: {e}")
            raise

    def list_objects_in_folder(self, site_id: str, folder_id: str) -> List[Dict]:
        """List all files in a SharePoint folder."""
        try:
            response = self._make_graph_api_request(
                f"sites/{site_id}/drive/items/{folder_id}/children"
            )
            return response.get("value", [])
        except requests.exceptions.RequestException as e:
            # Log and raise an error if the request fails
            logger.error(f"Error listing files in SharePoint folder {folder_id}: {e}")
            raise

    def get_item_details(self, site_id: str, item_id: str) -> Dict:
        """Get details of a specific item (file or folder) from a SharePoint site."""
        try:
            return self._make_graph_api_request(
                f"sites/{site_id}/drive/items/{item_id}"
            )
        except requests.exceptions.RequestException as e:
            # Log and raise an error if the request fails
            logger.error(f"Error getting details for SharePoint item {item_id}: {e}")
            raise

    # def update_collection_with_sites(
    #     self, collection_uuid: str, validation_result: Dict[str, List[Dict]]
    # ) -> Dict[str, List[Dict]]:
    #     """Update collection with validated sites and return processed site results."""
    #     try:
    #         accessible_sites = validation_result.get("accessible_sites", [])
    #         non_accessible_sites = list(
    #             validation_result.get("non_accessible_sites", [])
    #         )

    #         if not accessible_sites:
    #             return {
    #                 "accessible_sites": [],
    #                 "non_accessible_sites": non_accessible_sites,
    #             }

    #         # Get current collection config
    #         collection = self.data_collection_repository.get_data_collection_by_id(
    #             collection_uuid
    #         )
    #         if not collection:
    #             raise HTTPException(status_code=404, detail="Collection not found")

    #         config = dict(collection.collection_config or {})
    #         existing_sites = list(config.get("connected_sharepoint_sites", []))

    #         # Filter out duplicates - duplicates remain accessible but aren't added to DB
    #         new_sites = []
    #         for site in accessible_sites:
    #             if self._is_duplicate_site(site, existing_sites):
    #                 # Site is accessible but already connected - keep in accessible_sites
    #                 continue
    #             else:
    #                 new_sites.append(site)

    #         # Update database if there are new sites
    #         if new_sites:
    #             # Update config with new sites
    #             existing_sites.extend(new_sites)
    #             config["connected_sharepoint_sites"] = existing_sites

    #             # Use repository method for database update
    #             update_data = {
    #                 "data_collection_uuid": collection_uuid,
    #                 "collection_config": config,
    #             }

    #             updated_collection = (
    #                 self.data_collection_repository.update_data_collection(update_data)
    #             )
    #             if not updated_collection:
    #                 raise HTTPException(
    #                     status_code=500, detail="Failed to update collection"
    #                 )

    #         return {
    #             "accessible_sites": accessible_sites,  # Return all accessible sites (including duplicates)
    #             "non_accessible_sites": non_accessible_sites,
    #         }

    #     except HTTPException:
    #         raise
    #     except Exception as e:
    #         raise HTTPException(
    #             status_code=500, detail=f"Failed to update collection: {e}"
    #         )

    def _save_file_to_local(self, response: requests.Response, filename: str) -> str:
        """Save file content to local storage."""
        folder_path = os.path.join("data")
        os.makedirs(folder_path, exist_ok=True)

        file_path = os.path.join(folder_path, filename)
        with open(file_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)
        return file_path

    def connect_site_to_data_collection(
        self, data_collection_id: UUID, site_url: str
    ) -> Dict:
        """
        Connect SharePoint sites to a data collection after verifying their accessibility.

        Args:
            data_collection_id (UUID): UUID of the data collection to update.
            site_url (str): SharePoint site URL to connect.

        Returns:
           Dict: Details of the connected SharePoint Site.
        """
        try:
            data_collection_repository = DataCollectionRepository(self.db)

            data_collection = data_collection_repository.get_data_collection_by_id(
                data_collection_id
            )
            if not data_collection:
                raise HTTPException(
                    status_code=404,
                    detail="Collection not found. Please check and retry.",
                )

            # Verify site URL for accessibility
            sharepoint_site = self._verify_site_accessibility(site_url)
            if "error" in sharepoint_site:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to connect SharePoint Site to Data Collection: {sharepoint_site['error']}",
                )

            # Get existing connected sharepoint sites from collection config
            collection_config = dict(data_collection.collection_config or {})
            connected_sharepoint_sites = list(
                collection_config.get("connected_sharepoint_sites", [])
            )

            # Append sharepoint site or update if already connected, avoiding duplicates
            connected_sharepoint_site = next(
                (
                    connected_site
                    for connected_site in connected_sharepoint_sites
                    if connected_site["id"] == sharepoint_site["id"]
                ),
                None,
            )
            if connected_sharepoint_site:
                connected_sharepoint_site["name"] = sharepoint_site.get("name")
                connected_sharepoint_site["url"] = sharepoint_site.get("webUrl")
            else:
                connected_sharepoint_sites.append(sharepoint_site)

            collection_config["connected_sharepoint_sites"] = connected_sharepoint_sites

            # Update data collection
            updated_data_collection = data_collection_repository.update_data_collection(
                {
                    "data_collection_uuid": data_collection_id,
                    "collection_config": collection_config,
                }
            )

            if not updated_data_collection:
                raise HTTPException(
                    status_code=404,
                    detail="Failed to connect SharePoint Site to Data Collection.",
                )

            return sharepoint_site

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error occurred while connecting SharePoint Site: {str(e)}")
            return None

    def disconnect_sites_from_data_collection(
        self, data_collection_id: UUID, site_url: str
    ) -> Dict:
        """
        Disconnect a SharePoint site from a data collection if already connected.

        Args:
            data_collection_id (UUID): UUID of the data collection to update.
            site_url (str): SharePoint site URLs to disconnect.

        Returns:
            Dict: A dictionary with lists of connected, disconnected, and failed sites.
        """
        try:
            data_collection_repository = DataCollectionRepository(self.db)

            data_collection = data_collection_repository.get_data_collection_by_id(
                data_collection_id
            )
            if not data_collection:
                raise HTTPException(
                    status_code=404,
                    detail="Collection not found. Please check and retry.",
                )

            # Get existing connected sharepoint sites from collection config
            collection_config = dict(data_collection.collection_config or {})
            connected_sharepoint_sites = list(
                collection_config.get("connected_sharepoint_sites", [])
            )

            # Remove site if it exists in connected sharepoint sites
            sharepoint_site = next(
                (
                    connected_site
                    for connected_site in connected_sharepoint_sites
                    if connected_site["url"] == site_url
                ),
                None,
            )
            if not sharepoint_site:
                raise HTTPException(
                    status_code=400,
                    detail="SharePoint Site is not connected to the Data Collection.",
                )
            connected_sharepoint_sites.remove(sharepoint_site)

            collection_config["connected_sharepoint_sites"] = connected_sharepoint_sites

            # Update data collection
            updated_data_collection = data_collection_repository.update_data_collection(
                {
                    "data_collection_uuid": data_collection_id,
                    "collection_config": collection_config,
                }
            )

            if not updated_data_collection:
                raise HTTPException(
                    status_code=404,
                    detail="Failed to disconnect SharePoint site from Data Collection.",
                )

            return sharepoint_site

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Error occurred while disconnecting SharePoint sites: {str(e)}"
            )
            return None

    def download_file_content(
        self, site_id: str, item_id: str
    ) -> Optional[requests.Response]:
        """Download the raw file content from SharePoint."""
        try:
            # Get file content
            response = requests.get(
                f"{self.GRAPH_API_BASE_URL}/sites/{site_id}/drive/items/{item_id}/content",
                headers={"Authorization": f"Bearer {self.sharepoint_token}"},
                stream=True,
            )
            response.raise_for_status()
            return response
        except Exception as e:
            logger.error(
                f"Error downloading file {item_id} from SharePoint site {site_id}: {e}"
            )

    def download_file(
        self, site_id: str, item_id: str, collection_id: str
    ) -> Optional[Dict]:
        """Retrieve file details from SharePoint and save it to the database."""
        try:
            # Get file details from SharePoint
            file_details = self.get_item_details(site_id, item_id)
            filename = file_details["name"]

            # Use ROOT Data Collection if collection_id is not provided
            if not collection_id:
                collection = self.data_collection_repository.get_root_data_collection()
                collection_id = collection.id
            else:
                collection = self.data_collection_repository.get_data_collection_by_id(
                    collection_id
                )

            # Check if the file has a valid extension
            file_type = filename.split(".")[-1].lower()
            if file_type not in self.allowed_extensions:
                logger.warning(f"File type not supported: {filename}")
                return {
                    "name": filename,
                    "error": "File type not supported.",
                }

            # Check if a data file with the same name already exists in the folder and skip execution for it
            if self.data_file_repository.get_data_file_by_name_and_folder(
                filename, collection_id
            ):
                logger.warning(
                    f"File with same name already exists in the Collection: {filename}"
                )
                return {
                    "name": filename,
                    "error": "File with same name already exists in the Collection.",
                }

            # Save the file details to the database
            saved_data_file = self.data_file_repository.create_data_file(
                {
                    "name": filename,
                    "size": file_details["size"],
                    "mime_type": file_details["file"]["mimeType"],
                    "md5_hash": file_details["file"]["hashes"]["quickXorHash"],
                    "source_type": "SharePoint",
                    "collection_id": collection_id,
                    "last_synced": file_details["lastModifiedDateTime"],
                    "source_metadata": {
                        "site_id": site_id,
                        "file_id": file_details["id"],
                        "folder_id": file_details["parentReference"]["id"],
                        "drive_id": file_details["parentReference"]["driveId"],
                        "file_path": file_details["webUrl"],
                    },
                    "status": [
                        {
                            "status": "QUEUED",
                            "timestamp": str(datetime.now()),
                        }
                    ],
                }
            )

            if saved_data_file:
                document_record = {
                    "data_file_uuid": saved_data_file.id,
                    "data_file_name": saved_data_file.name,
                    "data_file_size": saved_data_file.size,
                    "source_metadata": saved_data_file.source_metadata,
                    "data_file_path": saved_data_file.source_metadata.get("file_path"),
                    "data_file_source": saved_data_file.source_type,
                    "collection_name": collection.name,
                    "collection_index": collection.index_name,
                    "collection_id": saved_data_file.collection_id,
                }
                celery.send_task(
                    "index_document",
                    args=[self.organization_schema, document_record],
                    queue="knowledge_queue",
                )

                return DataFileDetail.model_validate(saved_data_file).model_dump()

            else:
                logger.error(
                    f"Failed to save file details for {filename} in SharePoint site {site_id}"
                )
                return {
                    "name": filename,
                    "error": "An error occurred while downloading the file from SharePoint.",
                }

        except Exception as e:
            logger.error(
                f"Error downloading file {item_id} from SharePoint site {site_id}: {e}"
            )
            return {
                "name": filename,
                "error": "An error occurred while downloading the file from SharePoint.",
            }

    # def download_file(
    #     self, site_id: str, item_id: str, collection_id: str
    # ) -> Optional[Dict]:
    #     """Download a file from SharePoint and save it to the data store."""
    #     try:
    #         # Get file content
    #         response = requests.get(
    #             f"{self.GRAPH_API_BASE_URL}/sites/{site_id}/drive/items/{item_id}/content",
    #             headers={"Authorization": f"Bearer {self.sharepoint_token}"},
    #             stream=True,
    #         )
    #         response.raise_for_status()

    #         # Get filename from headers
    #         content_disposition = response.headers.get("Content-Disposition", "")
    #         filename = (
    #             content_disposition.split("filename=")[-1].strip('"')
    #             or f"{item_id}.file"
    #         )

    #         file_type = filename.split(".")[-1].lower()
    #         if file_type not in self.allowed_extensions:
    #             logger.warning(f"File type not supported: {filename}")
    #             return {
    #                 "name": filename,
    #                 "error": "File type not supported.",
    #             }

    #         # Get or validate data folder
    #         if not collection_id:
    #             root_folder = self.data_collection_repository.get_root_data_collection()
    #             collection_id = root_folder.id

    #         # Check for existing file
    #         if self.data_file_repository.get_data_file_by_name_and_folder(
    #             filename, collection_id
    #         ):
    #             logger.warning(
    #                 f"File with same name already exists in the Collection: {filename}"
    #             )
    #             return {
    #                 "name": filename,
    #                 "error": "File with same name already exists in the Collection.",
    #             }

    #         # Save file locally
    #         local_path = self._save_file_to_local(response, filename)
    #         logger.debug(f"Saving SharePoint file locally: {local_path}")

    #         try:
    #             collection = self.data_collection_repository.get_data_collection_by_id(
    #                 collection_id
    #             )
    #             data_store = collection.collection_config.get(
    #                 "data_store",
    #                 {
    #                     "storage_type": "local",
    #                     "storage_bucket": "",
    #                     "storage_folder": "files",
    #                     "storage_region": "",
    #                 },
    #             )
    #             data_store["storage_folder"] = f"knowledge-collection/{collection.name}"

    #             # Upload to S3
    #             remote_url = S3Utility(
    #                 self.organization_schema, data_store
    #             ).upload_file(
    #                 local_path,
    #                 f"{data_store['storage_folder']}/{filename}",
    #             )

    #             # Get file details and save to database
    #             file_details = self.get_item_details(site_id, item_id)
    #             saved_file = self.data_file_repository.create_data_file(
    #                 {
    #                     "name": filename,
    #                     "size": file_details["size"],
    #                     "mime_type": file_details["file"]["mimeType"],
    #                     "md5_hash": file_details["file"]["hashes"]["quickXorHash"],
    #                     "source_type": "SharePoint",
    #                     "collection_id": collection_id,
    #                     "last_synced": file_details["lastModifiedDateTime"],
    #                     "source_metadata": {
    #                         "site_id": site_id,
    #                         "file_id": file_details["id"],
    #                         "folder_id": file_details["parentReference"]["id"],
    #                         "drive_id": file_details["parentReference"]["driveId"],
    #                         "file_path": remote_url,
    #                     },
    #                     "status": [
    #                         {
    #                             "status": "QUEUED",
    #                             "timestamp": str(datetime.now()),
    #                         }
    #                     ],
    #                 }
    #             )
    #             collection = self.data_collection_repository.get_data_collection_by_id(
    #                 collection_id
    #             )
    #             document_record = {
    #                 "data_file_uuid": saved_file.id,
    #                 "data_file_name": saved_file.name,
    #                 "data_file_size": saved_file.size,
    #                 "data_file_path": saved_file.source_metadata.get("file_path"),
    #                 "data_file_source": saved_file.source_type,
    #                 "collection_name": collection.name,
    #                 "collection_index": collection.index_name,
    #                 "collection_id": saved_file.collection_id,
    #             }
    #             celery.send_task(
    #                 "index_document",
    #                 args=[self.organization_schema, document_record],
    #                 queue="knowledge_queue",
    #             )

    #             return DataFileDetail.model_validate(saved_file).model_dump()

    #         finally:
    #             # Cleanup local file
    #             if os.path.exists(local_path):
    #                 logger.debug(f"Deleting local SharePoint file: {local_path}")
    #                 os.remove(local_path)

    #     except Exception as e:
    #         logger.error(
    #             f"Error downloading file {item_id} from SharePoint site {site_id}: {e}"
    #         )
    #         return {
    #             "name": filename,
    #             "error": "An error occured while downloading the File from SharePoint.",
    #         }

    def download_folder(
        self, site_id: str, folder_id: str, collection_id: Optional[str] = None
    ) -> List[Dict]:
        """Download all files in a SharePoint folder recursively."""
        try:

            if not collection_id:
                root_folder = self.data_collection_repository.get_root_data_collection()
                collection_id = root_folder.id

            # Process items in folder
            items = self.list_objects_in_folder(site_id, folder_id)
            downloaded_files = []

            for item in items:
                if item.get("folder"):
                    # Recursively process subfolders
                    subfolder_files = self.download_folder(
                        site_id, item["id"], collection_id
                    )
                    downloaded_files.extend(subfolder_files)
                else:
                    # Download individual file
                    file = self.download_file(site_id, item["id"], collection_id)
                    if file:
                        downloaded_files.append(file)

            return downloaded_files

        except Exception as e:
            logger.error(
                f"Error downloading folder {folder_id} from SharePoint site {site_id}: {e}"
            )
            return []

    def download_site(
        self, site_id: str, collection_id: Optional[str] = None
    ) -> List[Dict]:
        """Download all files in a SharePoint site recursively."""
        try:
            if not collection_id:
                root_folder = self.data_collection_repository.get_root_data_collection()
                collection_id = root_folder.id

            # Process items at site root
            items = self.list_objects_in_site(site_id)
            downloaded_files = []

            for item in items:
                if item.get("folder"):
                    # Recursively process folders
                    subfolder_files = self.download_folder(
                        site_id, item["id"], collection_id
                    )
                    downloaded_files.extend(subfolder_files)
                else:
                    # Download individual file
                    file = self.download_file(site_id, item["id"], collection_id)
                    if file:
                        downloaded_files.append(file)

            return downloaded_files

        except Exception as e:
            logger.error(f"Error downloading site {site_id}: {e}")
            return []

    def process_downloads(self, items: List[Dict[str, str]]) -> Dict:
        """Process bulk downloads of files and folders from SharePoint sites."""
        try:
            download_successes = []
            download_failures = []

            # Convert items to dictionaries for processing
            item_dicts = [item.model_dump() for item in items]

            for item in item_dicts:
                try:
                    if "file_id" in item:
                        # Download a single file
                        file = self.download_file(
                            item["site_id"], item["file_id"], item["collection_id"]
                        )
                        if not "error" in file:
                            download_successes.append(file)
                        else:
                            logger.warning(
                                f"Failed to download file: {item['file_id']}"
                            )
                            download_failures.append(file)
                    elif "folder_id" in item:
                        # Download all files in a folder
                        folder_files = self.download_folder(
                            item["site_id"], item["folder_id"], item["collection_id"]
                        )

                        if folder_files:
                            for file in folder_files:
                                if "error" in file:
                                    download_failures.append(file)
                                else:
                                    download_successes.append(file)
                        else:
                            logger.warning(
                                f"Failed to download folder: {item['folder_id']}"
                            )
                            download_failures.append(
                                {
                                    "error": "Folder download failed or empty",
                                    "folder_id": item["folder_id"],
                                }
                            )

                    elif (
                        "site_id" in item
                        and "file_id" not in item
                        and "folder_id" not in item
                    ):
                        # Download all files in a site
                        site_files = self.download_site(
                            item["site_id"], item.get("collection_id")
                        )
                        if site_files:
                            for file in site_files:
                                if "error" in file:
                                    download_failures.append(file)
                                else:
                                    download_successes.append(file)
                        else:
                            logger.warning(
                                f"Failed to download site: {item['site_id']}"
                            )
                            download_failures.append(
                                {
                                    "error": "Site download failed or empty",
                                    "site_id": item["site_id"],
                                }
                            )

                    else:
                        # Log a warning if the item format is invalid
                        logger.warning(f"Invalid item format: {item}")
                except Exception as e:
                    # Log errors and continue processing remaining items
                    logger.error(f"Error processing item {item}: {e}")
                    continue

            # Log the result of the bulk download process
            logger.info(
                f"Bulk download completed. {len(download_successes)} files downloaded successfully."
            )
            return {
                "download_successes": download_successes,
                "download_failures": download_failures,
            }

        except Exception as e:
            # Log the error with the item details and continue processing
            logger.error(f"Error occurred while processing item {item}: {str(e)}")
            return None


class SharePointValidator:
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
        Validates SharePoint credentials by attempting to get an access token.
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
