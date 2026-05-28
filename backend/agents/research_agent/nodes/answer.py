"""Answer generation node for final research output."""

from datetime import datetime, timezone
from typing import Dict, Any

from jinja2 import Template
from langchain_core.runnables import RunnableConfig

from langchain_core.tools import StructuredTool

from ..schemas import ResearchState, ResearchOutput, ResearchKnowledge
from ..prompts import ANSWER_GENERATION_PROMPT
from ..utils import extract_tool_call, sources_to_citations

RESEARCH_OUTPUT_TOOL = StructuredTool.from_function(
    func=lambda **kwargs: kwargs,
    name="ResearchOutput",
    description="Generate the final research answer with citations and suggested follow-up queries.",
    args_schema=ResearchOutput,
)
from logger import configure_logging

logger = configure_logging(__name__)


async def answer_node(
    state: ResearchState,
    config: RunnableConfig,
) -> Dict[str, Any]:
    """Generate final comprehensive answer from accumulated research.

    Uses ainvoke() with config — LangGraph's messages stream mode
    captures tokens automatically for real-time answer streaming.

    Args:
        state: Current research state
        config: Runnable configuration

    Returns:
        Dict with updated state fields including final answer
    """
    node_config = config.get("configurable", {})
    llm = node_config.get("primary_llm")
    thread_id = node_config.get("thread_id", "unknown")

    if not llm:
        raise ValueError("primary_llm not found in config")

    try:
        logger.info(f"[thread_id={thread_id}] answer_node: generating final answer")

        # Fallback if no research knowledge
        if not state.research_knowledge:
            logger.warning(
                f"[thread_id={thread_id}] answer_node: no research knowledge available"
            )
            return {
                "final_answer": "I apologize, but I don't have enough information to answer your question. No research was conducted or no relevant sources were found.",
                "suggested_queries": [],
                "token_usage": [],
            }

        # Convert [uuid] citations to [1], [2] in research knowledge before sending to LLM
        formatted_knowledge = []
        for knowledge in state.research_knowledge:
            formatted_knowledge.append(
                ResearchKnowledge(
                    selected_sources=knowledge.selected_sources,
                    synthesized_knowledge=sources_to_citations(
                        knowledge.synthesized_knowledge, state.relevant_sources
                    ),
                    search_type=knowledge.search_type,
                    queries=knowledge.queries,
                )
            )

        # Extract additional context from config
        previous_messages = node_config.get("previous_messages")
        user_context = node_config.get("user_context", {})

        # Prepare prompt with formatted research knowledge
        answer_prompt = Template(ANSWER_GENERATION_PROMPT).render(
            date_time=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            original_query=state.original_query,
            previous_messages=previous_messages,
            user_context=user_context,
            research_knowledge=formatted_knowledge,
        )

        logger.info(
            f"[thread_id={thread_id}] answer_node: starting generation, "
            f"knowledge items={len(state.research_knowledge)}, "
            f"sources={len(state.relevant_sources)}"
        )

        # Invoke LLM with forced tool call — enables token streaming
        chain = llm.bind_tools([RESEARCH_OUTPUT_TOOL], tool_choice="ResearchOutput")
        response = await chain.ainvoke(answer_prompt, config)

        # Build token record
        usage_metadata = response.usage_metadata or {}
        token_record = {
            "node": "answer",
            "tool_call": None,
            "tool_call_id": None,
            "input_tokens": usage_metadata.get("input_tokens", 0),
            "output_tokens": usage_metadata.get("output_tokens", 0),
            "total_tokens": usage_metadata.get("total_tokens", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Parse ResearchOutput from tool call
        output = extract_tool_call(response, ResearchOutput)

        logger.info(
            f"[thread_id={thread_id}] answer_node: completed, "
            f"answer length={len(output.answer)}, "
            f"suggested queries={len(output.suggested_queries)}"
        )

        return_data = {
            "final_answer": output.answer,
            "suggested_queries": output.suggested_queries,
            "token_usage": [token_record],
        }

        # Set title from LLM output if available and not already set
        if hasattr(output, "title") and output.title and not state.title:
            return_data["title"] = output.title

        return return_data

    except Exception as e:
        logger.error(f"[thread_id={thread_id}] answer_node error: {e}", exc_info=True)
        return {
            "final_answer": f"I encountered an error while generating the answer: {str(e)}. Please try again.",
            "suggested_queries": [],
            "token_usage": [],
        }
