# Default libraries
import httpx
from typing import Dict, Optional, Tuple


class ExaValidatorV4:
    @staticmethod
    async def validate_credentials(credentials: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validates Exa API credentials by attempting to make a test API call.
        Returns a tuple of (is_valid, error_message).
        """
        if not credentials.get("api_key"):
            return False, "Missing required field: api_key"

        try:
            headers = {
                "x-api-key": credentials["api_key"],
                "Content-Type": "application/json",
            }

            payload = {
                "query": "test",
                "numResults": 1,
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.exa.ai/search",
                    headers=headers,
                    json=payload,
                    timeout=10.0,
                )

                if response.status_code == 200:
                    return True, None
                elif response.status_code == 401:
                    return False, "Invalid API key: Authentication failed"
                else:
                    try:
                        error_detail = (
                            response.json()
                            .get("error", response.json().get("message", "Unknown error"))
                        )
                    except (ValueError, KeyError):
                        error_detail = f"HTTP {response.status_code}"
                    return False, f"API key validation failed: {error_detail}"

        except httpx.RequestError as e:
            return False, f"Error validating API key: {str(e)}"
