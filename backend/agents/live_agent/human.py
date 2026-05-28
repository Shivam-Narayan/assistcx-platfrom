"""Human-in-the-loop for live agent chat execution.

Standalone module — no imports from task_agent.
Uses LangGraph's interrupt() + Command(resume=...) for graph pausing/resuming.
"""

from typing import Any, Literal, Optional

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.types import Command, interrupt
from langgraph.errors import GraphBubbleUp
from pydantic import BaseModel, Field
from logger import configure_logging

logger = configure_logging(__name__)

# Valid HITL actions
HITL_ACTION = Literal["approve", "reject"]


class LiveHumanInput(BaseModel):
    """Human's response to a tool call review request in live chat."""

    action: HITL_ACTION = Field(description="Action taken by the human reviewer.")
    feedback: Optional[str] = Field(
        default=None,
        description="Feedback when rejecting — guides the agent to adjust its approach.",
    )


def requires_human_review(tool: BaseTool) -> bool:
    """Check if a tool is marked as requiring human review."""
    return (tool.metadata or {}).get("review_required", False)


async def human_review_node(
    state: Any, config: Optional[RunnableConfig] = None
) -> Command:
    """Interrupt execution for human review of tool calls.

    Supports parallel tool calls — interrupts once per reviewable tool.
    LangGraph pauses at the first interrupt; on resume, re-enters and
    hits the next interrupt until all are resolved.

    Actions:
      approve  -> route to tool node (execute as-is)
      reject   -> inject rejection ToolMessage, route to agent node
    """
    last_message = state.messages[-1]
    if not last_message.tool_calls:
        logger.error("human_review_node: no tool call in last message")
        return Command(goto="agent")

    try:
        # Interrupt for each tool call — LangGraph pauses at first,
        # resumes sequentially through each on subsequent resumes.
        rejected_messages = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_call_id = tool_call["id"]

            interrupt_payload = {
                "tool_call": tool_call,
                "message": f"Review required for {tool_name}",
            }
            human_input_raw = interrupt(interrupt_payload)
            human_input = LiveHumanInput(**human_input_raw)

            logger.info(f"human_review: tool={tool_name}, action={human_input.action}")

            if human_input.action == "reject":
                feedback = human_input.feedback or "Tool call rejected by reviewer."
                rejected_messages.append(
                    ToolMessage(
                        content=f"[REJECTED] {feedback}",
                        tool_call_id=tool_call_id,
                        name=tool_name,
                    )
                )

        # If any tool was rejected, send feedback to agent
        if rejected_messages:
            return Command(goto="agent", update={"messages": rejected_messages})

        # All approved — proceed to tool execution
        return Command(goto="tool")

    except GraphBubbleUp:
        raise
    except Exception as e:
        logger.error(f"Error in human review node: {e}")
        # Build error messages for all tool calls
        error_messages = [
            ToolMessage(
                content=f"Review failed due to error: {str(e)}",
                tool_call_id=tc["id"],
                name=tc["name"],
            )
            for tc in last_message.tool_calls
        ]
        return Command(goto="agent", update={"messages": error_messages})


