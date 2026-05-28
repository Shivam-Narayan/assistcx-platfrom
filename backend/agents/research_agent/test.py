"""
Simple test file for Research Agent.
Run from backend directory: python agents/research_agent/test.py
"""

import asyncio
import os
from dotenv import load_dotenv
from agents.research_agent import ResearchAgentGraph
from agents.shared_utils import LLMProvider
from logger import configure_logging

load_dotenv()

logger = configure_logging(__name__)


async def main():
    """Main test function."""

    # Test query
    query = "What are the latest developments in quantum computing?"
    org_schema = "public"
    user_id = "test-user"
    thread_id = "test-thread"
    previous_messages = []
    user_context = {
        "user_id": user_id,
        "organization_schema": org_schema,
    }

    # Collections to search (include collection objects)
    knowledge_collections = [
        {
            "id": "123",
            "name": "Test Collection",
            "index_name": "test_collection",
            "description": "Test collection description",
            "document_count": 100,
            "metadata_fields": [
                {
                    "name": "field1",
                    "description": "Field 1 description",
                    "data_type": "text",
                    "keywords": ["keyword1", "keyword2", "keyword3"],
                }
            ],
            "knowledge_topics": [
                {
                    "name": "topic1",
                    "description": "Topic 1 description",
                    "keywords": ["keyword1", "keyword2"],
                },
            ],
        }
    ]

    # Initialize LLM provider
    llm_provider = LLMProvider(organization_schema=org_schema)

    # Get LLMs
    primary_llm = llm_provider.get_llm(llm_key="openai/gpt-4.1", temperature=0.1)

    fast_llm = llm_provider.get_llm(llm_key="openai/gpt-4.1-mini", temperature=0)

    config = {
        "configurable": {
            "thread_id": thread_id,
            "knowledge_collections": None,
            "previous_messages": previous_messages,
            "user_context": user_context,
        }
    }

    # Initialize research agent
    agent = ResearchAgentGraph(
        primary_llm=primary_llm,
        fast_llm=fast_llm,
    )

    logger.info("=" * 60)
    logger.info("Testing Research Agent")
    logger.info("=" * 60)
    logger.info(f"Query: {query}\n")

    async for chunk in agent.stream_response(query=query, config=config):
        chunk_type = chunk.get("type")

        if chunk_type == "state":
            msg_count = len(chunk.get("messages", []))
            tool_count = chunk.get("tool_call_count", 0)
            source_count = len(chunk.get("relevant_sources", []))
            knowledge_count = len(chunk.get("research_knowledge", []))
            logger.info(
                f"[STATE] messages={msg_count}, tools={tool_count}, sources={source_count}, knowledge={knowledge_count}"
            )

        elif chunk_type == "event":
            event = chunk.get("event", "unknown")
            node = chunk.get("node", "")
            logger.info(f"[{node.upper()}] {event}")

        elif chunk_type == "answer":
            content = chunk.get("content", "")
            # Keep print for answer streaming effect
            print(content, end="", flush=True)

    logger.info("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
