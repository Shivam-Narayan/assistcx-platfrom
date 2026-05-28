"""Knowledge search tools for searching internal knowledge base."""

import re
from typing import List, Optional, Dict, Any
from typing_extensions import Annotated
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from langgraph.prebuilt import InjectedState

from ..schemas import (
    ResearchState,
    ResearchKnowledge,
    SourceDocument,
)
from ..config import (
    SearchScope,
    DOCUMENT_METADATA_SEARCH_TOP_K,
    KNOWLEDGE_TOPIC_SEARCH_TOP_K,
    DOCUMENT_CONTENT_SEARCH_TOP_K,
)
from ..utils import synthesize_knowledge, deduplicate_sources, clean_doc_chunk
from logger import configure_logging

logger = configure_logging(__name__)
from knowledge.milvus_search import MilvusSearch
from knowledge.utils import get_embedding_model_for_collection
from langchain_core.language_models import BaseChatModel


# ============================================================================
# Private Helper Functions
# ============================================================================


def _process_search_filters(filter_expr: str) -> str:
    """Process filter expression: convert quoted values to lowercase for case-insensitive matching."""
    if not filter_expr:
        return filter_expr

    logger.info(f"Processing filter expression: {filter_expr}")

    # Convert all quoted values to lowercase (metadata values are stored normalized to lowercase)
    filter_expr = re.sub(r'"([^"]*)"', lambda m: f'"{m.group(1).lower()}"', filter_expr)

    logger.info(f"Processed filter expression: {filter_expr}")

    return filter_expr


def _format_metadata_results(sources: List[SourceDocument]) -> str:
    """Format document metadata results for agent consumption.

    Returns a structured list of documents with their metadata, suitable
    for both agent navigation (follow-up searches) and final answers
    about document properties.
    """
    if not sources:
        return "No documents found matching the search criteria."

    # Fields shown explicitly in fixed order
    ordered_keys = ["id", "file_uuid", "file_name", "type", "overview", "keywords", "entities"]
    # Internal/redundant keys to skip entirely
    skip_keys = {
        "document_id", "filename", "record_type", "created_at", "distance",
        "collection_name", "title",
        "doc_title", "doc_overview", "doc_keywords", "doc_entities",
    }

    lines = [f"## Documents Found ({len(sources)} results)\n"]
    for i, src in enumerate(sources, 1):
        meta = src.metadata or {}
        title = meta.get("title") or src.title or "Untitled"

        lines.append(f"### {i}. {title}")

        # Ordered fields first
        for key in ordered_keys:
            value = meta.get(key)
            if not value:
                continue
            if key == "overview":
                value = value[:500] + ("..." if len(value) > 500 else "")
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            lines.append(f"- **{key}:** {value}")

        # Remaining metadata fields (smart fields, page_count, etc.)
        shown = set(ordered_keys) | skip_keys
        for key, value in meta.items():
            if key in shown or not value:
                continue
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            lines.append(f"- **{key}:** {value}")

        lines.append("")

    return "\n".join(lines)


async def _execute_knowledge_search(
    queries: List[str],
    collection_index: str,
    search_scope: SearchScope,
    llm: BaseChatModel,
    research_state: ResearchState,
    result_limit: int,
    knowledge_collections: List[Dict[str, Any]],
    org_schema: str = "public",
    metadata_filters: Optional[str] = None,
    knowledge_topic: Optional[str] = None,
    file_ids: Optional[List[str]] = None,
    skip_synthesis: bool = False,
) -> Command:
    """Execute knowledge search and optionally synthesize results.

    Args:
        queries: Search queries (max 4)
        collection_index: Collection index name to search in
        search_scope: Search scope (document_metadata, knowledge_topic, document_content)
        llm: Language model for synthesis
        research_state: Current research state
        result_limit: Number of results to retrieve per query
        knowledge_collections: List of available knowledge collections
        org_schema: Organization schema for database lookups
        metadata_filters: Optional metadata filter expression
        knowledge_topic: Optional knowledge topic to focus the search
        skip_synthesis: If True, return formatted results directly without LLM synthesis.
                       Used by document_metadata_search for discovery/navigation.

    Returns:
        Command with state updates: messages, relevant_sources, and research_knowledge
    """
    # Extract tool_call_id from state
    tool_call_id = research_state.messages[-1].tool_calls[0]["id"]

    # Validate collection_index exists in available collections
    collection_found = any(
        coll.get("index_name") == collection_index for coll in knowledge_collections
    )

    if not collection_found:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Collection with index '{collection_index}' not found in available collections. Please check available knowledge collections and use correct collection index name for the search.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    # Build search configs for each query (index_name IS the Milvus collection name)
    search_config = {
        "collection_name": collection_index,
        "queries": queries,
        "search_scope": search_scope.value,
        "result_limit": result_limit,
    }

    # Add optional filters (preprocess to normalize case and translate IN syntax)
    if metadata_filters:
        search_config["filter_expr"] = _process_search_filters(metadata_filters)
    if knowledge_topic:
        search_config["knowledge_topic"] = knowledge_topic

    # Add file filtering if file_ids provided
    if file_ids:
        file_id_list = ", ".join([f'"{fid}"' for fid in file_ids])
        file_filter = f"document_id IN [{file_id_list}]"

        # Combine with existing filter if present
        existing_filter = search_config.get("filter_expr")
        search_config["filter_expr"] = (
            f"({existing_filter}) AND ({file_filter})"
            if existing_filter
            else file_filter
        )

    # Get the embedding model for this collection
    embedding_model = get_embedding_model_for_collection(org_schema, collection_index)
    logger.info(
        f"Using embedding model {embedding_model} for collection {collection_index}"
    )

    # Execute knowledge search
    milvus_search = MilvusSearch()
    results = await milvus_search.knowledge_search(
        dense_model=embedding_model, organization_schema=org_schema, **search_config
    )

    # Convert to SourceDocument objects
    sources: List[SourceDocument] = []
    for doc in results:
        # Resolve title: prefer file_name, then doc_title, then title
        doc_title = (
            doc.metadata.get("file_name")
            or doc.metadata.get("doc_title")
            or doc.metadata.get("title")
        )
        # Resolve URL from metadata if available
        doc_url = doc.metadata.get("url") or doc.metadata.get("source_url")

        source = SourceDocument(
            id=doc.metadata.get("id"),
            content=clean_doc_chunk(doc.page_content),
            source_type="doc_chunk",
            title=doc_title,
            url=doc_url,
            relevance_score=doc.metadata.get("distance"),
            metadata=doc.metadata,
        )
        sources.append(source)

    logger.info(
        f"Knowledge search ({search_scope.value}) completed: {len(sources)} results retrieved"
    )

    # For discovery/navigation tools (e.g., document_metadata_search),
    # return formatted results directly without LLM synthesis.
    # Still populate research_knowledge so answer_node can generate answers,
    # but don't add to relevant_sources (no citation mapping needed).
    if skip_synthesis:
        formatted = _format_metadata_results(sources)
        update = {
            "messages": [
                ToolMessage(content=formatted, tool_call_id=tool_call_id)
            ],
        }
        if sources:
            update["research_knowledge"] = [
                ResearchKnowledge(
                    selected_sources=[],
                    synthesized_knowledge=formatted,
                    search_type=search_scope.value,
                    queries=queries,
                )
            ]
        return Command(update=update)

    # Deduplicate sources and get unique ones to add to state
    unique_sources = deduplicate_sources(research_state.relevant_sources, sources)

    # Synthesize knowledge if sources found
    if sources:
        logger.info(f"Starting knowledge analysis: {len(sources)} knowledge sources")
        # Synthesize knowledge with inline [source_id] citations

        knowledge = await synthesize_knowledge(
            sources=sources,
            search_queries=queries,
            search_type=search_scope.value,
            llm=llm,
            user_query=research_state.original_query,
            collection_index=collection_index,
        )

        # Filter to only LLM-selected sources
        selected_sources = [
            s for s in unique_sources if s.id in knowledge.selected_sources
        ]

        logger.info(
            f"Knowledge analysis complete: {len(selected_sources)} sources selected"
        )

        # Return Command with knowledge in ToolMessage, sources in state only
        return Command(
            update={
                "research_knowledge": [knowledge],
                "relevant_sources": selected_sources,
                "messages": [
                    ToolMessage(
                        content=knowledge.synthesized_knowledge,
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )
    else:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="No relevant information was found in the knowledge base for these queries.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )


# ============================================================================
# Knowledge Search Tool Functions
# ============================================================================


async def document_metadata_search(
    queries: List[str],
    collection_index: str,
    state: Annotated[ResearchState, InjectedState],
    config: RunnableConfig,
    metadata_filters: Optional[str] = None,
) -> Command:
    """Search and filter documents by properties and metadata as specified in the knowledge collection. Use the metedata fields specified in the knowledge collection to create filter expression for the search.

    Use this when:
    - Query is about document properties and metadata rather than content
    - Query requires filtering and looking up metadata of the documents
    - Finding documents by specific metadata fields given in knowledge collection
    - Filtering documents by metadata before other search types are applicable
    - Need to get high-level understanding of the documents in the collection

    Args:
        queries: Search queries (max 4)
        collection_index: Index name of the knowledge collection to search
        state: Current research state (injected by LangGraph)
        config: Runnable configuration (injected by LangGraph)
        metadata_filters: Metadata filter expression using given fields

    Returns:
        Dict with state updates: relevant_sources and research_knowledge
    """
    node_config = config.get("configurable", {})
    llm = node_config.get("fast_llm") or node_config.get("primary_llm")
    knowledge_collections = node_config.get("knowledge_collections", [])
    user_context = node_config.get("user_context", {})
    org_schema = user_context.get("org_id", "public")
    research_state = state

    # Extract file_ids from user_context
    file_ids = user_context.get("file_ids")

    return await _execute_knowledge_search(
        queries=queries,
        collection_index=collection_index,
        search_scope=SearchScope.DOCUMENT_METADATA,
        llm=llm,
        research_state=research_state,
        result_limit=DOCUMENT_METADATA_SEARCH_TOP_K,
        knowledge_collections=knowledge_collections,
        org_schema=org_schema,
        metadata_filters=metadata_filters,
        file_ids=file_ids,
        skip_synthesis=True,
    )


async def knowledge_topic_search(
    queries: List[str],
    collection_index: str,
    knowledge_topic: str,
    state: Annotated[ResearchState, InjectedState],
    config: RunnableConfig,
    metadata_filters: Optional[str] = None,
) -> Command:
    """Search by predefined knowledge topics specified in the knowledge collection. This searches pre-indexed topic summaries that were created during document ingestion for the given knowledge collection. Supports metadata filters to scope to specific documents.

    Use this when:
    - Questions matching any of the available knowledge topics in the collection
    - Query requires thematic research across multiple documents on specific topic
    - Need comparative analysis of the topic across documents in the collection
    - Cross-document aggregation on a specific topic

    Args:
        queries: Search queries (max 4)
        collection_index: Index name of the knowledge collection to search
        knowledge_topic: Knowledge topic to focus the search
        state: Current research state (injected by LangGraph)
        config: Runnable configuration (injected by LangGraph)
        metadata_filters: Optional metadata filter expression to scope to specific documents

    Returns:
        Dict with state updates: relevant_sources and research_knowledge
    """
    node_config = config.get("configurable", {})
    llm = node_config.get("fast_llm") or node_config.get("primary_llm")
    knowledge_collections = node_config.get("knowledge_collections", [])
    user_context = node_config.get("user_context", {})
    org_schema = user_context.get("org_id", "public")
    research_state = state

    # Extract file_ids from user_context
    file_ids = user_context.get("file_ids")

    return await _execute_knowledge_search(
        queries=queries,
        collection_index=collection_index,
        search_scope=SearchScope.KNOWLEDGE_TOPIC,
        llm=llm,
        research_state=research_state,
        result_limit=KNOWLEDGE_TOPIC_SEARCH_TOP_K,
        knowledge_collections=knowledge_collections,
        org_schema=org_schema,
        metadata_filters=metadata_filters,
        knowledge_topic=knowledge_topic,
        file_ids=file_ids,
    )


async def document_content_search(
    queries: List[str],
    collection_index: str,
    state: Annotated[ResearchState, InjectedState],
    config: RunnableConfig,
    metadata_filters: Optional[str] = None,
) -> Command:
    """Search across all content chunks in the knowledge collection. Performs hybrid search on document content returning the most relevant results. Supports metadata filters to scope the search to specific documents.

    Use this when:
    - Searching for specific content or facts within documents
    - Cross-document content search and aggregation
    - Broad or exploratory queries requiring maximum coverage
    - Fallback when other search types do not yield sufficient results

    Args:
        queries: Search queries (max 4)
        collection_index: Index name of the knowledge collection to search
        state: Current research state (injected by LangGraph)
        config: Runnable configuration (injected by LangGraph)
        metadata_filters: Optional metadata filter expression to scope to specific documents

    Returns:
        Dict with state updates: relevant_sources and research_knowledge
    """
    node_config = config.get("configurable", {})
    llm = node_config.get("fast_llm") or node_config.get("primary_llm")
    knowledge_collections = node_config.get("knowledge_collections", [])
    user_context = node_config.get("user_context", {})
    org_schema = user_context.get("org_id", "public")
    research_state = state

    # Extract file_ids from user_context
    file_ids = user_context.get("file_ids")

    return await _execute_knowledge_search(
        queries=queries,
        collection_index=collection_index,
        search_scope=SearchScope.DOCUMENT_CONTENT,
        llm=llm,
        research_state=research_state,
        result_limit=DOCUMENT_CONTENT_SEARCH_TOP_K,
        knowledge_collections=knowledge_collections,
        org_schema=org_schema,
        metadata_filters=metadata_filters,
        file_ids=file_ids,
    )
