"""Tool registry for creating LangChain StructuredTools."""

from typing import List
from langchain_core.tools import StructuredTool

from ..schemas import (
    DocumentMetadataSearchInput,
    KnowledgeTopicSearchInput,
    DocumentContentSearchInput,
    WebSearchInput,
)
from .knowledge_search import (
    document_metadata_search,
    knowledge_topic_search,
    document_content_search,
)
from .web_search import external_web_search


# ============================================================================
# Tool Descriptions
# ============================================================================


DOCUMENT_METADATA_SEARCH_DESCRIPTION = """Search document overviews and metadata via hybrid search. Returns document-level summaries, properties, and metadata — not detailed content. Optionally use metadata_filters to filter by metadata fields defined in the collection. Use for: finding relevant documents by query or metadata, document property lookups, discovering documents before deeper content search, high-level collection overview."""

KNOWLEDGE_TOPIC_SEARCH_DESCRIPTION = """Search pre-indexed per-document topic summaries for a specific knowledge topic. Returns one summary per document per topic — best for cross-document thematic comparison and aggregation. Supports metadata_filters to scope to a subset of documents. Use for: questions matching a predefined knowledge topic, thematic comparison across documents, per-document topic aggregation."""

DOCUMENT_CONTENT_SEARCH_DESCRIPTION = """Search all document content chunks across the knowledge collection via hybrid search. Returns the most relevant content chunks ranked by relevance. Supports metadata_filters to scope to specific documents. Use for: specific content or facts within documents, cross-document content search, broad exploratory queries, fallback when other tools are insufficient."""

EXTERNAL_WEB_SEARCH_DESCRIPTION = """Search external web sources for current information not available in the knowledge base. Use for: recent news and current events, public information not in internal collections, industry trends and market data."""

# ============================================================================
# Tool Registry
# ============================================================================


def get_research_tools() -> List[StructuredTool]:
    """Get all research agent tools as StructuredTools."""
    tool_definitions = [
        (document_metadata_search, "document_metadata_search", DOCUMENT_METADATA_SEARCH_DESCRIPTION, DocumentMetadataSearchInput),
        (knowledge_topic_search, "knowledge_topic_search", KNOWLEDGE_TOPIC_SEARCH_DESCRIPTION, KnowledgeTopicSearchInput),
        (document_content_search, "document_content_search", DOCUMENT_CONTENT_SEARCH_DESCRIPTION, DocumentContentSearchInput),
        (external_web_search, "external_web_search", EXTERNAL_WEB_SEARCH_DESCRIPTION, WebSearchInput),
    ]

    return [
        StructuredTool.from_function(
            func=fn, name=name, description=desc, args_schema=schema, coroutine=fn,
        )
        for fn, name, desc, schema in tool_definitions
    ]
