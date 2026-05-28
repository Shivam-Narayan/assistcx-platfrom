"""Tool execution node with direct tool invocation."""

from typing import Dict, Any

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import merge_configs
from langgraph.types import Command

from agents.shared_utils.token_handler import TokenHandler
from ..schemas import ResearchState
from logger import configure_logging

logger = configure_logging(__name__)


async def tool_node(
    state: ResearchState,
    config: RunnableConfig,
    tools_by_name: Dict[str, Any],
) -> Command:
    """Execute the tool call from the last message.

    All research tools return Command objects with state updates,
    so this node has a single unified code path.

    Args:
        state: Current research state
        config: Runnable configuration
        tools_by_name: Tool name → tool mapping (injected via partial)

    Returns:
        Command from the executed tool
    """
    thread_id = config.get("configurable", {}).get("thread_id", "unknown")

    last_message = state.messages[-1]
    if not last_message.tool_calls:
        logger.warning(f"[thread_id={thread_id}] tool_node: no tool calls")
        return Command(update={"messages": []})

    tool_call = last_message.tool_calls[0]
    tool_name = tool_call["name"]
    tool_call_id = tool_call.get("id")

    tool = tools_by_name.get(tool_name)
    if not tool:
        error_msg = f"Tool '{tool_name}' not found"
        logger.error(f"[thread_id={thread_id}] tool_node: {error_msg}")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Error: {error_msg}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    logger.info(f"[thread_id={thread_id}] tool_node: executing {tool_name} tool")

    try:
        # Token tracking via callback
        token_handler = TokenHandler(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )
        tool_config = merge_configs(config, {"callbacks": [token_handler]})

        # Build tool arguments with state injection
        tool_args = {**tool_call.get("args", {})}
        tool_args["state"] = state

        # Execute tool — all tools return Command
        result = await tool.ainvoke(tool_args, config=tool_config)
        token_usage = token_handler.tokens

        logger.info(
            f"[thread_id={thread_id}] tool_node: {tool_name} successful, "
            f"tool_internal_llm_calls={len(token_usage)}"
        )

        # Inject token usage into the Command's update dict
        if token_usage and result.update:
            result.update["token_usage"] = token_usage
        return result

    except Exception as e:
        logger.error(
            f"[thread_id={thread_id}] tool_node: {tool_name} failed: {e}",
            exc_info=True,
        )
        raise
