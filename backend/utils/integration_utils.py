# Custom libraries
from logger import configure_logging
from integrations.anthropic.validator import AnthropicValidator
from integrations.aws.aws_s3 import AWSS3Validator
from integrations.gemini.validator import GeminiValidator
from integrations.office_365.outlook import OutlookValidator
from integrations.office_365.sharepoint import SharePointValidator
from integrations.openai.validator import OpenAIValidator

# Default libraries
from typing import Dict, Optional, Tuple


logger = configure_logging(__name__)


class IntegrationValidator:
    def __init__(self, auth_schema: dict, preset: dict, integrations: list):
        self.auth_schema = auth_schema
        self.integrations = integrations
        self.preset = preset

        # Initialize validators with preset configurations
        self.validators = {
            "sharepoint": SharePointValidator(preset=self.preset),
            "openai": OpenAIValidator(),
            "aws_s3": AWSS3Validator(),
            "outlook": OutlookValidator(),
            "anthropic": AnthropicValidator(),
            "gemini": GeminiValidator(),
        }

    def get_integration(self, key: str) -> Optional[dict]:
        """Get integration by key."""
        for integration in self.integrations:
            if integration["key"] == key:
                return integration
        return None

    def get_auth_schema(self, auth_schema: str) -> Optional[dict]:
        """Get auth schema by name."""
        return self.auth_schema.get(auth_schema)

    def validate_credentials(
        self, key: str, credentials: Dict
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates credentials based on integration key.
        Returns tuple of (is_valid, error_message).
        """
        integration = self.get_integration(key)
        if not integration:
            return False, f"Invalid integration key: {key}"

        auth_schema = self.get_auth_schema(integration["auth_schema"])
        if not auth_schema:
            return False, f"Invalid auth schema for integration: {key}"

        # Validate required fields are present
        required_fields = [
            field_name
            for field_name, field_config in auth_schema["user"].items()
            if field_config.get("required", False)
        ]

        for field in required_fields:
            if field not in credentials:
                return False, f"Missing required field: {field}"

        # Get the appropriate validator
        validator = self.validators.get(key)
        if validator:
            return validator.validate_credentials(credentials)

        return False, None  # If no specific validator exists, assume invalid
