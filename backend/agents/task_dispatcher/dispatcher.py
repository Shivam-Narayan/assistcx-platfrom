# Default libraries
from typing import List, Dict, Optional, Union
from typing_extensions import deprecated
import textwrap

# Installed libraries
from uuid import UUID
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage

# Custom libraries
# from agents.task_dispatcher.prompts import INTENT_CLASSIFICATION_PROMPT  # intent classification disabled
# from agents.task_dispatcher.schemas import IntentClassificationResponse
from agents.task_dispatcher.prompts import AGENT_SELECTION_PROMPT
from agents.task_dispatcher.schemas import AgentSelectionResponse
from agents.task_dispatcher.task_factory import TaskFactory
from agents.shared_utils.llm_provider import LLMProvider
from jinja2 import Template
from logger import configure_logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

# from repository.intent_repository import IntentRepository  # intent_repository.py commented out
from repository.email_repository import EmailRepository
from repository.attachment_repository import AttachmentRepository
from repository.agent_repository import AgentRepository
from schemas.email_schema import EmailDetail
from schemas.attachment_schema import AttachmentDetail
from schemas.agent_schema import AgentDetail
from utils.credits import CreditManager
import asyncio


load_dotenv()
logger = configure_logging(__name__)


class TaskDispatcher:
    def __init__(self, db: Session, organization_schema: str):
        self.db = db
        self.organization_schema = organization_schema
        self.agent_llm = LLMProvider(organization_schema, self.db)
        self.agent_repo = AgentRepository(self.db)
        self.attachment_repo = AttachmentRepository(self.db)
        self.email_repo = EmailRepository(self.db)
        # self.intent_repo = IntentRepository(self.db)

    # @deprecated("Use _get_agents instead")
    # def _get_intents(self) -> Optional[dict]:
    #     """
    #     Get structured intents data from the database
    #     """
    #     # try:
    #     #     intents, total = self.intent_repo.get_all_intents()
    #     #
    #     #     transformed_intents = []
    #     #     for intent in intents:
    #     #         transformed_intent = {
    #     #             "intent_class": intent.intent_class,
    #     #             "description": intent.description,
    #     #         }
    #     #         transformed_intents.append(transformed_intent)
    #     #
    #     #     return transformed_intents
    #     #
    #     # except SQLAlchemyError as e:
    #     #     logger.error(f"SQLAlchemy error: {e}")
    #     return None

    def _get_agents(self) -> Optional[list]:
        """
        Get active agents with their name and description for LLM-based selection.
        """
        try:
            agents, total = self.agent_repo.get_agents_by_assignment("ai_assignment")
            if not agents:
                return None

            return [
                {
                    "name": agent.name,
                    "description": agent.description,
                }
                for agent in agents
            ]
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy error: {e}")
            return None

    def _get_agent(self, agent_id: UUID) -> Optional[AgentDetail]:
        """
        Get agent data from DB using agent ID
        """
        try:
            agent_data = self.agent_repo.get_agent(agent_id)
            if not agent_data:
                return None

            # Validate and serialize using Pydantic schema
            return AgentDetail.model_validate(agent_data)

        except Exception as e:
            logger.error(f"Error in fetching agent: {e}")
            return None

    def _get_email(self, email_uuid: str) -> Optional[EmailDetail]:
        """
        Get structured email and attachment data from DB using email uuid.
        """
        try:
            # Get email data from the table using email uuid
            email_data = self.email_repo.get_email_by_id(email_uuid)
            if not email_data:
                return None

            # Validate and serialize using Pydantic schema
            return EmailDetail.model_validate(email_data)

        except ValueError as e:
            logger.error(f"Value Error: {e}")
            return None
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def _get_attachment(self, email_uuid: str) -> Optional[AttachmentDetail]:
        """
        Get structured email and attachment data from DB using email uuid.
        Select the attachment entry where the first item of content is the largest.
        """
        try:
            # Query to find the longest attachment for the given email_uuid
            attachment_data = self.attachment_repo.get_single_attachment(email_uuid)

            if attachment_data:
                return AttachmentDetail.model_validate(attachment_data)
            return None

        except ValueError as e:
            logger.error(f"Value Error: {e}")
            return None
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def _update_task(self, email_uuid: str, agent_id: str) -> Optional[EmailDetail]:
        """
        Assign agent_id to the email data in the database.
        """
        try:
            update_data = {"agent_id": agent_id}
            updated_email = self.email_repo.update_email(email_uuid, update_data)
            if not updated_email:
                logger.error(f"Failed to update email for UUID: {email_uuid}")
                return None

            # Serialize using Pydantic schema if necessary
            return EmailDetail.model_validate(updated_email)

        except ValueError as e:
            logger.error(f"Value Error: {e}")
            return None
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    # @deprecated("Intent classification disabled")
    # def classify_intent(
    #     self,
    #     intents: list,
    #     email_uuid: UUID,
    #     subject: str,
    #     email_body: str,
    #     attachment: Optional[str] = None,
    # ) -> str:
    #     """
    #     Classify the intent based on the given email and attachment data using LLM.
    #     Returns empty string if no intent is found or if LLM call fails.
    #     """
    #     # try:
    #     #     system_prompt = Template(INTENT_CLASSIFICATION_PROMPT).render(
    #     #         intents=intents
    #     #     )
    #     #
    #     #     input_data = f"""<query>\nSubject: {subject}\n\nEmail Body:\n{email_body}\n</query>\n\n<attachment>\n{attachment}\n</attachment>"""
    #     #
    #     #     llm = self.agent_llm.get_llm().with_structured_output(
    #     #         IntentClassificationResponse
    #     #     )
    #     #
    #     #     result = llm.invoke(
    #     #         [
    #     #             SystemMessage(content=system_prompt),
    #     #             HumanMessage(content=input_data),
    #     #         ],
    #     #     )
    #     #     logger.debug(f"Intent classification output is: {result.intent_class}")
    #     #
    #     #     credits = CreditManager(self.db)
    #     #     asyncio.run(credits.add_email_credits(email_uuid, 1))
    #     #
    #     #     return result.intent_class if result.intent_class else ""
    #     #
    #     # except Exception as e:
    #     #     logger.error(f"Failed to classify intent: {e}")
    #     return ""

    def select_agent(
        self,
        agents: list,
        email_uuid: UUID,
        subject: str,
        email_body: str,
        attachment: Optional[str] = None,
    ) -> str:
        """
        Select the best agent for the email based on agent name and description using LLM.
        Returns the agent name string, or empty string if no match / LLM failure.
        """
        try:
            system_prompt = Template(AGENT_SELECTION_PROMPT).render(agents=agents)

            input_data = (
                f"<query>\nSubject: {subject}\n\nEmail Body:\n{email_body}\n</query>"
                f"\n\n<attachment>\n{attachment}\n</attachment>"
            )

            llm = self.agent_llm.get_llm().with_structured_output(
                AgentSelectionResponse
            )

            result = llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=input_data),
                ],
            )
            logger.debug(f"Agent selection output is: {result.agent_name}")

            credits = CreditManager(self.db)
            asyncio.run(credits.add_email_credits(email_uuid, 1))

            return result.agent_name if result.agent_name else ""

        except Exception as e:
            logger.error(f"Failed to select agent: {e}")
            return ""

    def assign_by_mailbox(self, email_data) -> Optional[Dict[str, str]]:
        """Assign agent to the task as per the mailbox if mailbox is assigned to a single agent"""
        try:
            mailbox = f"{email_data.mailbox_email}|{email_data.mailbox_folder}".lower()
            mailbox_agents = self.agent_repo.get_mailbox_agent(mailbox)

            if mailbox_agents and len(mailbox_agents) == 1:
                agent = mailbox_agents[0]
                return {"agent_id": str(agent.id)}
            else:
                return None
        except Exception as e:
            logger.error(f"Failed to assign agent by mailbox: {e}")
            return None

    # @deprecated("Intent-based assignment disabled; use assign_by_agent")
    # def assign_by_intent(self, email_data, attachment_data):
    #     """Assign agent to the task as per the intent class if none or multiple agents are assigned with the mailbox"""
    #     # try:
    #     #     intents = self._get_intents()
    #     #
    #     #     if not intents or email_data is None:
    #     #         raise ValueError("Intents or email data is missing")
    #     #
    #     #     subject = email_data.subject
    #     #     email_body = email_data.email_body
    #     #
    #     #     if attachment_data and attachment_data.content and attachment_data.content[0]:
    #     #         attachment_content = attachment_data.content[0]
    #     #         words = attachment_content.split()
    #     #         attachment_snippet = (
    #     #             " ".join(words[:250]) if len(words) > 250 else attachment_content
    #     #         )
    #     #     else:
    #     #         attachment_snippet = None
    #     #
    #     #     task_intent = self.classify_intent(
    #     #         intents=intents,
    #     #         email_uuid=email_data.id,
    #     #         subject=subject,
    #     #         email_body=email_body,
    #     #         attachment=attachment_snippet,
    #     #     )
    #     #
    #     #     if not task_intent:
    #     #         return None
    #     #
    #     #     intent_class = task_intent.lower().replace(" ", "_")
    #     #     agent = self.agent_repo.get_agent(intent_class)
    #     #
    #     #     if not agent:
    #     #         return None
    #     #
    #     #     return {"agent_id": str(agent.id), "intent_class": agent.intent_class}
    #     # except Exception as e:
    #     #     logger.error(f"Failed to assign agent by intent: {e}")
    #     return None

    def assign_by_agent(self, email_data, attachment_data) -> Optional[Dict[str, str]]:
        """Assign agent based on LLM selection using agent name and description."""
        try:
            agents = self._get_agents()

            if not agents or email_data is None:
                raise ValueError("No agents available or email data is missing")

            subject = email_data.subject
            email_body = email_data.email_body

            if (
                attachment_data
                and attachment_data.content
                and attachment_data.content[0]
            ):
                attachment_content = attachment_data.content[0]
                words = attachment_content.split()
                attachment_snippet = (
                    " ".join(words[:250]) if len(words) > 250 else attachment_content
                )
            else:
                attachment_snippet = None

            selected_agent_name = self.select_agent(
                agents=agents,
                email_uuid=email_data.id,
                subject=subject,
                email_body=email_body,
                attachment=attachment_snippet,
            )

            if not selected_agent_name:
                return None

            agent = self.agent_repo.get_agent_by_name(selected_agent_name)

            if not agent:
                return None

            return {"agent_id": str(agent.id)}
        except Exception as e:
            logger.error(f"Failed to assign agent by agent selection: {e}")
            return None

    def assign_agent(self, email_uuid: str) -> Optional[EmailDetail]:
        """
        Assign agent to the task based on the given email data and attachment.
        """
        try:
            email_data = self._get_email(email_uuid)
            if not email_data:
                raise ValueError(f"No email found for UUID: {email_uuid}")

            attachment_data = self._get_attachment(email_uuid)

            # Log dispatch start with email context
            logger.info(
                f"[email_uuid={email_uuid}] dispatch_started "
                f'subject="{email_data.subject}" '
                f"from_email={email_data.email_id} "
                f"mailbox_email={email_data.mailbox_email} "
            )

            # Try to assign agent by mailbox
            task_agent = self.assign_by_mailbox(email_data)
            assignment_method = "mailbox" if task_agent else None

            # If no agent found by mailbox, try to assign by agent name/description
            if task_agent is None:
                task_agent = self.assign_by_agent(email_data, attachment_data)
                assignment_method = "ai_assignment" if task_agent else None

            # If still no agent found, raise an exception
            if task_agent is None:
                raise Exception("No valid agent found for the given email")

            # Update the task with the assigned agent ID
            updated_email_data = self._update_task(
                email_uuid=email_uuid,
                agent_id=task_agent["agent_id"],
            )

            # Return with assignment method stored in context for later logging
            updated_email_data._assignment_method = assignment_method
            return EmailDetail.model_validate(updated_email_data)
        except Exception as e:
            logger.error(
                f'[email_uuid={email_uuid}] agent_assignment_failed error="{str(e)}"'
            )
            return None

    def create_tasks(
        self, email_uuid: str, assignment_method: str = None
    ) -> tuple[List[Union[UUID, str]], Optional[AgentDetail]]:
        """
        Create tasks for the given email using TaskFactory.
        Returns tuple of (task_ids, agent_data) for logging in route_task.
        """
        try:
            email_data = self._get_email(email_uuid)
            if email_data is None:
                raise ValueError(f"No email found for UUID: {email_uuid}")

            agent_data = self._get_agent(email_data.agent_id)
            if agent_data is None:
                raise ValueError(f"No agent found for ID: {email_data.agent_id}")

            task_factory = TaskFactory(
                self.db, agent_data.model_dump(), email_data.model_dump()
            )
            task_ids = task_factory.generate_tasks()

            return task_ids, agent_data
        except Exception as e:
            logger.error(
                f'[email_uuid={email_uuid}] task_creation_failed error="{str(e)}"'
            )
            return [], None

    def dispatch_task(self, email_uuid: str) -> tuple[List[UUID], Optional[UUID]]:
        """
        Assign agent to the task and create tasks based on the given email data.
        Returns: (task_ids, agent_id)
        """
        try:
            # Fetch email data
            email_data = self._get_email(email_uuid)
            if not email_data:
                raise ValueError(f"No email found for UUID: {email_uuid}")

            assignment_method = None

            # Check if email_data.agent_id exists
            if email_data.agent_id:
                # Pre-assigned agent case - log dispatch start here
                attachment_count = (
                    len(email_data.attachment_details.attachments)
                    if email_data.attachment_details
                    else 0
                )
                logger.info(
                    f"[email_uuid={email_uuid}] dispatch_started "
                    f'subject="{email_data.subject}" '
                    f"from={email_data.email_id} "
                    f"to={email_data.mailbox_email} "
                    f"attachments={attachment_count}"
                )

                # Fetch agent data using email_data.agent_id and validate
                agent_data = self._get_agent(email_data.agent_id)
                if not agent_data:
                    raise ValueError(f"No agent found for ID: {email_data.agent_id}")
                assignment_method = "pre_assigned"
            else:
                # If no email_data.agent_id, then go to assign_agent (which logs dispatch_started)
                updated_email_data = self.assign_agent(email_uuid)
                if not updated_email_data:
                    raise ValueError(f"Failed to assign agent for email: {email_uuid}")

                # Get assignment method from the returned data
                assignment_method = getattr(
                    updated_email_data, "_assignment_method", "unknown"
                )
                agent_data = self._get_agent(updated_email_data.agent_id)

            # Call create_tasks(email_uuid)
            task_ids, agent_data = self.create_tasks(email_uuid, assignment_method)

            # Log consolidated agent assignment and task creation
            logger.info(
                f"[email_uuid={email_uuid}] agent_assigned "
                f"method={assignment_method} "
                f"agent_id={agent_data.id} "
                f'agent_name="{agent_data.name}" '
                f"tasks_created={len(task_ids)} "
                f"task_ids={task_ids}"
            )

            # Return task IDs and agent ID
            return task_ids, agent_data.id
        except Exception as e:
            logger.error(f'[email_uuid={email_uuid}] routing_failed error="{str(e)}"')
            return [], None


# Fetch email data
# Check id email_data.agent_id exists
# Fetch agent data using email_data.agent_id, validate, and throw exception
# if no email_data.agent_id then Go to assign_agent(email_uuid)
# Call create_task (email_uuid)
# Return list of task Ids
