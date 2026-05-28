"""
LangChain callback handler for automatic token tracking.

This callback automatically captures token usage from ANY LLM call
within tool executions, without requiring manual instrumentation.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from logger import configure_logging

logger = configure_logging(__name__)


class TokenHandler(AsyncCallbackHandler):
    """
    Async callback handler that automatically tracks token usage from LLM calls.

    This callback is injected into the LangChain execution context and intercepts
    all LLM responses to extract and store token usage information.
    """

    def __init__(self, tool_name: Optional[str] = None,tool_call_id: Optional[str] = None):
        """
        Initialize the callback.

        Args:
            tool_name: Name of the tool making LLM calls (for tracking purposes)
        """
        super().__init__()
        self.tool_name = tool_name or "unknown_tool"
        self.tool_call_id = tool_call_id or "unknown_tool_call"
        self.tokens = []  # Store token records directly in instance

    async def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """
        IMPORTANT: Do not remove this method even though it appears to be a no-op.

        This method is required by LangChain's callback system when using chat models
        (e.g., ChatOpenAI, ChatAnthropic).

        Without this method, you will encounter the error:
            NotImplementedError('TokenHandler does not implement `on_chat_model_start`')
        """
        pass

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """
        Called when LLM ends running.

        Extracts token usage from the LLM response and stores it.
        """
        try:
            # Extract token usage from LLM result
            llm_output = response.llm_output or {}
            token_usage = llm_output.get("token_usage", {})

            # Extract request ID from generation info
            request_id = None
            if response.generations and len(response.generations) > 0:
                if len(response.generations[0]) > 0:
                    generation = response.generations[0][0]
                    if (
                        hasattr(generation, "generation_info")
                        and generation.generation_info
                    ):
                        request_id = generation.generation_info.get("id")

            # Only track if we have valid token data
            if token_usage and token_usage.get("total_tokens", 0) > 0:
                token_data = {
                    "node": "tool",
                    "tool_call": self.tool_name,
                    "tool_call_id": self.tool_call_id,
                    "input_tokens": token_usage.get("prompt_tokens", 0),
                    "output_tokens": token_usage.get("completion_tokens", 0),
                    "total_tokens": token_usage.get("total_tokens", 0),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                # Store directly in instance
                self.tokens.append(token_data)

                logger.info(
                    f"[{self.tool_name}] Tokens tracked: "
                    f"input={token_data['input_tokens']}, "
                    f"output={token_data['output_tokens']}, "
                    f"total={token_data['total_tokens']}"
                )

        except Exception as e:
            # Don't fail the LLM call if token tracking fails
            logger.error(
                f"[{self.tool_name}] Failed to track tokens in callback: {e}",
                exc_info=True,
            )
