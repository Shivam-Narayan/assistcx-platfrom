# Custom libraries
from logger import configure_logging

# Database modules
from repository.organization_repository import OrganizationRepository

# Default libraries
import os
import requests
from typing import Optional

# Instaled libraries
from dotenv import load_dotenv
import jwt
import redis
from sqlalchemy.orm import Session

load_dotenv()

# Configure logging
logger = configure_logging(logger_name=__name__)


class License:
    def __init__(self, db: Session):
        self.db = db
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.redis_client = redis.from_url(redis_url)

    def get_license_token(self, tenant_code) -> Optional[bool]:

        try:
            # Get jwt_secret
            organization_repository = OrganizationRepository(self.db)
            organization = organization_repository.get_organization_by_tenant_code(
                tenant_code
            )
            logger.debug(f"Creting new license for {tenant_code}")
            # # Construct the external API endpoint URL
            # api_url = "url/license"

            # Create the JWT payload
            payload = {"tenant_code": tenant_code}

            jwt_token = jwt.encode(payload, os.getenv("JWT_SECRET"), algorithm="HS256")

            logger.debug(f"JWT token for license validation : {jwt_token}")
            # # Set up the headers with the JWT token
            # headers = {"tenant_code": jwt_token}

            # # Make a GET request to the external API with the custom header
            # response = requests.get(api_url, headers=headers)
            # response.raise_for_status()

            # # Get the response data
            # license_token = response.text

            # Store the data in Redis under the key 'license'
            self.redis_client.set("license_token", "license_token")
            logger.debug(f"Created new license for {tenant_code}")
            return True

        except Exception as e:
            logger.error(f"Unexpected error during get_license_token: {e}")
            return False
