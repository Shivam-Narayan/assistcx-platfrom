# Custom libraries
from logger import configure_logging
from schemas.agent_schema import AgentCreate

# Database modules
from models.agent import Agent
from models.agent_tool import AgentTool
# from repository.intent_repository import IntentRepository  # intent_repository.py commented out
from repository.mailbox_polling_repository import MailboxPollingRepository

# Default libraries
from typing import Optional, Tuple, Union, Dict, List
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import asc, desc, func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session


logger = configure_logging(__name__)


class AgentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_agent(self, agent_data: AgentCreate) -> Optional[Agent]:
        # Ensure at least one of intent_class or agent_mailbox is provided
        # if not (agent_data.intent_class or agent_data.agent_mailbox):
        #     raise HTTPException(
        #         status_code=400,
        #         detail="Agent must have either Intent Class or Agent Mailbox.",
        #     )
        # # Check for existing agent with same intent_class or agent_mailbox (intent_class path deprecated)
        # if agent_data.intent_class or agent_data.agent_mailbox:
        #     existing_agent = (
        #         self.db.query(Agent)
        #         .filter(
        #             (
        #                 (Agent.intent_class == agent_data.intent_class)
        #                 & Agent.intent_class.isnot(None)
        #                 & (Agent.intent_class != "")
        #             )
        #             | (
        #                 (Agent.agent_mailbox == agent_data.agent_mailbox)
        #                 & Agent.agent_mailbox.isnot(None)
        #                 & (Agent.agent_mailbox != "")
        #             )
        #         )
        #         .first()
        #     )
        #     if existing_agent:
        #         if (
        #             agent_data.intent_class
        #             and existing_agent.intent_class == agent_data.intent_class
        #         ):
        #             raise HTTPException(
        #                 status_code=409,
        #                 detail=f"Agent with Intent Class '{agent_data.intent_class}' already exists.",
        #             )
        #         if (
        #             agent_data.agent_mailbox
        #             and existing_agent.agent_mailbox == agent_data.agent_mailbox
        #         ):
        #             raise HTTPException(
        #                 status_code=409,
        #                 detail=f"Agent with Agent Mailbox '{agent_data.agent_mailbox}' already exists.",
        #             )
        if agent_data.agent_mailbox:
            agent_data.agent_mailbox = agent_data.agent_mailbox.lower()
            existing_agent = (
                self.db.query(Agent)
                .filter(
                    (func.lower(Agent.agent_mailbox) == agent_data.agent_mailbox)
                    & Agent.agent_mailbox.isnot(None)
                    & (Agent.agent_mailbox != "")
                )
                .first()
            )
            if existing_agent:
                raise HTTPException(
                    status_code=409,
                    detail=f"Agent with Agent Mailbox '{agent_data.agent_mailbox}' already exists.",
                )
            mailbox_polling_repository = MailboxPollingRepository(self.db)
            mailbox_polling = mailbox_polling_repository.get_mailbox_polling(
                agent_data.agent_mailbox
            )
            if not mailbox_polling:
                raise HTTPException(
                    status_code=400,
                    detail=f"Agent Mailbox '{agent_data.agent_mailbox}' does not exist. Please create the Mailbox Polling first.",
                )
        # # Validate intent_class via IntentRepository (intent_repository commented out)
        # if agent_data.intent_class:
        #     mailbox_polling_repository = IntentRepository(self.db)
        #     intent = mailbox_polling_repository.get_intent(agent_data.intent_class)
        #     if not intent:
        #         raise HTTPException(
        #             status_code=400,
        #             detail=f"Intent Class '{agent_data.intent_class}' does not exist. Please create the Intent first.",
        #         )
        # Remove any duplicate agent tools
        agent_tools = []
        for tool in agent_data.tools:
            if tool not in agent_tools:
                agent_tools.append(tool)
        agent_data.tools = agent_tools
        new_agent = Agent(**agent_data.model_dump())
        try:
            self.db.add(new_agent)
            self.db.commit()
            self.db.refresh(new_agent)
            return new_agent
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Agent with same Name already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_agent(self, update_data: dict) -> Optional[Agent]:
        # intent_class = (update_data.get("intent_class") or "").strip()
        agent_mailbox = (update_data.get("agent_mailbox") or "").strip().lower()
        # Ensure at least one of intent_class or agent_mailbox is provided
        # if not (intent_class or agent_mailbox):
        #     raise HTTPException(
        #         status_code=400,
        #         detail="Agent must have either Intent Class or Agent Mailbox.",
        #     )

        identifier = update_data.get("agent_uuid")
        # query_filter = (
        #     Agent.id == identifier
        #     if isinstance(identifier, UUID)
        #     else Agent.intent_class == identifier
        # )
        if not isinstance(identifier, UUID):
            return None
        query_filter = Agent.id == identifier
        agent = self.db.query(Agent).filter(query_filter).first()
        if not agent:
            return None

        # # Check for existing agent with same intent_class (deprecated)
        # if intent_class and intent_class != agent.intent_class:
        #     existing_agent = (
        #         self.db.query(Agent).filter(Agent.intent_class == intent_class).first()
        #     )
        #     if existing_agent:
        #         raise HTTPException(
        #             status_code=409,
        #             detail=f"Agent with Intent Class '{intent_class}' already exists. Please check and retry.",
        #         )

        if agent_mailbox and agent_mailbox != (agent.agent_mailbox or "").lower():
            existing_agent = (
                self.db.query(Agent)
                .filter(func.lower(Agent.agent_mailbox) == agent_mailbox)
                .first()
            )
            if existing_agent:
                raise HTTPException(
                    status_code=409,
                    detail=f"Agent with Agent Mailbox '{agent_mailbox}' already exists. Please check and retry.",
                )

        # # Validate intent_class via IntentRepository (intent_repository commented out)
        # if intent_class:
        #     mailbox_polling_repository = IntentRepository(self.db)
        #     intent = mailbox_polling_repository.get_intent(intent_class)
        #     if not intent:
        #         raise HTTPException(
        #             status_code=400,
        #             detail=f"Intent Class '{intent_class}' does not exist. Please create the Intent first.",
        #         )
        if agent_mailbox:
            mailbox_polling_repository = MailboxPollingRepository(self.db)
            mailbox_polling = mailbox_polling_repository.get_mailbox_polling(
                agent_mailbox
            )
            if not mailbox_polling:
                raise HTTPException(
                    status_code=400,
                    detail=f"Agent Mailbox '{agent_mailbox}' does not exist. Please create the Mailbox Polling first.",
                )

        try:
            for key, value in update_data.items():
                if hasattr(agent, key):
                    setattr(agent, key, value)
            self.db.commit()
            self.db.refresh(agent)
            return agent
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Agent with same Name already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def create_or_update_agent(self, data: dict) -> Optional[Agent]:
        # Deprecated: upsert by intent_class while IntentRepository is commented out
        # intent_class = data.get("intent_class")
        # if not intent_class:
        #     return None
        # agent = self.db.query(Agent).filter(Agent.intent_class == intent_class).first()
        # if agent:
        #     return self.update_agent(agent.id, data)
        # else:
        #     return self.create_agent(data)
        return None

    def get_agent(self, identifier: Union[UUID, str]) -> Optional[Agent]:
        if isinstance(identifier, UUID):
            query_filter = Agent.id == identifier
        elif isinstance(identifier, str):
            # query_filter = Agent.intent_class == identifier
            return None
        else:
            raise ValueError("Identifier must be a UUID")
        try:
            return self.db.query(Agent).filter(query_filter).first()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def resolve_plan_tools(self, agent_detail) -> None:
        """Resolves plan tool action strings to dicts with name and action."""
        if not agent_detail.plan:
            return

        tools_lookup = {tool.action: tool.name for tool in agent_detail.tools} if agent_detail.tools else {}

        all_actions = set()
        for step in agent_detail.plan:
            if not step.tool:
                continue
            if isinstance(step.tool, str):
                all_actions.add(step.tool)
            elif isinstance(step.tool, list):
                all_actions.update(a for a in step.tool if isinstance(a, str))

        missing_actions = all_actions - tools_lookup.keys()
        if missing_actions:
            try:
                db_tools = (
                    self.db.query(AgentTool.action, AgentTool.name)
                    .filter(AgentTool.action.in_(missing_actions))
                    .all()
                )
                tools_lookup.update({t.action: t.name for t in db_tools})
            except SQLAlchemyError as e:
                logger.error(f"Error fetching tool names for plan resolution: {e}")

        for step in agent_detail.plan:
            if not step.tool:
                continue
            if isinstance(step.tool, str):
                step.tool = {
                    "name": tools_lookup.get(step.tool, step.tool),
                    "action": step.tool,
                }
            elif isinstance(step.tool, list):
                step.tool = [
                    {"name": tools_lookup.get(action, action), "action": action}
                    if isinstance(action, str)
                    else action
                    for action in step.tool
                ]

    def get_agent_by_name(self, name: str) -> Optional[List[Agent]]:
        query_filter = Agent.name == name
        try:
            return self.db.query(Agent).filter(query_filter).first()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_mailbox_agent(self, mailbox_email: str) -> List[Agent]:
        try:
            agents = (
                self.db.query(Agent).filter(func.lower(Agent.agent_mailbox) == mailbox_email.lower()).all()
            )
            return agents
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error while fetching agents: {e}")
            return []

    def get_all_agents(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[Agent], int]:
        query = self.db.query(Agent)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(Agent, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(Agent, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(Agent, key) == values)
            # Always exclude ARCHIVED unless explicitly included
            if "status" not in filters or "ARCHIVED" not in filters["status"]:
                query = query.filter(Agent.status != "ARCHIVED")
        else:
            query = query.filter(Agent.status != "ARCHIVED")

        # Apply sorting
        if hasattr(Agent, sort_by):
            order = (
                asc(getattr(Agent, sort_by))
                if sort_order == "asc"
                else desc(getattr(Agent, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                agents = query.offset(skip).limit(page_size).all()
            else:
                agents = query.all()

            return agents, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def search_agents(
        self,
        keyword: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[Agent], int]:
        query = self.db.query(Agent)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(Agent, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(Agent, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(Agent, key) == values)
            # Always exclude ARCHIVED unless explicitly included
            if "status" not in filters or "ARCHIVED" not in filters["status"]:
                query = query.filter(Agent.status != "ARCHIVED")
        else:
            query = query.filter(Agent.status != "ARCHIVED")

        # Apply search
        if keyword:
            query = query.filter(
                or_(
                    Agent.name.ilike(f"%{keyword}%"),
                    Agent.description.ilike(f"%{keyword}%"),
                    # Agent.intent_class.ilike(f"%{keyword}%"),
                    Agent.style.ilike(f"%{keyword}%"),
                    Agent.goal.ilike(f"%{keyword}%"),
                )
            )

        # Apply sorting
        if hasattr(Agent, sort_by):
            order = (
                asc(getattr(Agent, sort_by))
                if sort_order == "asc"
                else desc(getattr(Agent, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                agents = query.offset(skip).limit(page_size).all()
            else:
                agents = query.all()

            return agents, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def get_agents_by_assignment(
        self,
        assignment_type: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[Agent], int]:
        query = self.db.query(Agent)

        # Apply assignment type filter (JSONB @> operator for boolean keys)
        if assignment_type == "ai_assignment":
            query = query.filter(
                Agent.agent_config.contains({"ai_assignment": True})
            )
        elif assignment_type == "external_task_api":
            query = query.filter(
                Agent.agent_config.contains({"external_task_api": True})
            )
        elif assignment_type == "mailbox_assignment":
            query = query.filter(Agent.agent_mailbox.isnot(None))
        else:
            raise ValueError("Invalid assignment type")

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(Agent, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(Agent, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(Agent, key) == values)
            # Always exclude ARCHIVED unless explicitly included
            if "status" not in filters or "ARCHIVED" not in filters["status"]:
                query = query.filter(Agent.status != "ARCHIVED")
        else:
            query = query.filter(Agent.status != "ARCHIVED")

        # Apply sorting
        if hasattr(Agent, sort_by):
            order = (
                asc(getattr(Agent, sort_by))
                if sort_order == "asc"
                else desc(getattr(Agent, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                agents = query.offset(skip).limit(page_size).all()
            else:
                agents = query.all()

            return agents, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def archive_agent_by_id(self, agent_id: UUID) -> Optional[bool]:
        try:
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()

            if not agent:
                logger.warning(f"No agent found: {agent_id}")
                return False

            if agent.status == "ARCHIVED":
                logger.warning(f"Agent is already ARCHIVED: {agent_id}")
                return False

            # --- Clear mailbox assignment (intent_class writes disabled) ---
            if agent.agent_mailbox:
                agent.agent_mailbox = None
            # else:
            #     agent.intent_class = None

            agent.status = "ARCHIVED"
            self.db.commit()
            logger.info(
                f"Agent {agent_id} archived successfully. Cleared mailbox assignment."
            )
            return True

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return False

    def delete_agent(self, identifier: Union[UUID, str]) -> Optional[bool]:
        # query_filter = (
        #     Agent.id == identifier
        #     if isinstance(identifier, UUID)
        #     else Agent.intent_class == identifier
        # )
        if not isinstance(identifier, UUID):
            return False
        query_filter = Agent.id == identifier
        agent = self.db.query(Agent).filter(query_filter).first()
        if not agent:
            return False
        try:
            self.db.delete(agent)
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return False

    # def paginated_search_agent(
    #     self,
    #     keyword: str,
    #     page: int = 1,
    #     page_size: int = 10,
    #     filters: Optional[Dict[str, any]] = None,
    #     sort_by: str = "updated_at",
    #     sort_order: str = "desc",
    # ) -> Tuple[List[Agent], int]:
    #     skip = (page - 1) * page_size
    #     query = self.db.query(Agent)

    #     # Apply filters
    #     if filters:
    #         for key, values in filters.items():
    #             if hasattr(Agent, key):
    #                 if isinstance(values, list):
    #                     # Handle multiple values for the same filter key
    #                     condition = or_(
    #                         *(getattr(Agent, key) == value for value in values)
    #                     )
    #                     query = query.filter(condition)
    #                 else:
    #                     query = query.filter(getattr(Agent, key) == values)

    #     # Apply search
    #     if keyword:
    #         query = query.filter(
    #             or_(
    #                 Agent.name.ilike(f"%{keyword}%"),
    #                 Agent.description.ilike(f"%{keyword}%"),
    #                 Agent.intent_class.ilike(f"%{keyword}%"),
    #                 Agent.style.ilike(f"%{keyword}%"),
    #                 Agent.goal.ilike(f"%{keyword}%"),
    #             )
    #         )

    #     # Apply sorting
    #     if hasattr(Agent, sort_by):
    #         order = (
    #             asc(getattr(Agent, sort_by))
    #             if sort_order == "asc"
    #             else desc(getattr(Agent, sort_by))
    #         )
    #         query = query.order_by(order)

    #     try:
    #         agents = query.offset(skip).limit(page_size).all()
    #         total = query.count()
    #         return agents, total
    #     except SQLAlchemyError as e:
    #         logger.error(f"SQLAlchemy Error: {e}")
    #         return [], 0

    # def paginated_get_all_agents(
    #     self,
    #     page: int = 1,
    #     page_size: int = 10,
    #     filters: Optional[Dict[str, any]] = None,
    #     sort_by: str = "updated_at",
    #     sort_order: str = "desc",
    # ) -> Tuple[List[Agent], int]:
    #     skip = (page - 1) * page_size
    #     query = self.db.query(Agent)

    #     # Apply filters
    #     if filters:
    #         for key, values in filters.items():
    #             if hasattr(Agent, key):
    #                 if isinstance(values, list):
    #                     # Handle multiple values for the same filter key
    #                     condition = or_(
    #                         *(getattr(Agent, key) == value for value in values)
    #                     )
    #                     query = query.filter(condition)
    #                 else:
    #                     query = query.filter(getattr(Agent, key) == values)

    #     # Apply sorting
    #     if hasattr(Agent, sort_by):
    #         order = (
    #             asc(getattr(Agent, sort_by))
    #             if sort_order == "asc"
    #             else desc(getattr(Agent, sort_by))
    #         )
    #         query = query.order_by(order)

    #     try:
    #         agents = query.offset(skip).limit(page_size).all()
    #         total = query.count()
    #         return agents, total
    #     except SQLAlchemyError as e:
    #         logger.error(f"SQLAlchemy Error: {e}")
    #         return [], 0
