"""LiveAgentGraph — Lightweight agent→tool loop for live chat execution.

A standalone LangGraph workflow for executing agents in the assistant chat
with real-time token streaming. Independent from the task_agent module.
"""

from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional

from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import (
    AIMessageChunk,
    BaseMessage,
    SystemMessage,
    ToolMessage,
    convert_to_openai_messages,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from logger import configure_logging

from .human import human_review_node, requires_human_review
from .schemas import GenerateFinalAnswer, LiveAgentState

logger = configure_logging(__name__)

GRAPH_RECURSION_LIMIT = 50


class LiveAgentGraph:
    """Lightweight LangGraph agent→tool loop for live chat execution.

    Nodes: agent (LLM call) → tool (execution) → agent (loop)
    End condition: Agent responds without tool calls → END
    """

    def __init__(
        self,
        llm: BaseLanguageModel,
        tools: List[BaseTool],
        system_prompt: str,
        checkpointer: Optional[AsyncPostgresSaver] = None,
        **kwargs,
    ):
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.tools_by_name = {tool.name: tool for tool in tools}
        self.checkpointer = checkpointer
        self.kwargs = kwargs
        self._graph: Optional[CompiledStateGraph] = None

    # ──────────────────────────────────────────────────────────────────────
    # Nodes
    # ──────────────────────────────────────────────────────────────────────

    async def agent_node(self, state: Any, config: RunnableConfig) -> dict:
        """Invoke the LLM with bound tools and track token usage."""
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")

        # Bind tools + GenerateFinalAnswer to LLM
        llm_with_tools = self.llm.bind_tools(
            [*self.tools, GenerateFinalAnswer], parallel_tool_calls=False
        )

        # Prepare messages with system prompt
        messages = self._prepare_messages(state.messages)

        # Enforce tool usage — if last AI message had no tool calls, inject reminder
        if len(messages) > 1:
            last_msg = messages[-1]
            if hasattr(last_msg, "tool_calls") and not last_msg.tool_calls:
                from langchain_core.messages import HumanMessage

                messages.append(
                    HumanMessage(
                        content="Please proceed with the appropriate action using the available tools or call GenerateFinalAnswer to provide your response."
                    )
                )

        logger.info(
            f"[thread_id={thread_id}] llm_request: node=agent, messages={len(messages)}"
        )

        response = await llm_with_tools.ainvoke(messages, config)

        # Build token record
        tool_call_names = [tc["name"] for tc in response.tool_calls] if response.tool_calls else []
        usage_metadata = response.usage_metadata or {}
        token_record = {
            "node": "agent",
            "tool_call": tool_call_names[0] if len(tool_call_names) == 1 else tool_call_names or None,
            "tool_call_id": response.tool_calls[0].get("id") if response.tool_calls else None,
            "input_tokens": usage_metadata.get("input_tokens", 0),
            "output_tokens": usage_metadata.get("output_tokens", 0),
            "total_tokens": usage_metadata.get("total_tokens", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {"messages": [response], "token_usage": [token_record]}

    async def tool_node(self, state: Any, config: RunnableConfig) -> Dict[str, Any]:
        """Execute all tool calls from the last message with token tracking."""
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
        from agents.shared_utils.token_handler import TokenHandler

        last_message = state.messages[-1]
        if not last_message.tool_calls:
            logger.warning(f"[thread_id={thread_id}] No tool call in last message")
            return {"messages": []}

        all_messages = []
        all_token_usage = []

        for tool_call in last_message.tool_calls:
            tool = self.tools_by_name.get(tool_call["name"])

            if not tool:
                logger.error(f"[thread_id={thread_id}] Tool not found: {tool_call['name']}")
                all_messages.append(
                    ToolMessage(
                        content=f"Error: Tool '{tool_call['name']}' not found",
                        name=tool_call["name"],
                        tool_call_id=tool_call["id"],
                    )
                )
                continue

            args_preview = str(tool_call["args"])[:100]
            logger.info(
                f"[thread_id={thread_id}] tool_execution_started: "
                f"tool={tool_call['name']}, tool_call_id={tool_call['id']}, "
                f"tool_args={args_preview}"
            )

            try:
                token_handler = TokenHandler(
                    tool_name=tool_call["name"], tool_call_id=tool_call["id"]
                )

                # Merge callbacks
                callbacks = [token_handler]
                if config and "callbacks" in config:
                    existing = config.get("callbacks")
                    if isinstance(existing, list):
                        callbacks = existing + callbacks
                    elif hasattr(existing, "handlers"):
                        callbacks = list(existing.handlers) + callbacks

                tool_config = {**(config or {}), "callbacks": callbacks}
                tool_result = await tool.ainvoke(tool_call["args"], config=tool_config)

                if token_handler.tokens:
                    all_token_usage.extend(token_handler.tokens)

                output_preview = str(tool_result)[:100]
                logger.info(
                    f"[thread_id={thread_id}] tool_execution_completed: "
                    f"tool={tool_call['name']}, status=SUCCESS, "
                    f'tool_output="{output_preview}..."'
                )

                all_messages.append(
                    ToolMessage(
                        content=str(tool_result),
                        name=tool_call["name"],
                        tool_call_id=tool_call["id"],
                    )
                )

            except Exception as e:
                logger.error(
                    f"[thread_id={thread_id}] tool_execution_completed: "
                    f"tool={tool_call['name']}, status=FAILED, "
                    f'error="{str(e)}"'
                )
                all_messages.append(
                    ToolMessage(
                        content=f"Error: {str(e)}",
                        name=tool_call["name"],
                        tool_call_id=tool_call["id"],
                    )
                )

        return_data = {"messages": all_messages}
        if all_token_usage:
            return_data["token_usage"] = all_token_usage
        return return_data

    async def answer_node(self, state: Any, config: RunnableConfig) -> dict:
        """Extract answer from GenerateFinalAnswer and return required ToolMessage."""
        last_message = state.messages[-1]
        tool_call = next(
            (
                tc
                for tc in last_message.tool_calls
                if tc["name"] == "GenerateFinalAnswer"
            ),
            None,
        )
        if not tool_call:
            return {"messages": []}

        return {
            "messages": [
                ToolMessage(
                    content="Answer delivered successfully.",
                    tool_call_id=tool_call["id"],
                    name="GenerateFinalAnswer",
                )
            ],
        }

    # ──────────────────────────────────────────────────────────────────────
    # Router
    # ──────────────────────────────────────────────────────────────────────

    def node_router(
        self, state: Any
    ) -> Literal["tool", "human_review", "answer", "end"]:
        """Route based on the agent's tool calls."""
        last_message = state.messages[-1]
        if not last_message.tool_calls:
            return "end"

        # Check all tool calls
        has_final_answer = False
        has_review_required = False
        for tc in last_message.tool_calls:
            if tc["name"] == "GenerateFinalAnswer":
                has_final_answer = True
            elif self.tools_by_name.get(tc["name"]) and requires_human_review(self.tools_by_name[tc["name"]]):
                has_review_required = True

        if has_final_answer:
            return "answer"
        if has_review_required:
            return "human_review"
        return "tool"

    # ──────────────────────────────────────────────────────────────────────
    # Graph Creation
    # ──────────────────────────────────────────────────────────────────────

    async def create_graph(self) -> CompiledStateGraph:
        """Create and compile the live agent graph."""
        if self._graph is not None:
            return self._graph

        try:
            graph_builder = StateGraph(LiveAgentState)

            # Nodes
            graph_builder.add_node("agent", self.agent_node)
            graph_builder.add_node("tool", self.tool_node)
            graph_builder.add_node("answer", self.answer_node)

            # Add human_review node only if any tool requires review
            has_review_tools = any(requires_human_review(t) for t in self.tools)
            if has_review_tools:
                graph_builder.add_node("human_review", human_review_node)

            # Entry point
            graph_builder.set_entry_point("agent")

            # Edges: tool → agent (loop back), answer → END
            graph_builder.add_edge("tool", "agent")
            graph_builder.add_edge("answer", END)

            # Conditional: agent → tool | human_review | answer | END
            edge_map = {"tool": "tool", "answer": "answer", "end": END}
            if has_review_tools:
                edge_map["human_review"] = "human_review"

            graph_builder.add_conditional_edges(
                "agent",
                self.node_router,
                edge_map,
            )

            graph_name = f"Assistant - {self.kwargs.get('agent_name', 'Live Agent')}"
            self._graph = graph_builder.compile(
                checkpointer=self.checkpointer,
                name=graph_name,
            )
            logger.info(
                f"live_agent_graph_compiled: "
                f"tools={len(self.tools)}, "
                f"has_review_tools={has_review_tools}, "
                f"has_checkpointer={self.checkpointer is not None}"
            )
            return self._graph

        except Exception as e:
            logger.error(f"Graph creation failed: {e}", exc_info=True)
            raise

    # ──────────────────────────────────────────────────────────────────────
    # Streaming
    # ──────────────────────────────────────────────────────────────────────

    async def stream_events(
        self,
        thread_id: str,
        messages: List[BaseMessage],
        agent_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream execution with token-level granularity.

        Yields events:
        - {"type": "thinking", "content": "..."}              — agent reasoning
        - {"type": "tool_call", "tool": "...", "args": {...}}  — tool invocation
        - {"type": "tool_result", "tool": "...", "output": "..."} — tool completion
        - {"type": "answer", "content": "..."}                 — final answer tokens
        - {"type": "review_required", "tool_call": {...}, ...} — HITL pause
        - {"type": "final_state", "answer": "...", ...}        — completion
        - {"type": "error", "error": "..."}
        """
        if self._graph is None:
            self._graph = await self.create_graph()

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": GRAPH_RECURSION_LIMIT,
        }

        initial_state = {"messages": messages}
        if agent_id:
            initial_state["agent_id"] = agent_id

        all_token_usage = []
        answer_buffer: list[str] = []

        try:
            async for event in self._process_stream_chunks(
                self._graph.astream(
                    initial_state, config, stream_mode=["messages", "updates"]
                ),
                all_token_usage,
                answer_buffer,
            ):
                yield event

            # Build completion event (None if paused — interrupt already yielded)
            completion = await self._build_completion_event(
                thread_id, config, all_token_usage, answer_buffer
            )
            if completion:
                yield completion

        except Exception as e:
            logger.error(
                f"[thread_id={thread_id}] stream_events error: {e}", exc_info=True
            )
            yield {"type": "error", "error": str(e)}

    async def resume_stream(
        self,
        thread_id: str,
        human_input: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Resume paused execution with human input, streaming tokens.

        Uses Command(resume=...) with the same stream_mode as stream_events.
        Supports chained reviews (resume may itself pause again).
        """
        if self._graph is None:
            self._graph = await self.create_graph()

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": GRAPH_RECURSION_LIMIT,
        }

        all_token_usage = []
        answer_buffer: list[str] = []

        try:
            async for event in self._process_stream_chunks(
                self._graph.astream(
                    Command(resume=human_input),
                    config,
                    stream_mode=["messages", "updates"],
                ),
                all_token_usage,
                answer_buffer,
            ):
                yield event

            # Build completion event (None if paused again — chained reviews)
            completion = await self._build_completion_event(
                thread_id, config, all_token_usage, answer_buffer
            )
            if completion:
                yield completion

        except Exception as e:
            logger.error(
                f"[thread_id={thread_id}] resume_stream error: {e}", exc_info=True
            )
            yield {"type": "error", "error": str(e)}

    # ──────────────────────────────────────────────────────────────────────
    # Shared Stream Processing
    # ──────────────────────────────────────────────────────────────────────

    async def _process_stream_chunks(
        self,
        stream,
        all_token_usage: List[Dict[str, Any]],
        answer_buffer: List[str],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Process stream chunks from astream(), yielding SSE events.

        Shared between stream_events() and resume_stream().
        Distinguishes thinking tokens (agent reasoning) from answer tokens
        (GenerateFinalAnswer tool call) for frontend display.
        """
        # Track accumulated AI message to detect GenerateFinalAnswer during streaming
        gathered = None
        last_answer_length = 0
        is_streaming_answer = False
        pending_tool_name = None  # Track tool name for tool_result

        async for stream_type, chunk in stream:
            if stream_type == "messages":
                msg_chunk, metadata = chunk
                node = metadata.get("langgraph_node", "")

                # Only process streaming chunks, skip complete messages
                if node == "agent" and isinstance(msg_chunk, AIMessageChunk):
                    # Accumulate chunks to track tool calls
                    if gathered is None:
                        gathered = msg_chunk
                    else:
                        gathered = gathered + msg_chunk

                    # Check if this is a GenerateFinalAnswer tool call
                    if gathered.tool_calls:
                        for tc in gathered.tool_calls:
                            if tc[
                                "name"
                            ] == "GenerateFinalAnswer" and "answer" in tc.get(
                                "args", {}
                            ):
                                if not is_streaming_answer:
                                    is_streaming_answer = True
                                # Stream incremental answer content
                                current = tc["args"]["answer"]
                                if len(current) > last_answer_length:
                                    new_content = current[last_answer_length:]
                                    last_answer_length = len(current)
                                    answer_buffer.append(new_content)
                                    yield {"type": "answer", "content": new_content}

                    # Regular text content → thinking tokens
                    elif msg_chunk.content and not is_streaming_answer:
                        yield {"type": "thinking", "content": msg_chunk.content}

            elif stream_type == "updates":
                # Reset accumulated message for next agent iteration
                gathered = None
                last_answer_length = 0
                is_streaming_answer = False

                # Check for interrupt in update chunks
                if "__interrupt__" in chunk:
                    for itr in chunk["__interrupt__"]:
                        interrupt_value = itr.value if hasattr(itr, "value") else itr
                        if isinstance(interrupt_value, dict):
                            tc = interrupt_value.get("tool_call", {})
                            yield {
                                "type": "review_required",
                                "tool_call": {
                                    "name": tc.get("name"),
                                    "args": tc.get("args"),
                                    "tool_call_id": tc.get("id"),
                                },
                                "message": interrupt_value.get("message"),
                            }
                    continue

                for node_name, update in chunk.items():
                    if node_name == "agent":
                        if "token_usage" in update:
                            all_token_usage.extend(update["token_usage"])

                        # Emit tool_call for each action tool (not GenerateFinalAnswer)
                        agent_messages = update.get("messages", [])
                        if agent_messages:
                            last_msg = agent_messages[-1]
                            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                                for tc in last_msg.tool_calls:
                                    if tc["name"] != "GenerateFinalAnswer":
                                        yield {
                                            "type": "tool_call",
                                            "tool": tc["name"],
                                            "tool_call_id": tc["id"],
                                            "args": tc["args"],
                                        }

                    elif node_name == "tool":
                        if "token_usage" in update:
                            all_token_usage.extend(update["token_usage"])

                        for tool_msg in update.get("messages", []):
                            yield {
                                "type": "tool_result",
                                "tool": getattr(tool_msg, "name", ""),
                                "tool_call_id": getattr(tool_msg, "tool_call_id", ""),
                                "output": str(tool_msg.content),
                            }

    async def _build_completion_event(
        self,
        thread_id: str,
        config: Dict[str, Any],
        all_token_usage: List[Dict[str, Any]],
        answer_buffer: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Build the final completion event.

        Interrupt detection is handled in _process_stream_chunks via __interrupt__
        in update chunks. This method only builds the final_state event on completion.
        Returns None if graph is paused (interrupt already yielded during streaming).
        """
        state_snapshot = await self._graph.aget_state(config)

        # Graph is paused — interrupt event already yielded during streaming
        if state_snapshot.next:
            return None

        answer = "".join(answer_buffer)

        # Fallback: extract answer from GenerateFinalAnswer if not streamed
        if not answer:
            messages = state_snapshot.values.get("messages", [])
            for msg in reversed(messages):
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        if tc["name"] == "GenerateFinalAnswer":
                            answer = tc["args"].get("answer", "")
                            break
                    if answer:
                        break

        messages = state_snapshot.values.get("messages", [])
        return {
            "type": "final_state",
            "answer": answer,
            "token_usage": all_token_usage,
            "messages": convert_to_openai_messages(messages) if messages else [],
        }

    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────

    def _prepare_messages(self, messages: list) -> List[BaseMessage]:
        """Prepend system prompt and optimize message content."""
        processed = []
        if self.system_prompt:
            processed.append(SystemMessage(content=self.system_prompt))

        # Trim long tool message content (except the most recent)
        last_idx = len(messages) - 1
        for i, msg in enumerate(messages):
            if isinstance(msg, ToolMessage) and i != last_idx:
                if isinstance(msg.content, str) and len(msg.content) > 8000:
                    trimmed = ToolMessage(
                        content=msg.content[:8000] + "...",
                        tool_call_id=msg.tool_call_id,
                        name=getattr(msg, "name", None),
                    )
                    processed.append(trimmed)
                    continue
            processed.append(msg)

        return processed
