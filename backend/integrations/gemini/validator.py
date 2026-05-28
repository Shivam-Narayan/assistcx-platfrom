# Custom libraries
from logger import configure_logging

# Default libraries
from typing import Dict, Optional, Tuple

# Installed libraries
import requests


logger = configure_logging(__name__)


class GeminiValidator:
    @staticmethod
    def validate_credentials(credentials: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validates Google Gemini API credentials by attempting to make a test API call.
        Returns a tuple of (is_valid, error_message).
        """
        # Check if API key is present
        if "API_KEY" not in credentials:
            return False, "Missing required field: API_KEY"

        try:
            # Google Gemini API endpoint for testing credentials
            test_url = "https://generativelanguage.googleapis.com/v1/models"

            # Prepare headers with the API key
            headers = {
                "Content-Type": "application/json",
            }
            params = {"key": credentials["API_KEY"]}

            # Make a simple GET request to list models
            response = requests.get(test_url, headers=headers, params=params)

            if response.status_code == 200:
                return True, None
            elif response.status_code == 401 or response.status_code == 403:
                return False, "Invalid API key: Authentication failed"
            else:
                # Attempt to get more detailed error information
                error_detail = (
                    response.json().get("error", {}).get("message", "Unknown error")
                )
                return False, f"API key validation failed: {error_detail}"

        except requests.RequestException as e:
            return False, f"Error validating API key: {str(e)}"
        