# Custom libraries
from logger import configure_logging

# Database modules
from repository.agent_task_repository import AgentTaskRepository
from repository.email_repository import EmailRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional

# Installed libraries
from uuid import UUID


logger = configure_logging(__name__)


class CreditManager:
    def __init__(self, db: Session):
        self.db = db
        self.agent_task_repository = AgentTaskRepository(db)
        self.email_repository = EmailRepository(db)

    async def _get_email_credits(self, email_id: UUID) -> Optional[int]:
        try:
            email = self.email_repository.get_email_by_id(email_id)
            if not email:
                logger.error(f"Email not found: {email_id}")
                return None

            return email.credits_used if email.credits_used else 0

        except Exception as e:
            logger.error(f"Unexpected error occurred: {e}")
            return None

    async def _get_agent_task_credits(self, agent_task_id: str) -> Optional[int]:
        try:
            agent_task = self.agent_task_repository.get_task_by_id(agent_task_id)
            if not agent_task:
                logger.error(f"Agent Task not found: {agent_task_id}")
                return None

            return agent_task.credits_used if agent_task.credits_used else 0

        except Exception as e:
            logger.error(f"Unexpected error occurred: {e}")
            return None

    async def add_email_credits(self, email_id: UUID, credits: Optional[int] = None):
        try:
            credits_used = await self._get_email_credits(email_id)
            if credits_used is None:
                return None  # Email not found

            credits_used += credits or 1  # Default to 1 if credits is None

            updated_email = self.email_repository.update_email(
                email_id, {"credits_used": credits_used}
            )
            if not updated_email:
                logger.error(f"Failed to update credits for email: {email_id}")
                return None

            logger.info(f"Successfully updated credits for email: {email_id}")
            return updated_email

        except Exception as e:
            logger.error(f"Unexpected error occurred: {e}")
            return None

    async def add_agent_task_credits(
        self, agent_task_id: str, credits: Optional[int] = None
    ):
        try:
            credits_used = await self._get_agent_task_credits(agent_task_id)
            if credits_used is None:
                return None  # Agent task not found

            credits_used += credits or 1  # Default to 1 if credits is None

            updated_agent_task = self.agent_task_repository.update_task(
                agent_task_id, {"credits_used": credits_used}
            )
            if not updated_agent_task:
                logger.error(
                    f"Failed to update credits for agent task: {agent_task_id}"
                )
                return None

            await self.add_email_credits(updated_agent_task.email_data_id, credits)

            logger.info(f"Successfully updated credits for agent task: {agent_task_id}")
            return updated_agent_task

        except Exception as e:
            logger.error(f"Unexpected error occurred: {e}")
            return None
