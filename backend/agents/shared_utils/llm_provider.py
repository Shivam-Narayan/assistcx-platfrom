# Custom libraries
from logger import configure_logging
from repository.agent_llm_repository import AgentLLMRepository
from utils.crypto_utils import decrypt_string
from utils.environment import environment

# Default libraries
from typing import Dict, List, Optional, Tuple

# Installed libraries
from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain.chat_models import init_chat_model
from sqlalchemy.orm import Session


load_dotenv()

logger = configure_logging(__name__)

DEFAULT_TEMPERATURE = 0.0
DEFAULT_TIMEOUT = 120

PROVIDER_KEY_MAP = {
    "openai": "OPENAI",
    "anthropic": "ANTHROPIC",
    "google_genai": "GEMINI",
}


class LLMProvider:
    def __init__(self, organization_schema: str, db: Session):
        """
        Initialize LLMProvider with database session.
        
        Args:
            organization_schema: Organization schema name
            db: Database session (required)
        
        Raises:
            ValueError: If db is None
        """
        if db is None:
            raise ValueError("Database session (db) is required for LLMProvider")
        self.organization_schema = organization_schema
        self.db = db
        self._llm_cache = None

    def _get_llm_data(self) -> List[Dict]:
        """
        Fetch LLM data from database.
        
        Returns:
            List[Dict]: List of LLM data dictionaries with llm_key, llm_config, model_name, provider
        
        Raises:
            ValueError: If database query fails or no LLMs found
        """
        if self._llm_cache is not None:
            return self._llm_cache

        try:
            repo = AgentLLMRepository(self.db)
            llms = repo.get_all_agent_llms()
            
            if not llms:
                raise ValueError(
                    f"No LLMs found in database for organization '{self.organization_schema}'. "
                    "Please run /platform/setup to seed the database with LLM configurations."
                )
            
            self._llm_cache = [
                {
                    "llm_key": llm.llm_key,
                    "llm_config": llm.data.get("llm_config", {}) if llm.data else {},
                    "model_name": llm.data.get("model_name") if llm.data else None,
                    "provider": llm.data.get("provider") if llm.data else None,
                }
                for llm in llms
            ]
            logger.info(f"Loaded {len(self._llm_cache)} LLMs from database for organization '{self.organization_schema}'")
            return self._llm_cache
        except ValueError:
            # Re-raise ValueError (e.g., empty database)
            raise
        except Exception as e:
            logger.error(f"Failed to load LLMs from database for organization '{self.organization_schema}': {e}")
            raise ValueError(
                f"Failed to load LLM configurations from database: {str(e)}. "
                "Ensure the database is properly seeded with LLM data via /platform/setup."
            ) from e

    def _get_config_by_key(self) -> Dict[str, Dict]:
        """Get llm_config mapping from database."""
        llm_data = self._get_llm_data()
        return {item["llm_key"]: item["llm_config"] for item in llm_data}

    def _get_models_by_provider(self) -> Dict[str, List[str]]:
        """Get models mapping from database."""
        llm_data = self._get_llm_data()
        supported = {}
        for item in llm_data:
            provider = item["provider"]
            if provider not in supported:
                supported[provider] = []
            supported[provider].append(item["model_name"])
        return supported

    def _get_default_llm_key(self, llm_type: str) -> str:
        """Get default LLM key from organization preferences."""
        org_preferences = environment.get_preferences(self.organization_schema)
        if not org_preferences:
            raise ValueError(
                f"Organization preferences not found for schema '{self.organization_schema}'"
            )

        if llm_type not in {"primary", "fast"}:
            raise ValueError(
                f"Invalid LLM type: {llm_type}. Must be 'primary' or 'fast'"
            )

        default_llm = org_preferences.get("default_llm")
        if not default_llm:
            raise ValueError("'default_llm' not found in organization preferences")

        return org_preferences.get(
            "fast_llm" if llm_type == "fast" else "default_llm", default_llm
        )

    def _get_llm_credentials(self, provider: str) -> str:
        """
        Retrieves API key for the specified LLM provider from the organization environment.

        Args:
            provider (str): LLM provider name (e.g., "openai", "anthropic", "gemini").

        Returns:
            str: Decrypted API key for the specified provider.
        """
        if provider not in PROVIDER_KEY_MAP:
            raise ValueError(f"Unsupported LLM provider: {provider}")

        env_key = PROVIDER_KEY_MAP[provider]
        credentials = environment.get_environment_key(
            key=env_key, organization_schema=self.organization_schema
        )
        if credentials is None or "API_KEY" not in credentials:
            raise ValueError(
                f"{env_key} credentials not found in organization environment"
            )

        return decrypt_string(credentials["API_KEY"])

    def _load_chat_model(
        self, llm_key: str, api_key: str, **model_kwargs
    ) -> BaseChatModel:
        """
        Loads a chat model from a fully specified name.

        Args:
            llm_key (str): Fully specified model name with provider in string format 'provider/model'.
            api_key (str): API key for the provider.
            **model_kwargs: Additional model parameters to pass to init_chat_model.

        Returns:
            BaseChatModel: Configured chat model instance.
        """
        provider, model = llm_key.split("/", maxsplit=1)
        return init_chat_model(
            model,
            model_provider=provider,
            api_key=api_key,
            **model_kwargs,
        )

    def _validate_llm_key(self, llm_key: str) -> Tuple[str, str]:
        """
        Validates the llm_key against supported providers and models.

        Args:
            llm_key (str): LLM key in format "provider/model" (e.g., "openai/gpt-4o").

        Returns:
            Tuple[str, str]: Tuple containing (provider, model) if validation succeeds.
        """
        try:
            provider, model = llm_key.split("/", maxsplit=1)
        except ValueError:
            raise ValueError(
                f"Invalid LLM key format: {llm_key}. Expected format: 'provider/model'"
            )

        supported_models = self._get_models_by_provider()

        if provider not in supported_models:
            raise ValueError(
                f"Unsupported LLM provider: {provider}. Supported providers: {list(supported_models.keys())}"
            )

        if model not in supported_models[provider]:
            raise ValueError(
                f"Unsupported model: {model}. Supported models: {list(supported_models[provider])}"
            )

        return provider, model

    def get_llm(
        self, llm_key: Optional[str] = None, llm_type: str = "primary", **kwargs
    ) -> BaseChatModel:
        """
        Configures and returns an LLM model based on the provided llm_key or organization preferences.

        Args:
            llm_key (Optional[str]): Specific LLM key to use. If None, uses default based on llm_type.
            llm_type (str): Type of default LLM to use ("primary" or "fast").

        Keyword Args:
            temperature (float): Temperature for the model.
            max_tokens (int): Maximum tokens for the model.

        Returns:
            BaseChatModel: Configured LLM model instance.
        """
        try:
            # Resolve llm_key if not provided
            if not llm_key:
                llm_key = self._get_default_llm_key(llm_type)

            # Validate llm_key format (provider/model) andget provider
            provider, _ = self._validate_llm_key(llm_key)

            # Get model config
            llm_config = self._get_config_by_key().get(llm_key, {})

            # Merge: defaults → llm_config → kwargs (kwargs have highest priority)
            model_kwargs = {
                "temperature": DEFAULT_TEMPERATURE,
                "timeout": DEFAULT_TIMEOUT,
            }
            model_kwargs.update(llm_config)
            model_kwargs.update(kwargs)

            # Remove any parameters marked as unsupported
            model_kwargs = {
                k: v for k, v in model_kwargs.items() if v != "__unsupported__"
            }

            logger.info(
                f"Configuring LLM instance: llm_key={llm_key}, model_type={llm_type}, model_kwargs={model_kwargs}"
            )

            # Get credentials and load model
            api_key = self._get_llm_credentials(provider)
            return self._load_chat_model(llm_key, api_key, **model_kwargs)

        except Exception as error:
            logger.error(f"Error loading LLM model: {error}")
            raise
