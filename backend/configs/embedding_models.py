"""
Embedding Models Configuration

This module defines available embedding models for knowledge collections.
Each collection can have ONE embedding model configured (immutable after set).

Structure:
- embedding_model: Unique identifier stored in collection_config (used to look up model)
- provider: "local" (self-hosted) or API provider name
- integration_key: Required integration for API-based models (None for local)
- dimensions: Vector dimensions (important for Milvus schema)
- is_default: Whether this is the default embedding model
- features: List of features supported by the model
- metadata: User-friendly and extra-detail fields for UI
"""

EMBEDDING_MODELS = [
    # ============================================
    # LOCAL MODELS (Self-hosted, no API key needed)
    # ============================================
    {
        "name": "Alibaba GTE Multilingual",
        "description": "High-quality multilingual embedding model. Fast, free, and runs locally. Recommended for most use cases.",
        "embedding_model": "Alibaba-NLP/gte-multilingual-base",
        "provider": "local",
        "integration_key": None,
        "dimensions": 768,
        "is_default": True,
        "features": ["multilingual", "local", "fast"],
        "metadata": {
            "speed": 5,
            "intelligence": 4,
            "type": "Local",
            "status": "Stable",
            "best_for": "General documents, multilingual content, PDFs, and first-time setup. No API key or extra cost.",
            "tags": ["Free", "No Setup", "Multilingual", "Recommended"],
            "short_label": "Free, runs on your server — no API key needed.",
            "recommended_badge": "Recommended",
            "provider_display_name": "Your server",
        },
    },
    # ============================================
    # OPENAI MODELS (Requires OpenAI integration)
    # ============================================
    {
        "name": "OpenAI Text Embedding 3 Small",
        "description": "Cost-effective OpenAI embedding model with excellent performance. Good balance of quality and cost.",
        "embedding_model": "openai/text-embedding-3-small",
        "provider": "openai",
        "integration_key": "openai",
        "dimensions": 1024,
        "is_default": False,
        "features": ["high-quality", "api", "cost-effective"],
        "metadata": {
            "speed": 5,
            "intelligence": 3,
            "type": "Cloud",
            "status": "Stable",
            "best_for": "When you need higher accuracy than the free model without the cost of the large model. Good for English and multilingual content.",
            "tags": ["Paid", "API Key Required", "Cost Effective"],
            "short_label": "Good quality at lower cost — requires OpenAI API key.",
            "recommended_badge": None,
            "provider_display_name": "OpenAI",
        },
    },
    {
        "name": "OpenAI Text Embedding 3 Large",
        "description": "Most powerful OpenAI embedding model. Best quality but higher cost.",
        "embedding_model": "openai/text-embedding-3-large",
        "provider": "openai",
        "integration_key": "openai",
        "dimensions": 1536,
        "is_default": False,
        "features": ["highest-quality", "api", "premium"],
        "metadata": {
            "speed": 3,
            "intelligence": 5,
            "type": "Cloud",
            "status": "Stable",
            "best_for": "Legal, medical, financial, or compliance-heavy content where precision matters most. Highest accuracy with higher cost.",
            "tags": ["Paid", "API Key Required", "Premium", "High Accuracy"],
            "short_label": "Highest quality — requires OpenAI API key and has higher per-use cost.",
            "recommended_badge": None,
            "provider_display_name": "OpenAI",
        },
    },
]

# ============================================
# SPARSE EMBEDDING CONFIG (Hardcoded)
# ============================================

SPARSE_EMBEDDING_CONFIG = {
    "name": "BM25",
    "description": "Built-in BM25 sparse retrieval for keyword matching",
    "type": "bm25",
    "enabled": True,
}

# ============================================
# LOOKUP DICTIONARIES (O(1) access)
# ============================================

EMBEDDING_MODELS_BY_KEY = {
    model["embedding_model"]: model for model in EMBEDDING_MODELS
}


def get_embedding_config(embedding_model: str) -> dict | None:
    """Get embedding model config by its identifier. O(1) lookup."""
    return EMBEDDING_MODELS_BY_KEY.get(embedding_model)
