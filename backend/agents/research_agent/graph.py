"""Research Agent Graph with agent loop pattern."""

from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, Any, List, Optional, Literal
from functools import partial
import asyncio

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, HumanMessage, convert_to_openai_messages
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from .schemas import ResearchState
from .nodes.agent import agent_node
from .nodes.tool import tool_node
from .nodes.answer import answer_node
from .tools.registry import get_research_tools
from .config import MAX_ITERATIONS
from logger import configure_logging

logger = configure_logging(__name__)


class ResearchAgentGraph:
    """Research Agent with agent loop pattern.

    This agent uses tool calling to dynamically decide which searches to perform
    and when to generate the final answer, rather than following a fixed graph flow.
    The agent handles query screening, direct responses, and research in a single pass.
    """

    def __init__(
        self,
        primary_llm: Optional[BaseChatModel] = None,
        fast_llm: Optional[BaseChatModel] = None,
        checkpointer: Optional[AsyncPostgresSaver] = None,
    ):
        """Initialize the Research Agent Graph.

        Args:
            primary_llm: Primary LLM for agent and synthesis (optional)
            fast_llm: Fast LLM (optional, reserved for future use)
            checkpointer: AsyncPostgresSaver for state persistence
        """
        self.checkpointer = checkpointer
        self.primary_llm = primary_llm
        self.fast_llm = fast_llm

        self._graph: Optional[CompiledStateGraph] = None
        self._tools = get_research_tools()  # Create tools once

    # ========================================================================
    # Routers
    # ========================================================================

    def node_router(
        self, state: ResearchState
    ) -> Literal["tool", "answer", "end"]:
        """Route after agent node based on response type.

        Routes:
        - final_answer set (DirectResponse handled inline) → END
        - research_complete (tool or max limit) → answer node
        - tool_calls present → tool node for execution
        - text + research_knowledge (fallback completion) → answer node
        - fallback → END

        Args:
            state: Current research state

        Returns:
            Next node name
        """
        # Direct response already handled by agent_node (DirectResponse or text fallback)
        if state.final_answer:
            logger.info("node_router: final_answer set, routing to END")
            return "end"

        # Research complete via CompleteResearch or max tool calls
        if state.research_complete:
            logger.info("node_router: research complete, routing to answer node")
            return "answer"

        last_message = state.messages[-1]

        # Tool call → execute in tool_node
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tool"

        # No tool call — loop back to agent with nudge
        logger.warning(
            "node_router: no tool call in response, routing back to agent"
        )
        return "agent"

    def tool_router(self, state: ResearchState) -> Literal["agent", "answer"]:
        """Route after tool execution.

        Args:
            state: Current research state

        Returns:
            Next node name
        """
        # Check if research was marked complete by tool execution
        if state.research_complete:
            logger.info("tool_router: research complete, routing to answer node")
            return "answer"

        # Continue agent loop
        return "agent"

    # ========================================================================
    # Graph Creation
    # ========================================================================

    async def create_graph(self) -> CompiledStateGraph:
        """Create and compile the research agent graph.

        Returns:
            Compiled state graph
        """
        if self._graph is not None:
            return self._graph

        try:
            # Initialize graph builder
            graph_builder = StateGraph(ResearchState)

            # Add nodes
            tools_by_name = {tool.name: tool for tool in self._tools}
            graph_builder.add_node("agent", partial(agent_node, tools=self._tools))
            graph_builder.add_node("tool", partial(tool_node, tools_by_name=tools_by_name))
            graph_builder.add_node("answer", answer_node)

            # Set entry point — agent handles all query types
            graph_builder.set_entry_point("agent")

            # Agent routes to tool, answer, or END
            graph_builder.add_conditional_edges(
                "agent",
                self.node_router,
                {
                    "tool": "tool",
                    "answer": "answer",
                    "end": END,
                },
            )

            # Tool routes back to agent or to answer (if research complete)
            graph_builder.add_conditional_edges(
                "tool",
                self.tool_router,
                {
                    "agent": "agent",
                    "answer": "answer",
                },
            )

            # Answer node always ends
            graph_builder.add_edge("answer", END)

            # Compile graph
            self._graph = graph_builder.compile(
                checkpointer=self.checkpointer,
                name="Research Agent",
                debug=False,
            )

            logger.info("Research agent graph compiled successfully")
            return self._graph

        except Exception as e:
            logger.error(f"Failed to create research agent graph: {e}", exc_info=True)
            raise

    # ========================================================================
    # Public API
    # ========================================================================

    def _prepare_execution(
        self, query: str, config: Optional[RunnableConfig]
    ) -> tuple[ResearchState, dict]:
        """Build initial state and normalize config for graph execution."""
        if config is None:
            config = {}

        node_config = config.setdefault("configurable", {})
        user_context = node_config.get("user_context", {})
        thread_id = node_config.get("thread_id")

        state = ResearchState(
            original_query=query,
            messages=[HumanMessage(content=query)],
            metadata={
                "thread_id": thread_id,
                "chat_id": user_context.get("chat_id"),
                "user_id": user_context.get("user_id"),
                "org_id": user_context.get("org_id"),
            },
        )

        # Freeze timestamp for prompt caching
        node_config.setdefault(
            "current_date_time",
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        )
        config["recursion_limit"] = MAX_ITERATIONS
        node_config.setdefault("primary_llm", self.primary_llm)
        node_config.setdefault("fast_llm", self.fast_llm)

        return state, config

    async def get_response(
        self,
        query: str,
        config: Optional[RunnableConfig] = None,
    ) -> ResearchState:
        """Get response from the research agent.

        Args:
            query: User query string
            config: Runnable configuration with knowledge_collections, previous_messages, user_context, etc.

        Returns:
            Final research state
        """
        graph = await self.create_graph()
        state, config = self._prepare_execution(query, config)

        final_state = await graph.ainvoke(state, config)
        return ResearchState(**final_state)

    async def stream_response(
        self,
        query: str,
        config: Optional[RunnableConfig] = None,
    ):
        """Stream research agent execution with token-level granularity.

        Uses messages+updates stream mode (matching live agent pattern).

        Yields events:
        - {"type": "thinking", "content": "..."}              — agent reasoning
        - {"type": "tool_call", "tool": "...", "args": {...}}  — tool invocation
        - {"type": "tool_result", "tool": "...", "output": "..."} — tool completion
        - {"type": "answer", "content": "..."}                 — answer tokens
        - {"type": "final_state", "answer": "...", ...}        — completion
        - {"type": "error", "error": "..."}
        """
        graph = await self.create_graph()
        state, config = self._prepare_execution(query, config)

        all_token_usage: List[Dict[str, Any]] = []
        answer_buffer: list[str] = []

        try:
            async for event in self._process_stream_chunks(
                graph.astream(
                    state, config, stream_mode=["messages", "updates"]
                ),
                all_token_usage,
                answer_buffer,
                graph,
                config,
            ):
                yield event

            # Build and yield final_state
            yield await self._build_completion_event(
                config, all_token_usage, answer_buffer
            )

        except Exception as e:
            logger.error(f"stream_response error: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}

    # ========================================================================
    # Stream Processing (matches live agent pattern)
    # ========================================================================

    async def _process_stream_chunks(
        self,
        stream,
        all_token_usage: List[Dict[str, Any]],
        answer_buffer: List[str],
        graph=None,
        config: Dict[str, Any] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Process stream chunks from astream(), yielding SSE events.

        Handles two answer-producing patterns:
        - Agent node: DirectResponse tool call → streams 'response' field
        - Answer node: ResearchOutput tool call → streams 'answer' field

        Only processes message chunks from 'agent' and 'answer' nodes
        (ignores 'tool' node which has internal synthesis LLM calls).
        """
        gathered = None
        last_answer_length = 0
        last_reasoning_length = 0
        is_streaming_answer = False
        pending_tool_name = None  # Track tool name for tool_result

        async for stream_type, chunk in stream:
            if stream_type == "messages":
                msg_chunk, metadata = chunk
                node = metadata.get("langgraph_node", "")

                # Only process agent and answer node messages
                if node not in ("agent", "answer"):
                    continue

                # Only process streaming chunks, skip complete messages
                if not isinstance(msg_chunk, AIMessageChunk):
                    continue

                # Accumulate chunks to track tool calls
                if gathered is None:
                    gathered = msg_chunk
                else:
                    gathered = gathered + msg_chunk

                # Check for answer tool calls
                if gathered.tool_calls:
                    for tc in gathered.tool_calls:
                        # Agent node: DirectResponse
                        if (
                            node == "agent"
                            and tc["name"] == "DirectResponse"
                            and "response" in tc.get("args", {})
                        ):
                            if not is_streaming_answer:
                                is_streaming_answer = True
                            current = tc["args"]["response"]
                            if len(current) > last_answer_length:
                                new_content = current[last_answer_length:]
                                last_answer_length = len(current)
                                answer_buffer.append(new_content)
                                yield {"type": "answer", "content": new_content}

                        # Agent node: CompleteResearch → stream reasoning as thinking
                        elif (
                            node == "agent"
                            and tc["name"] == "CompleteResearch"
                            and "reasoning" in tc.get("args", {})
                        ):
                            current = tc["args"]["reasoning"]
                            if len(current) > last_reasoning_length:
                                new_content = current[last_reasoning_length:]
                                last_reasoning_length = len(current)
                                yield {"type": "thinking", "content": new_content}

                        # Answer node: ResearchOutput
                        elif (
                            node == "answer"
                            and tc["name"] == "ResearchOutput"
                            and "answer" in tc.get("args", {})
                        ):
                            if not is_streaming_answer:
                                is_streaming_answer = True
                            current = tc["args"]["answer"]
                            if len(current) > last_answer_length:
                                new_content = current[last_answer_length:]
                                last_answer_length = len(current)
                                answer_buffer.append(new_content)
                                yield {"type": "answer", "content": new_content}

                # Regular text content → thinking tokens (agent node only)
                elif node == "agent" and msg_chunk.content and not is_streaming_answer:
                    yield {"type": "thinking", "content": msg_chunk.content}

            elif stream_type == "updates":
                # Reset accumulated message for next node iteration
                gathered = None
                last_answer_length = 0
                last_reasoning_length = 0
                is_streaming_answer = False

                for node_name, update in chunk.items():
                    if node_name == "__end__":
                        continue

                    # Collect token usage from all nodes
                    if isinstance(update, dict) and "token_usage" in update:
                        all_token_usage.extend(update["token_usage"])

                    if node_name == "agent":
                        # Emit state snapshot before answer_node starts
                        if isinstance(update, dict) and update.get("research_complete") and graph and config:
                            state_snapshot = await graph.aget_state(config)
                            if state_snapshot and state_snapshot.values:
                                research_state = ResearchState(**state_snapshot.values)
                                state_event = {"type": "state"}
                                state_event.update(research_state.model_dump(exclude={"messages", "metadata", "token_usage"}))
                                yield state_event

                        # Emit tool_call for real tools (not DirectResponse)
                        agent_messages = update.get("messages", [])
                        if agent_messages:
                            last_msg = agent_messages[-1]
                            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                                tc = last_msg.tool_calls[0]
                                if tc["name"] not in ("DirectResponse", "CompleteResearch"):
                                    pending_tool_name = tc["name"]
                                    yield {
                                        "type": "tool_call",
                                        "tool": tc["name"],
                                        "tool_call_id": tc.get("id", ""),
                                        "args": tc["args"],
                                    }

                    elif node_name == "tool":
                        # Emit tool_result from ToolMessage
                        tool_messages = update.get("messages", [])
                        if tool_messages:
                            tool_msg = tool_messages[-1]
                            tool_name = getattr(tool_msg, "name", None) or pending_tool_name or ""
                            yield {
                                "type": "tool_result",
                                "tool": tool_name,
                                "tool_call_id": getattr(
                                    tool_msg, "tool_call_id", ""
                                ),
                                "output": str(tool_msg.content),
                            }
                            pending_tool_name = None

    async def _build_completion_event(
        self,
        config: Dict[str, Any],
        all_token_usage: List[Dict[str, Any]],
        answer_buffer: List[str],
    ) -> Dict[str, Any]:
        """Build the final_state event from graph state snapshot."""
        graph = await self.create_graph()
        state_snapshot = await graph.aget_state(config)
        answer = "".join(answer_buffer)

        if not state_snapshot or not state_snapshot.values:
            return {
                "type": "final_state",
                "answer": answer,
                "token_usage": all_token_usage,
                "messages": [],
            }

        final_state = ResearchState(**state_snapshot.values)
        state_dict = {"type": "final_state"}
        state_dict.update(final_state.model_dump())

        # Use final_answer from state if not streamed
        if not answer:
            answer = final_state.final_answer or ""

        # Convert messages to OpenAI format
        if final_state.messages:
            state_dict["messages"] = convert_to_openai_messages(
                final_state.messages
            )

        state_dict["answer"] = answer
        state_dict["token_usage"] = all_token_usage

        return state_dict

    async def observe_response(self, thread_id: str) -> Optional[ResearchState]:
        """Get current state snapshot for a research query (read-only).

        This method retrieves the current state of a research query execution
        from the checkpointer without triggering any new execution. Useful for observing the progress of ongoing queries.

        Args:
            thread_id: Thread ID for the research query to observe.

        Returns:
            ResearchState if found, None otherwise.
        """
        from langgraph.types import StateSnapshot

        graph = await self.create_graph()

        config = {"configurable": {"thread_id": thread_id}}

        try:
            # Get state snapshot (read-only)
            state: StateSnapshot = await graph.aget_state(config)

            if not state or not state.values:
                logger.warning(f"No state found for thread_id {thread_id}")
                return None

            # Return ResearchState directly (consistent with get_response)
            return ResearchState(**state.values)

        except Exception as e:
            logger.error(
                f"Error observing state for thread_id {thread_id}: {e}", exc_info=True
            )
            return None

    async def observe_output(
        self,
        thread_id: str,
        poll_interval: float = 0.5,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Observe research query execution by polling checkpoint state (read-only).

        Similar to TaskAgentGraph.observe_output - polls the checkpointer for state
        updates and yields them until execution completes.

        Args:
            thread_id: Thread ID for the research query to observe.
            poll_interval: Time in seconds between checkpoint polls (default: 0.5).

        Yields:
            Dict containing ResearchState fields with "type": "state" or "final_state".
        """
        from langgraph.types import StateSnapshot

        graph = await self.create_graph()

        config = {"configurable": {"thread_id": thread_id}}
        previous_values = None

        while True:
            try:
                # Get current checkpoint state (read-only)
                state: StateSnapshot = await graph.aget_state(config)

                if not state or not state.values:
                    # No state found for this thread
                    yield {
                        "type": "error",
                        "error": f"No state found for thread_id {thread_id}",
                    }
                    return

                current_values = state.values

                # Only yield if state changed or first poll
                if previous_values is None or current_values != previous_values:
                    # Check if graph execution is complete (no more nodes to run)
                    is_complete = state.next == ()

                    # Properly serialize using ResearchState.model_dump()
                    # This ensures Pydantic objects (SourceDocument, ResearchKnowledge)
                    # are converted to dicts, not repr() strings
                    state_model = ResearchState(**current_values)
                    state_dict = state_model.model_dump()

                    # Set type based on completion status
                    state_dict["type"] = "final_state" if is_complete else "state"

                    # Convert messages to OpenAI format (overwrite the model_dump version)
                    if state_model.messages:
                        state_dict["messages"] = convert_to_openai_messages(
                            state_model.messages
                        )

                    yield state_dict

                    # Exit if complete
                    if is_complete:
                        logger.info(
                            f"Research query {thread_id} completed, stopping observation"
                        )
                        return

                    previous_values = current_values

                # Wait before next poll
                await asyncio.sleep(poll_interval)

            except Exception as e:
                logger.error(
                    f"[thread_id={thread_id}] Error observing research query: {e}",
                    exc_info=True,
                )
                yield {"type": "error", "error": str(e)}
                return
