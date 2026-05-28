# Default librarie
import os
import requests

# Installed libraries
from dotenv import load_dotenv
from requests.structures import CaseInsensitiveDict

# Database modules
from logger import configure_logging
from sqlalchemy.orm import Session
from utils.crypto_utils import encrypt_string, decrypt_string
from utils.environment import environment


load_dotenv()

logger = configure_logging(logger_name=__name__)


class MSGraphAPI:
    """
    A class for interacting with the Microsoft Graph API to manage email-related operations.
    """

    def __init__(self, db: Session = None):
        self.redirect_uri = os.getenv("REDIRECT_URI")
        self.scope = "https://graph.microsoft.com/.default"
        self.graph_url = "https://graph.microsoft.com/v1.0"
        self.subscription_url = f"{self.graph_url}/subscriptions"
        self.db = db

    def get_token(self, organization_schema):
        """
        Retrieve an MS Graph access token using application environment.
        """
        try:
            headers = CaseInsensitiveDict()
            headers["Content-Type"] = "application/x-www-form-urlencoded"

            # Get the organization environment
            org_env = environment.get_environment(organization_schema)
            if org_env:
                client_id = decrypt_string(org_env["CLIENT_ID"])
                client_secret = decrypt_string(org_env["CLIENT_SECRET"])
                tenant_id = decrypt_string(org_env["TENANT_ID"])

                data = f"client_id={client_id}&scope={self.scope}&client_secret={client_secret}&grant_type=client_credentials"

                auth_url = (
                    f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
                )
                resp = requests.post(auth_url, headers=headers, data=data)
                resp.raise_for_status()

                if resp.status_code != 200:
                    logger.error(f"Failed to get token for: {organization_schema}")

                token = resp.json().get("access_token")

                org_env["MSGRAPH_TOKEN"] = encrypt_string(token)

                environment.set_environment(org_env, organization_schema)
                logger.info(
                    f"MS Graph Token updated successfully for: {organization_schema}"
                )

                if not org_env.get("MSGRAPH_TOKEN") and organization_schema != "public":
                    logger.error(
                        f"Unable to update MS Graph Token for: {organization_schema}"
                    )

        except requests.exceptions.RequestException as e:
            logger.error(f"Error in getting token for {organization_schema}: {e}")
