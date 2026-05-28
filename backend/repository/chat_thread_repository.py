# Custom libraries
from logger import configure_logging

# Database modules
from models.chat_message import ChatMessage
from models.chat_thread import ChatHistory

# Default libraries
from typing import Optional, Dict, List, Union
from uuid import UUID

# Installed libraries
from sqlalchemy import asc, desc, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


logger = configure_logging(__name__)


class ChatThreadRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_chat_thread(self, chat_thread_data: dict) -> ChatHistory:
        new_chat_thread = ChatHistory(**chat_thread_data)
        try:
            self.db.add(new_chat_thread)
            self.db.commit()
            self.db.refresh(new_chat_thread)
            return new_chat_thread
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return None

    def update_chat_thread(self, update_data: dict) -> Optional[ChatHistory]:
        chat_thread_uuid = update_data.get("chat_thread_uuid")
        chat_thread = (
            self.db.query(ChatHistory).filter(ChatHistory.id == chat_thread_uuid).first()
        )
        if not chat_thread:
            return None
        try:
            for key, value in update_data.items():
                if hasattr(chat_thread, key):
                    setattr(chat_thread, key, value)
            self.db.commit()
            self.db.refresh(chat_thread)
            return chat_thread
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def create_thread_message(self, chat_message_data: dict) -> ChatMessage:
        new_chat_message = ChatMessage(**chat_message_data)
        try:
            self.db.add(new_chat_message)
            self.db.commit()
            self.db.refresh(new_chat_message)
            return new_chat_message
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return None

    def update_chat_message(self, update_data: dict) -> Optional[ChatMessage]:
        chat_message_uuid = update_data.get("chat_message_uuid")
        chat_message = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.id == chat_message_uuid)
            .first()
        )
        if not chat_message:
            return None
        try:
            for key, value in update_data.items():
                if hasattr(chat_message, key):
                    setattr(chat_message, key, value)
            self.db.commit()
            self.db.refresh(chat_message)
            return chat_message
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_message_token_usage(
        self,
        message_id: UUID,
        token_usage: dict,
        credits_used: int,
    ) -> Optional[ChatMessage]:
        """
        Updates a ChatMessage with token usage and credits.

        - Overwrites: token_usage (full metrics dict)
        - Accumulates: credits_used

        Args:
            message_id: Chat message UUID
            token_usage: Token usage metrics dict
            credits_used: Credits to add to existing credits_used

        Returns:
            Updated ChatMessage or None if not found/error
        """
        try:
            chat_message = (
                self.db.query(ChatMessage)
                .filter(ChatMessage.id == message_id)
                .first()
            )

            if not chat_message:
                logger.warning(f"No chat message found for id: {message_id}")
                return None

            # Accumulate credits
            existing_credits = chat_message.credits_used or 0
            accumulated_credits = existing_credits + credits_used

            # Update fields
            chat_message.token_usage = token_usage
            chat_message.credits_used = accumulated_credits

            self.db.commit()
            self.db.refresh(chat_message)

            logger.info(
                f"Updated token usage for message_id={message_id}: "
                f"credits={existing_credits}+{credits_used}={accumulated_credits}"
            )
            return chat_message

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error in update_message_token_usage: {e}")
            return None

    def get_chat_thread_by_id(self, identifier: UUID) -> Optional[ChatHistory]:
        try:
            chat_thread = (
                self.db.query(ChatHistory).filter(ChatHistory.id == identifier).first()
            )
            if chat_thread:
                thread_messages = self.get_thread_messages(chat_thread.id)
                chat_thread.chat_messages = thread_messages
            return chat_thread
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_chat_threads_by_user_id(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 10,
        filters: Optional[Dict[str, any]] = None,
        sort_by: Optional[str] = "updated_at",
        sort_order: Optional[str] = "desc",
    ) -> List[ChatHistory]:
        skip = (page - 1) * page_size
        query = self.db.query(ChatHistory)

        # Filter by user ID
        query = query.filter(ChatHistory.user_id == user_id)

        # Exclude archived threads by default unless explicitly asked
        if not filters or "is_archived" not in filters:
            query = query.filter(ChatHistory.is_archived == False)

        # Apply filters
        chat_type_filter_applied = False
        if filters:
            for key, values in filters.items():
                if key == "chat_type":
                    chat_type_filter_applied = True
                    if isinstance(values, list):
                        condition = or_(
                            *(ChatHistory.chat_type == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(ChatHistory.chat_type == values)
                elif hasattr(ChatHistory, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(ChatHistory, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(ChatHistory, key) == values)

        # If no chat_type filter was applied, default to excluding task threads
        if not chat_type_filter_applied:
            query = query.filter(
                or_(
                    ChatHistory.chat_type != "task",
                    ChatHistory.chat_type.is_(None),
                )
            )
        else:
            query = query.filter(ChatHistory.parent_id == ChatHistory.id)

        # Apply sorting
        if hasattr(ChatHistory, sort_by):
            order = (
                asc(getattr(ChatHistory, sort_by))
                if sort_order == "asc"
                else desc(getattr(ChatHistory, sort_by))
            )
            query = query.order_by(order)

        try:
            return query.offset(skip).limit(page_size).all()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def search_chat_threads_by_user_id(
        self,
        user_id: UUID,
        keyword: str,
        page: int = 1,
        page_size: int = 10,
        filters: Optional[Dict[str, any]] = None,
        sort_by: Optional[str] = "updated_at",
        sort_order: Optional[str] = "desc",
    ) -> List[ChatHistory]:
        skip = (page - 1) * page_size
        query = self.db.query(ChatHistory)

        # Filter by user ID
        query = query.filter(ChatHistory.user_id == user_id)

        # Exclude archived threads by default unless explicitly asked
        if not filters or "is_archived" not in filters:
            query = query.filter(ChatHistory.is_archived == False)

        # Apply filters
        chat_type_filter_applied = False
        if filters:
            for key, values in filters.items():
                if key == "chat_type":
                    chat_type_filter_applied = True
                    if isinstance(values, list):
                        condition = or_(
                            *(ChatHistory.chat_type == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(ChatHistory.chat_type == values)
                elif hasattr(ChatHistory, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(ChatHistory, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(ChatHistory, key) == values)

        # If no chat_type filter was applied, default to excluding task threads
        if not chat_type_filter_applied:
            query = query.filter(
                or_(
                    ChatHistory.chat_type != "task",
                    ChatHistory.chat_type.is_(None),
                )
            )
        else:
            query = query.filter(ChatHistory.parent_id == ChatHistory.id)

        # Apply search
        if keyword:
            query = query.filter(
                or_(
                    ChatHistory.title.ilike(f"%{keyword}%"),
                )
            )

        # Apply sorting
        if hasattr(ChatHistory, sort_by):
            order = (
                asc(getattr(ChatHistory, sort_by))
                if sort_order == "asc"
                else desc(getattr(ChatHistory, sort_by))
            )
            query = query.order_by(order)

        try:
            return query.offset(skip).limit(page_size).all()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_thread_messages(
        self,
        thread_id: Union[UUID, str],
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: Optional[str] = "updated_at",
        sort_order: Optional[str] = "desc",
    ) -> List[ChatMessage]:
        query = self.db.query(ChatMessage)

        # Filter by thread_id
        query = query.filter(
            ChatMessage.chat_history_id
            == (UUID(thread_id) if isinstance(thread_id, str) else thread_id)
        )

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(ChatMessage, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(ChatMessage, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(ChatMessage, key) == values)

        # Apply sorting
        if hasattr(ChatMessage, sort_by):
            order = (
                asc(getattr(ChatMessage, sort_by))
                if sort_order == "asc"
                else desc(getattr(ChatMessage, sort_by))
            )
            query = query.order_by(order)

        try:
            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                chat_messages = query.offset(skip).limit(page_size).all()
            else:
                chat_messages = query.all()
            return chat_messages
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def delete_chat_thread(self, chat_thread_uuid: UUID) -> bool:
        chat_thread = (
            self.db.query(ChatHistory).filter(ChatHistory.id == chat_thread_uuid).first()
        )
        if not chat_thread:
            return False
        try:
            self.db.query(ChatMessage).filter(
                ChatMessage.chat_history_id == chat_thread.id
            ).delete()
            self.db.delete(chat_thread)
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return False

    def get_child_threads_by_parent_id(
        self,
        parent_id: UUID,
        page: Optional[int] = 1,
        page_size: Optional[int] = 10,
        filters: Optional[Dict[str, any]] = None,
        sort_by: Optional[str] = "updated_at",
        sort_order: Optional[str] = "desc",
    ) -> List[ChatHistory]:
        """Get all child threads for a given parent thread ID."""
        skip = (page - 1) * page_size
        query = self.db.query(ChatHistory)

        # Filter by thread type and parent ID
        query = (
            query.filter(ChatHistory.chat_type == "task")
            .filter(ChatHistory.parent_id == parent_id)
            .filter(ChatHistory.id != parent_id)
        )

        # Exclude archived threads by default unless explicitly asked
        if not filters or "is_archived" not in filters:
            query = query.filter(ChatHistory.is_archived == False)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(ChatHistory, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(ChatHistory, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(ChatHistory, key) == values)

        # Apply sorting
        if hasattr(ChatHistory, sort_by):
            order = (
                asc(getattr(ChatHistory, sort_by))
                if sort_order == "asc"
                else desc(getattr(ChatHistory, sort_by))
            )
            query = query.order_by(order)

        try:
            return query.offset(skip).limit(page_size).all()

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []
