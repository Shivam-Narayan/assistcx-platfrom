"""
Research Agent Module

A dynamic research agent that uses tool calling to perform knowledge and web search.

Key Features:
- Agent loop with tool calling (not static graph)
- 3 knowledge search types: document_metadata, knowledge_topic, document_content
- Web search for external information
- Dynamic synthesis of knowledge from sources
- Proper agent reasoning and iteration control

Usage:
    from agents.research_agent import ResearchAgentGraph

    graph = ResearchAgentGraph(organization_schema)
    result = await graph.invoke({
        "original_query": "What are the deployment best practices?",
        "knowledge_collections": [...],
        "metadata": {...}
    })
"""

from .graph import ResearchAgentGraph
from .schemas import ResearchState, ResearchOutput, SourceDocument

__all__ = [
    "ResearchAgentGraph",
    "ResearchState",
    "ResearchOutput",
    "SourceDocument",
]
