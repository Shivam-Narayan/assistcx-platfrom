"""Utility functions for data collection management."""

from typing import Optional, Dict, List
import os
from uuid import UUID

from knowledge.milvus_store import MilvusStore
from logger import configure_logging
from models.data_collection import DataCollection
from repository.data_collection_repository import DataCollectionRepository
from repository.user_repository import UserRepository
from sqlalchemy.orm import Session
from utils.common_utils import generate_short_id

logger = configure_logging(__name__)


def get_default_knowledge_data_store() -> Dict:
    """Return default data_store for knowledge collections (same as private_data_collection)."""
    return {
        "storage_type": "minio",
        "storage_bucket": os.getenv("MINIO_KNOWLEDGE_BUCKET", "assistcx-knowledge"),
        "storage_folder": "knowledge-collection",
        "storage_region": "",
    }


def create_private_data_collection(
    db: Session, milvus_store: MilvusStore, user_uuid: UUID
) -> Optional[DataCollection]:
    """
    Creates a private data collection for the specified user.

    Args:
        db (Session): SQLAlchemy database session.
        milvus_store: Instance managing the Milvus vector database operations.
        user_uuid (str): UUID of the user who owns the private data collection.

    Returns:
        Optional[object]: Private data collection object if successful, otherwise None.
    """
    try:
        import os

        from configs.embedding_models import EMBEDDING_MODELS

        data_collection_repository = DataCollectionRepository(db=db)
        user_repository = UserRepository(db=db)
        user = user_repository.get_user_by_id(identifier=UUID(user_uuid))
        root_data_collection = data_collection_repository.get_root_data_collection()

        index_name = f"{(user.first_name).lower()}_{(user.last_name).lower()}_{generate_short_id(4)}"

        # Get default embedding model config
        default_embedding = next(
            (m for m in EMBEDDING_MODELS if m.get("is_default")), EMBEDDING_MODELS[0]
        )
        embedding_model = default_embedding["embedding_model"]
        dense_dim = default_embedding["dimensions"]

        # Use MinIO bucket for local (knowledge collection)
        storage_bucket = os.getenv("MINIO_KNOWLEDGE_BUCKET", "assistcx-knowledge")

        if milvus_store.create_collection(
            collection_name=index_name, dense_dim=dense_dim
        ):
            private_data_collection = data_collection_repository.create_data_collection(
                {
                    "name": index_name,
                    "index_name": index_name,
                    "description": f"{user.first_name} {user.last_name}'s Private Data Collection.",
                    "icon": "folder",
                    "is_root": False,
                    "parent_id": root_data_collection.id,
                    "owner_id": user_uuid,
                    "status": "ACTIVE",
                    "collection_config": {
                        "embedding_model": embedding_model,
                        "data_store": {
                            "storage_type": "minio",
                            "storage_bucket": storage_bucket,
                            "storage_folder": "knowledge-collection",
                            "storage_region": "",
                        },
                    },
                    "availability": "PRIVATE",
                }
            )
            return private_data_collection
        else:
            logger.error(f"Failed to create Milvus collection for user: {user_uuid}")
            return None

    except Exception as e:
        logger.error(f"An error occurred in create_private_data_collection: {e}")
        return None


def collection_in_allowed_tree(
    collection: DataCollection, allowed_names: List[str], repo: DataCollectionRepository
) -> bool:
    """
    Check target or any ancestor matches an allowed collection name.

    Args:
        collection: Data Collection object to check.
        allowed_names: Allowed collection names.
        repo: Data Collection Repository instance.
    Returns:
        bool: True if the collection is in the allowed tree, False otherwise.
    """
    current = collection
    visited = set()
    while current is not None and current.id not in visited:
        visited.add(current.id)
        if current.name in allowed_names:
            return True
        if not current.parent_id:
            break
        current = repo.get_data_collection_by_id(current.parent_id)
    return False
