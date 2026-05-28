"""This file contains the LangGraph Agent/workflow and interactions with the LLM."""

import asyncio
from datetime import datetime, timezone
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    List,
    Literal,
    Optional,
)

from langchain_core.language_models import BaseLanguageModel
from langchain_core.tools import BaseTool
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import StateSnapshot, Command
from openai import OpenAIError
from pydantic import BaseModel
from logger import configure_logging

from .schemas import GraphState
from .human import (
    requires_human_review,
    human_review_node,
    HumanInput,
)


# Configure logging for this module
logger = configure_logging(__name__)

MAX_LLM_CALL_RETRIES = 3
GRAPH_RECURSION_LIMIT = 100


class TaskAgentGraph:
    """Manages the LangGraph Agent/workflow and interactions with the LLM.

    This class handles the creation and management of the LangGraph workflow,
    including LLM interactions, tool calls, human-in-the-loop review, and
    structured response processing.
    """

    def __init__(
        self,
        llm: BaseLanguageModel,
        tools: List[BaseTool],
        system_prompt: str,
        checkpointer: Optional[AsyncPostgresSaver] = None,
        human_review: bool = False,
        agent_kwargs: Optional[Dict[str, Any]] = None,
    ):
        """Initialize the LangGraph Agent with necessary components."""
        # Setting up core components
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.tools_by_name = {tool.name: tool for tool in tools}
        self.human_review = human_review
        self.agent_kwargs = agent_kwargs or {}
        self.review_rules = self.agent_kwargs.get("human_review_rules", [])
        self.checkpointer = checkpointer
        self._graph: Optional[CompiledStateGraph] = None

    async def llm_call_node(self, state: GraphState, config: RunnableConfig) -> dict:
        """Process the chat state and generate a response.

        Args:
            state (GraphState): The current state of the conversation.
            config (RunnableConfig): The runnable configuration.

        Returns:
            dict: Updated state with new messages and pending tool calls.
        """
        # Preparing messages and LLM configuration
        llm_with_tools = self.llm.bind_tools(self.tools, parallel_tool_calls=False)
        thread_id = config.get("configurable", {}).get("thread_id", None)
        max_retries = MAX_LLM_CALL_RETRIES

        # Check if last AI message had no tool calls (thought-only response)
        # If so, inject a reminder to proceed to next step
        messages_to_process = list(state.messages)
        if len(messages_to_process) > 0:
            last_message = messages_to_process[-1]
            # Check if it's an AI message with no tool calls
            if hasattr(last_message, "tool_calls") and not last_message.tool_calls:
                # Inject reminder to proceed to next step
                reminder = HumanMessage(
                    content="Your reasoning has been noted. Please proceed to the next step in the execution plan. Do not skip any remaining steps. Only call generate_task_output after all steps are fully completed."
                )
                messages_to_process.append(reminder)

        # Prepend system prompt to messages
        messages = [SystemMessage(content=self.system_prompt)] + messages_to_process if self.system_prompt else messages_to_process

        # Log LLM request
        logger.info(
            f"[thread_id={thread_id}] llm_request: node=agent, messages={len(messages)}"
        )

        # Invoking LLM with retry logic
        for attempt in range(max_retries):
            try:
                response = await llm_with_tools.ainvoke(messages, config)

                # Extract token usage from response
                usage_metadata = response.usage_metadata or {}

                # Create token usage record
                tool_call_name = None
                tool_call_id = None
                if response.tool_calls:
                    if len(response.tool_calls) > 1:
                        logger.warning(
                            "Multiple tool calls detected, using only the first one"
                        )
                        response.tool_calls = [response.tool_calls[0]]
                    tool_call_name = response.tool_calls[0]["name"]
                    tool_call_id = response.tool_calls[0].get("id")

                # Build token record
                token_record = {
                    "node": "agent",
                    "tool_call": tool_call_name,
                    "tool_call_id": tool_call_id,
                    "run_id": response.id if hasattr(response, "id") else None,
                    "input_tokens": usage_metadata.get("input_tokens", 0),
                    "output_tokens": usage_metadata.get("output_tokens", 0),
                    "total_tokens": usage_metadata.get("total_tokens", 0),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                return {"messages": [response], "token_usage": [token_record]}
            except OpenAIError as e:
                logger.error(
                    f"LLM call failed (attempt {attempt + 1}/{max_retries}): {e}",
                    exc_info=True,
                )
                continue

        # Raising error after max retries
        raise Exception(
            f"Failed to get a response from the LLM after {max_retries} attempts"
        )

    def node_router(
        self, state: GraphState
    ) -> Literal["tool_call", "human_review", "output", "agent"]:
        """Determine the next step based on the last message and tool requirements.

        Args:
            state (GraphState): The current state of the conversation.

        Returns:
            Literal["tool_call", "human_review", "output", "agent"]: The next step to take.
        """
        last_message = state.messages[-1]

        # Check if last message has generate_task_output tool call
        if last_message.tool_calls and any(
            tc["name"] == "generate_task_output" for tc in last_message.tool_calls
        ):
            return "output"

        # Check if last message has a tool call
        if last_message.tool_calls:
            tool_call = last_message.tool_calls[0]
            tool_name = tool_call["name"]

            # Check if human review is enabled and tool requires review
            if self.human_review and requires_human_review(
                self.tools_by_name[tool_name]
            ):
                return "human_review"

            # Regular tool call (no review required)
            return "tool_call"

        # If no tool calls detected, loop back to agent with reminder
        # The llm_call_node will inject a reminder message to prompt action
        return "agent"

    async def tool_call_node(
        self, state: GraphState, config: RunnableConfig
    ) -> Dict[str, Any]:
        """Execute the tool call from the last message.

        Args:
            state: The current agent state containing messages and tool calls.
            config: The runnable configuration containing thread_id.

        Returns:
            Dict with updated messages containing tool response.
        """
        # Extract thread_id from config
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")

        # Get the tool call from the last message
        last_message = state.messages[-1]
        if not last_message.tool_calls:
            logger.warning(f"[thread_id={thread_id}] No tool call in last message")
            return {"messages": []}

        tool_call = last_message.tool_calls[0]
        tool = self.tools_by_name[tool_call["name"]]

        # Create args preview for logging
        args_str = str(tool_call["args"])
        args_preview = args_str[:100] if len(args_str) > 100 else args_str

        logger.info(
            f"[thread_id={thread_id}] tool_execution_started: "
            f"tool={tool_call['name']}, tool_call_id={tool_call['id']}, "
            f"tool_args={args_preview}"
        )

        try:
            # Create callback for automatic token tracking
            from agents.shared_utils.token_handler import TokenHandler

            token_handler = TokenHandler(
                tool_name=tool_call["name"], tool_call_id=tool_call["id"]
            )

            # Inject callback into LangChain config
            # LangChain accepts callbacks as a list in RunnableConfig
            callbacks = [token_handler]

            # Merge with existing callbacks if any
            if config and "callbacks" in config:
                existing_callbacks = config.get("callbacks")
                # If existing callbacks is a list, extend it
                if isinstance(existing_callbacks, list):
                    callbacks = existing_callbacks + callbacks
                # If it's a CallbackManager, extract handlers
                elif hasattr(existing_callbacks, "handlers"):
                    callbacks = list(existing_callbacks.handlers) + callbacks

            # Create tool config with merged callbacks
            tool_config = {**(config or {}), "callbacks": callbacks}

            # Execute the tool with callback-enabled config
            tool_result = await tool.ainvoke(tool_call["args"], config=tool_config)

            # Get tokens directly from callback instance
            token_usage = token_handler.tokens

            # Create output preview for logging
            result_str = str(tool_result)
            output_preview = result_str[:100] if len(result_str) > 100 else result_str

            logger.info(
                f"[thread_id={thread_id}] tool_execution_completed: "
                f"tool={tool_call['name']}, tool_call_id={tool_call['id']}, "
                f"status=SUCCESS, tool_internal_llm_calls={len(token_usage)}, "
                f'tool_output="{output_preview}..."'
            )

            return_data = {
                "messages": [
                    ToolMessage(
                        content=str(tool_result),
                        name=tool_call["name"],
                        tool_call_id=tool_call["id"],
                    )
                ]
            }

            # Add tool tokens to graph state if any were collected
            if token_usage:
                return_data["token_usage"] = token_usage

            return return_data

        except Exception as e:
            logger.error(
                f"[thread_id={thread_id}] tool_execution_completed: "
                f"tool={tool_call['name']}, tool_call_id={tool_call['id']}, "
                f'status=FAILED, error="{str(e)}"'
            )

            return {
                "messages": [
                    ToolMessage(
                        content=f"Error: {str(e)}",
                        name=tool_call["name"],
                        tool_call_id=tool_call["id"],
                    )
                ]
            }

    async def structured_output_node(
        self, state: GraphState, config: RunnableConfig
    ) -> dict:
        """Extract structured output from generate_task_output tool call.

        Args:
            state (GraphState): The current state of the conversation.
            config (RunnableConfig): The runnable configuration.

        Returns:
            dict: Updated state with structured_output and tool message.
        """
        thread_id = config.get("configurable", {}).get("thread_id", None)

        try:
            # Get the generate_task_output tool call from last message
            last_message = state.messages[-1]
            tool_call = next(
                (
                    tc
                    for tc in last_message.tool_calls
                    if tc["name"] == "generate_task_output"
                ),
                None,
            )

            if not tool_call:
                logger.error(
                    f"[thread_id={thread_id}] generate_task_output tool call not found"
                )
                return {"structured_output": {}}

            # Tool args are already validated by LangChain's tool args_schema
            structured_output = tool_call["args"]

            logger.info(
                f"[thread_id={thread_id}] structured_output_extracted: "
                f'preview="{str(structured_output)[:100]}..."'
            )

            # Return output with required tool message
            return {
                "structured_output": structured_output,
                "messages": [
                    ToolMessage(
                        content="Task output generated successfully",
                        tool_call_id=tool_call["id"],
                        name="generate_task_output",
                    )
                ],
            }

        except Exception as e:
            logger.error(
                f"[thread_id={thread_id}] Error extracting structured output: {e}",
                exc_info=True,
            )
            return {"structured_output": {}}

    async def create_graph(self) -> Optional[CompiledStateGraph]:
        """Create and configure the LangGraph workflow with clearer structure.

        Returns:
            Optional[CompiledStateGraph]: The compiled LangGraph workflow or None if creation fails
        """
        # Checking for existing compiled graph
        if self._graph is not None:
            logger.debug("Returning existing compiled graph")
            return self._graph

        # Initializing graph builder
        try:
            agent_name = self.agent_kwargs.get("agent_name", "Task Agent")
            graph_builder = StateGraph(GraphState)

            # Core nodes (always present)
            graph_builder.add_node("agent", self.llm_call_node)
            graph_builder.add_node("tool", self.tool_call_node)
            graph_builder.add_node("output", self.structured_output_node)

            # Adding HITL node if human review is enabled
            if self.human_review:
                graph_builder.add_node("human_review", human_review_node)

            # Graph entry point
            graph_builder.set_entry_point("agent")

            # Defining the core agent loop
            graph_builder.add_edge("tool", "agent")

            # Defining conditional transitions from agent
            edge_map = {
                "tool_call": "tool",
                "human_review": "human_review" if self.human_review else None,
                "output": "output",
                "agent": "agent",  # Loop back to agent when no tool calls (with reminder)
            }

            # Filter out None values to remove unused paths
            edge_map = {k: v for k, v in edge_map.items() if v is not None}

            graph_builder.add_conditional_edges("agent", self.node_router, edge_map)
            graph_builder.add_edge("output", END)

            # Compile agent graph
            self._graph = graph_builder.compile(
                checkpointer=self.checkpointer,
                name=agent_name,
            )
            logger.info(
                f'agent_graph_compiled: name="{agent_name}", '
                f"human_review={self.human_review}, "
                f"has_checkpointer={self.checkpointer is not None}"
            )
        except Exception as e:
            logger.error(f"Graph creation failed: {e}", exc_info=True)
            raise e
        return self._graph

    def _build_config(self, thread_id: str) -> Dict[str, Any]:
        """Build a RunnableConfig with thread_id and optional HITL configurable keys."""
        configurable = {"thread_id": thread_id}
        if self.human_review:
            configurable["llm"] = self.llm
            configurable["human_review_rules"] = self.review_rules
        return {
            "configurable": configurable,
            "recursion_limit": GRAPH_RECURSION_LIMIT,
        }

    async def get_output(
        self,
        thread_id: str,
        messages: Optional[list[BaseMessage]] = None,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> GraphState:
        """Get agent output for a given thread ID.

        Args:
            thread_id: Thread ID for task execution history.
            messages: Optional messages to start a new task.
            task_id: Optional task ID to include in the state.
            agent_id: Optional agent ID to include in the state.

        Returns:
            GraphState: The current or final state of the graph execution.
        """
        if self._graph is None:
            self._graph = await self.create_graph()

        config = self._build_config(thread_id)

        if messages is None:
            state: StateSnapshot = await self._graph.aget_state(config)
            if not state or not state.values:
                logger.error(f"No valid state found for thread_id {thread_id}")
                raise ValueError(f"No active task for thread_id {thread_id}")
            if state.next == ():
                logger.info(f"Task for thread_id {thread_id} has completed")
                return state.values

        try:
            initial_state = {"messages": messages} if messages else None
            if initial_state and (task_id or agent_id):
                if task_id:
                    initial_state["task_id"] = task_id
                if agent_id:
                    initial_state["agent_id"] = agent_id

            response: GraphState = await self._graph.ainvoke(initial_state, config)
            return response
        except Exception as e:
            logger.error(
                f"Error getting response for thread_id {thread_id}: {e}", exc_info=True
            )
            raise

    async def stream_output(
        self,
        thread_id: str,
        messages: list[BaseMessage],
        full_state: bool = True,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        clear_output: bool = False,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream the execution output for a task (active execution).

        This method starts a new task execution or continues an existing one with new messages.

        Args:
            thread_id: Thread ID for task execution history.
            messages: Messages to execute the task with (required).
            full_state: If True, streams full GraphState after each step (stream_mode="values").
                       If False, streams only node updates (stream_mode="updates").
            task_id: Optional task ID to include in the state.
            agent_id: Optional agent ID to include in the state.

        Yields:
            Dict[str, Any]: Either full GraphState or node updates, depending on full_state parameter.
        """
        if self._graph is None:
            self._graph = await self.create_graph()

        config = self._build_config(thread_id)

        # Build initial state with messages
        initial_state = {"messages": messages}
        if clear_output:
            initial_state["structured_output"] = None
        if task_id:
            initial_state["task_id"] = task_id
        if agent_id:
            initial_state["agent_id"] = agent_id

        stream_mode = "values" if full_state else "updates"

        try:
            async for chunk in self._graph.astream(
                initial_state,
                config,
                stream_mode=stream_mode,
            ):
                # For full_state mode, filter out None values
                if full_state:
                    yield {
                        k: v.model_dump() if isinstance(v, BaseModel) else v
                        for k, v in chunk.items()
                        if v is not None
                    }
                else:
                    yield {
                        k: v.model_dump() if isinstance(v, BaseModel) else v
                        for k, v in chunk.items()
                    }
        except Exception as e:
            logger.error(f"Stream error for thread_id {thread_id}: {e}", exc_info=True)
            raise

    async def observe_output(
        self,
        thread_id: str,
        poll_interval: float = 1.0,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Observe task execution by polling checkpoint state (read-only).

        Args:
            thread_id: Thread ID for the task to observe.
            poll_interval: Time in seconds between checkpoint polls (default: 1.0).

        Yields:
            Dict containing GraphState fields.
        """
        if self._graph is None:
            self._graph = await self.create_graph()

        config = {"configurable": {"thread_id": thread_id}}
        previous_values = None

        while True:
            try:
                # Get current checkpoint state (read-only)
                state: StateSnapshot = await self._graph.aget_state(config)

                if not state or not state.values:
                    # No state found for this thread
                    yield {
                        "error": f"No task state found for thread_id {thread_id}",
                    }
                    return

                # Check if state has changed since last poll
                current_values = state.values

                # Only yield if state changed or first poll
                if previous_values is None or current_values != previous_values:
                    # Serialize state values (GraphState fields)
                    state_dict = {
                        k: v.model_dump() if isinstance(v, BaseModel) else v
                        for k, v in state.values.items()
                        if v is not None
                    }

                    yield state_dict

                    # Exit if task is completed or paused for human review
                    is_paused = bool(state.next and "human_review" in state.next)
                    if state.next == () or is_paused:
                        return

                    previous_values = current_values

                # Wait before next poll
                await asyncio.sleep(poll_interval)

            except Exception as e:
                logger.error(
                    f"[thread_id={thread_id}] Error observing task: {e}", exc_info=True
                )
                yield {"error": str(e)}
                return

    async def get_state(self, thread_id: str) -> StateSnapshot:
        """Get the current state snapshot for a given thread.

        Args:
            thread_id: Thread ID to get state for.

        Returns:
            StateSnapshot: The current state snapshot.
        """
        if self._graph is None:
            raise ValueError("Graph not compiled. Call create_graph() first.")
        config = {"configurable": {"thread_id": thread_id}}
        return await self._graph.aget_state(config)

    async def resume_graph(
        self, thread_id: str, human_input: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Resume paused graph execution with human input (streaming).

        Args:
            thread_id: Thread ID for the paused execution.
            human_input: Dict with action, feedback, edited_params, and user_id.

        Yields:
            Dict with node updates and final state.
        """
        if self._graph is None:
            raise ValueError("Graph not compiled. Call create_graph() first.")

        # Validate human input against schema
        validated_input = HumanInput(**human_input)

        # Build config for this thread
        config = self._build_config(thread_id)

        # Check current state - verify we're paused at human_review
        state_snapshot: StateSnapshot = await self.get_state(thread_id)

        if not state_snapshot or not state_snapshot.values:
            raise ValueError(f"No state found for thread_id {thread_id}")

        if not state_snapshot.next or "human_review" not in state_snapshot.next:
            raise ValueError(
                f"Thread {thread_id} is not waiting for human input. "
                f"Current next nodes: {state_snapshot.next}"
            )

        logger.info(
            f"[thread_id={thread_id}] resuming_graph_execution: "
            f"action={validated_input.action}"
        )

        try:
            # Stream resume execution
            async for chunk in self._graph.astream(
                Command(resume=validated_input.model_dump()),
                config=config,
                stream_mode="values",
            ):
                yield {
                    k: v.model_dump() if isinstance(v, BaseModel) else v
                    for k, v in chunk.items()
                    if v is not None
                }

            logger.info(f"[thread_id={thread_id}] graph_execution_resumed")

        except Exception as e:
            logger.error(
                f"[thread_id={thread_id}] Error resuming graph: {e}", exc_info=True
            )
            raise
