"""Utility functions for the Research Agent."""

import re
import os
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from collections import defaultdict

from langchain_core.documents import Document
from exa_py import Exa
from langchain_core.language_models import BaseChatModel
from jinja2 import Template

from .schemas import SourceDocument, ResearchKnowledge
from .prompts import KNOWLEDGE_SYNTHESIS_PROMPT
from knowledge.milvus_store import MilvusStore
from logger import configure_logging

logger = configure_logging(__name__)


# ============================================================================
# Tool Call Extraction
# ============================================================================


def extract_tool_call(response, schema_class):
    """Extract and validate tool call result from LLM response.

    This helper function extracts structured output from LLM responses that use
    the bind_tools() pattern, handling the tool_calls extraction and validation.

    Args:
        response: AIMessage from LLM with tool_calls attribute
        schema_class: Pydantic schema class to validate against (e.g., ResearchOutput)

    Returns:
        Validated schema instance

    Raises:
        ValueError: If no tool calls found or no matching schema tool call
    """
    if not response.tool_calls:
        raise ValueError(f"No tool calls in LLM response")

    schema_name = schema_class.__name__
    for tool_call in response.tool_calls:
        if tool_call["name"] == schema_name:
            return schema_class.model_validate(tool_call["args"])

    raise ValueError(
        f"No tool call found for schema '{schema_name}'. "
        f"Available: {[tc['name'] for tc in response.tool_calls]}"
    )



# ============================================================================
# Content Cleaning
# ============================================================================


def clean_web_content(text: str) -> str:
    """Clean messy web content for better processing.

    Handles navigation, ads, excessive formatting, and other web-specific issues.

    Args:
        text: Raw web content

    Returns:
        Cleaned content suitable for analysis
    """
    if not text or not isinstance(text, str):
        return ""

    # Remove common navigation and UI elements
    nav_patterns = [
        r"\[Skip to content\].*?\n",
        r"\[Home\].*?».*?\n",
        r"Table of Contents.*?\n",
        r"\[Toggle\].*?\n",
        r"Connect with us.*?\n",
        r"Sign Up.*?\n",
        r"Don\'t Miss.*?\n",
        r"Up Next.*?\n",
        r"You may also like.*?\n",
        r"Related Topics:.*?\n",
        r"Popular.*?\n",
    ]

    for pattern in nav_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Remove image references and data URIs
    text = re.sub(r"!\[.*?\]\(data:image/.*?\)", "", text)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)

    # Clean up links - keep text but remove URLs for long links
    text = re.sub(r"\[([^\]]+)\]\(https?://[^\s\)]{50,}\)", r"\1", text)

    # Remove standalone long URLs
    text = re.sub(r"https?://[^\s]{50,}", "", text)

    # Remove email/social sharing elements
    text = re.sub(
        r"- \[?(Twitter|Facebook|LinkedIn|Reddit|Pinterest|Email)\]?.*?\n", "", text
    )

    # Remove advertisement patterns
    ad_patterns = [
        r"\[!\[.*?\]\(.*?\)\]\(.*?\)",  # Ad banner markdown
        r'target="_blank".*?style=".*?"',  # Ad styling
        r"utm_source=.*?utm_campaign=.*?",  # Tracking parameters
    ]

    for pattern in ad_patterns:
        text = re.sub(pattern, "", text)

    # Clean up table formatting - preserve but simplify
    text = re.sub(r"\| --- \|", "|---|", text)
    text = re.sub(r"\|\s*\|\s*\|\s*\|", "|||", text)

    # Remove excessive newlines only
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)  # Max 2 consecutive newlines
    text = text.strip()

    return text


def clean_doc_chunk(text: str) -> str:
    """Simple cleanup for document chunks (PDFs, Word docs, etc.).

    Only handles basic formatting issues since document chunks are usually cleaner.

    Args:
        text: Document chunk content

    Returns:
        Cleaned content with basic formatting fixed
    """
    if not text or not isinstance(text, str):
        return ""

    # Remove image references (sometimes present in PDFs)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[Image:.*?\]", "", text)
    text = re.sub(r"Figure \d+:.*?\n", "", text)

    # Fix excessive newlines (max 2 consecutive)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()


# ============================================================================
# Web Search (Exa API)
# ============================================================================

EXA_SUMMARY_PROMPT = """Extract and summarize all key information from this web page. Include comprehensive details covering facts, data, insights, methodologies, examples, and contextual information. Prioritize completeness over brevity - capture all important content that could be relevant for understanding the topic thoroughly."""


async def perform_exa_search(queries: List[str], top_k: int = 4) -> List[Any]:
    """Perform Exa search for multiple queries concurrently.

    Args:
        queries: List of search queries
        top_k: Number of results per query

    Returns:
        Flattened list of all Exa search results
    """
    exa = Exa(api_key=os.environ["EXA_API_KEY"])

    async def search_query(query: str, delay: float = 0.5):
        await asyncio.sleep(delay)  # Stagger the start time
        # Run synchronous Exa search in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: exa.search_and_contents(
                query,
                type="auto",
                num_results=top_k,
                text=False,
                highlights=False,
                summary={"query": EXA_SUMMARY_PROMPT},
            ),
        )

    # Execute searches with staggered start times
    tasks = [search_query(q, i * 0.5) for i, q in enumerate(queries)]
    search_results = await asyncio.gather(*tasks)

    # Flatten results from all queries
    all_results = []
    for result in search_results:
        all_results.extend(result.results)

    return all_results


def exa_to_langchain(exa_results: List[Any]) -> List[Document]:
    """Convert Exa search results to LangChain Documents with deduplication.

    Args:
        exa_results: List of Exa search result objects

    Returns:
        List of deduplicated and sorted LangChain Documents
    """
    # Convert each result to Document
    documents = []
    for result in exa_results:
        # Use summary as primary content, fallback to text if available
        page_content = ""
        if hasattr(result, "summary") and result.summary:
            page_content = result.summary
        elif hasattr(result, "text") and result.text:
            page_content = result.text

        # Skip results without meaningful content
        if not page_content or len(page_content.strip()) < 50:
            continue

        # Build comprehensive metadata
        metadata = {
            "source": "exa",
            "url": getattr(result, "url", ""),
            "title": getattr(result, "title", ""),
            "score": getattr(result, "score", 0.0) or 0.0,
            "author": getattr(result, "author", None),
            "published_date": getattr(result, "publishedDate", None),
            "exa_id": getattr(result, "id", None),
        }

        # Remove None values from metadata
        metadata = {k: v for k, v in metadata.items() if v is not None}

        documents.append(Document(page_content=page_content, metadata=metadata))

    # Deduplicate by URL and keep highest scoring result
    unique_map = {}
    for doc in documents:
        url = doc.metadata.get("url", "")
        if not url:
            continue

        score = doc.metadata.get("score", 0.0)
        existing = unique_map.get(url)
        existing_score = existing.metadata.get("score", 0.0) if existing else 0.0

        if not existing or score > existing_score:
            unique_map[url] = doc

    # Sort by score (highest first)
    deduped = list(unique_map.values())
    deduped.sort(key=lambda d: d.metadata.get("score", 0.0), reverse=True)

    return deduped


# ============================================================================
# Source Deduplication
# ============================================================================


def deduplicate_sources(
    existing: List[SourceDocument], new: List[SourceDocument]
) -> List[SourceDocument]:
    """Deduplicate sources by ID or URL.

    Args:
        existing: Existing sources in state
        new: New sources to add

    Returns:
        List of unique new sources
    """
    if not new:
        return []

    # Determine the source type (all sources are the same type)
    source_type = new[0].source_type

    if source_type == "web_page":
        # For web pages, use URL as the uniqueness key
        existing_keys = {
            s.url for s in existing if s.source_type == "web_page" and s.url is not None
        }
        unique_new = [
            s for s in new if s.url is not None and s.url not in existing_keys
        ]
    else:
        # For document chunks, use ID as the uniqueness key
        existing_keys = {s.id for s in existing if s.source_type == "doc_chunk"}
        unique_new = [s for s in new if s.id not in existing_keys]

    return unique_new


# ============================================================================
# Citation Management
# ============================================================================


def sources_to_citations(text: str, sources: List[SourceDocument]) -> str:
    """Convert source UUIDs to numbered citations: [uuid] → [1]."""
    if not sources or not text:
        return text

    # Create mapping from source UUID to numeric index
    uuid_to_number = {src.id: str(idx + 1) for idx, src in enumerate(sources)}

    # Replace [uuid] with [number] using regex for precise matching
    result = text
    for uuid, number in uuid_to_number.items():
        # Use regex to match [uuid] exactly, avoiding partial matches
        pattern = rf"\[{re.escape(uuid)}\]"
        result = re.sub(pattern, f"[{number}]", result)

    return result


def citations_to_sources(text: str, sources: List[SourceDocument]) -> str:
    """Convert numbered citations to source UUIDs: [1] → [uuid]."""
    if not sources or not text:
        return text

    # Create mapping from numeric index to source UUID
    number_to_uuid = {str(idx + 1): src.id for idx, src in enumerate(sources)}

    # Replace [number] with [uuid] using regex for precise matching
    result = text
    for number, uuid in number_to_uuid.items():
        # Use regex to match [1], [2], etc., avoiding partial matches
        pattern = rf"\[{re.escape(number)}\]"
        result = re.sub(pattern, f"[{uuid}]", result)

    return result


def selected_sources_to_uuids(
    selected_sources: List[str], sources: List[SourceDocument]
) -> List[str]:
    """Convert selected_sources from citation indices ["1", "3"] to UUIDs."""
    converted = []
    for sid in selected_sources:
        try:
            idx = int(sid) - 1
            if 0 <= idx < len(sources):
                converted.append(sources[idx].id)
        except ValueError:
            # Already a UUID, keep it
            if any(s.id == sid for s in sources):
                converted.append(sid)
    return converted


# ============================================================================
# Source Formatting for LLM Prompts
# ============================================================================


def format_knowledge_collections(
    collections: List[Dict[str, Any]], include_details: bool = True
) -> Optional[str]:
    """Format knowledge collections for LLM prompt consumption.

    Args:
        collections: List of collection dictionaries
        include_details: If True, includes metadata fields and knowledge topics. If False, shows only basic collection info.

    Returns:
        Formatted string ready for LLM prompt inclusion
    """
    if not collections:
        return None

    formatted_collections = []

    for collection in collections:
        if include_details:
            # Detailed format with all information
            collection_info = [
                f"### {collection['name']}",
                f"- **Collection ID:** {collection['id']}",
                f"- **Collection Index:** {collection['index_name']}",
                f"- **Description:** {collection['description']}",
                f"- **Documents:** {collection['document_count']} documents",
            ]

            # Format metadata fields
            if collection.get("metadata_fields"):
                collection_info.append("\n**Metadata Fields:**")
                for field in collection["metadata_fields"]:
                    # Display list fields as "text" so LLM uses LIKE syntax (lists stored as comma-separated strings in Milvus)
                    display_type = field.get('data_type', 'text')
                    if display_type == 'list':
                        display_type = 'text'
                    desc = field['description'].rstrip('. ')
                    field_line = f"- {field['name']} (type: {display_type}): {desc}. "
                    field_line += f"Keywords: [{', '.join(field.get('keywords', []))}]"
                    collection_info.append(field_line)
            else:
                collection_info.append("\n**Metadata Fields:** N/A")

            # Format knowledge topics
            if collection.get("knowledge_topics"):
                collection_info.append("\n**Knowledge Topics:**")
                for topic in collection["knowledge_topics"]:
                    desc = topic['description'].rstrip('. ')
                    topic_line = f"- {topic['name']}: {desc}. Keywords: [{', '.join(topic.get('keywords', []))}]"
                    collection_info.append(topic_line)
            else:
                collection_info.append("\n**Knowledge Topics:** N/A")

            formatted_collections.append("\n".join(collection_info))
        else:
            # Basic format - just essential info with same structure
            collection_info = [
                f"### {collection['name']}",
                f"- **Collection ID:** {collection['id']}",
                f"- **Collection Index:** {collection['index_name']}",
                f"- **Description:** {collection['description']}",
                f"- **Documents:** {collection['document_count']} documents",
            ]
            formatted_collections.append("\n".join(collection_info))

    return "**Available Knowledge Collections:**\n\n" + "\n\n---\n\n".join(
        formatted_collections
    )


def format_web_sources(sources: List[SourceDocument]) -> str:
    """Format web page sources for LLM analysis.

    Args:
        sources: List of SourceDocument objects from web search

    Returns:
        Formatted markdown string ready for prompt inclusion
    """
    if not sources:
        return "No web sources found."

    formatted_sources = []

    for idx, source in enumerate(sources, 1):
        # Clean web content for better analysis
        cleaned_content = clean_web_content(source.content)

        source_block = [
            "---",
            f"**Source {idx}**",
            f"**ID:** {source.id}",
            f"**Title:** {source.title or 'Untitled Web Page'}",
            f"**Type:** {source.source_type}",
            f"**URL:** {source.url}",
        ]

        # Add web-specific metadata if available
        metadata = source.metadata or {}
        if author := metadata.get("author"):
            source_block.append(f"**Author:** {author}")
        if published_date := metadata.get("published_date"):
            source_block.append(f"**Published Date:** {published_date}")
        if source.relevance_score:
            source_block.append(f"**Relevance Score:** {source.relevance_score}")

        # Add content
        source_block.extend(["", "**Content:**", cleaned_content])

        formatted_sources.append("\n".join(source_block))

    return "\n\n".join(formatted_sources)


def _fetch_document_contexts(
    document_ids: List[str], collection_name: str, milvus_store: MilvusStore
) -> Dict[str, Any]:
    """Fetch document contexts for given document IDs using MilvusStore."""
    if not document_ids or not collection_name or not milvus_store:
        return {}

    try:
        doc_id_list = ", ".join([f'"{doc_id}"' for doc_id in document_ids])
        filter_expr = (
            f'record_type == "document_context" AND document_id in [{doc_id_list}]'
        )

        contexts = milvus_store.fetch_documents_with_filter(
            collection_name=collection_name,
            filter_expr=filter_expr,
            result_limit=len(document_ids),
            output_fields=["content", "document_id", "metadata"],
        )

        return {
            ctx.metadata["file_uuid"]: ctx
            for ctx in contexts
            if ctx.metadata and ctx.metadata.get("file_uuid")
        }
    except Exception:
        return {}


def _format_document_group(
    doc_id: str, sources: List[SourceDocument], doc_context=None, start_idx: int = 1
) -> str:
    """Format a single document with its chunks in hierarchical structure.

    Args:
        doc_id: Document ID
        sources: List of sources from this document
        doc_context: Optional document context
        start_idx: Starting index for source numbering (for global numbering across documents)
    """
    # Document header
    if doc_context:
        ctx_meta = doc_context.metadata or {}
        doc_title = ctx_meta.get("doc_title") or ctx_meta.get(
            "title", "Untitled Document"
        )
        doc_overview = clean_doc_chunk(doc_context.page_content)
        metadata = ctx_meta
    else:
        first_meta = sources[0].metadata or {}
        doc_title = first_meta.get("doc_title", "Untitled Document")
        doc_overview = f"Document contains {len(sources)} relevant sections."
        metadata = first_meta

    doc_block = [
        "---",
        f'## Document: "{doc_title}"',
        f"**Document ID:** {doc_id}",
    ]

    # Add metadata
    if filename := metadata.get("file_name"):
        doc_block.append(f"**File:** {filename}")
    if keywords := metadata.get("doc_keywords"):
        doc_block.append(f"**Keywords:** {', '.join(keywords)}")
    if knowledge_topic := metadata.get("knowledge_topic"):
        doc_block.append(f"**Knowledge Topic:** {knowledge_topic}")

    doc_block.extend(["", f"**Overview:** {doc_overview}", "", "### Related Content:"])

    # Add individual sources with numbering
    for local_idx, source in enumerate(sources):
        global_idx = start_idx + local_idx
        cleaned_content = clean_doc_chunk(source.content)
        relevance = (
            f" (Relevance: {source.relevance_score:.2f})"
            if source.relevance_score
            else ""
        )
        doc_block.extend(
            [
                "",
                f"#### Source {global_idx}",
                f"**ID:** {source.id}{relevance}",
                "**Content:**",
                cleaned_content,
            ]
        )

    return "\n".join(doc_block)


def format_knowledge_sources(
    sources: List[SourceDocument], milvus_store=None, collection_index: str = None
) -> str:
    """Format knowledge document sources for LLM analysis.

    Args:
        sources: List of SourceDocument objects from knowledge search
        milvus_store: Optional MilvusStore instance for enhanced document formatting
        collection_index: Milvus collection index name (preferred over metadata)

    Returns:
        Formatted markdown string ready for prompt inclusion
    """
    if not sources:
        return "No knowledge sources found."

    first_metadata = sources[0].metadata or {}
    record_type = first_metadata.get("record_type", "document_chunk")
    # Use provided collection_index (Milvus index name) first, fallback to metadata
    collection_name = collection_index or first_metadata.get(
        "index_name"
    ) or first_metadata.get("collection_index")

    # Try document-centric formatting for chunks/knowledge
    if (
        record_type in ["document_chunk", "document_knowledge"]
        and milvus_store
        and collection_name
    ):
        # Group sources by document_id
        doc_groups = defaultdict(list)
        for source in sources:
            doc_id = source.metadata.get("file_uuid") if source.metadata else None
            if doc_id:
                doc_groups[doc_id].append(source)

        # Fetch document contexts and format with hierarchy
        if doc_groups:
            doc_contexts = _fetch_document_contexts(
                list(doc_groups.keys()), collection_name, milvus_store
            )
            if doc_contexts:  # Only use enhanced formatting if contexts were fetched
                formatted_docs = []
                current_idx = 1
                for doc_id, doc_sources in doc_groups.items():
                    formatted_doc = _format_document_group(
                        doc_id,
                        doc_sources,
                        doc_contexts.get(doc_id),
                        start_idx=current_idx,
                    )
                    formatted_docs.append(formatted_doc)
                    current_idx += len(doc_sources)  # Track global source numbering
                return "\n\n".join(formatted_docs)

    # Simple formatting for record_type: document_context
    formatted_sources = []
    for idx, source in enumerate(sources, 1):
        cleaned_content = clean_doc_chunk(source.content)
        metadata = source.metadata or {}

        source_block = [
            "---",
            f"**Source {idx}**",
            f"**ID:** {source.id}",
            f"**Title:** {source.title or metadata.get('doc_title', 'Untitled Document')}",
            f"**Type:** {source.source_type}",
        ]

        if filename := metadata.get("file_name"):
            source_block.append(f"**File:** {filename}")
        if keywords := metadata.get("doc_keywords"):
            source_block.append(f"**Keywords:** {', '.join(keywords)}")
        if entities := metadata.get("doc_entities"):
            source_block.append(f"**Entities:** {', '.join(entities)}")
        if knowledge_topic := metadata.get("knowledge_topic"):
            source_block.append(f"**Knowledge Topic:** {knowledge_topic}")
        if source.relevance_score:
            source_block.append(f"**Relevance Score:** {source.relevance_score}")

        source_block.extend(["", "**Content:**", "", cleaned_content])
        formatted_sources.append("\n".join(source_block))

    return "\n\n".join(formatted_sources)


# ============================================================================
# Knowledge Synthesis
# ============================================================================


async def synthesize_knowledge(
    sources: List[SourceDocument],
    search_queries: List[str],
    search_type: str,
    llm: BaseChatModel,
    user_query: str = None,
    collection_index: str = None,
    previous_knowledge: str = None,
) -> ResearchKnowledge:
    """Synthesize knowledge from sources using LLM.

    Args:
        sources: List of source documents
        search_queries: List of search queries
        search_type: Type of search (document_metadata, knowledge_topic, document_content, web)
        llm: Language model to use
        user_query: The original user's question (for context)
        collection_index: Milvus collection index name for enhanced source formatting (optional)
        previous_knowledge: Synthesized knowledge from previous searches (optional)

    Returns:
        ResearchKnowledge object with synthesized knowledge and inline [source_id] citations
    """
    if not sources:
        return ResearchKnowledge(
            selected_sources=[],
            synthesized_knowledge="No sources found.",
            search_type=search_type,
            queries=search_queries,
        )

    # Format sources based on type
    web_sources = [s for s in sources if s.source_type == "web_page"]
    knowledge_sources = [s for s in sources if s.source_type == "doc_chunk"]

    formatted_sources = ""
    if web_sources:
        formatted_sources += format_web_sources(web_sources)
    if knowledge_sources:
        if formatted_sources:  # Add separator if both types exist
            formatted_sources += "\n\n"

        # Try enhanced formatting with MilvusStore
        try:
            milvus_store = MilvusStore()
            formatted_sources += format_knowledge_sources(
                knowledge_sources, milvus_store, collection_index
            )
        except Exception as e:
            logger.warning(f"Failed to use enhanced source formatting: {e}")
            formatted_sources += format_knowledge_sources(
                knowledge_sources, collection_index=collection_index
            )

    # Compute source summary for prompt header
    if web_sources:
        source_summary = f"{len(web_sources)} web sources"
    else:
        doc_ids = {s.metadata.get("file_uuid") for s in knowledge_sources if s.metadata}
        source_summary = f"{len(doc_ids)} documents, {len(knowledge_sources)} chunks"

    # Prepare prompt
    prompt_text = Template(KNOWLEDGE_SYNTHESIS_PROMPT).render(
        search_queries=search_queries,
        search_type=search_type,
        formatted_sources=formatted_sources,
        source_summary=source_summary,
        user_query=user_query,
        date_time=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    )

    # Invoke LLM with structured output (guarantees single response)
    structured_llm = llm.with_structured_output(ResearchKnowledge).with_retry(
        stop_after_attempt=2,
        wait_exponential_jitter=True,
    )

    try:
        knowledge = await structured_llm.ainvoke(prompt_text)

        # Convert number citations [1], [2], [3] to UUID citations [uuid1], [uuid2], [uuid3]
        # This maintains stable references in storage regardless of source ordering
        synthesized_text = citations_to_sources(
            knowledge.synthesized_knowledge, sources
        )
        converted_selected_sources = selected_sources_to_uuids(
            knowledge.selected_sources, sources
        )

        # Compute analysis summary and prepend to synthesized knowledge
        selected_sources_set = set(converted_selected_sources)

        def _plural(n, word):
            return f"{n} {word}" if n == 1 else f"{n} {word}s"

        if web_sources:
            selected_web = len([s for s in web_sources if s.id in selected_sources_set])
            analysis_summary = (
                f"**Analysis:** Searched {_plural(len(web_sources), 'web source')}"
                f" → {_plural(selected_web, 'source')} selected"
            )
        else:
            total_doc_ids = {s.metadata.get("file_uuid") for s in knowledge_sources if s.metadata}
            selected_doc_ids = {
                s.metadata.get("file_uuid") for s in knowledge_sources
                if s.id in selected_sources_set and s.metadata
            }
            selected_chunks = len([s for s in knowledge_sources if s.id in selected_sources_set])
            analysis_summary = (
                f"**Analysis:** Searched {_plural(len(knowledge_sources), 'chunk')}"
                f" across {_plural(len(total_doc_ids), 'document')}"
                f" → {_plural(selected_chunks, 'chunk')} selected"
                f" from {_plural(len(selected_doc_ids), 'document')}"
            )

        synthesized_text = f"{analysis_summary}\n\n---\n\n{synthesized_text}"

        return ResearchKnowledge(
            selected_sources=converted_selected_sources,
            synthesized_knowledge=synthesized_text,
            search_type=search_type,
            queries=search_queries,
        )
    except Exception as err:
        logger.error(f"Knowledge synthesis failed: {err}", exc_info=True)
        return ResearchKnowledge(
            selected_sources=[s.id for s in sources],
            synthesized_knowledge="Unable to synthesize knowledge from the retrieved sources due to a parsing error.",
            search_type=search_type,
            queries=search_queries,
        )
