# Default libraries
import httpx
from typing import Dict, Optional, Tuple


class OpenAIValidatorV4:
    @staticmethod
    async def validate_credentials(credentials: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validates OpenAI API credentials by attempting to make a test API call.
        Returns a tuple of (is_valid, error_message).
        """
        if not credentials.get("api_key"):
            return False, "Missing required field: api_key"

        try:
            headers = {
                "Authorization": f"Bearer {credentials['api_key']}",
                "Content-Type": "application/json",
            }

            if credentials.get("organization_id"):
                headers["OpenAI-Organization"] = credentials["organization_id"]

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.openai.com/v1/models", headers=headers, timeout=10.0
                )

                if response.status_code == 200:
                    return True, None
                elif response.status_code == 401:
                    return False, "Invalid API key: Authentication failed"
                else:
                    try:
                        error_detail = (
                            response.json()
                            .get("error", {})
                            .get("message", "Unknown error")
                        )
                    except (ValueError, KeyError):
                        error_detail = f"HTTP {response.status_code}"
                    return False, f"API key validation failed: {error_detail}"

        except httpx.RequestError as e:
            return False, f"Error validating API key: {str(e)}"
