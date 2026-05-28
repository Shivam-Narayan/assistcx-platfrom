"""Schemas for the Research Agent."""

from typing import Dict, List, Literal, Optional, Any, Annotated
from uuid import uuid4
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, AnyMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt import InjectedState
from operator import add


# Query classification types
QueryClassification = Literal[
    "direct_response", "needs_clarification", "harmful_query", "requires_research"
]


# Direct Response Schema (structured output for non-research responses from agent)
class DirectResponse(BaseModel):
    """Structured output for non-research direct responses from agent node."""

    title: str = Field(
        description="A brief title for the user query, to be used as title of chat thread."
    )
    query_type: QueryClassification = Field(
        description="Classification of the user query: direct_response, needs_clarification, or harmful_query"
    )
    response: str = Field(
        description="The direct response to the user's query. For direct_response: friendly, conversational answer. For needs_clarification: clarifying questions. For harmful_query: polite decline."
    )


# Complete Research Schema (structured output to signal research completion)
class CompleteResearch(BaseModel):
    """Signal that research is complete and ready for answer generation."""

    reasoning: str = Field(
        description="Why the accumulated research is sufficient to answer the question"
    )
    title: str = Field(
        description="A brief title for the chat thread based on the user's query"
    )


# Source Document Model
class SourceDocument(BaseModel):
    """Source document that can represent document chunks or web search results."""

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for the source.",
    )
    content: str = Field(description="The textual content from this source.")
    source_type: Literal["doc_chunk", "web_page"] = Field(
        description="Type of the source (document or web)."
    )
    title: Optional[str] = Field(
        default=None, description="Title of the document or web page."
    )
    url: Optional[str] = Field(
        default=None, description="URL if the source is web-based."
    )
    relevance_score: Optional[float] = Field(
        default=None, description="Relevance score of the source to the query."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (collection name, file name, file type, page number, etc.)",
    )


# Research Knowledge Entry
class ResearchKnowledge(BaseModel):
    """Synthesized knowledge from a search operation."""

    selected_sources: List[str] = Field(
        description="List of source index numbers (1, 2, 3, etc.) used to synthesize relevant knowledge. Example: ['1', '3', '5']"
    )
    synthesized_knowledge: str = Field(
        min_length=100,
        description="Relevant knowledge synthesized from selected sources with inline [1], [2], [3] citations",
    )
    # Metadata fields — populated after LLM synthesis, not part of LLM tool schema
    search_type: Optional[str] = Field(
        default=None,
        description="Type of search that produced this knowledge (e.g., document_focused, web)",
    )
    queries: Optional[List[str]] = Field(
        default=None,
        description="Search queries used to retrieve sources for this knowledge",
    )


# Research State for Agent Loop
class ResearchState(BaseModel):
    """State for the research agent graph."""

    # Core conversation - agent loop uses message history
    messages: Annotated[List[AnyMessage], add_messages] = Field(
        default_factory=list,
        description="Agent conversation history including tool calls and results",
    )

    # Query context
    original_query: str = Field(description="The original user query to research")

    # Research accumulation
    relevant_sources: Annotated[List[SourceDocument], add] = Field(
        default_factory=list,
        description="Selected sources that were actually used in research (deduplicated)",
    )
    research_knowledge: Annotated[List[ResearchKnowledge], add] = Field(
        default_factory=list,
        description="Synthesized knowledge from each search operation",
    )

    # Query classification output
    query_type: QueryClassification = Field(
        default="requires_research",
        description="Classification of the user query",
    )
    title: Optional[str] = Field(
        default=None,
        description="Title for the chat thread",
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Session metadata (org_schema, session_id, user_id, thread_id, etc.)",
    )

    # Agent control
    tool_call_count: int = Field(
        default=0,
        description="Number of tools called by agent (used to enforce max limit)",
    )
    research_complete: bool = Field(
        default=False,
        description="Flag to signal research completion and route to answer node",
    )
    final_answer: Optional[str] = Field(
        default=None,
        description="Final answer text (for all query types)",
    )
    suggested_queries: List[str] = Field(
        default_factory=list,
        description="Suggested queries for the follow up question.",
    )
    # Token consumption tracking (accumulates across multiple LLM calls)
    token_usage: Annotated[List[Dict[str, Any]], add] = Field(
        default_factory=list,
        description="List of token usage records for each LLM call in this task execution. Each record contains node name, tool call, input/output tokens, and timestamp.",
    )

    class Config:
        arbitrary_types_allowed = True


# Tool Input Schemas
class BaseKnowledgeSearchInput(BaseModel):
    """Shared fields for all knowledge searches."""

    queries: List[str] = Field(
        min_length=1,
        description="List of 1-4 search queries that cover different aspects of the user's question. Each query should be specific and focused on a particular aspect.",
    )
    collection_index: str = Field(
        description="The index_name of the knowledge collection to search. Must exactly match an index_name from the available collections list provided. Do not use the display name or make up new names."
    )
    state: Annotated[ResearchState, InjectedState]


class DocumentMetadataSearchInput(BaseKnowledgeSearchInput):
    """Input schema for document metadata search."""

    metadata_filters: Optional[str] = Field(
        default=None,
        description='Metadata filter expression to filter documents by their properties. Use metadata fields specified in the collection. Format: `metadata["field_name"] OPERATOR value`.',
    )


class KnowledgeTopicSearchInput(BaseKnowledgeSearchInput):
    """Input schema for knowledge topic search."""

    knowledge_topic: str = Field(
        description="The specific knowledge topic to search within. Must exactly match one of the knowledge topics listed for the collection."
    )
    metadata_filters: Optional[str] = Field(
        default=None,
        description='Optional metadata filter expression to scope search to specific documents. Uses metadata fields from the collection. Format: `metadata["field_name"] OPERATOR value`.',
    )


class DocumentContentSearchInput(BaseKnowledgeSearchInput):
    """Input schema for document content search."""

    metadata_filters: Optional[str] = Field(
        default=None,
        description='Optional metadata filter expression to scope search to specific documents. Uses metadata fields from the collection. Format: `metadata["field_name"] OPERATOR value`.',
    )


class WebSearchInput(BaseModel):
    """Input for external web search to find current information from internet sources."""

    queries: List[str] = Field(
        min_length=1,
        description="List of 1-4 web search queries to find current information from the internet. Each query should be optimized for web search engines and focus on different aspects of the information needed.",
    )
    state: Annotated[ResearchState, InjectedState]


# Final Answer Schema
class ResearchOutput(BaseModel):
    """Final output from the research agent."""

    title: Optional[str] = Field(
        default=None,
        description="A brief title for the user query, to be used as title of chat thread.",
    )
    answer: str = Field(
        description="Comprehensive answer to the user's query in markdown format with inline [1], [2] citations"
    )
    suggested_queries: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="3-5 relevant follow-up questions related to the user's query and the answer that users might want to explore further",
    )
