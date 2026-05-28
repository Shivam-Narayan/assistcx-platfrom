import json
from typing import List, Dict, Any, Optional
from langgraph.types import interrupt, Command
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import ToolMessage, AIMessage
from langgraph.errors import GraphBubbleUp
from jinja2 import Template
from logger import configure_logging
from .prompts import (
    LLM_REVIEW_PROMPT,
    HUMAN_REJECT_PROMPT,
)
from .schemas import HumanInput, HumanReviewRecord

# Configure logging for this module
logger = configure_logging(__name__)


# Helper to check if a tool requires human review
def requires_human_review(tool: BaseTool) -> bool:
    """Checks if a tool is marked as requiring human review."""
    return (tool.metadata or {}).get("review_required", False)


# Structured output schema for LLM review decisions
class LLMReviewDecision(BaseModel):
    """LLM's decision on whether a tool call requires human review."""

    requires_review: bool = Field(
        description="Whether the tool call needs human review."
    )
    reasoning: str = Field(
        description="Why the decision was made (rule violations, concerns, or why auto-approved)."
    )
    question: Optional[str] = Field(
        default=None,
        description=(
            "A short question (1-2 sentences) for the reviewer about what to decide. "
            "Do not repeat the tool name or input. Required when requires_review=True."
        ),
    )


# Helper function to perform LLM review
async def perform_llm_review(
    tool_call: Dict[str, Any], rules: List[str], llm: Any
) -> LLMReviewDecision:
    """Performs LLM-based review to determine if a tool call requires human review.

    Args:
        tool_call: The tool call to evaluate (dict with name, args, id)
        rules: List of review rules to evaluate
        llm: The LLM instance to use for evaluation

    Returns:
        LLMReviewDecision: The structured decision from the LLM. On error or when
            no rules are provided, returns a fail-safe decision with
            requires_review=True.
    """
    if not rules:
        return LLMReviewDecision(
            requires_review=True,
            reasoning="No review rules configured; defaulting to human review.",
            question=None,
        )

    try:
        tool_name = tool_call["name"]
        tool_args = tool_call.get("args", {})
        tool_input = (
            json.dumps(tool_args, indent=2)
            if isinstance(tool_args, (dict, list))
            else str(tool_args)
        )
        review_prompt = Template(LLM_REVIEW_PROMPT).render(
            tool_name=tool_name,
            tool_input=tool_input,
            review_rules="\n".join([f"{i}. {rule}" for i, rule in enumerate(rules, 1)]),
        )

        structured_llm = llm.with_structured_output(LLMReviewDecision)
        decision = await structured_llm.ainvoke(review_prompt)

        logger.info(
            f"LLM review for {tool_name}: "
            f"requires_review={decision.requires_review}, reasoning={decision.reasoning}"
        )
        return decision

    except Exception as e:
        logger.error(f"Error in LLM rule evaluation: {str(e)}", exc_info=True)
        return LLMReviewDecision(
            requires_review=True,
            reasoning=f"LLM evaluation failed: {str(e)}",
            question=None,
        )


# Handling human review of proposed tool calls
async def human_review_node(
    state: Any, config: Optional[RunnableConfig] = None
) -> Command:
    """Processes human input for reviewing a single tool call.

    This node:
    1. Optionally evaluates LLM rules to auto-approve
    2. Interrupts to get human input
    3. Routes to appropriate next node based on human action

    Args:
        state: Current graph state with messages
        config: RunnableConfig with configurable containing llm and rules

    Returns:
        Command: LangGraph command with routing and state updates
    """
    try:
        # Get the tool call from the last message
        last_message = state.messages[-1]
        if not last_message.tool_calls:
            logger.error("No tool call found in last message")
            return Command(goto="agent")

        tool_call = last_message.tool_calls[0]
        tool_call_id = tool_call["id"]
        tool_name = tool_call["name"]

        # Get LLM and per-tool rules from configurable
        configurable = config.get("configurable", {}) if config else {}
        llm = configurable.get("llm")
        all_rules = configurable.get("human_review_rules", {})
        # Support per-tool rules (dict) or flat list (backward compatible)
        rules = (
            all_rules.get(tool_name, []) if isinstance(all_rules, dict) else all_rules
        )

        # Optional: Perform LLM review first
        llm_question: Optional[str] = None
        if llm and rules:
            decision = await perform_llm_review(tool_call, rules, llm)
            if not decision.requires_review:
                logger.info(f"Tool call {tool_call_id} auto-approved by LLM rules")
                return Command(goto="tool")
            llm_question = decision.question

        # Trigger the interrupt to collect human input
        interrupt_payload = {
            "question": llm_question
            or f"Please review the proposed tool call for {tool_name}: {tool_call['args']}",
            "tool_call": tool_call,
        }
        human_input_raw = interrupt(interrupt_payload)
        human_input = HumanInput(**human_input_raw)

        logger.info(
            f"Human action for {tool_name} (ID: {tool_call_id}): {human_input.action}"
        )

        # Create review record for audit trail
        review_record = HumanReviewRecord(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            action_taken=human_input.action,
            feedback=human_input.feedback,
            edited_params=human_input.edited_params,
            user_id=human_input.user_id,
            question=llm_question,
        )

        # Common update — add reducer auto-appends to review_history
        update = {"review_history": [review_record]}

        # Route based on action
        if human_input.action == "approve":
            return Command(goto="tool", update=update)

        elif human_input.action == "edit":
            review_record.original_params = tool_call["args"]
            edited_tool_call = {**tool_call, "args": human_input.edited_params}
            update["messages"] = [
                AIMessage(
                    content=last_message.content,
                    tool_calls=[edited_tool_call],
                    id=last_message.id,
                )
            ]
            return Command(goto="tool", update=update)

        elif human_input.action == "reject":
            feedback = human_input.feedback or "No feedback provided"
            content = Template(HUMAN_REJECT_PROMPT).render(feedback=feedback)
            update["messages"] = [
                ToolMessage(
                    content=content,
                    tool_call_id=tool_call_id,
                    name=tool_name,
                )
            ]
            return Command(goto="agent", update=update)
    except GraphBubbleUp:
        # interrupt() raises GraphInterrupt; must propagate to the graph runtime
        raise
    except Exception as e:
        logger.error(f"Error in human review node: {str(e)}", exc_info=True)

        error_message = ToolMessage(
            content=f"Tool call failed due to error during review: {str(e)}",
            tool_call_id=tool_call_id if "tool_call_id" in locals() else "unknown",
            name=tool_name if "tool_name" in locals() else "unknown",
        )

        return Command(
            goto="agent",
            update={"messages": [error_message]},
        )
