import os
import threading
from contextlib import contextmanager
from collections import OrderedDict
from typing import Any, Optional

from pymilvus import MilvusClient
from dotenv import load_dotenv
from logger import configure_logging
from .model_provider import ModelProvider

logger = configure_logging(__name__)

load_dotenv()


class MilvusBase:
    """
    Shared base for MilvusStore and MilvusSearch.

    Provides:
    - Milvus client initialization
    - Dense embedder retrieval (via ModelProvider singleton)
    - LRU collection loader with thread-safe eviction
    - Common constants for hybrid search weights and dimensions
    """

    # Class-level defaults (subclasses can override via __init__)
    DENSE_DIM = 768
    MAX_LOADED_COLLECTIONS = 5
    DENSE_WEIGHT = 0.7
    SPARSE_WEIGHT = 0.3
    USE_RRF = False
    RRF_K = 60
    INSERT_BATCH_SIZE = 50

    def __init__(self):
        self.uri = os.getenv("MILVUS_URI", "http://milvus:19530")
        self.token = os.getenv("MILVUS_TOKEN", "root:Milvus")
        self._initialize_client(self.uri, self.token)

        # Instance copies so callers can tweak per-instance if needed
        self.dense_dim: int = self.DENSE_DIM
        self.max_loaded_collections: int = self.MAX_LOADED_COLLECTIONS
        self.dense_weight: float = self.DENSE_WEIGHT
        self.sparse_weight: float = self.SPARSE_WEIGHT
        self.use_rrf: bool = self.USE_RRF
        self.rrf_k: int = self.RRF_K

        # LRU tracking for loaded collections
        self._loaded: OrderedDict = OrderedDict()
        self._loaded_lock = threading.Lock()

    def _initialize_client(self, uri: str, token: str) -> None:
        """Initialize Milvus client with error handling."""
        try:
            self.client = MilvusClient(uri=uri, token=token)
            logger.info(f"Connected to Milvus at: {uri}")
        except Exception as e:
            logger.error(f"Failed to initialize Milvus client: {e}")
            raise

    def _get_dense_embedder(
        self, dense_model: str, organization_schema: Optional[str] = None
    ) -> tuple[Any, int]:
        """
        Get dense embedding function from ModelProvider (cached at class level).

        Returns:
            Tuple of (embedder, dimension)
        """
        if not dense_model:
            raise ValueError(
                "dense_model cannot be empty. Ensure collection has embedding_model configured."
            )
        try:
            model_cache = ModelProvider()
            dense_ef, dense_dim = model_cache.get_dense_embedder(
                model_name=dense_model,
                organization_schema=organization_schema,
            )
            return dense_ef, dense_dim
        except Exception as e:
            logger.error(f"Failed to get dense embedding function: {e}")
            raise

    @contextmanager
    def collection_loader(self, collection_name: str, fields: list[str] | None = None):
        """
        Context-manager that:
          1) LRU-loads "collection_name" with only the specified fields
          2) Evicts (and releases) the least-recently-used collection if at capacity
          3) Yields control so you can insert/search
          4) Does *not* auto-release on exit (only on eviction or via release_all())
        """
        with self._loaded_lock:
            if collection_name in self._loaded:
                self._loaded.move_to_end(collection_name)
            else:
                if len(self._loaded) >= self.max_loaded_collections:
                    oldest, _ = self._loaded.popitem(last=False)
                    self.client.release_collection(oldest)
                    logger.info(f"Evicted and released collection `{oldest}`")

                load_params = {"collection_name": collection_name}
                if fields is not None:
                    load_params["load_fields"] = fields
                self.client.load_collection(**load_params)
                logger.info(f"Loaded `{collection_name}` with fields={fields}")
                self._loaded[collection_name] = fields

        try:
            yield
        finally:
            pass

    def release_all(self):
        """Force-release every loaded collection right now."""
        with self._loaded_lock:
            for name in list(self._loaded):
                self.client.release_collection(name)
                logger.info(f"Released collection `{name}`")
            self._loaded.clear()
