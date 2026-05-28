"""Configuration constants for the Research Agent."""

from enum import Enum


# Graph Configuration
MAX_ITERATIONS = 25  # Maximum recursion limit for agent loop
MAX_TOOL_CALLS = 5  # Maximum tool calls before forcing completion


# Search Configuration - Top K defaults per tool (score cutoff handles relevance filtering)
DOCUMENT_METADATA_SEARCH_TOP_K = 100  # Document-level summaries
KNOWLEDGE_TOPIC_SEARCH_TOP_K = 100  # Topic-based search
DOCUMENT_CONTENT_SEARCH_TOP_K = 100  # Document content search
WEB_SEARCH_RESULT_COUNT = 4  # Number of web results to retrieve per query


# Search Scopes (for knowledge search)
class SearchScope(str, Enum):
    """Knowledge search scope types."""

    DOCUMENT_METADATA = "document_metadata"
    KNOWLEDGE_TOPIC = "knowledge_topic"
    DOCUMENT_CONTENT = "document_content"
