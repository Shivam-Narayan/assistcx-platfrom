# Custom libraries
from logger import configure_logging

# Default libraries
from typing import Dict, Optional, Tuple

# Installed libraries
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage


logger = configure_logging(__name__)


class AnthropicValidator:
    @staticmethod
    def validate_credentials(credentials: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validates Anthropic API credentials using LangChain's Anthropic wrapper.
        Returns a tuple of (is_valid, error_message).
        """
        # Check for the presence of the API key
        if "API_KEY" not in credentials:
            return False, "Missing required field: API_KEY"

        # Optional: Ensure the key has the expected prefix
        if not credentials["API_KEY"].startswith("sk-"):
            return False, "Invalid API key format: Must start with 'sk-'"

        try:
            # Initialize the Anthropic LLM with the provided API key
            llm = init_chat_model(
                model="claude-3-7-sonnet-latest",
                model_provider="anthropic",
                api_key=credentials["API_KEY"],
            )

            # Create a simple message structure for testing
            messages = [
                SystemMessage(content="You are a helpful AI assistant."),
                HumanMessage(content="Hello, world!"),
            ]

            # Make a test call with structured messages
            response = llm.invoke(messages)

            # Check if we received a valid response
            if response and hasattr(response, "content"):
                logger.debug(
                    f"Response: {response.content}, Data type: {type(response)}"
                )
                return True, None
            else:
                return False, "Received an empty or invalid response from the API."

        except Exception as e:
            # Return the error message if something went wrong
            return False, f"Error validating API key: {str(e)}"


# # Example usage:
# if __name__ == "__main__":
#     credentials = {"API_KEY": "sk-your-anthropic-api-key"}
#     valid, message = AnthropicValidator.validate_credentials(credentials)
#     if valid:
#         print("API key is valid!")
#     else:
#         print("API key validation failed:", message)