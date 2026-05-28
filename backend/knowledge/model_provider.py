import os
import gc
import shutil
import threading
from typing import Any, Dict, Optional, Tuple
from pymilvus import model
from logger import configure_logging
from utils.environment import environment
from utils.crypto_utils import decrypt_string
from configs.embedding_models import get_embedding_config

logger = configure_logging(__name__)

# Suppress HuggingFace Hub warnings about code downloads
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_EXPERIMENTAL_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Provider to environment key mapping for embeddings
EMBEDDING_PROVIDER_KEY_MAP = {
    "openai": "OPENAI",
}


class ModelProvider:
    """
    Thread-safe cache for dense embedding models (local SentenceTransformer and OpenAI API).

    Sparse embeddings (BM25) are handled natively by Milvus, no model needed.
    """

    _instance = None
    _lock = threading.RLock()

    # In-memory embedder cache (unified for local and API-based models)
    _embedders = {}

    # Cache directory
    ARTIFACTS_DIR = os.getenv("ARTIFACTS_DIR", "./artifacts")
    CACHE_DIR = os.path.join(ARTIFACTS_DIR, "models")

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ModelProvider, cls).__new__(cls)
                os.makedirs(cls.CACHE_DIR, exist_ok=True)

                os.environ["HF_HOME"] = cls.CACHE_DIR

                logger.info(f"Model provider initialized at {cls.CACHE_DIR}")
            return cls._instance

    @classmethod
    def _get_embedding_credentials(cls, provider: str, organization_schema: str) -> str:
        """
        Retrieves API key for the specified embedding provider from the organization environment.

        Args:
            provider: Embedding provider name (e.g., "openai").
            organization_schema: Organization schema for credential lookup.

        Returns:
            Decrypted API key for the specified provider.

        Raises:
            ValueError: If provider is unsupported or credentials not found.
        """
        if provider not in EMBEDDING_PROVIDER_KEY_MAP:
            raise ValueError(f"Unsupported embedding provider: {provider}")

        env_key = EMBEDDING_PROVIDER_KEY_MAP[provider]
        credentials = environment.get_environment_key(
            key=env_key, organization_schema=organization_schema
        )
        if credentials is None or "API_KEY" not in credentials:
            raise ValueError(
                f"{env_key} credentials not found in organization environment for embeddings"
            )

        return decrypt_string(credentials["API_KEY"])

    @classmethod
    def get_dense_embedder(
        cls,
        model_name: str,
        organization_schema: Optional[str] = None,
        device: str = "cpu",
        **kwargs,
    ) -> Tuple[Any, int]:
        """
        Get a cached dense embedding function or load it if not available.

        Supports both local models (SentenceTransformer) and API-based models (OpenAI).

        Args:
            model_name: Model name (e.g., "Alibaba-NLP/gte-multilingual-base" or "openai/text-embedding-3-small")
            organization_schema: Required for API-based models (OpenAI) to fetch credentials
            device: Device for local models (default: "cpu")
            **kwargs: Additional model parameters

        Returns:
            Tuple of (embedder, dimension)
        """
        # Check if this is an OpenAI model
        if model_name.startswith("openai/"):
            return cls._get_openai_embedder(model_name, organization_schema)

        # Local model (SentenceTransformer)
        cache_key = f"{model_name}_{device}"

        with cls._lock:
            if cache_key in cls._embedders:
                logger.debug(f"Using cached dense embedder for {model_name}")
                return cls._embedders[cache_key]

            logger.info(f"Loading dense embedding model: {model_name}")
            embedder = model.dense.SentenceTransformerEmbeddingFunction(
                model_name=model_name,
                device=device,
                trust_remote_code=True,
                cache_folder=cls.CACHE_DIR,
                **kwargs,
            )

            cls._embedders[cache_key] = (embedder, embedder.dim)
            return cls._embedders[cache_key]

    @classmethod
    def _get_openai_embedder(
        cls, model_name: str, organization_schema: str
    ) -> Tuple[Any, int]:
        """
        Get OpenAI embedding function for API-based embeddings.

        Args:
            model_name: Model name in format "openai/model-name"
            organization_schema: Organization schema for API key lookup

        Returns:
            Tuple of (embedder, dimension)
        """
        if not organization_schema:
            raise ValueError(
                "organization_schema is required for OpenAI embedding models"
            )

        # Extract the actual model name (e.g., "text-embedding-3-small")
        _, openai_model = model_name.split("/", maxsplit=1)

        # Cache key includes org_schema since API keys differ per org
        cache_key = f"{model_name}_{organization_schema}"

        with cls._lock:
            if cache_key in cls._embedders:
                logger.debug(f"Using cached OpenAI embedder for {model_name}")
                return cls._embedders[cache_key]

            logger.info(f"Loading OpenAI embedding model: {openai_model}")

            api_key = cls._get_embedding_credentials("openai", organization_schema)

            # Use configured dimensions for Matryoshka truncation (reduces cost and storage)
            embed_config = get_embedding_config(model_name)
            dimensions = embed_config["dimensions"] if embed_config else None

            embedder = model.dense.OpenAIEmbeddingFunction(
                model_name=openai_model,
                api_key=api_key,
                dimensions=dimensions,
            )

            cls._embedders[cache_key] = (embedder, embedder.dim)
            return cls._embedders[cache_key]

    @classmethod
    def release_all_models(cls) -> int:
        """Release all cached embedding models from memory."""
        with cls._lock:
            count = len(cls._embedders)
            cls._embedders.clear()
            gc.collect()
            logger.info(f"Released {count} embedding models from memory")
            return count

    @classmethod
    def delete_cached_models(cls) -> Dict[str, Any]:
        """Delete all cached model files from disk."""
        if not os.path.exists(cls.CACHE_DIR):
            return {"deleted": False, "reason": "Cache directory does not exist"}

        try:
            total_size = sum(
                os.path.getsize(os.path.join(root, f))
                for root, _, files in os.walk(cls.CACHE_DIR)
                for f in files
                if os.path.exists(os.path.join(root, f))
            )
            size_mb = total_size / (1024 * 1024)

            shutil.rmtree(cls.CACHE_DIR)
            os.makedirs(cls.CACHE_DIR, exist_ok=True)

            logger.info(f"Deleted cached models: {size_mb:.1f} MB")
            return {"deleted": True, "size_mb": round(size_mb, 1)}

        except Exception as e:
            logger.error(f"Failed to delete cached models: {e}")
            return {"deleted": False, "error": str(e)}
