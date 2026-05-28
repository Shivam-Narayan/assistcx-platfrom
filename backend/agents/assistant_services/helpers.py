"""Helper base class for AssistantQueryService — data access, context prep, and utilities."""

# Custom libraries
from agents.shared_utils import LLMProvider
from logger import configure_logging
from utils.common_utils import generate_short_id

# Database modules
from repository.chat_thread_repository import ChatThreadRepository
from repository.data_collection_repository import DataCollectionRepository
from sqlalchemy.orm import Session

# Default libraries
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4
import math
import time

# Installed libraries
from asgiref.sync import sync_to_async


logger = configure_logging(__name__)


class AssistantServiceHelper:
    """Base helper with data-access, context-preparation, and token utilities.

    Inherited by AssistantQueryService so the service file only contains
    execution logic (graph orchestration, streaming, etc.).
    """

    def __init__(
        self,
        db: Session,
        org_schema: str = "public",
        user_id: Optional[str] = None,
    ):
        """Initialize repositories, LLMs, and shared state."""
        self.db = db
        self.org_schema = org_schema
        self.user_id = user_id

        # Repositories
        self.collection_repo = DataCollectionRepository(self.db)
        self.chat_thread_repo = ChatThreadRepository(self.db)

        # LLM setup
        self.llm_provider = LLMProvider(self.org_schema, self.db)
        self.primary_llm = self.llm_provider.get_llm(llm_type="primary")
        self.fast_llm = self.llm_provider.get_llm(llm_type="fast")

    # ──────────────────────────────────────────────────────────────────────
    # Collection helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _format_collection(collection) -> Dict[str, Any]:
        """Format a DataCollection ORM object into a serializable dict."""
        return {
            "id": str(collection.id),
            "name": collection.name,
            "index_name": collection.index_name,
            "description": collection.description,
            "document_count": getattr(collection, "file_count", 0),
            "metadata_fields": collection.smart_fields,
            "knowledge_topics": collection.knowledge_topics,
        }

    async def _get_knowledge_collections(
        self, user_id: str, collections: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """Get knowledge collections a user has access to or fetch specific collections by ID."""
        logger.info(f"Fetching knowledge collections for user {user_id}")

        try:
            # Fetch specific collections by ID if provided
            if collections:
                logger.info(f"Fetching {len(collections)} specific collections by ID")
                collection_results = []

                for collection_dict in collections:
                    collection_id = collection_dict.get("id")
                    if not collection_id:
                        continue

                    try:
                        collection = await sync_to_async(
                            self.collection_repo.get_data_collection_by_id
                        )(identifier=collection_id)

                        if collection and collection.availability == "PUBLISHED":
                            collection_results.append(self._format_collection(collection))
                        else:
                            logger.warning(
                                f"Collection with ID {collection_id} not found"
                            )
                    except Exception as e:
                        logger.error(f"Error fetching collection {collection_id}: {e}")

                return collection_results

            # Default behavior: fetch all collections for user
            user_collections = await sync_to_async(
                self.collection_repo.get_collections_by_user
            )(user_id=user_id)

            if not user_collections:
                logger.warning(f"No collections found for user {user_id}")
                return []

            filtered_collections = [
                self._format_collection(collection)
                for collection in user_collections
                if collection.availability in ["PUBLISHED", "PRIVATE"]
            ]
            return filtered_collections

        except Exception as e:
            logger.error(f"Error fetching knowledge collections: {e}", exc_info=True)
            return []

    async def _get_user_private_collection(self, user_id: str) -> List[Dict[str, Any]]:
        """Get the user's private collection for file-based search."""
        logger.debug(f"Getting private collection for user {user_id}")

        try:
            private_collection = await sync_to_async(
                self.collection_repo.get_private_data_collection_by_owner_id
            )(user_id=user_id)

            if private_collection:
                logger.debug(
                    f"Found private collection: {private_collection.name} (index: {private_collection.index_name})"
                )
                return [self._format_collection(private_collection)]
            else:
                logger.warning(f"No private collection found for user {user_id}")
                return []

        except Exception as e:
            logger.error(
                f"Error getting private collection for user {user_id}: {e}",
                exc_info=True,
            )
            return []

    # ──────────────────────────────────────────────────────────────────────
    # Chat thread helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _update_chat_thread(self, update_data: Dict[str, Any]) -> Optional[str]:
        """Update chat thread."""
        logger.info(f"Updating chat thread")
        try:
            chat_thread = await sync_to_async(self.chat_thread_repo.update_chat_thread)(
                update_data
            )
            return chat_thread
        except Exception as e:
            logger.error(f"Error creating chat thread: {e}", exc_info=True)
            return None

    async def _create_thread_id(self, chat_id: str) -> str:
        """Create a thread ID with microsecond precision."""
        logger.info(f"Creating thread ID for chat {chat_id}")
        try:
            graph_thread_id = f"thread-{chat_id}-{int(time.time() * 1000000)}"
            return graph_thread_id
        except Exception as e:
            logger.error(f"Error creating thread ID: {e}", exc_info=True)
            raise ValueError(f"Error creating thread ID: {str(e)}")

    async def _create_chat_thread(
        self, user_id: str, chat_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new chat thread with microsecond precision."""
        logger.info(f"Creating new chat thread for user {user_id}")
        try:
            chat_id = chat_id or str(uuid4())
            graph_thread_id = await self._create_thread_id(chat_id)
            thread_data = {
                "id": chat_id,
                "external_id": graph_thread_id,
                "user_id": user_id,
                "chat_type": "chat",
            }
            chat_thread = await sync_to_async(self.chat_thread_repo.create_chat_thread)(
                thread_data
            )
            if not chat_thread:
                raise ValueError("Failed to create chat thread")
            return {
                "chat_id": str(chat_thread.id),
                "thread_id": chat_thread.external_id,
                "user_id": user_id,
            }
        except Exception as e:
            logger.error(f"Error creating chat thread: {e}", exc_info=True)
            raise ValueError(f"Error creating chat thread: {str(e)}")

    async def _fetch_chat_thread(self, chat_id: UUID) -> Optional[Any]:
        """Helper to fetch a chat thread by ID asynchronously."""
        try:
            return await sync_to_async(self.chat_thread_repo.get_chat_thread_by_id)(
                chat_id
            )
        except Exception as e:
            logger.error(f"Error fetching chat thread {chat_id}: {e}", exc_info=True)
            return None

    async def _validate_chat_thread(
        self, user_id: str, chat_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get or create a chat thread for a given user_id and optional chat_id."""
        logger.debug(
            f"Validating chat thread {chat_id if chat_id else 'new'} for user {user_id}"
        )

        try:
            if not chat_id:
                return await self._create_chat_thread(
                    user_id=user_id,
                    chat_id=str(uuid4()),
                )

            # Validate UUID format
            try:
                uuid_obj = UUID(chat_id)
            except ValueError:
                logger.warning(f"Invalid chat ID format: {chat_id}. Generating new ID.")
                return await self._create_chat_thread(
                    user_id=user_id,
                    chat_id=str(uuid4()),
                )

            # Fetch existing thread
            chat_thread = await self._fetch_chat_thread(uuid_obj)

            if not chat_thread:
                logger.info(
                    f"No chat thread found for ID {chat_id}. Creating new thread with given ID."
                )
                return await self._create_chat_thread(
                    user_id=user_id,
                    chat_id=chat_id,
                )

            return {
                "chat_id": str(chat_thread.id),
                "thread_id": await self._create_thread_id(chat_thread.id),
                "user_id": user_id,
            }

        except Exception as e:
            logger.error(f"Failed to validate chat thread: {e}", exc_info=True)
            raise ValueError(f"Error processing chat thread: {str(e)}")

    @staticmethod
    def _format_message_history(messages: List[Dict[str, Any]]) -> Optional[str]:
        """Format message history for LLM prompt consumption.

        Args:
            messages: List of message dictionaries with role, content, and timestamp

        Returns:
            Formatted string ready for LLM prompt inclusion
        """
        if not messages:
            return None

        formatted_messages = []

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            timestamp = message.get("timestamp", "")

            role_display = "**User:**" if role == "user" else "**Assistant:**"
            header_line = f"{role_display} [{timestamp}]"

            message_block = [header_line]
            if content:
                message_block.append(content)

            formatted_messages.append("\n".join(message_block))

        return "\n\n".join(formatted_messages)

    async def _get_thread_messages(
        self, chat_thread_id: str, limit: int = None, truncate: bool = True
    ) -> List[Dict[str, Any]]:
        """Get conversation history for a thread.

        Args:
            chat_thread_id: Chat thread UUID.
            limit: Max messages to return (most recent N).
            truncate: If True, truncate content to 500 chars (default for RAG/Research).
                      Set False for agent mode which needs full message content.
        """
        logger.debug(f"Fetching thread history for thread {chat_thread_id}")
        try:
            kwargs = {}
            if limit is not None:
                kwargs["page"] = 1
                kwargs["page_size"] = limit
                kwargs["sort_order"] = "desc"  # newest first

            thread_messages = await sync_to_async(
                self.chat_thread_repo.get_thread_messages
            )(chat_thread_id, **kwargs)

            if not thread_messages:
                return []

            # Reverse to chronological order (oldest → newest)
            if limit is not None:
                thread_messages = list(reversed(thread_messages))

            return [
                {
                    "role": message.role,
                    "content": message.content[:500] if truncate else message.content,
                    "timestamp": message.created_at.strftime("%b %-d, %Y %-I:%M %p UTC"),
                }
                for message in thread_messages
            ]
        except Exception as e:
            logger.error(f"Error fetching thread history: {e}", exc_info=True)
            return []

    async def _save_thread_message(
        self, chat_thread_id: str, message_data: Dict[str, Any]
    ) -> Optional[str]:
        """Store a message in the thread."""
        try:
            logger.info(f"Saving message to thread {chat_thread_id}")
            message_data["chat_history_id"] = chat_thread_id
            saved_message = await sync_to_async(
                self.chat_thread_repo.create_thread_message
            )(message_data)
            return saved_message.id if saved_message else None
        except Exception as e:
            logger.error(f"Error saving thread message: {e}", exc_info=True)
            return None

    # ──────────────────────────────────────────────────────────────────────
    # Context preparation
    # ──────────────────────────────────────────────────────────────────────

    async def _prepare_user_context(
        self,
        user_id: str,
        chat_thread_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        user_context: Dict[str, Any] = None,
        web_search_enabled: bool = True,
        attachments: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Prepare context for Assistant execution."""
        context = user_context or {}

        context["user_id"] = user_id
        context["chat_id"] = chat_thread_id
        context["thread_id"] = thread_id
        context["org_id"] = self.org_schema
        context["web_search_enabled"] = web_search_enabled

        if attachments:
            context["file_ids"] = [a["id"] for a in attachments]
            context["attachments"] = attachments
        else:
            logger.debug("Assistant Service prepare_user_context: No attachments provided")
        return context

    async def _prepare_execution_context(
        self,
        user_id: str,
        chat_id: str,
        thread_id: str,
        collections: Optional[List[Dict[str, Any]]],
        attachments: Optional[List[Dict[str, str]]],
        user_context: Optional[Dict[str, Any]],
        web_search_enabled: bool,
    ) -> Tuple[List[Dict[str, Any]], Optional[str], Dict[str, Any]]:
        """Resolve collections, fetch messages, and prepare user context.

        Returns:
            (knowledge_collections, formatted_previous_messages, prepared_user_context)
        """
        # Resolve knowledge collections
        if collections is None:
            if attachments:
                knowledge_collections = await self._get_user_private_collection(
                    user_id=user_id
                )
            else:
                knowledge_collections = []
        else:
            knowledge_collections = await self._get_knowledge_collections(
                user_id=user_id, collections=collections if collections else None
            )

        raw_messages = (
            await self._get_thread_messages(chat_id, limit=5) if chat_id else None
        )
        # Exclude the last user message (current query) from previous messages
        if raw_messages and raw_messages[-1].get("role") == "user":
            raw_messages = raw_messages[:-1]
        previous_messages = self._format_message_history(raw_messages or [])

        prepared_user_context = await self._prepare_user_context(
            user_id=user_id,
            chat_thread_id=chat_id,
            thread_id=thread_id,
            user_context=user_context,
            web_search_enabled=web_search_enabled,
            attachments=attachments,
        )

        return knowledge_collections, previous_messages, prepared_user_context

    # ──────────────────────────────────────────────────────────────────────
    # Notification
    # ──────────────────────────────────────────────────────────────────────

    async def _send_notification(
        self, user_id: str, final_state: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Send notification for harmful queries detected by triage."""
        try:
            # Check if this is a harmful query from triage context
            context = final_state.get("context", {})
            triage_classification = context.get("triage_classification")

            # Only process harmful queries
            if triage_classification != "harmful_query":
                return None

            # Extract relevant information from graph state
            notification_data = {
                "user_id": user_id,
                "query": final_state.get("question", ""),
                "answer": final_state.get("answer", ""),
                "thread_id": final_state.get("thread_id"),
                "chat_id": final_state.get("chat_id"),
                "triage_classification": triage_classification,
                "triage_confidence": context.get("triage_confidence", 0.0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Log the harmful query attempt
            logger.warning(
                f"Harmful query detected for user {user_id} in org {self.org_schema}. "
                f"Classification: {triage_classification}, "
                f"Confidence: {context.get('triage_confidence', 0.0):.2f}, "
                f"Query: {final_state.get('question', '')[:100]}..."
            )

            return notification_data

        except Exception as e:
            logger.error(
                f"Error sending harmful query notification: {e}", exc_info=True
            )
            return None

    # ──────────────────────────────────────────────────────────────────────
    # Save context builder
    # ──────────────────────────────────────────────────────────────────────

    def _build_save_context(
        self,
        event: Dict[str, Any],
        mode: str,
        thread_id: str,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build context dict for saving assistant message, varies by mode."""
        if mode == "research":
            return {"graph_thread_id": thread_id}
        else:  # agent
            return {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "graph_thread_id": thread_id,
            }

    # ──────────────────────────────────────────────────────────────────────
    # Token usage & credits
    # ──────────────────────────────────────────────────────────────────────

    def _parse_token_usage(
        self, token_usage_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Aggregate token usage records into metrics."""
        if not token_usage_list:
            return {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "llm_calls_count": 0,
                "token_details": [],
            }
        try:
            return {
                "total_input_tokens": sum(
                    r.get("input_tokens", 0) for r in token_usage_list
                ),
                "total_output_tokens": sum(
                    r.get("output_tokens", 0) for r in token_usage_list
                ),
                "total_tokens": sum(r.get("total_tokens", 0) for r in token_usage_list),
                "llm_calls_count": len(token_usage_list),
                "token_details": token_usage_list,
            }
        except Exception as e:
            logger.error(f"Error parsing token usage: {e}", exc_info=True)
            return {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "llm_calls_count": 0,
                "token_details": [],
            }

    def _calculate_credits(self, token_metrics: Dict[str, Any]) -> int:
        """Calculate credits: 1 credit per 10k tokens, ceil."""
        token_details = token_metrics.get("token_details", [])
        if not token_details:
            return 0

        combined_tokens = {}
        for step in token_details:
            key = step.get("tool_call_id") or step.get("node", "unknown")
            step_total = step.get("total_tokens", 0)
            if step_total > 0:
                combined_tokens[key] = combined_tokens.get(key, 0) + step_total

        return sum(math.ceil(t / 10000) for t in combined_tokens.values())

    async def _save_token_usage(
        self, message_id, token_metrics: Dict[str, Any], credits_used: int
    ) -> None:
        """Persist token usage and credits to the chat message."""
        try:
            await sync_to_async(self.chat_thread_repo.update_message_token_usage)(
                message_id=message_id,
                token_usage=token_metrics,
                credits_used=credits_used,
            )
            logger.info(
                f"Saved token usage for message {message_id}: "
                f"total_tokens={token_metrics.get('total_tokens', 0)}, "
                f"credits={credits_used}"
            )
        except Exception as e:
            logger.error(f"Error saving token usage: {e}", exc_info=True)

    # ──────────────────────────────────────────────────────────────────────
    # Health
    # ──────────────────────────────────────────────────────────────────────

    async def health_check(self) -> Dict[str, Any]:
        """Health check for the service."""
        try:
            return {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "database": "connected" if self.db else "disconnected",
                "org_schema": self.org_schema,
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
