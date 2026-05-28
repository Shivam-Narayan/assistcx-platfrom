# Standard library imports
import ast
import json
import math
import time
from datetime import datetime
from typing import Any, Dict, List, Literal, NamedTuple, Optional, Tuple
from uuid import UUID

# Third-party imports
from asgiref.sync import sync_to_async
from jinja2 import Template
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

# Local application imports
from logger import configure_logging
from agents.data_extractor.model_generator import DataModelGenerator
from schemas.agent_output_schema import AgentOutputDetail
from schemas.agent_schema import AgentDetail
from schemas.agent_task_schema import AgentTaskDetail
from schemas.email_schema import EmailDetail
from utils.notification import Notification

# Local module imports
from .schemas import GraphState
from .prompts import DEFAULT_OUTPUT_SCHEMA, TASK_INPUT_PROMPT

logger = configure_logging(__name__)

AGGREGATE_TOOL_TOKENS = True


class GraphSetupResult(NamedTuple):
    """Return type for _setup_agent_graph."""

    task_data: AgentTaskDetail
    agent_data: AgentDetail
    email_data: Optional[EmailDetail]
    task_context: Dict[str, Any]


class TaskExecutorHelper:
    """
    Mixin class containing pre/post processing methods for TaskExecutor.
    Handles context preparation, output parsing, and execution lifecycle.

    Note: This class assumes the following attributes are provided by TaskExecutor:
    - organization_schema, agent_llm, db, _graph
    - agent_task_repo, email_repo, agent_repo, agent_tool_repo, agent_output_repo
    - credits_manager
    - _configure_tools(), _initialize_graph()
    """

    # ─────────────────────────────────────────────────────────────────────────────
    # DATABASE HELPER METHODS
    # ─────────────────────────────────────────────────────────────────────────────

    async def _update_task_status(self, task_id: str, status: str):
        """
        Update task progress in DB
        """
        try:
            progress = {
                "status": status,
                "timestamp": str(datetime.now()),
            }

            await sync_to_async(self.agent_task_repo.append_task_progress)(
                task_id, progress
            )

        except Exception as e:
            logger.error(f"Error in updating task progress: {e}")
            return None

    async def _update_agent_task(self, task_id: str, agent_task_data: dict):
        """
        Update agent task data in DB
        """
        try:
            await sync_to_async(self.agent_task_repo.update_task)(
                task_id, agent_task_data
            )

        except Exception as e:
            logger.error(f"Error in updating task progress: {e}")
            return None

    async def _get_task(self, task_id: UUID) -> Optional[AgentTaskDetail]:
        """Asynchronously fetches task data from the DB."""
        try:
            # Wrap the synchronous repository call
            task_data = await sync_to_async(self.agent_task_repo.get_task_by_id)(
                task_id
            )
            if not task_data:
                logger.warning(f"No task found with uuid: {task_id}")
                return None
            return AgentTaskDetail.model_validate(task_data)
        except Exception as e:
            logger.error(f"Error fetching task {task_id}: {e}", exc_info=True)
            return None

    async def _get_email(self, email_uuid: UUID) -> Optional[EmailDetail]:
        """Asynchronously fetches email data from the DB."""
        try:
            # Wrap the synchronous repository call
            email_data = await sync_to_async(self.email_repo.get_email_by_id)(
                email_uuid
            )
            if not email_data:
                logger.warning(f"No email found with uuid: {email_uuid}")
                return None
            return EmailDetail.model_validate(email_data)
        except Exception as e:
            logger.error(f"Error fetching email {email_uuid}: {e}", exc_info=True)
            return None

    async def _get_agent(self, agent_id: UUID) -> Optional[AgentDetail]:
        """Asynchronously fetches agent data from the DB."""
        try:
            # Wrap the synchronous repository call
            agent_data = await sync_to_async(self.agent_repo.get_agent)(agent_id)
            if not agent_data:
                logger.warning(f"No agent found with id: {agent_id}")
                return None
            return AgentDetail.model_validate(agent_data)
        except Exception as e:
            logger.error(f"Error fetching agent {agent_id}: {e}", exc_info=True)
            return None

    async def _notify_paused_reviewers(
        self,
        task_id: UUID,
        agent_data: AgentDetail,
        task_data: AgentTaskDetail,
        pending_review: Optional[Dict[str, Any]],
    ) -> None:
        """
        Sends a paused-task notification to the agent's configured reviewers.
        Notification failure is caught and logged — it must never fail the task.

        Args:
            task_id: UUID of the paused task.
            agent_data: AgentDetail containing the agent_config with human_review_users.
            task_data: AgentTaskDetail for task title and attachments.
            pending_review: Interrupt payload dict (tool_name, question, …) or None.
        """
        logger.info(
            f"[task_id={task_id}] notify_paused_reviewers: "
            f"agent_id={agent_data.id}, agent_config={agent_data.agent_config}"
        )
        human_review_users = (
            agent_data.agent_config.get("human_review_users") or []
            if agent_data.agent_config
            else []
        )
        if not human_review_users:
            logger.info(
                f"[task_id={task_id}] No reviewers configured — skipping paused notification"
            )
            return
        try:
            await sync_to_async(Notification(self.db).notify_task_paused)(
                task_id=task_id,
                agent_data=agent_data,
                task_data=task_data,
                pending_review=pending_review,
                reviewer_user_ids=human_review_users,
            )
        except Exception as e:
            logger.error(
                f"[task_id={task_id}] Failed to send paused notification: {e}"
            )

    # ─────────────────────────────────────────────────────────────────────────────
    # CONTEXT PREPARATION METHODS
    # ─────────────────────────────────────────────────────────────────────────────

    async def _prepare_context(
        self,
        task_data: AgentTaskDetail,
        email_data: Optional[EmailDetail],
        agent_data: AgentDetail,
        user_instructions: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Prepares the task context and the tool runtime context."""
        # Prepare Task Context (for Agent Task Input)
        task_context = {
            "current_utc_date_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if email_data:
            task_context.update(
                {
                    "task_id": str(task_data.id),
                    "email_data_id": str(email_data.id),
                    "message_id": email_data.message_id,
                    "conversation_id": email_data.conversation_id,
                    "mailbox_email": email_data.mailbox_email,
                    "sender_email": email_data.email_id,
                    "email_received_at": email_data.received_at.isoformat() if email_data.received_at else None,
                    "email_created_at": email_data.created_at.isoformat() if email_data.created_at else None,
                }
            )

            # Check if task_data.data is already a dict, if not, try to parse it
            if task_data.attachments:
                if isinstance(task_data.attachments, list) and all(
                    isinstance(item, dict) for item in task_data.attachments
                ):
                    task_context["attachments"] = task_data.attachments
                else:
                    try:
                        task_data_dict = [
                            json.loads(attachment)
                            for attachment in task_data.attachments
                        ]
                        task_context["attachments"] = task_data_dict
                    except json.JSONDecodeError:
                        logger.warning(
                            "Failed to parse task_data.data as JSON. Skipping."
                        )

        # Prepare Tool Runtime Context (for Agent Tools)
        tool_runtime_context = {
            "organization_schema": self.organization_schema,
            "task_id": str(task_data.id),
            "email_uuid": str(email_data.id) if email_data else "",
            "agent_id": str(agent_data.id),
            "email_subject": email_data.subject if email_data else "",
            "email_file_url": (
                email_data.additional_data.get("remote_url", "")
                if email_data and email_data.additional_data
                else ""
            ),
            "user_instructions": user_instructions if user_instructions else None,
            # Add agent-specific config needed by tools
            "plan": agent_data.plan if agent_data.plan else None,
            "data_store": (
                agent_data.data_store.model_dump() if agent_data.data_store else None
            ),
            "vision_data_extraction": (
                agent_data.agent_config.get("vision_data_extraction", False)
                if agent_data.agent_config
                else False
            ),
            "task_context": task_context,
            "llm": self.agent_llm,
            "db": self.db,
        }

        return task_context, tool_runtime_context

    async def _create_output_tool(
        self, agent_data: AgentDetail
    ) -> Optional[StructuredTool]:
        """
        Creates a StructuredTool for generating task output based on agent config. Merges agent-defined response schema with defaults.

        Args:
            agent_data: The agent configuration data

        Returns:
            StructuredTool for generating task output, or None if creation fails
        """
        # Get agent schema, defaulting to empty list
        default_schema = list(DEFAULT_OUTPUT_SCHEMA)
        agent_schema = agent_data.response_schema or []

        # Validate agent schema is a list of dicts
        is_valid_schema = isinstance(agent_schema, list) and all(
            isinstance(item, dict) and "name" in item for item in agent_schema
        )

        if not is_valid_schema and agent_schema:
            logger.warning(
                f"Agent {agent_data.id} has invalid output schema. Using defaults only. "
                f"Found: {type(agent_schema)}"
            )
            agent_schema = []

        # Merge schemas with dictionary comprehension, prioritizing agent schema
        schema_by_name = {item["name"]: item for item in agent_schema if "name" in item}
        # Add default items only if name not already present
        for item in default_schema:
            if "name" in item and item["name"] not in schema_by_name:
                schema_by_name[item["name"]] = item

        combined_schema = list(schema_by_name.values())

        # Fallback to default schema if empty (should never happen since default is always merged)
        if not combined_schema:
            combined_schema = default_schema

        try:
            generator = DataModelGenerator()
            model_name = f"{generator.sanitize_name(agent_data.name, 'Agent')}_Response"

            output_schema = generator.create_pydantic_model(
                combined_schema,
                model_name=model_name,
                wrap_as_list=False,
            )

            async def generate_task_output(**kwargs):
                """Generate structured task output."""
                return output_schema(**kwargs)

            return StructuredTool.from_function(
                coroutine=generate_task_output,
                name="generate_task_output",
                description="Generate the final structured output for the task. Use this tool to provide the final output when task is finished.",
                args_schema=output_schema,
            )
        except Exception as e:
            logger.error(
                f"Failed to generate output tool for agent {agent_data.id}: {e}",
                exc_info=True,
            )
            return None

    # ─────────────────────────────────────────────────────────────────────────────
    # OUTPUT PARSING METHODS
    # ─────────────────────────────────────────────────────────────────────────────

    def _parse_agent_output(
        self, task_id: UUID, graph_state: GraphState
    ) -> Tuple[Any, str]:
        """
        Extracts the final output and task status from the graph's state.
        Returns a tuple of (agent_output, task_status).
        """
        # Extract agent output based on available data
        agent_output = None

        if "structured_output" in graph_state and graph_state["structured_output"]:
            agent_output = graph_state["structured_output"]
        elif graph_state.get("messages"):
            last_message = graph_state["messages"][-1]
            agent_output = getattr(last_message, "content", str(last_message))

        if agent_output is None:
            logger.warning(f"Could not parse agent output for task {task_id}.")
            return None, "FAILED"

        # Parse task status from the output - default to INCOMPLETE
        task_status = "INCOMPLETE"

        # Handle Pydantic model or dict
        output_dict = None
        if hasattr(agent_output, "model_dump"):
            # Pydantic model - convert to dict
            output_dict = agent_output.model_dump()
        elif isinstance(agent_output, dict):
            # Already a dict
            output_dict = agent_output

        # Check for task_status field
        if output_dict:
            status_value = str(output_dict.get("task_status", "")).lower()
            if "completed" in status_value or "successful" in status_value:
                task_status = "SUCCESSFUL"

        return agent_output, task_status

    async def _parse_agent_actions(
        self, task_id: UUID, graph_state: GraphState
    ) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        Extracts agent actions from the graph state.
        Returns a tuple of (task_log, task_metadata).
        """
        from langchain_core.messages import convert_to_openai_messages

        total_credits = 0
        ai_messages_count = 0
        tools_used_count = 0

        try:
            task_messages = graph_state.get("messages", [])
            if not task_messages:
                logger.warning(f"No messages found in graph state for task {task_id}")
                return [], {
                    "total_messages": 0,
                    "ai_messages": 0,
                    "tools_used": 0,
                    "total_credits": 0,
                }

            # Convert to OpenAI message format (list of dicts)
            task_log = convert_to_openai_messages(task_messages)

            # Iterate and process messages
            for message in task_log:
                role = message.get("role")

                if role == "assistant":
                    ai_messages_count += 1

                elif role == "tool":
                    tools_used_count += 1
                    tool_name = message.get("name")
                    credits = 1  # Default credits

                    if tool_name:
                        tool_data = await sync_to_async(
                            self.agent_tool_repo.get_agent_tool
                        )(tool_name)
                        credits_used = (
                            tool_data.tool_config.get("credit_consumption")
                            if tool_data and tool_data.tool_config
                            else None
                        )

                        # Update credits if consumption is valid
                        if isinstance(credits_used, (int, float)) and credits_used >= 0:
                            credits = int(credits_used)
                    else:
                        logger.warning(
                            f"Tool message without a 'name' action log for task {task_id}"
                        )

                    total_credits += credits  # Add to running total

                    # Check if content looks like a Python dict string representation
                    content = message.get("content", "")
                    if (
                        isinstance(content, str)
                        and content.strip().startswith("{")
                        and "'" in content
                    ):  # Single quotes indicate Python dict string

                        try:
                            # Parse Python dict string and convert to JSON
                            parsed_dict = ast.literal_eval(content)
                            message["content"] = json.dumps(parsed_dict)
                        except (ValueError, SyntaxError):
                            # If parsing fails, leave content as-is
                            pass

            task_metadata = {
                "total_messages": len(task_log),
                "ai_messages": ai_messages_count,
                "tools_used": tools_used_count,
                "total_credits": total_credits,
            }

            return task_log, task_metadata

        except Exception as e:
            logger.error(
                f"Error parsing agent actions for task {task_id}: {str(e)}",
                exc_info=True,
            )
            return [], {
                "total_messages": 0,
                "ai_messages": 0,
                "tools_used": 0,
                "total_credits": 0,
            }

    def _parse_token_usage(
        self, task_id: UUID, graph_state: GraphState
    ) -> Dict[str, Any]:
        """
        Extracts token usage statistics from the graph state.
        Returns aggregated token metrics and detailed breakdown.
        """
        try:
            token_usage_list = graph_state.get("token_usage", [])

            if not token_usage_list:
                logger.warning(f"No token usage data found for task {task_id}")
                return {
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_tokens": 0,
                    "llm_calls_count": 0,
                    "token_details": [],
                }

            # Aggregate totals
            total_input = sum(
                record.get("input_tokens", 0) for record in token_usage_list
            )
            total_output = sum(
                record.get("output_tokens", 0) for record in token_usage_list
            )
            total_tokens = sum(
                record.get("total_tokens", 0) for record in token_usage_list
            )

            token_metrics = {
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_tokens,
                "llm_calls_count": len(token_usage_list),
                "token_details": token_usage_list,  # Full breakdown
            }

            return token_metrics

        except Exception as e:
            logger.error(
                f"Error parsing token usage for task {task_id}: {str(e)}", exc_info=True
            )
            return {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "llm_calls_count": 0,
                "token_details": [],
            }

    def _calculate_task_credits(self, token_metrics: Dict[str, Any]) -> int:
        """
        Calculate credits based on token consumption per step.
        Each step: 0-10,000 tokens = 1 credit (minimum charge per step)
                   10,001-20,000 tokens = 2 credits, etc.

        Args:
            token_metrics: Dictionary containing token usage metrics with token_details

        Returns:
            Total credits summed across all steps
        """
        token_details = token_metrics.get("token_details", [])

        if not token_details:
            return 0

        if AGGREGATE_TOOL_TOKENS:
            combined_tokens = {}
            for step in token_details:
                tool_call_id = step.get("tool_call_id")
                step_total_tokens = step.get("total_tokens", 0)

                # Skip steps without tool_call_id or with zero tokens
                if not tool_call_id or step_total_tokens == 0:
                    continue

                combined_tokens[tool_call_id] = (
                    combined_tokens.get(tool_call_id, 0) + step_total_tokens
                )

            total_credits = sum(
                math.ceil(total_tokens / 10000)
                for total_tokens in combined_tokens.values()
            )
            return total_credits

        else:
            total_credits = 0
            for step in token_details:
                step_tokens = step.get("total_tokens", 0)
                step_credits = math.ceil(step_tokens / 10000)
                total_credits += step_credits

            return total_credits

    # ─────────────────────────────────────────────────────────────────────────────
    # OUTPUT SAVE/UPDATE METHODS
    # ─────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _serialize_output(agent_output: Any) -> str:
        """Serialize agent output to string for DB storage."""
        if isinstance(agent_output, BaseModel):
            return agent_output.model_dump_json()
        elif isinstance(agent_output, (dict, list)):
            return json.dumps(agent_output)
        return str(agent_output)

    async def _save_output(
        self,
        task_id: UUID,
        thread_id: str,
        agent_id: UUID,
        agent_output: Any,
        execution_log: List[Dict[str, Any]],
        credits_used: int,
        token_usage: Dict[str, Any] = None,
    ) -> Optional[AgentOutputDetail]:
        """Asynchronously saves the agent's output, actions, credits, and token usage to the DB."""
        try:
            output_str = self._serialize_output(agent_output)

            # Prepare data structure matching AgentOutput model
            output_data = {
                "agent_task_id": task_id,
                "thread_id": thread_id,
                "agent_id": agent_id,
                "output": output_str,
                "execution_log": execution_log,
                "credits_used": credits_used,
                "output_metadata": {},
                "token_usage": token_usage,
            }

            # Use sync_to_async for the synchronous repository call
            saved_output = await sync_to_async(
                self.agent_output_repo.create_agent_output
            )(output_data)

            if not saved_output:
                logger.error(
                    f"DB call to create_agent_output returned None for task: {task_id}"
                )
                return None

            # Validate and return Pydantic detail schema
            saved_output_detail = AgentOutputDetail.model_validate(saved_output)
            return saved_output_detail

        except Exception as e:
            logger.error(
                f"Error occurred in _save_output for task {task_id}: {e}",
                exc_info=True,  # Include traceback for detailed debugging
            )
            return None

    async def _update_output(
        self,
        task_id: UUID,
        thread_id: str,
        agent_output: Any,
        execution_log: List[Dict[str, Any]],
        new_credits: int,
        new_token_usage: Dict[str, Any],
    ) -> Optional[AgentOutputDetail]:
        """
        Updates an existing AgentOutput record with new output, logs, and accumulated credits/tokens.

        - Overwrites: output, execution_log
        - Accumulates: credits_used, token_usage

        Args:
            task_id: Agent task UUID
            thread_id: Thread ID to scope the update to the current execution
            agent_output: New agent output (Pydantic model, dict, or string)
            execution_log: New execution log (overwrites existing)
            new_credits: Credits to add to existing credits_used
            new_token_usage: Token usage metrics to accumulate

        Returns:
            Updated AgentOutputDetail or None if update failed
        """
        try:
            output_str = self._serialize_output(agent_output)

            # Use sync_to_async for the synchronous repository call
            updated_output = await sync_to_async(
                self.agent_output_repo.update_output_by_task_id
            )(
                task_id=task_id,
                thread_id=thread_id,
                output=output_str,
                execution_log=execution_log,
                new_credits=new_credits,
                new_token_usage=new_token_usage,
            )

            if not updated_output:
                logger.error(
                    f"DB call to update_output_by_task_id returned None for task: {task_id}"
                )
                return None

            # Validate and return Pydantic detail schema
            updated_output_detail = AgentOutputDetail.model_validate(updated_output)
            logger.info(
                f"[task_id={task_id}] output_updated: "
                f"new_credits={new_credits}, "
                f"accumulated_credits={updated_output.credits_used}"
            )
            return updated_output_detail

        except Exception as e:
            logger.error(
                f"Error occurred in _update_output for task {task_id}: {e}",
                exc_info=True,
            )
            return None

    # ─────────────────────────────────────────────────────────────────────────────
    # GRAPH SETUP AND EXECUTION HANDLERS
    # ─────────────────────────────────────────────────────────────────────────────

    async def _setup_agent_graph(
        self,
        task_id: UUID,
        checkpointer,
        user_instructions: Optional[str] = None,
    ) -> GraphSetupResult:
        """Set up the agent graph for the given task.

        Fetches task/agent/email data, prepares context, configures tools,
        and initializes the graph. Skips graph compilation if already cached.

        Args:
            task_id: Task UUID to set up graph for
            checkpointer: PostgreSQL checkpointer instance
            user_instructions: Optional user instructions for tool context

        Returns:
            GraphSetupResult with task_data, agent_data, email_data, task_context.

        Raises:
            ValueError: If task or agent not found.
        """
        # 1. Fetch core data
        task_data = await self._get_task(task_id)
        if not task_data:
            raise ValueError(f"Task not found: {task_id}")

        agent_data = await self._get_agent(task_data.agent_id)
        if not agent_data:
            raise ValueError(f"Agent not found for task {task_id}")

        email_data = await self._get_email(task_data.email_data_id)

        # 2. Prepare context
        task_context, tool_runtime_context = await self._prepare_context(
            task_data=task_data,
            email_data=email_data,
            agent_data=agent_data,
            user_instructions=user_instructions,
        )

        # 3. Skip graph compilation if already initialized
        if self._graph is not None:
            return GraphSetupResult(task_data, agent_data, email_data, task_context)

        logger.info(f"[task_id={task_id}] Graph not in memory, reconstructing...")

        # 4. Configure tools and initialize graph
        agent_tools = await self._configure_tools(agent_data, tool_runtime_context)
        await self._initialize_graph(agent_data, agent_tools, checkpointer)

        logger.info(f"[task_id={task_id}] Graph reconstructed successfully")
        return GraphSetupResult(task_data, agent_data, email_data, task_context)

    async def _preprocess_execution(
        self,
        task_id: UUID,
        checkpointer: Any,
        thread_id: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """DEPRECATED: Use _setup_agent_graph directly and inline remaining logic.

        Preprocessing for new task execution.
        Handles: status update, graph setup, thread_id generation, initial message.

        Args:
            task_id: Task UUID
            checkpointer: PostgreSQL checkpointer instance
            thread_id: Existing thread_id (None for new executions)
            additional_data: Optional additional data (e.g., user instructions)

        Returns:
            Dict containing: task_data, agent_data, email_data,
            thread_id, initial_message

        Raises:
            ValueError: If task or agent not found
        """
        additional_data = additional_data or {}
        user_instructions = additional_data.get("instructions")

        try:
            # 1. Set task status to EXECUTING
            await self._update_task_status(task_id, "EXECUTING")

            # 2. Set up graph (fetch data, configure tools, initialize graph)
            setup_result = await self._setup_agent_graph(
                task_id, checkpointer, user_instructions=user_instructions
            )
            task_data = setup_result.task_data
            agent_data = setup_result.agent_data
            email_data = setup_result.email_data
            task_context = setup_result.task_context

            # 3. Handle thread_id
            if thread_id is None:
                thread_id = f"thread-{str(task_id)}-{int(time.time() * 1000)}"
                await self._update_agent_task(task_id, {"thread_id": thread_id})

            # 4. Build initial message (task_context from _setup_agent_graph)
            task_input = Template(TASK_INPUT_PROMPT).render(
                task_title=(
                    task_data.title.strip() if task_data.title else "Untitled Task"
                ),
                task_description=(
                    task_data.description.strip() if task_data.description else ""
                ),
                task_context=task_context,
                user_instructions=user_instructions,
            )
            initial_message = HumanMessage(content=task_input)

            return {
                "task_data": task_data,
                "agent_data": agent_data,
                "email_data": email_data,
                "thread_id": thread_id,
                "initial_message": initial_message,
            }

        except Exception as e:
            logger.error(f"[task_id={task_id}] preprocess_failed: {e}", exc_info=True)
            raise

    async def _postprocess_execution(
        self,
        task_id: UUID,
        thread_id: str,
        agent_id: UUID,
        final_state: Dict[str, Any],
        save_mode: Literal["create", "update"] = "update",
    ) -> Dict[str, Any]:
        """
        Common postprocessing for all graph executions.

        Handles:
        - Parsing output, actions, tokens
        - Calculating and adding credits
        - Saving/updating output
        - Updating task status and completed_at

        Args:
            task_id: Task UUID
            thread_id: Thread ID
            agent_id: Agent UUID
            final_state: Final graph state after execution
            save_mode: "create" for new output, "update" for existing

        Returns:
            Dict with: task_status, credits_used, total_tokens, output_id
        """
        # 1. Parse output and status
        agent_output, task_status = self._parse_agent_output(task_id, final_state)

        # 2. Parse actions/execution log
        execution_log, task_metadata = await self._parse_agent_actions(
            task_id, final_state
        )

        # 3. Parse token usage
        token_metrics = self._parse_token_usage(task_id, final_state)

        # 4. Calculate credits
        credits_used = self._calculate_task_credits(token_metrics)

        # 5. Add credits to account
        await self.credits_manager.add_agent_task_credits(task_id, credits_used)

        # 6. Save or Update output based on mode
        if save_mode == "create":
            saved_output = await self._save_output(
                task_id=task_id,
                thread_id=thread_id,
                agent_id=agent_id,
                agent_output=agent_output,
                execution_log=execution_log,
                credits_used=credits_used,
                token_usage=token_metrics,
            )
        else:  # update
            saved_output = await self._update_output(
                task_id=task_id,
                thread_id=thread_id,
                agent_output=agent_output,
                execution_log=execution_log,
                new_credits=credits_used,
                new_token_usage=token_metrics,
            )
            if saved_output is None:
                logger.info(
                    f"[task_id={task_id}] no existing output to update, "
                    f"creating new record (task was likely paused before first save)"
                )
                saved_output = await self._save_output(
                    task_id=task_id,
                    thread_id=thread_id,
                    agent_id=agent_id,
                    agent_output=agent_output,
                    execution_log=execution_log,
                    credits_used=credits_used,
                    token_usage=token_metrics,
                )
        # 7. Update task status
        await self._update_task_status(task_id, task_status)

        # 8. Update completed_at
        await self._update_agent_task(task_id, {"completed_at": datetime.now()})

        # 9. Return result
        return {
            "task_status": task_status,
            "credits_used": credits_used,
            "total_tokens": token_metrics.get("total_tokens", 0),
            "saved_output": saved_output,
            "output_id": saved_output.id if saved_output else None,
            "agent_output": agent_output,
            "execution_log": execution_log,
            "task_metadata": task_metadata,
            "token_metrics": token_metrics,
        }
