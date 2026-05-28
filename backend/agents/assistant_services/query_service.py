"""Assistant query service — unified execution for research and live agent modes."""

# Custom libraries
from agents.live_agent.graph import LiveAgentGraph
from agents.live_agent.prompts import LIVE_AGENT_SYSTEM_PROMPT
from agents.research_agent.config import MAX_ITERATIONS as RESEARCH_MAX_ITERATIONS
from agents.research_agent.graph import ResearchAgentGraph
from agents.research_agent.schemas import ResearchState
from agents.shared_utils.checkpointer import get_checkpointer_context
from agents.shared_utils.tools_factory import ToolsFactory
from logger import configure_logging

# Database modules
from repository.agent_repository import AgentRepository
from repository.agent_tool_repository import AgentToolRepository
from schemas.agent_schema import AgentDetail
from schemas.agent_tool_schema import AgentToolDetail

# Default libraries
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID
import asyncio

# Installed libraries
from asgiref.sync import sync_to_async
from jinja2 import Template
from langchain_core.messages import HumanMessage, AIMessage, convert_to_openai_messages

# Base class
from .helpers import AssistantServiceHelper


logger = configure_logging(__name__)


class AssistantQueryService(AssistantServiceHelper):
    """Unified assistant service for RAG, research, and live agent execution."""

    # ──────────────────────────────────────────────────────────────────────
    # Direct (non-streaming) execution
    # ──────────────────────────────────────────────────────────────────────

    async def execute_query_direct(
        self,
        query: str,
        user_id: str,
        mode: str = "research",
        chat_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        collections: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[Dict[str, str]]] = None,
        user_context: Optional[Dict[str, Any]] = None,
        web_search_enabled: bool = True,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """Execute a query and return the complete response (non-streaming).

        Supports modes: research (default) and agent.
        """
        start_time = datetime.now(timezone.utc)

        chat_thread = await self._validate_chat_thread(chat_id=chat_id, user_id=user_id)
        chat_id = chat_thread.get("chat_id")
        thread_id = chat_thread.get("thread_id")

        # Prepare execution context (collections, messages, user context)
        knowledge_collections, previous_messages, prepared_user_context = (
            await self._prepare_execution_context(
                user_id=user_id,
                chat_id=chat_id,
                thread_id=thread_id,
                collections=collections,
                attachments=attachments,
                user_context=user_context,
                web_search_enabled=web_search_enabled,
            )
        )

        # Save user query
        prepared_user_context["collections"] = collections
        await self._save_thread_message(
            chat_thread_id=chat_id,
            message_data={
                "role": "user",
                "content": query,
                "context": prepared_user_context,
            },
        )

        async with get_checkpointer_context(self.org_schema) as checkpointer:
            try:
                if mode == "research":
                    response = await self._execute_research_direct(
                        query,
                        thread_id,
                        knowledge_collections,
                        previous_messages,
                        prepared_user_context,
                        checkpointer,
                        timeout,
                    )
                elif mode == "agent":
                    response = await self._execute_agent_direct(
                        query,
                        chat_id,
                        thread_id,
                        user_id,
                        agent_id,
                        checkpointer,
                        timeout,
                    )
                else:
                    raise ValueError(f"Unsupported mode: {mode}")

                # Common post-processing
                execution_time = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds()
                response["execution_time"] = execution_time
                response["thread_id"] = thread_id
                response["chat_id"] = chat_id

                # Store assistant response
                if response.get("answer"):
                    context = self._build_save_context(
                        response, mode, thread_id, agent_id=agent_id
                    )
                    message_id = await self._save_thread_message(
                        chat_thread_id=chat_id,
                        message_data={
                            "role": "assistant",
                            "content": response.get("answer"),
                            "context": context,
                        },
                    )
                    if message_id:
                        response["message_id"] = message_id

                # Check for harmful queries (no-op unless triage flagged it)
                await self._send_notification(user_id, response)

                return response

            except asyncio.TimeoutError:
                logger.error(f"Query timeout for chat thread {chat_id}")
                raise TimeoutError(f"Query execution timed out after {timeout} seconds")
            except Exception as e:
                logger.error(f"Error executing query: {e}", exc_info=True)
                raise

    async def _execute_research_direct(
        self,
        query,
        thread_id,
        knowledge_collections,
        previous_messages,
        prepared_user_context,
        checkpointer,
        timeout,
    ) -> Dict[str, Any]:
        """Execute research mode query directly."""
        agent = ResearchAgentGraph(
            primary_llm=self.primary_llm,
            fast_llm=self.fast_llm,
            checkpointer=checkpointer,
        )
        config = {
            "configurable": {
                "knowledge_collections": knowledge_collections or [],
                "previous_messages": previous_messages,
                "user_context": prepared_user_context,
                "thread_id": thread_id,
                "primary_llm": self.primary_llm,
                "fast_llm": self.fast_llm,
            },
            "recursion_limit": RESEARCH_MAX_ITERATIONS,
        }
        final_state = await asyncio.wait_for(
            agent.get_response(query=query, config=config),
            timeout=timeout,
        )

        # Parse token usage and credits
        token_metrics = self._parse_token_usage(final_state.token_usage or [])
        credits_used = self._calculate_credits(token_metrics)

        # Convert messages to OpenAI format
        messages = (
            convert_to_openai_messages(final_state.messages)
            if final_state.messages
            else []
        )

        return {
            "answer": final_state.final_answer or "",
            "sources": [s.model_dump() for s in (final_state.relevant_sources or [])],
            "citations": [],
            "suggested_queries": final_state.suggested_queries or [],
            "title": final_state.title,
            "query_type": final_state.query_type,
            "token_usage": token_metrics,
            "credits_used": credits_used,
            "messages": messages,
        }

    async def _execute_agent_direct(
        self,
        query,
        chat_id,
        thread_id,
        user_id,
        agent_id,
        checkpointer,
        timeout,
    ) -> Dict[str, Any]:
        """Execute agent mode query directly by consuming the streaming pipeline."""
        if not agent_id:
            raise ValueError("agent_id is required for agent mode")

        # Fetch conversation history for system prompt context
        previous_messages = (
            await self._get_thread_messages(chat_id, limit=10, truncate=False)
            if chat_id
            else []
        )

        agent_setup = await self._setup_live_agent(
            agent_id, user_id, previous_messages=previous_messages
        )
        if not agent_setup:
            raise ValueError(f"Agent not found: {agent_id}")

        graph = LiveAgentGraph(
            llm=agent_setup["agent_llm"],
            tools=agent_setup["tools"],
            system_prompt=agent_setup["system_prompt"],
            checkpointer=checkpointer,
            agent_name=agent_setup["agent_data"].name,
        )
        await graph.create_graph()

        # Consume stream to get final response
        final_event = None
        async for event in graph.stream_events(
            thread_id=thread_id,
            messages=[HumanMessage(content=query)],
            agent_id=agent_id,
        ):
            if event.get("type") in ("final_state", "review_required"):
                final_event = event
                break

        if not final_event:
            return {"answer": "", "sources": [], "citations": []}

        return {
            "answer": final_event.get("answer", ""),
            "sources": [],
            "citations": [],
            "suggested_queries": final_event.get("suggested_queries", []),
            "token_usage": final_event.get("token_usage", []),
            "messages": final_event.get("messages", []),
        }

    # ──────────────────────────────────────────────────────────────────────
    # Unified Streaming
    # ──────────────────────────────────────────────────────────────────────

    async def execute_query_stream(
        self,
        query: str,
        user_id: str,
        mode: str = "research",
        chat_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        collections: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[Dict[str, str]]] = None,
        user_context: Optional[Dict[str, Any]] = None,
        web_search_enabled: bool = True,
    ):
        """Unified streaming execution for all agent types.

        Yields:
            SSE event dicts — execution events pass through, final_state/review_required
            enriched with message saving and metadata.
        """
        # 1. Common setup: validate/create chat thread
        chat_thread = await self._validate_chat_thread(chat_id=chat_id, user_id=user_id)
        chat_id = chat_thread.get("chat_id")
        thread_id = chat_thread.get("thread_id")

        # 2. For agent mode, fetch history BEFORE saving (needs full untreated content)
        agent_previous_messages = None
        if mode == "agent":
            agent_previous_messages = (
                await self._get_thread_messages(chat_id, limit=10, truncate=False)
                if chat_id
                else []
            )

        # 3. Save user message
        await self._save_thread_message(
            chat_thread_id=chat_id,
            message_data={
                "role": "user",
                "content": query,
                "context": {
                    "user_id": user_id,
                    "mode": mode,
                    "agent_id": agent_id,
                    "collections": collections,
                    "attachments": attachments,
                },
            },
        )

        # 4. Build mode-specific graph + stream, then process uniformly
        start_time = datetime.now(timezone.utc)
        agent_name = None
        try:
            async with get_checkpointer_context(self.org_schema) as checkpointer:
                if mode == "agent":
                    agent_setup = await self._setup_live_agent(
                        agent_id, user_id, previous_messages=agent_previous_messages
                    )
                    if not agent_setup:
                        yield {
                            "type": "error",
                            "error": f"Agent not found or invalid: {agent_id}",
                            "chat_id": chat_id,
                        }
                        return

                    agent_name = agent_setup["agent_data"].name

                    graph = LiveAgentGraph(
                        llm=agent_setup["agent_llm"],
                        tools=agent_setup["tools"],
                        system_prompt=agent_setup["system_prompt"],
                        checkpointer=checkpointer,
                        agent_name=agent_setup["agent_data"].name,
                    )
                    await graph.create_graph()
                    stream = graph.stream_events(
                        thread_id=thread_id,
                        messages=[HumanMessage(content=query)],
                        agent_id=str(agent_setup["agent_data"].id),
                    )

                elif mode == "research":
                    knowledge_collections, previous_messages, prepared_ctx = (
                        await self._prepare_execution_context(
                            user_id,
                            chat_id,
                            thread_id,
                            collections,
                            attachments,
                            user_context,
                            web_search_enabled,
                        )
                    )
                    agent = ResearchAgentGraph(
                        primary_llm=self.primary_llm,
                        fast_llm=self.fast_llm,
                        checkpointer=checkpointer,
                    )
                    config = {
                        "configurable": {
                            "thread_id": thread_id,
                            "knowledge_collections": knowledge_collections,
                            "previous_messages": previous_messages,
                            "user_context": prepared_ctx,
                            "primary_llm": self.primary_llm,
                            "fast_llm": self.fast_llm,
                        },
                        "recursion_limit": RESEARCH_MAX_ITERATIONS,
                    }
                    stream = agent.stream_response(query=query, config=config)

                else:
                    raise ValueError(f"Unsupported mode: {mode}")

                # 4. Unified streaming loop
                async for event in self._process_agent_stream(
                    stream=stream,
                    chat_id=chat_id,
                    thread_id=thread_id,
                    user_id=user_id,
                    mode=mode,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    start_time=start_time,
                ):
                    yield event

        except Exception as e:
            end_time = datetime.now(timezone.utc)
            logger.error(
                f"Error in execute_query_stream (mode={mode}): {e}", exc_info=True
            )
            yield {
                "type": "error",
                "error": str(e),
                "chat_id": chat_id,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "execution_time": (end_time - start_time).total_seconds(),
                "timestamp": end_time.isoformat(),
            }

    async def _process_agent_stream(
        self,
        stream,
        chat_id: str,
        thread_id: str,
        user_id: str,
        mode: str,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Unified streaming loop for all agent modes.

        Relays events from graph stream, intercepts final_state and review_required
        for message saving and metadata enrichment. All other events pass through.
        """
        answer_buffer = ""

        async for event in stream:
            event["chat_id"] = chat_id
            event["thread_id"] = thread_id
            event_type = event.get("type")

            # Buffer answer tokens (all modes)
            if event_type in ("token", "answer"):
                answer_buffer += event.get("content", "")
                yield event
                continue

            # Pass through thinking, tool_call, tool_result (agent mode)
            if event_type in ("thinking", "tool_call", "tool_result"):
                yield event
                continue

            # Final state — save assistant message + mode-specific post-processing
            if event_type == "final_state":
                answer = event.get("answer") or answer_buffer
                context = self._build_save_context(
                    event, mode, thread_id, agent_id, agent_name
                )
                message_id = await self._save_thread_message(
                    chat_thread_id=chat_id,
                    message_data={
                        "role": "assistant",
                        "content": answer,
                        "context": context,
                    },
                )
                if message_id:
                    event["message_id"] = message_id

                # Update chat thread title
                title = event.get("title")
                if title:
                    await self._update_chat_thread(
                        update_data={"chat_thread_uuid": chat_id, "title": title}
                    )

                # Harmful-query notification (no-op unless triage flagged it)
                await self._send_notification(user_id, event)

                # Execution timing
                end_time = datetime.now(timezone.utc)
                event["start_time"] = start_time.isoformat() if start_time else None
                event["end_time"] = end_time.isoformat()
                if start_time:
                    event["execution_time"] = (end_time - start_time).total_seconds()

                # Mode-specific post-processing
                if mode == "research":
                    token_metrics = self._parse_token_usage(
                        event.get("token_usage", [])
                    )
                    credits_used = self._calculate_credits(token_metrics)
                    event["token_usage"] = token_metrics
                    event["credits_used"] = credits_used
                    if message_id:
                        await self._save_token_usage(
                            message_id, token_metrics, credits_used
                        )
                    logger.info(
                        f"[chat_id={chat_id}] research_token_usage: "
                        f"total_tokens={token_metrics['total_tokens']}, "
                        f"credits={credits_used}"
                    )

                yield event
                continue

            # HITL review pause (agent mode) — save partial answer
            if event_type == "review_required":
                event["graph_thread_id"] = thread_id
                partial_answer = event.get("answer") or answer_buffer
                if partial_answer:
                    await self._save_thread_message(
                        chat_thread_id=chat_id,
                        message_data={
                            "role": "assistant",
                            "content": partial_answer,
                            "context": {
                                "agent_id": agent_id,
                                "agent_name": agent_name,
                                "graph_thread_id": thread_id,
                                "review_pending": True,
                            },
                        },
                    )
                    answer_buffer = ""
                yield event
                continue

            # Pass through: state, event, error, and any other types
            yield event

    # ──────────────────────────────────────────────────────────────────────
    # Agent Setup & Resume
    # ──────────────────────────────────────────────────────────────────────

    async def _setup_live_agent(
        self,
        agent_id: str,
        user_id: str,
        previous_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Set up live agent config: fetch agent data, LLM, tools, and system prompt.

        Returns:
            Dict with agent_data, agent_llm, tools, system_prompt, or None if agent not found.
        """
        agent_repo = AgentRepository(self.db)
        agent_tool_repo = AgentToolRepository(self.db)

        try:
            agent_data_raw = await sync_to_async(agent_repo.get_agent)(UUID(agent_id))
        except (ValueError, TypeError):
            return None

        if not agent_data_raw:
            return None

        agent_data = AgentDetail.model_validate(agent_data_raw)

        # Resolve agent LLM
        if agent_data.agent_llm:
            agent_llm = self.llm_provider.get_llm(llm_key=agent_data.agent_llm)
        else:
            agent_llm = self.llm_provider.get_llm()

        # Configure tools
        tool_runtime_context = {
            "organization_schema": self.org_schema,
            "agent_id": str(agent_data.id),
            "user_id": user_id,
            "llm": agent_llm,
            "db": self.db,
        }

        task_tools = []
        if agent_data.tools:
            tool_generator = ToolsFactory(tool_runtime_context)
            for tool_config in agent_data.tools:
                action = tool_config.action
                if not action:
                    continue
                try:
                    saved_tool = await sync_to_async(agent_tool_repo.get_agent_tool)(
                        action
                    )
                    if saved_tool:
                        tool_data = AgentToolDetail.model_validate(
                            saved_tool
                        ).model_dump()
                        agent_tool = tool_generator.generate(
                            tool_data,
                            review_required=getattr(tool_config, "human_review", False),
                        )
                        if agent_tool:
                            task_tools.append(agent_tool)
                except Exception as e:
                    logger.error(f"Error configuring tool {action}: {e}")
                    continue

        # Build system prompt
        formatted_rules = "\n".join([f"* {rule}" for rule in (agent_data.rules or [])])
        current_date_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Format previous messages for system prompt context
        formatted_history = self._format_message_history(previous_messages or [])

        system_prompt = Template(LIVE_AGENT_SYSTEM_PROMPT).render(
            agent_name=agent_data.name,
            agent_goal=agent_data.goal,
            agent_instruction=agent_data.instructions,
            task_rules=formatted_rules,
            previous_messages=formatted_history,
            current_date_time=current_date_time,
        )

        return {
            "agent_data": agent_data,
            "agent_llm": agent_llm,
            "tools": task_tools,
            "system_prompt": system_prompt,
        }

    async def resume_agent_stream(
        self,
        chat_id: str,
        agent_id: str,
        graph_thread_id: str,
        human_input: Dict[str, Any],
        user_id: str,
    ):
        """Resume a paused live agent execution after human review."""
        agent_setup = await self._setup_live_agent(agent_id, user_id)
        if not agent_setup:
            yield {
                "type": "error",
                "error": f"Agent not found or invalid: {agent_id}",
                "chat_id": chat_id,
            }
            return

        logger.info(
            f"Live agent resume: agent={agent_setup['agent_data'].name}, "
            f"agent_id={agent_id}, chat_id={chat_id}, "
            f"action={human_input.get('action')}"
        )

        resume_start_time = datetime.now(timezone.utc)

        async with get_checkpointer_context(self.org_schema) as checkpointer:
            graph = LiveAgentGraph(
                llm=agent_setup["agent_llm"],
                tools=agent_setup["tools"],
                system_prompt=agent_setup["system_prompt"],
                checkpointer=checkpointer,
                agent_name=agent_setup["agent_data"].name,
            )
            await graph.create_graph()

            async for event in self._process_agent_stream(
                stream=graph.resume_stream(
                    thread_id=graph_thread_id,
                    human_input=human_input,
                ),
                chat_id=chat_id,
                thread_id=graph_thread_id,
                user_id=user_id,
                mode="agent",
                agent_id=agent_id,
                agent_name=agent_setup["agent_data"].name,
                start_time=resume_start_time,
            ):
                yield event

    # ──────────────────────────────────────────────────────────────────────
    # Observe Query Execution (for research mode reconnection)
    # ──────────────────────────────────────────────────────────────────────

    async def observe_query_execution(
        self,
        thread_id: str,
        poll_interval: Optional[float] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Observe research query execution state.

        Provides read-only access to the current state of a research query execution,
        enabling clients to reconnect to in-progress or completed research threads.

        Args:
            thread_id: Thread ID for the research query to observe.
            poll_interval: Optional polling interval in seconds.
                          If None, returns single snapshot.
                          If provided, polls continuously until completion.

        Yields:
            Dict containing ResearchState fields with "type": "state", or error dict.
        """
        async with get_checkpointer_context(self.org_schema) as checkpointer:
            agent = ResearchAgentGraph(
                primary_llm=self.primary_llm,
                fast_llm=self.fast_llm,
                checkpointer=checkpointer,
            )

            try:
                if poll_interval is None:
                    # Single snapshot
                    state = await agent.observe_response(thread_id)

                    if state is None:
                        yield {
                            "type": "error",
                            "error": f"No state found for thread_id {thread_id}",
                        }
                    else:
                        yield self._enrich_observe_output(state)
                else:
                    # Continuous polling
                    async for state_update in agent.observe_output(
                        thread_id=thread_id,
                        poll_interval=poll_interval,
                    ):
                        update_type = state_update.get("type")

                        if update_type in ("state", "final_state"):
                            # Enrich from dict directly — do NOT reconstruct ResearchState
                            # because model_dump() strips the 'type' attr from LangChain messages
                            yield self._enrich_observe_dict(state_update)
                        else:
                            yield state_update

            except Exception as e:
                logger.error(f"Error observing query {thread_id}: {e}", exc_info=True)
                yield {
                    "type": "error",
                    "error": f"Observation failed: {str(e)}",
                    "thread_id": thread_id,
                }

    def _enrich_observe_dict(self, state_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich an already-serialized state dict (from observe_output polling).

        Mirrors _enrich_observe_output but works on a plain dict so we avoid
        reconstructing ResearchState from model_dump() output, which loses
        the LangChain message 'type' attribute and raises a validation error.
        """
        enriched = {k: v for k, v in state_dict.items() if v is not None}

        # Promote chat_id from nested metadata to top level
        metadata = state_dict.get("metadata") or {}
        if isinstance(metadata, dict) and "chat_id" in metadata:
            enriched["chat_id"] = metadata["chat_id"]

        # For final states add aggregated token usage and credits
        if state_dict.get("final_answer"):
            token_usage_list = state_dict.get("token_usage") or []
            token_metrics = self._parse_token_usage(token_usage_list)
            enriched["token_usage"] = token_metrics
            enriched["credits_used"] = self._calculate_credits(token_metrics)

        return enriched

    def _serialize_research_state(self, state: ResearchState) -> Dict[str, Any]:
        """Serialize ResearchState to dict with proper message conversion."""
        state_dict = {"type": "state"}
        state_data = state.model_dump()

        for k, v in state_data.items():
            if v is not None:
                if k == "messages":
                    state_dict[k] = convert_to_openai_messages(state.messages)
                else:
                    state_dict[k] = v

        return state_dict

    def _enrich_observe_output(self, state: ResearchState) -> Dict[str, Any]:
        """Enrich observe output with computed fields to match stream format."""
        serialized = self._serialize_research_state(state)

        # Add chat_id from metadata
        metadata = state.metadata or {}
        if "chat_id" in metadata:
            serialized["chat_id"] = metadata["chat_id"]

        # For final states, add aggregated token usage and credits
        if state.final_answer:
            token_usage_list = state.token_usage or []
            token_metrics = self._parse_token_usage(token_usage_list)
            serialized["token_usage"] = token_metrics
            serialized["credits_used"] = self._calculate_credits(token_metrics)

        return serialized
