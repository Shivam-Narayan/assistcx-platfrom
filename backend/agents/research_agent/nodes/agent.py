"""Agent node with tool calling and direct response."""

from datetime import datetime, timezone
from typing import Dict, Any

from jinja2 import Template
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool

from ..schemas import ResearchState, DirectResponse, CompleteResearch
from ..utils import format_knowledge_collections
from ..config import MAX_TOOL_CALLS
from ..prompts import AGENT_SYSTEM_PROMPT


DIRECT_RESPONSE_TOOL = StructuredTool.from_function(
    func=lambda **kwargs: kwargs,
    name="DirectResponse",
    description="Respond directly without research. Use for: greetings, simple questions, needs_clarification, harmful_query, or questions answerable from the knowledge collection context.",
    args_schema=DirectResponse,
)

COMPLETE_RESEARCH_TOOL = StructuredTool.from_function(
    func=lambda **kwargs: kwargs,
    name="CompleteResearch",
    description="Signal that research is complete and sufficient to answer the question. Use when accumulated knowledge covers all aspects of the query.",
    args_schema=CompleteResearch,
)
from logger import configure_logging

logger = configure_logging(__name__)


async def agent_node(
    state: ResearchState,
    config: RunnableConfig,
    tools,
) -> Dict[str, Any]:
    """Agent node with tool calling and direct response.

    Uses ainvoke() — LangGraph's messages stream mode captures tokens
    automatically for real-time streaming at the graph level.

    Handles four response types:
    A) DirectResponse - non-research queries (answer streamed by graph)
    B) CompleteResearch - signal research done, route to answer_node
    C) Search tool calls - route to tool_node for execution
    D) Text response (no tool call) - fallback research completion or direct

    Args:
        state: Current research state
        config: Runnable configuration
        tools: List of tools (search tools)

    Returns:
        Updated state with new messages
    """
    node_config = config.get("configurable", {})
    llm = node_config.get("primary_llm")
    thread_id = node_config.get("thread_id", "unknown")
    knowledge_collections = node_config.get("knowledge_collections", [])
    previous_messages = node_config.get("previous_messages")
    user_context = node_config.get("user_context")
    current_date_time = node_config.get("current_date_time", "")

    if not llm:
        raise ValueError("primary_llm not found in config")

    # Bind all tools (search tools + DirectResponse + CompleteResearch) to LLM
    llm_with_tools = llm.bind_tools([*tools, DIRECT_RESPONSE_TOOL, COMPLETE_RESEARCH_TOOL], parallel_tool_calls=False)

    # Prepare system prompt with context
    formatted_collections = format_knowledge_collections(knowledge_collections)
    system_prompt = Template(AGENT_SYSTEM_PROMPT).render(
        knowledge_collections=formatted_collections,
        previous_messages=previous_messages,
        user_context=user_context,
        current_date_time=current_date_time,
    )

    # Prepare messages
    messages = list[AnyMessage](state.messages)
    if not messages or messages[0].type != "system":
        messages.insert(0, SystemMessage(content=system_prompt))

    # Nudge if last message was an AI response without tool calls (looped back by router)
    if len(messages) > 1:
        last_msg = messages[-1]
        if hasattr(last_msg, "tool_calls") and not last_msg.tool_calls:
            messages.append(HumanMessage(
                content="You must use a tool call in every response. Call a search tool, DirectResponse, or CompleteResearch."
            ))

    logger.info(
        f"[thread_id={thread_id}] agent_node: calling LLM with {len(messages)} messages"
    )

    max_tool_calls = node_config.get("max_tool_calls", MAX_TOOL_CALLS)
    current_tool_calls = state.tool_call_count

    try:
        # Invoke LLM — pass config so messages stream mode captures tokens
        response = await llm_with_tools.ainvoke(messages, config)

        # Build token record (same pattern as live agent)
        usage_metadata = response.usage_metadata or {}
        tool_call_name = None
        tool_call_id = None
        if response.tool_calls:
            tool_call_name = response.tool_calls[0]["name"]
            tool_call_id = response.tool_calls[0].get("id")

        token_record = {
            "node": "agent",
            "tool_call": tool_call_name,
            "tool_call_id": tool_call_id,
            "input_tokens": usage_metadata.get("input_tokens", 0),
            "output_tokens": usage_metadata.get("output_tokens", 0),
            "total_tokens": usage_metadata.get("total_tokens", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # (A) DirectResponse — answer tokens streamed by graph-level code
        if response.tool_calls and response.tool_calls[0]["name"] == "DirectResponse":
            args = response.tool_calls[0]["args"]
            final_answer = args.get("response", "")

            logger.info(
                f"[thread_id={thread_id}] agent_node: DirectResponse "
                f"query_type={args.get('query_type')}, answer_length={len(final_answer)}"
            )

            return {
                "messages": [AIMessage(content=final_answer)],
                "final_answer": final_answer,
                "title": args.get("title"),
                "query_type": args.get("query_type", "direct_response"),
                "research_complete": True,
                "token_usage": [token_record],
            }

        # (B) CompleteResearch — signal research done, route to answer_node
        if response.tool_calls and response.tool_calls[0]["name"] == "CompleteResearch":
            args = response.tool_calls[0]["args"]
            logger.info(
                f"[thread_id={thread_id}] agent_node: CompleteResearch, "
                f"title={args.get('title')}"
            )
            return {
                "messages": [AIMessage(content=args.get("reasoning", ""))],
                "research_complete": True,
                "title": args.get("title"),
                "token_usage": [token_record],
            }

        # (C) Search tool call → route to tool_node
        if response.tool_calls:
            tool_name = response.tool_calls[0]["name"]
            logger.info(
                f"[thread_id={thread_id}] agent_node: tool_call={tool_name} "
                f"(count: {current_tool_calls + 1}/{max_tool_calls})"
            )

            if current_tool_calls >= max_tool_calls:
                logger.warning(
                    f"[thread_id={thread_id}] agent_node: max tool calls "
                    f"({max_tool_calls}) reached, forcing research completion"
                )
                return {
                    "messages": [response],
                    "research_complete": True,
                    "tool_call_count": current_tool_calls + 1,
                    "token_usage": [token_record],
                }

            return {
                "messages": [response],
                "tool_call_count": current_tool_calls + 1,
                "token_usage": [token_record],
            }

        # (D) No tool call — router will loop back to agent with nudge
        logger.warning(
            f"[thread_id={thread_id}] agent_node: no tool call in response"
        )
        return {
            "messages": [response],
            "token_usage": [token_record],
        }

    except Exception as e:
        logger.error(f"[thread_id={thread_id}] agent_node error: {e}", exc_info=True)
        error_msg = HumanMessage(
            content=f"Error during reasoning: {str(e)}. Please try again with your query."
        )
        return {"messages": [error_msg]}
