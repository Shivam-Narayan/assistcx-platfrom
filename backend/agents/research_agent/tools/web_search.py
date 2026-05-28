"""Web search tool using Exa API."""

from typing import List, Optional

from typing_extensions import Annotated
from langchain_core.documents import Document
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from langgraph.prebuilt import InjectedState

from ..schemas import ResearchState, ResearchKnowledge, SourceDocument
from ..config import WEB_SEARCH_RESULT_COUNT
from ..utils import (
    perform_exa_search,
    exa_to_langchain,
    synthesize_knowledge,
    deduplicate_sources,
    clean_web_content,
)
from logger import configure_logging

logger = configure_logging(__name__)


async def external_web_search(
    queries: List[str],
    state: Annotated[ResearchState, InjectedState],
    config: RunnableConfig,
    result_count: int = WEB_SEARCH_RESULT_COUNT,
) -> Command:
    """Search external web sources for current information not in the knowledge base. This tool searches external web sources and returns content with latest and most relevant information related to the query.

    Use this when:
    - Need recent news, current events, or time-sensitive information
    - Query is about public information not in internal knowledge base
    - Query requires industry trends, market data, or statistics from intenet

    Args:
        queries: Search queries (max 4)
        state: Current research state (injected by LangGraph)
        config: Runnable configuration (injected by LangGraph)
        result_count: Number of web results to retrieve per query

    Returns:
        Dict with state updates: relevant_sources and research_knowledge
    """
    # Get LLM from config (prefer fast_llm for synthesis)
    node_config = config.get("configurable", {})
    llm = node_config.get("fast_llm") or node_config.get("primary_llm")

    # State is injected as ResearchState object by LangGraph
    research_state = state

    # Extract tool_call_id from the last message's tool_calls
    tool_call_id = research_state.messages[-1].tool_calls[0]["id"]

    # Perform Exa search with all queries
    exa_results = await perform_exa_search(queries, top_k=result_count)

    # Convert to LangChain documents
    langchain_docs: List[Document] = exa_to_langchain(exa_results)

    # Convert to SourceDocument objects
    sources: List[SourceDocument] = []
    for doc in langchain_docs:
        source = SourceDocument(
            content=clean_web_content(doc.page_content),
            source_type="web_page",
            title=doc.metadata.get("title") or "Untitled",
            url=doc.metadata.get("url") or None,
            relevance_score=doc.metadata.get("score"),
            metadata=doc.metadata,
        )
        sources.append(source)

    logger.info(f"Web search completed: {len(sources)} results retrieved")

    # Deduplicate sources
    unique_sources = deduplicate_sources(research_state.relevant_sources, sources)

    # Synthesize knowledge if sources found
    if sources:
        logger.info(f"Starting knowledge analysis: {len(sources)} web sources")
        # Synthesize knowledge with inline [source_id] citations

        # Get previous knowledge for context
        previous_knowledge: Optional[str] = None
        if research_state.research_knowledge:
            previous_knowledge = "\n\n".join(
                k.synthesized_knowledge for k in research_state.research_knowledge
            )

        knowledge = await synthesize_knowledge(
            sources=sources,
            search_queries=queries,
            search_type="web",
            llm=llm,
            user_query=research_state.original_query,
            previous_knowledge=previous_knowledge,
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
        # Return empty knowledge if no sources found
        knowledge = ResearchKnowledge(
            selected_sources=[],
            synthesized_knowledge="No relevant web pages were found for these queries.",
            search_type="web_search",
            queries=queries,
        )
        return Command(
            update={
                "research_knowledge": [knowledge],
                "messages": [
                    ToolMessage(
                        content=knowledge.synthesized_knowledge,
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )
