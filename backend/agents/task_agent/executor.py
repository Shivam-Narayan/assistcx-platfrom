# Standard library imports
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple
from uuid import UUID

# Third-party imports
from asgiref.sync import sync_to_async
from jinja2 import Template
from langchain_core.messages import HumanMessage, convert_to_openai_messages
from sqlalchemy.orm import Session

# Local application imports
from logger import configure_logging
from agents.shared_utils.tools_factory import ToolsFactory
from agents.shared_utils.checkpointer import get_checkpointer_context
from agents.shared_utils.llm_provider import LLMProvider

# Database modules
from repository.agent_output_repository import AgentOutputRepository
from repository.agent_repository import AgentRepository
from repository.agent_task_repository import AgentTaskRepository
from repository.agent_tool_repository import AgentToolRepository
from repository.attachment_repository import AttachmentRepository
from repository.class_group_repository import ClassGroupRepository
from repository.data_collection_repository import DataCollectionRepository
from repository.data_template_repository import DataTemplateRepository
from repository.email_repository import EmailRepository
from schemas.agent_output_schema import AgentOutputDetail
from schemas.agent_schema import AgentDetail
from schemas.agent_task_schema import AgentTaskDetail
from schemas.agent_tool_schema import AgentToolDetail
from schemas.email_schema import EmailDetail
from utils.credits import CreditManager

# Config
from configs.agent_tools_data import KNOWLEDGE_SEARCH_TOOLS

# Local module imports
from .graph import TaskAgentGraph
from .schemas import GraphState
from .prompts import TASK_SYSTEM_PROMPT, TASK_INPUT_PROMPT
from .utils import format_knowledge_collections, format_task_plan
from .executor_helper import TaskExecutorHelper

logger = configure_logging(__name__)


class TaskExecutor(TaskExecutorHelper):
    """
    Executes agent tasks using the TaskAgentGraph asynchronously.
    Handles fetching data, setting up the agent, running the graph,
    and storing results, while interacting with synchronous repositories.
    """

    def __init__(
        self,
        db: Session,
        organization_schema: str,
    ):
        """
        Initializes the TaskExecutor.

        Args:
            db: SQLAlchemy Session for synchronous database operations.
            organization_schema: The schema name for the organization.
        """
        # Store dependencies
        self.db = db
        self.organization_schema = organization_schema

        # Initialize synchronous repositories using the passed-in db
        self.agent_task_repo = AgentTaskRepository(self.db)
        self.email_repo = EmailRepository(self.db)
        self.attachment_repo = AttachmentRepository(self.db)
        self.agent_repo = AgentRepository(self.db)
        self.agent_tool_repo = AgentToolRepository(self.db)
        self.template_repo = DataTemplateRepository(self.db)
        self.class_group_repo = ClassGroupRepository(self.db)
        self.collection_repo = DataCollectionRepository(self.db)
        self.agent_output_repo = AgentOutputRepository(self.db)
        self.credits_manager = CreditManager(self.db)

        # Agent LLM and graph instance
        self.llm_provider = LLMProvider(self.organization_schema, self.db)
        self.agent_llm = self.llm_provider.get_llm()
        self._graph: Optional[TaskAgentGraph] = None

    # ─────────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_human_review_config(
        agent_data: AgentDetail,
    ) -> Tuple[bool, Dict[str, list]]:
        """Check if any tool requires human review and collect review rules.

        Returns:
            Tuple of (human_review_enabled, tool_review_rules).
            tool_review_rules maps tool action names to their rule lists.
        """
        review_rules = {}
        enabled = False
        for tc in agent_data.tools or []:
            if getattr(tc, "human_review", False):
                enabled = True
                if tc.review_rules:
                    review_rules[tc.action] = tc.review_rules
        return enabled, review_rules

    # ─────────────────────────────────────────────────────────────────────────────
    # STREAM HELPERS
    # ─────────────────────────────────────────────────────────────────────────────

    def _build_review_payload(
        self, snapshot: Any, task_id: UUID, thread_id: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Build the (paused_state_update, review_terminator) pair for a paused task.

        - paused_state_update: transformed graph state with `pending_review` attached.
        - review_terminator: typed `{type: "review", ...}` event signaling stream end.
        """
        state_update = self._transform_state_update(dict(snapshot.values))

        # Extract pending_review from snapshot.interrupts (LangGraph built-in).
        # human_review_node sets: {"question": "...", "tool_call": {id, name, args}}
        pending_review = None
        if snapshot.interrupts:
            interrupt_value = snapshot.interrupts[0].value
            if isinstance(interrupt_value, dict):
                tool_call = interrupt_value.get("tool_call", {})
                tool_name = tool_call.get("name", "")

                # Get per-tool review rules from graph config
                all_rules = getattr(self._graph, "review_rules", None) or []
                rules = (
                    all_rules.get(tool_name, [])
                    if isinstance(all_rules, dict)
                    else all_rules
                )

                pending_review = {
                    "tool_name": tool_name,
                    "tool_call_id": tool_call.get("id"),
                    "tool_args": tool_call.get("args", {}),
                    "review_rules": rules,
                    "question": interrupt_value.get("question"),
                }
                state_update["pending_review"] = pending_review

        terminator = {
            "type": "review",
            "task_id": str(task_id),
            "thread_id": thread_id,
            "task_status": "PAUSED",
            "tool_call_id": pending_review["tool_call_id"] if pending_review else None,
        }
        return state_update, terminator

    @staticmethod
    def _transform_state_update(update: Dict[str, Any]) -> Dict[str, Any]:
        """Transform internal graph state keys to API-facing keys."""
        if "messages" in update and update["messages"]:
            update["execution_log"] = convert_to_openai_messages(update["messages"])
            del update["messages"]
        if "structured_output" in update:
            update["output"] = update["structured_output"]
            del update["structured_output"]
        if "review_history" in update and update["review_history"]:
            update["review_history"] = [
                (
                    record.model_dump(mode="json")
                    if hasattr(record, "model_dump")
                    else record
                )
                for record in update["review_history"]
            ]
        return update

    # ─────────────────────────────────────────────────────────────────────────────
    # TOOL AND GRAPH CONFIGURATION
    # ─────────────────────────────────────────────────────────────────────────────

    async def _configure_tools(
        self, agent_data: AgentDetail, tool_runtime_context: Dict[str, Any]
    ) -> List[Any]:
        """Configures LangChain tools for the agent graph asynchronously."""
        task_tools = []
        if not agent_data.tools and not agent_data.knowledge_base:
            return []

        tool_generator = ToolsFactory(tool_runtime_context)

        for tool_config in agent_data.tools or []:
            action = tool_config.action
            if not action:
                logger.warning("Agent tool configuration missing 'action'. Skipping.")
                continue

            try:
                # Fetch tool details from DB asynchronously
                saved_tool = await sync_to_async(self.agent_tool_repo.get_agent_tool)(
                    action
                )

                if not saved_tool:
                    logger.warning(
                        f"No tool details found in DB for action: {action}. Skipping tool."
                    )
                    continue

                # Validate and prepare tool data
                tool_data = AgentToolDetail.model_validate(saved_tool).model_dump()

                # Generate the Langchain tool instance
                agent_tool = tool_generator.generate(
                    tool_data,
                    review_required=getattr(tool_config, "human_review", False),
                )
                if agent_tool:
                    task_tools.append(agent_tool)
                else:
                    logger.warning(
                        f"Failed to generate tool instance for action: {action}"
                    )

            except Exception as e:
                logger.error(
                    f"Error configuring tool {action} for agent {agent_data.id}: {e}",
                    exc_info=True,
                )
                continue

        default_tools = await self._configure_default_tools(
            agent_data, tool_generator, task_tools
        )

        return task_tools + default_tools

    async def _configure_default_tools(
        self,
        agent_data: AgentDetail,
        tool_generator: ToolsFactory,
        existing_tools: List[Any],
    ) -> List[Any]:
        """Auto-inject default tools based on agent configuration.

        These are capability tools the agent needs but weren't explicitly
        configured by the user (e.g., knowledge search, output generation).
        """
        default_tools = []
        existing_names = {getattr(t, "name", None) for t in existing_tools}

        if (
            agent_data.knowledge_base
            and "search_knowledge_collections" not in existing_names
        ):
            try:
                default_tools.append(tool_generator.generate(KNOWLEDGE_SEARCH_TOOLS[0]))
            except Exception as e:
                logger.warning("Could not add default knowledge search tool: %s", e)

        # Output tool for structured task output
        output_tool = await self._create_output_tool(agent_data)
        if output_tool:
            default_tools.append(output_tool)

        return default_tools

    async def _initialize_graph(
        self, agent_data: AgentDetail, tools: List[Any], checkpointer
    ) -> TaskAgentGraph:
        """Initializes and compiles the TaskAgentGraph based on agent configuration with provided checkpointer."""
        # Format the agent rules
        formatted_rules = "\n".join([f"* {rule}" for rule in agent_data.rules])
        current_date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Format execution plan if available
        formatted_execution_plan = (
            format_task_plan(
                [
                    step.model_dump() if hasattr(step, "model_dump") else step
                    for step in agent_data.plan
                ]
            )
            if agent_data.plan
            else None
        )

        # Format success criteria as bullet points
        formatted_success_criteria = (
            "\n".join(
                [
                    f"- {line.strip()}"
                    for line in agent_data.success_criteria.strip().split("\n")
                    if line.strip()
                ]
            )
            if agent_data.success_criteria
            else None
        )

        # Fetch data template details for agent's assigned data templates
        data_templates_data = None
        if agent_data.data_templates:
            data_templates_data = []
            for data_template_class in agent_data.data_templates:
                data_template = await sync_to_async(self.template_repo.get_template)(
                    data_template_class
                )
                if data_template:
                    data_templates_data.append(
                        {
                            "template_class": data_template.template_class,
                            "description": data_template.description
                            or data_template.name,
                        }
                    )

        # Fetch class group details for agent's assigned class_groups
        class_groups_data = None
        if agent_data.class_groups:
            class_groups_data = []
            for class_group_key in agent_data.class_groups:
                class_group = await sync_to_async(
                    self.class_group_repo.get_class_group_by_id
                )(class_group_key)
                if class_group:
                    class_groups_data.append(
                        {
                            "key": class_group.key,
                            "description": class_group.description or class_group.name,
                        }
                    )

        # Fetch knowledge collection details for agent's assigned knowledge base
        knowledge_collections_data = None
        if agent_data.knowledge_base:
            knowledge_collections = []
            for knowledge in agent_data.knowledge_base:
                collection = await sync_to_async(
                    self.collection_repo.get_data_collection_by_id
                )(UUID(knowledge.collection_id))
                if collection and collection.availability == "PUBLISHED":
                    knowledge_collections.append(
                        {
                            "id": str(collection.id),
                            "name": collection.name,
                            "index_name": collection.index_name,
                            "description": collection.description,
                            "document_count": collection.file_count,
                            "metadata_fields": collection.smart_fields,
                            "knowledge_topics": collection.knowledge_topics,
                        }
                    )
            if knowledge_collections:
                knowledge_collections_data = format_knowledge_collections(
                    knowledge_collections
                )

        # Extract other necessary configurations
        system_prompt = Template(TASK_SYSTEM_PROMPT).render(
            agent_name=agent_data.name,
            agent_goal=agent_data.goal,
            agent_instruction=agent_data.instructions,
            task_rules=formatted_rules,
            execution_plan=formatted_execution_plan,
            success_criteria=formatted_success_criteria,
            current_date_time=current_date_time,
            data_templates=data_templates_data,
            class_groups=class_groups_data,
            knowledge_collections=knowledge_collections_data,
        )

        # HITL Configuration
        human_review_enabled, tool_review_rules = self._get_human_review_config(
            agent_data
        )

        # Build agent kwargs
        agent_kwargs = {
            "agent_name": agent_data.name,
            "agent_goal": agent_data.goal,
            "agent_instructions": agent_data.instructions,
            "task_rules": formatted_rules,
            "success_criteria": agent_data.success_criteria,
            "human_review_rules": tool_review_rules,
        }

        # Instantiate the TaskAgentGraph with provided checkpointer
        graph_builder = TaskAgentGraph(
            llm=self.agent_llm,
            tools=tools,
            system_prompt=system_prompt,
            checkpointer=checkpointer,
            human_review=human_review_enabled,
            agent_kwargs=agent_kwargs,
        )

        # Compile the graph
        try:
            compiled_graph = await graph_builder.create_graph()
            if compiled_graph is None:
                # create_graph might return None if compilation fails internally and logs error
                raise RuntimeError(
                    f"Graph compilation failed for agent {agent_data.id}"
                )
            self._graph = graph_builder  # Store the graph builder instance
            return graph_builder  # Return the graph builder instance
        except Exception as e:
            logger.error(
                f"Failed to initialize or compile graph for agent {agent_data.id}: {e}",
                exc_info=True,
            )
            # Re-raise or handle as appropriate for the executor's flow
            raise RuntimeError(
                f"Graph initialization failed for agent {agent_data.id}"
            ) from e

    # ─────────────────────────────────────────────────────────────────────────────
    # MAIN EXECUTION METHODS
    # ─────────────────────────────────────────────────────────────────────────────

    async def execute_task(
        self,
        task_id: UUID,
        thread_id: str = None,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Tuple[AgentOutputDetail, str]]:
        """Asynchronously executes a specific agent task using checkpointer context manager."""
        async with get_checkpointer_context(self.organization_schema) as checkpointer:
            try:
                logger.info(f"[task_id={task_id}] task_execution_started")
                additional_data = additional_data or {}
                user_instructions = additional_data.get("instructions")

                # ─── PREPROCESS ───
                await self._update_task_status(task_id, "EXECUTING")

                setup_result = await self._setup_agent_graph(
                    task_id, checkpointer, user_instructions=user_instructions
                )

                # Generate thread_id for new executions
                if thread_id is None:
                    thread_id = f"thread-{str(task_id)}-{int(time.time() * 1000)}"
                    await self._update_agent_task(task_id, {"thread_id": thread_id})

                # Build initial message
                task_input = Template(TASK_INPUT_PROMPT).render(
                    task_title=setup_result.task_data.title.strip() if setup_result.task_data.title else "Untitled Task",
                    task_description=setup_result.task_data.description.strip() if setup_result.task_data.description else "",
                    task_context=setup_result.task_context,
                    user_instructions=user_instructions,
                )
                initial_message = HumanMessage(content=task_input)

                logger.info(
                    f"[task_id={task_id}] preprocess_completed: "
                    f"agent={setup_result.agent_data.name}, "
                    f"email_uuid={setup_result.email_data.id if setup_result.email_data else 'None'}, "
                    f"thread_id={thread_id}"
                )

                # ─── EXECUTE GRAPH ───
                logger.info(
                    f"[task_id={task_id}] graph_execution_started: "
                    f"agent={setup_result.agent_data.name}, thread_id={thread_id}"
                )

                final_state: GraphState = await self._graph.get_output(
                    thread_id=thread_id,
                    messages=[initial_message],
                    task_id=str(task_id),
                    agent_id=str(setup_result.task_data.agent_id),
                )

                # ─── CHECK FOR INTERRUPT (HITL pause) ───
                state_snapshot = await self._graph.get_state(thread_id)
                if state_snapshot.next:
                    await self._update_task_status(task_id, "PAUSED")
                    logger.info(
                        f"[task_id={task_id}] task_paused_for_review: "
                        f"thread_id={thread_id}, next_node={list(state_snapshot.next)}"
                    )
                    paused_state, _ = self._build_review_payload(
                        state_snapshot, task_id, thread_id
                    )
                    await self._notify_paused_reviewers(
                        task_id=task_id,
                        agent_data=setup_result.agent_data,
                        task_data=setup_result.task_data,
                        pending_review=paused_state.get("pending_review"),
                    )
                    return paused_state, "PAUSED"

                # ─── POSTPROCESS ───
                logger.info(
                    f"[task_id={task_id}] graph_execution_completed, postprocessing output..."
                )

                result = await self._postprocess_execution(
                    task_id=task_id,
                    thread_id=thread_id,
                    agent_id=setup_result.agent_data.id,
                    final_state=final_state,
                    save_mode="create",
                )

                logger.info(
                    f"[task_id={task_id}] task_execution_completed: "
                    f"status={result['task_status']}, "
                    f"credits={result['credits_used']}, "
                    f"output_id={result['output_id']}"
                )

                # Return the DB-validated saved output and status
                return result["saved_output"], result["task_status"]

            except Exception as e:
                await self._update_task_status(task_id, "FAILED")
                logger.error(
                    f'[task_id={task_id}] task_execution_failed: error="{str(e)}"',
                    exc_info=True,
                )
                return {}, "FAILED"

    async def observe_task_execution(
        self, task_id: UUID, thread_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream the execution state of a task using task_id and thread_id."""
        async with get_checkpointer_context(self.organization_schema) as checkpointer:
            try:
                # Ensure graph is initialized
                await self._setup_agent_graph(task_id, checkpointer)

                # Observe the task state (read-only, no execution triggered)
                async for state_update in self._graph.observe_output(
                    thread_id,
                    poll_interval=1.0,
                ):
                    yield self._transform_state_update(state_update)

                # ─── TERMINAL EVENT ───
                # Emit review/completion terminator for parity with resume/continue.
                final_snapshot = await self._graph.get_state(thread_id)
                if not final_snapshot:
                    return

                if final_snapshot.next:
                    paused_update, terminator = self._build_review_payload(
                        final_snapshot, task_id, thread_id
                    )
                    yield paused_update
                    yield terminator
                else:
                    # Read-only: credits/tokens/output not recomputed here.
                    task_data = await self._get_task(task_id)
                    task_status = (
                        task_data.progress[-1].status
                        if task_data and task_data.progress
                        else None
                    )
                    yield {
                        "type": "completion",
                        "task_id": str(task_id),
                        "thread_id": thread_id,
                        "task_status": task_status,
                    }

            except Exception as e:
                logger.error(
                    f"Error streaming task execution for task_id {task_id}, thread_id {thread_id}: {e}",
                    exc_info=True,
                )
                yield {
                    "error": f"Streaming failed: {str(e)}",
                    "task_id": str(task_id),
                    "thread_id": thread_id,
                }

    async def _run_streaming_execution(
        self,
        task_id: UUID,
        thread_id: str,
        stream_fn: Callable[[], AsyncGenerator[Dict[str, Any], None]],
        operation: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run a streaming task execution lifecycle: setup, stream, postprocess.

        Shared implementation for resume_task_execution and continue_task_execution.

        Args:
            task_id: Task UUID
            thread_id: Thread ID for the execution
            stream_fn: Callable that returns the async generator to stream from
            operation: Label for logging ("resume" or "continue")

        Yields:
            Dict with node updates and final completion event
        """
        async with get_checkpointer_context(self.organization_schema) as checkpointer:
            try:
                logger.info(
                    f"[task_id={task_id}] task_{operation}_execution_started: thread_id={thread_id}"
                )

                # ─── PREPROCESS ───
                await self._update_task_status(task_id, "EXECUTING")

                setup_result = await self._setup_agent_graph(task_id, checkpointer)

                # ─── STREAM EXECUTION ───
                async for update in stream_fn():
                    yield self._transform_state_update(update)

                # ─── CHECK FOR INTERRUPT (HITL pause) ───
                final_state_snapshot = await self._graph.get_state(thread_id)

                if final_state_snapshot.next:
                    await self._update_task_status(task_id, "PAUSED")
                    logger.info(
                        f"[task_id={task_id}] task_paused_for_review: "
                        f"thread_id={thread_id}, next_node={list(final_state_snapshot.next)}"
                    )
                    paused_update, terminator = self._build_review_payload(
                        final_state_snapshot, task_id, thread_id
                    )
                    await self._notify_paused_reviewers(
                        task_id=task_id,
                        agent_data=setup_result.agent_data,
                        task_data=setup_result.task_data,
                        pending_review=paused_update.get("pending_review"),
                    )
                    yield paused_update
                    yield terminator
                    return

                # ─── POSTPROCESS ───
                logger.info(
                    f"[task_id={task_id}] task_{operation}_streaming_completed, postprocessing..."
                )

                final_state = final_state_snapshot.values
                result = await self._postprocess_execution(
                    task_id=task_id,
                    thread_id=thread_id,
                    agent_id=setup_result.task_data.agent_id,
                    final_state=final_state,
                    save_mode="update",
                )

                # Yield completion event
                yield {
                    "type": "completion",
                    "task_id": str(task_id),
                    "thread_id": thread_id,
                    "task_status": result["task_status"],
                    "credits_used": result["credits_used"],
                    "total_tokens": result["total_tokens"],
                    "output_id": (
                        str(result["output_id"]) if result["output_id"] else None
                    ),
                }

                logger.info(
                    f"[task_id={task_id}] task_{operation}_execution_completed: "
                    f"status={result['task_status']}, credits={result['credits_used']}"
                )

            except Exception as e:
                await self._update_task_status(task_id, "FAILED")
                logger.error(
                    f"[task_id={task_id}] task_{operation}_execution_failed: {str(e)}",
                    exc_info=True,
                )
                yield {
                    "error": f"Failed to {operation} task execution: {str(e)}",
                    "task_id": str(task_id),
                    "thread_id": thread_id,
                }

    async def resume_task_execution(
        self, task_id: UUID, thread_id: str, human_input: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Resume a paused task with human input (streaming).

        Args:
            task_id: Task UUID
            thread_id: Thread ID for the paused execution
            human_input: Dict with action, feedback, edited_params, and user_id

        Yields:
            Dict with node updates and final completion event
        """
        stream_fn = lambda: self._graph.resume_graph(thread_id, human_input)
        async for update in self._run_streaming_execution(
            task_id, thread_id, stream_fn, "resume"
        ):
            yield update

    async def continue_task_execution(
        self, task_id: UUID, thread_id: str, message: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Continue a task with additional human instructions.

        Args:
            task_id: Task UUID
            thread_id: Thread ID for the execution
            message: Human instruction to continue execution

        Yields:
            Dict with node updates and final completion event
        """
        human_message = HumanMessage(content=message)
        stream_fn = lambda: self._graph.stream_output(
            thread_id, messages=[human_message], full_state=True, clear_output=True
        )
        async for update in self._run_streaming_execution(
            task_id, thread_id, stream_fn, "continue"
        ):
            yield update
