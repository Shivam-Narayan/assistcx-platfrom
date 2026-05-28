from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict, Union
import logging
import numpy as np
import re

logger = logging.getLogger(__name__)


def convert_sparse_vector(sparse_vector: Any) -> Dict[int, float]:
    """
    Convert sparse vector to Milvus-compatible dictionary format.

    Args:
        sparse_vector: CSR matrix, NumPy array, or dictionary.

    Returns:
        Dictionary with indices as keys and values as floats.
    """
    # Handle scipy sparse matrices (CSR, CSC, COO, etc.)
    if hasattr(sparse_vector, "tocoo"):
        if len(sparse_vector.shape) == 1:
            sparse_vector = sparse_vector.reshape(1, -1)
        coo = sparse_vector.tocoo()
        if coo.shape[0] != 1:
            raise ValueError(f"Expected 1 row, got shape: {coo.shape}")
        return {int(col): float(val) for col, val in zip(coo.col, coo.data)}
    # Handle numpy arrays
    elif isinstance(sparse_vector, np.ndarray):
        if sparse_vector.ndim == 1:
            nonzero_indices = np.nonzero(sparse_vector)[0]
            values = sparse_vector[nonzero_indices]
            return {int(idx): float(val) for idx, val in zip(nonzero_indices, values)}
        elif sparse_vector.ndim == 2:
            if sparse_vector.shape[0] != 1:
                raise ValueError(f"Expected 1 row, got shape: {sparse_vector.shape}")
            nonzero_indices = np.nonzero(sparse_vector[0])[0]
            values = sparse_vector[0, nonzero_indices]
            return {int(idx): float(val) for idx, val in zip(nonzero_indices, values)}
        else:
            raise ValueError(f"Unsupported array dimensions: {sparse_vector.ndim}")
    # Handle dictionaries
    elif isinstance(sparse_vector, dict):
        return {int(k): float(v) for k, v in sparse_vector.items() if v != 0}
    else:
        raise TypeError("Unsupported type for sparse vector conversion.")


class DocumentContext(BaseModel):
    """A structured document context of a document's key information."""

    title: str = Field(
        description="A clear and concise title that captures the document's main subject or purpose."
    )
    type: Optional[str] = Field(
        default=None,
        description="The broad functional category or type of document (e.g., 'contract', 'policy', 'report', 'guide', 'email' etc.)",
    )
    overview: str = Field(
        description="Comprehensive 5-10 sentence summary covering document type, overview, purpose, key information, entities, dates, and context"
    )
    keywords: List[str] = Field(
        description="5-10 key terms, entities, topics, or keywords that are central to the document's content"
    )
    entities: List[str] = Field(
        default_factory=list,
        description="Key entities mentioned in the document such as organizations, people, groups, products, locations, dates, etc.",
    )
    filename: str = Field(
        description="The filename of the document that is being summarized (Same as the file name in input)"
    )


def normalize_text(text: Union[str, List[str]]) -> Union[str, List[str]]:
    """Normalize text for reliable matching. Handles both strings and lists of strings."""
    if isinstance(text, list):
        # Handle list of strings
        return [normalize_text(item) for item in text if item]
    elif isinstance(text, str):
        # Handle single string
        if not text:
            return ""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)  # Remove special characters
        text = re.sub(r"\s+", " ", text)  # Normalize spaces
        return text
    else:
        # Return as-is for non-string/non-list types
        return text


def format_document_context(document_context: Dict[str, Any]) -> str:
    """Format a document context dict into a standard text representation."""
    return (
        f"Title: {document_context.get('title', '')}\n"
        f"Type: {document_context.get('type', '')}\n"
        f"Overview: {document_context.get('overview', '')}\n"
        f"Keywords: {', '.join(document_context.get('keywords', []))}\n"
        f"Entities: {', '.join(document_context.get('entities', []))}\n"
        f"Filename: {document_context.get('filename', '')}"
    )


def get_embedding_model_for_collection(org_schema: str, collection_name: str) -> str:
    """
    Look up the embedding model configured for a Milvus collection.

    Creates its own DB session, so safe to call from anywhere.
    """
    from db_pool import DatabasePoolManager
    from repository.data_collection_repository import DataCollectionRepository

    try:
        db_pool = DatabasePoolManager()
        with db_pool.get_session(org_schema) as db:
            repo = DataCollectionRepository(db)
            collection = repo.get_data_collection_by_index_name(collection_name)
            if collection and collection.collection_config:
                return collection.collection_config.get("embedding_model") or ""
            return ""
    except Exception as e:
        logger.warning(f"Failed to get embedding model for {collection_name}: {e}")
        return ""


class SmartFieldExtraction(BaseModel):
    """Extracted smart field value with proper typing."""

    field_name: str = Field(description="Name of the extracted field")
    field_value: Optional[Union[str, int, float, bool, List[str]]] = Field(
        description="Extracted field value: str for text/date, int/float for number, bool for boolean, List[str] for list, or null if not found"
    )
