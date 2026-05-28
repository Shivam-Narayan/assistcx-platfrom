from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class EmbeddingModel(BaseModel):
    name: str
    description: Optional[str] = None
    embedding_model: str  # Unique identifier stored in collection_config
    provider: str
    integration_key: Optional[str] = None
    dimensions: int
    is_default: bool = False
    features: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

class EmbeddingModelsResponse(BaseModel):
    embedding_models: List[EmbeddingModel]
    total: int
