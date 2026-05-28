# Custom libraries
from configs.auth_schemas_v4 import AUTH_SCHEMAS
from configs.integrations_v4 import INTEGRATIONS
from integrations.openai.validator_v4 import OpenAIValidatorV4
from integrations.aws.aws_s3_v4 import AWSS3V4Validator
from integrations.office_365.outlook_v4 import OutlookValidatorV4
from integrations.exa.validator_v4 import ExaValidatorV4

# Default libraries
from typing import Dict, Optional, Tuple


class IntegrationValidatorV4:
    """Validates credentials based on provider_key and auth_schema_key."""

    def __init__(self):
        self.validators = {
            "openai": OpenAIValidatorV4(),
            "aws_s3": AWSS3V4Validator(),
            "outlook": OutlookValidatorV4(),
            "exa": ExaValidatorV4(),
        }

    def get_integration(self, provider_key: str) -> Optional[Dict]:
        """Get integration configuration by provider_key."""
        for integration in INTEGRATIONS:
            if integration.get("key") == provider_key:
                return integration
        return None

    async def validate_credentials(
        self,
        provider_key: str,
        auth_schema_key: str,
        credentials: Dict,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates credentials for a given integration and auth schema.
        Returns tuple of (is_valid, error_message).
        """
        integration = self.get_integration(provider_key)
        if not integration:
            return False, f"Invalid provider_key: {provider_key}"

        auth_schema = AUTH_SCHEMAS.get(auth_schema_key)
        if not auth_schema:
            return False, f"Invalid auth_schema_key: {auth_schema_key}"

        if auth_schema_key not in integration.get("supported_auth_schemas", []):
            return (
                False,
                f"Auth schema '{auth_schema_key}' is not supported by integration '{provider_key}'",
            )

        # Validate required fields
        for field_name, field_config in auth_schema.get("input_fields", {}).items():
            if field_config.get("required") and not credentials.get(field_name):
                return False, f"Missing required field: {field_name}"

        # Delegate to provider-specific validator if available
        validator = self.validators.get(provider_key)
        if not validator:
            return True, None

        return await validator.validate_credentials(credentials)
