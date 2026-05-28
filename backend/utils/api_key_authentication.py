# Default libraries
import hashlib
import hmac
import secrets
from typing import Dict

# Database modules
from repository.api_key_repository import ApiKeyRepository

# Installed libraries
from fastapi import HTTPException, status

from db_pool import DatabasePoolManager
from logger import configure_logging
from utils.crypto_utils import decrypt_string, encrypt_string
from datetime import datetime, timezone


db_pool = DatabasePoolManager()

logger = configure_logging(__name__)


class APIKeyAuthentication:
    """
    Handles API Key based authentication.
    """

    def __init__(self):
        """
        Initializes the APIKeyAuthentication class.
        """
        self.api_key_prefix = "ascx-"
        self.secret_length = 8
        self.secret_encoded_length = (self.secret_length * 8 + 5) // 6

    def _constant_time_compare(self, string_a: str, string_b: str) -> bool:
        """
        Compares two strings in constant time.

        Args:
            string_a: First string to compare
            string_b: Second string to compare

        Returns:
            True if the strings are equal, False otherwise
        """
        return hmac.compare_digest(string_a.encode("utf-8"), string_b.encode("utf-8"))

    def generate_api_key(self, organization_schema: str) -> str:
        """
        Generates a new API Key.

        Args:
            organization_schema: Organization schema to generate API Key

        Returns:
            str: Generated API Key
        """
        secret = secrets.token_urlsafe(self.secret_length)
        encrypted_organization_schema = encrypt_string(organization_schema)
        return f"{self.api_key_prefix}{encrypted_organization_schema}-{secret}"

    def generate_api_key_hint(self, api_key: str) -> str:
        """
        Generates a hint for the API Key.

        Args:
            api_key: API Key to generate hint for

        Returns:
            str: Generated API Key Hint
        """
        if len(api_key) <= 16:
            return api_key[:8] + ("..." if len(api_key) > 8 else "")
        return api_key[:8] + "..." + api_key[-8:]

    def generate_api_key_hash(self, api_key: str) -> str:
        """
        Generates a SHA-256 hash of the API Key.

        Args:
            api_key: API Key to generate hash for

        Returns:
            str: Generated API Key Hash
        """
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    def parse_api_key(self, raw_api_key: str) -> Dict:
        """
        Parses the API Key and returns the prefix, organization schema, and secret.

        Args:
            raw_api_key: Raw API Key to parse

        Returns:
            Dict: Parsed API Key containing prefix, organization schema, and secret
        """
        # Validate the API Key format
        if not raw_api_key or not raw_api_key.strip():
            return None

        # Validate the API Key prefix (e.g. "ascx-") using startswith and fixed length
        prefix = raw_api_key[: len(self.api_key_prefix)]
        if prefix != self.api_key_prefix:
            return None

        # Validate the API Key without the prefix
        api_key_without_prefix = raw_api_key[len(self.api_key_prefix) :]
        if len(api_key_without_prefix) <= self.secret_encoded_length + 1:
            return None

        # Validate the API Key without the prefix and secret
        secret = api_key_without_prefix[-self.secret_encoded_length :]
        encrypted_schema = api_key_without_prefix[: -(self.secret_encoded_length + 1)]
        if not encrypted_schema:
            return None

        # Decrypt the organization schema
        organization_schema = decrypt_string(encrypted_schema)
        if not organization_schema:
            return None

        return {
            "prefix": prefix,
            "organization_schema": organization_schema,
            "secret": secret,
        }

    def validate_api_key(self, raw_api_key: str) -> Dict:
        """
        Validates the API Key and returns the user UUID, organization schema, and API Key.

        Args:
            raw_api_key: Raw API Key to validate

        Returns:
            Dict: User UUID, organization schema, and API Key
        """
        try:
            parsed_api_key = self.parse_api_key(raw_api_key)
            if not parsed_api_key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid API Key",
                    headers={"WWW-Authenticate": "API Key"},
                )

            key_hash = self.generate_api_key_hash(raw_api_key)

            organization_schema = parsed_api_key.get("organization_schema")

            with db_pool.get_session(organization_schema) as tenant_db:
                api_key_repository = ApiKeyRepository(tenant_db)
                user_api_key = api_key_repository.get_api_key_by_id(key_hash)

                if not user_api_key or not self._constant_time_compare(
                    key_hash, user_api_key.key_hash
                ):
                    logger.warning("API Key not found")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid API key.",
                    )

                api_key_repository.update_api_key(
                    {
                        "api_key_uuid": user_api_key.id,
                        "last_used_at": datetime.now(timezone.utc),
                    }
                )

            return {
                "org_id": organization_schema,
                "api_key_id": user_api_key.id,
            }

        except HTTPException:
            # Re-raise HTTPExceptions
            raise
        except Exception as e:
            # Handle any other unexpected errors
            logger.error(f"API Key verification failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key verification failed.",
                headers={"WWW-Authenticate": "Bearer"},
            )
