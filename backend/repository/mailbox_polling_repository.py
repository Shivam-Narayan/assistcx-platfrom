# Custom libraries
from logger import configure_logging

# Database modules
from models.agent import Agent
from models.mailbox_polling import MailboxPolling

# Default libraries
from typing import Optional, Tuple, Union, Dict, List
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import asc, desc, or_
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session


logger = configure_logging(__name__)


class MailboxPollingRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_mailbox_polling(self, polling_data: dict) -> Optional[MailboxPolling]:
        new_polling = MailboxPolling(**polling_data)

        if (
            new_polling.polling_config.get("notification_recipients")
            and new_polling.email_id
            in new_polling.polling_config["notification_recipients"]
        ):
            raise HTTPException(
                status_code=422,
                detail="The polling email ID cannot be included in the notification recipients.",
            )

        try:
            self.db.add(new_polling)
            self.db.commit()
            self.db.refresh(new_polling)
            return new_polling
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Email polling exists.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_mailbox_polling(
        self, identifier: Union[UUID, str], update_data: dict
    ) -> Optional[MailboxPolling]:
        if isinstance(identifier, UUID):
            query_filter = MailboxPolling.id == identifier
        elif isinstance(identifier, str):
            query_filter = MailboxPolling.task_name == identifier
        else:
            raise ValueError("Identifier must be a UUID or a task name string")

        polling = self.db.query(MailboxPolling).filter(query_filter).first()
        if not polling:
            return None

        notification_recipients = update_data.get("polling_config", {}).get(
            "notification_recipients",
            polling.polling_config.get("notification_recipients", []),
        )
        if polling.email_id in notification_recipients:
            raise HTTPException(
                status_code=400,
                detail="The polling email ID cannot be included in the notification recipients.",
            )

        try:
            for key, value in update_data.items():
                if hasattr(polling, key):
                    setattr(polling, key, value)
            self.db.commit()
            self.db.refresh(polling)
            return polling
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def create_or_update_polling(
        self, identifier: Union[UUID, str], data: dict
    ) -> Optional[MailboxPolling]:
        # Determine the type of identifier and construct the appropriate query filter
        if isinstance(identifier, UUID):
            query_filter = MailboxPolling.id == identifier
        elif isinstance(identifier, str):
            query_filter = MailboxPolling.task_name == identifier
        else:
            raise ValueError("Identifier must be a UUID or a task_name string")

        try:
            existing_polling = (
                self.db.query(MailboxPolling).filter(query_filter).first()
            )
            if existing_polling:
                return self.update_mailbox_polling(identifier, data)
            else:
                return self.create_mailbox_polling(data)
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_mailbox_polling(
        self, identifier: Union[UUID, str]
    ) -> Optional[MailboxPolling]:
        # Determine the type of identifier and construct the appropriate query filter
        if isinstance(identifier, UUID):
            query_filter = MailboxPolling.id == identifier
        elif isinstance(identifier, str):
            query_filter = MailboxPolling.task_name == identifier
        else:
            raise ValueError("Identifier must be a UUID or a task_name string")

        try:
            return self.db.query(MailboxPolling).filter(query_filter).first()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_all_mailbox_pollings(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[MailboxPolling], int]:
        query = self.db.query(MailboxPolling)
        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(MailboxPolling, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(MailboxPolling, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(MailboxPolling, key) == values)

        # Apply sorting
        if hasattr(MailboxPolling, sort_by):
            order = (
                desc(getattr(MailboxPolling, sort_by))
                if sort_order == "desc"
                else getattr(MailboxPolling, sort_by)
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                mailbox_pollings = query.offset(skip).limit(page_size).all()
            else:
                mailbox_pollings = query.all()

            return mailbox_pollings, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def search_mailbox_polling(
        self,
        keyword: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[MailboxPolling], int]:
        """
        Search mailbox pollings based on a keyword with optional sorting.
        """
        query = self.db.query(MailboxPolling)

        keyword = f"%{keyword}%"  # Format keyword for ilike operation

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(MailboxPolling, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(MailboxPolling, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(MailboxPolling, key) == values)

        try:
            query = query.filter(
                or_(
                    MailboxPolling.email_id.ilike(keyword),
                    MailboxPolling.folder.ilike(keyword),
                    MailboxPolling.task_name.ilike(keyword),
                    # Add other fields here if needed
                )
            )

            # Apply sorting
            if hasattr(MailboxPolling, sort_by):
                order = (
                    desc(getattr(MailboxPolling, sort_by))
                    if sort_order == "desc"
                    else getattr(MailboxPolling, sort_by)
                )
                query = query.order_by(order)

            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                mailbox_pollings = query.offset(skip).limit(page_size).all()
            else:
                mailbox_pollings = query.all()

            return mailbox_pollings, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def get_filtered_mailbox_pollings(
        self, email_id: Optional[str] = None, status: Optional[str] = None
    ) -> List[MailboxPolling]:
        try:
            query = self.db.query(MailboxPolling)
            if email_id is not None:
                query = query.filter(MailboxPolling.email_id == email_id)
            if status is not None:
                query = query.filter(MailboxPolling.status == status)
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def delete_mailbox_polling(self, identifier: Union[UUID, str]) -> Optional[bool]:
        """
        Deletes an existing mailbox polling based on its identifier.
        """
        # Determine the type of identifier and construct the appropriate query filter
        query_filter = (
        MailboxPolling.id == identifier
        if isinstance(identifier, UUID)
        else MailboxPolling.task_name == identifier  
    )

        mailbox_polling = self.db.query(MailboxPolling).filter(query_filter).first()
        if not mailbox_polling:
            return False
        
        # Check if any Agent is assigned this mailbox polling
        agent = (
            self.db.query(Agent)
            .filter(Agent.agent_mailbox == mailbox_polling.task_name)  
            .first()
        )
        if agent:
            raise HTTPException(
                status_code=409,
                detail=f"The Mailbox Polling '{mailbox_polling.task_name}' is assigned to agent '{agent.name}'. Please delete or update the associated agent first.",
            )
        try:
            self.db.delete(mailbox_polling)
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return False

    # def paginated_get_all_mailbox_pollings(
    #     self,
    #     page: int = 1,
    #     page_size: int = 10,
    #     filters: Optional[Dict[str, any]] = None,
    #     sort_by: str = "updated_at",
    #     sort_order: str = "desc",
    # ) -> Tuple[List[MailboxPolling], int]:
    #     skip = (page - 1) * page_size
    #     query = self.db.query(MailboxPolling)

    #     # Apply filters
    #     if filters:
    #         for key, values in filters.items():
    #             if hasattr(MailboxPolling, key):
    #                 if isinstance(values, list):
    #                     # Handle multiple values for the same filter key
    #                     condition = or_(
    #                         *(getattr(MailboxPolling, key) == value for value in values)
    #                     )
    #                     query = query.filter(condition)
    #                 else:
    #                     query = query.filter(getattr(MailboxPolling, key) == values)

    #     # Apply sorting
    #     if hasattr(MailboxPolling, sort_by):
    #         order = (
    #             asc(getattr(MailboxPolling, sort_by))
    #             if sort_order == "asc"
    #             else desc(getattr(MailboxPolling, sort_by))
    #         )
    #         query = query.order_by(order)

    #     try:
    #         pollings = query.offset(skip).limit(page_size).all()
    #         total = query.count()
    #         return pollings, total
    #     except SQLAlchemyError as e:
    #         logger.error(f"SQLAlchemy Error: {e}")
    #         return [], 0

    # def paginated_search_mailbox_polling(
    #     self,
    #     keyword: str,
    #     page: int = 1,
    #     page_size: int = 10,
    #     filters: Optional[Dict[str, any]] = None,
    #     sort_by: str = "updated_at",
    #     sort_order: str = "desc",
    # ) -> Tuple[List[MailboxPolling], int]:
    #     skip = (page - 1) * page_size
    #     query = self.db.query(MailboxPolling)

    #     # Apply filters
    #     if filters:
    #         for key, values in filters.items():
    #             if hasattr(MailboxPolling, key):
    #                 if isinstance(values, list):
    #                     # Handle multiple values for the same filter key
    #                     condition = or_(
    #                         *(getattr(MailboxPolling, key) == value for value in values)
    #                     )
    #                     query = query.filter(condition)
    #                 else:
    #                     query = query.filter(getattr(MailboxPolling, key) == values)

    #     # Apply search
    #     if keyword:
    #         query = query.filter(
    #             or_(
    #                 MailboxPolling.email_id.ilike(keyword),
    #                 MailboxPolling.folder.ilike(keyword),
    #                 MailboxPolling.task_name.ilike(keyword),
    #                 # Add other fields here if needed
    #             )
    #         )

    #     # Apply sorting
    #     if hasattr(MailboxPolling, sort_by):
    #         order = (
    #             asc(getattr(MailboxPolling, sort_by))
    #             if sort_order == "asc"
    #             else desc(getattr(MailboxPolling, sort_by))
    #         )
    #         query = query.order_by(order)

    #     try:
    #         mailbox_pollings = query.offset(skip).limit(page_size).all()
    #         total = query.count()
    #         return mailbox_pollings, total
    #     except SQLAlchemyError as e:
    #         logger.error(f"SQLAlchemy Error: {e}")
    #         return [], 0
