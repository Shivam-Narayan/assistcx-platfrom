# Custom libraries
from logger import configure_logging

# Database modules
from models.agent import Agent
from models.agent_tool import AgentTool

# Default libraries
from typing import Optional, Tuple, Union, Dict, List
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import asc, desc, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session


logger = configure_logging(__name__)


class AgentToolRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_agent_tool(self, agent_tool_data: Dict) -> Optional[AgentTool]:
        new_agent_tool = AgentTool(**agent_tool_data)
        try:
            self.db.add(new_agent_tool)
            self.db.commit()
            self.db.refresh(new_agent_tool)
            return new_agent_tool
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Agent tool with the same action name already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_agent_tool(self, update_data: dict) -> Optional[AgentTool]:
        try:
            action_to_update = update_data.get("action")

            agent_tool = (
                self.db.query(AgentTool)
                .filter(AgentTool.action == action_to_update)
                .first()
            )

            if agent_tool:
                # Update the fields based on the provided data
                for field, value in update_data.items():
                    setattr(agent_tool, field, value)
            else:
                # Create a new agent tool if the name is missing
                agent_tool = AgentTool(**update_data)
                self.db.add(agent_tool)

            self.db.commit()
            self.db.refresh(agent_tool)
            return agent_tool

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Agent tool update failed due to integrity constraint.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_agent_tool_by_id(self, update_data: dict) -> Optional[AgentTool]:
        identifier = update_data.get("agent_tool_uuid") or update_data.get("action")
        query_filter = (
            AgentTool.id == identifier
            if isinstance(identifier, UUID)
            else AgentTool.action == identifier
        )
        agent_tool = self.db.query(AgentTool).filter(query_filter).first()
        if not agent_tool:
            return None
        if agent_tool.is_default:
            raise HTTPException(
                status_code=403,
                detail="Default tools cannot be modified.",
            )
        try:
            for key, value in update_data.items():
                setattr(agent_tool, key, value)
            self.db.commit()
            self.db.refresh(agent_tool)
            return agent_tool
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Agent tool with same action name already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_agent_tool_by_integration(
        self, integration_key: str, status: str
    ) -> List[AgentTool]:
        """
        Update all agent tools matching the integration key to enabled/disabled status.
        """
        try:
            if status.lower() not in ["enable", "disable"]:
                logger.error(f"Invalid status provided: {status}")
                raise HTTPException(
                    status_code=400,
                    detail="Status must be either 'enable' or 'disable'",
                )

            agent_tools = (
                self.db.query(AgentTool)
                .filter(AgentTool.integration_key == integration_key)
                .all()
            )

            if not agent_tools:
                logger.warning(
                    f"No agent tools found with integration key: {integration_key}"
                )
                return []

            updated_tools = []
            for tool in agent_tools:
                update_data = {
                    "action": tool.action,
                    "is_enabled": True if status.lower() == "enable" else False,
                }

                updated_tool = self.update_agent_tool(update_data)
                if updated_tool:
                    updated_tools.append(updated_tool)
                else:
                    logger.error(
                        f"Failed to update agent tool with action: {tool.action}"
                    )

            return updated_tools

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error while updating agent tools: {e}")
            return []

    def create_or_update_agent_tool(self, data: dict) -> Optional[AgentTool]:
        action = data.get("action")
        if not action:
            return None
        agent_tool = self.db.query(AgentTool).filter(AgentTool.action == action).first()
        if agent_tool:
            return self.update_agent_tool_by_id(agent_tool.id, data)
        else:
            return self.create_agent_tool(data)

    def get_agent_tool(self, identifier: Union[UUID, str]) -> Optional[AgentTool]:
        if isinstance(identifier, UUID):
            query_filter = AgentTool.id == identifier
        elif isinstance(identifier, str):
            query_filter = AgentTool.action == identifier
        else:
            raise ValueError("Identifier must be a UUID or action string")
        try:
            return self.db.query(AgentTool).filter(query_filter).first()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_agent_tools_by_integration(self, integration_key: str) -> List[AgentTool]:
        """
        Retrieves all agent tools associated with a specific integration key.
        """
        try:
            tools = (
                self.db.query(AgentTool)
                .filter(AgentTool.integration_key == integration_key)
                .order_by(AgentTool.created_at)
                .all()
            )
            return tools
        except SQLAlchemyError as e:
            logger.error(f"Error fetching tools for integration {integration_key}: {e}")
            return []

    def get_agent_tools_by_agent_id(self, agent_id: UUID) -> List[AgentTool]:
        """
        Return agent tools for the given agent, ordered as in Agent.tools.
        """
        try:
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent or not agent.tools:
                return []

            # Extract action strings in order (Agent.tools is list of dicts with "action" key)
            ordered_actions = []
            for tool_entry in agent.tools:
                if isinstance(tool_entry, dict):
                    action = tool_entry.get("action")
                    if action:
                        ordered_actions.append(action)

            if not ordered_actions:
                return []

            agent_tools = (
                self.db.query(AgentTool)
                .filter(AgentTool.action.in_(ordered_actions))
                .all()
            )
            tools_by_action = {agent_tool.action: agent_tool for agent_tool in agent_tools}
            return [
                tools_by_action[action]
                for action in ordered_actions
                if action in tools_by_action
            ]

        except SQLAlchemyError as e:
            logger.error(
                f"SQLAlchemy Error while fetching agent tools for agent {agent_id}: {e}"
            )
            return []

    def get_all_agent_tools(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[AgentTool], int]:
        query = self.db.query(AgentTool)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(AgentTool, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(AgentTool, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(AgentTool, key) == values)

        # Apply sorting
        if hasattr(AgentTool, sort_by):
            order = (
                asc(getattr(AgentTool, sort_by))
                if sort_order == "asc"
                else desc(getattr(AgentTool, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                agent_tools = query.offset(skip).limit(page_size).all()
            else:
                agent_tools = query.all()

            return agent_tools, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def get_agent_tool_filters(
        self,
        filters: Optional[Dict[str, any]] = None,
    ) -> Dict[str, List[str]]:
        query = self.db.query(AgentTool.integration_key)

        # Apply filters using preferred style
        if filters:
            for key, values in filters.items():
                if hasattr(AgentTool, key):
                    if isinstance(values, list):
                        condition = or_(
                            *(getattr(AgentTool, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(AgentTool, key) == values)

        query = query.order_by(AgentTool.integration_key.asc())

        try:
            results = query.distinct().all()

            integration_keys = [
                result.integration_key for result in results if result.integration_key
            ]

            return {"integration_keys": list(integration_keys)}

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return {"integration_keys": []}

    def search_agent_tools(
        self,
        keyword: str = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[AgentTool], int]:
        query = self.db.query(AgentTool)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(AgentTool, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(AgentTool, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(AgentTool, key) == values)

        # Apply search
        if keyword:
            query = query.filter(
                or_(
                    AgentTool.name.ilike(f"%{keyword}%"),
                    AgentTool.description.ilike(f"%{keyword}%"),
                    AgentTool.action.ilike(f"%{keyword}%"),
                )
            )

        # Apply sorting
        if hasattr(AgentTool, sort_by):
            order = (
                asc(getattr(AgentTool, sort_by))
                if sort_order == "asc"
                else desc(getattr(AgentTool, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                agent_tools = query.offset(skip).limit(page_size).all()
            else:
                agent_tools = query.all()

            return agent_tools, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def delete_agent_tool(self, identifier: Union[UUID, str]) -> Optional[bool]:
        query_filter = (
            AgentTool.id == identifier
            if isinstance(identifier, UUID)
            else AgentTool.action == identifier
        )
        agent_tool = self.db.query(AgentTool).filter(query_filter).first()
        if not agent_tool:
            return False
        # Check if any Agent is using this tool by matching action name
        agents = (
            self.db.query(Agent)
            .filter(Agent.tools.contains([{"action": agent_tool.action}]))
            .all()
        )
        if agents:
            agent_names = ", ".join(agent.name for agent in agents)
            raise HTTPException(
                status_code=409,
                detail=f"The Agent Tool '{agent_tool.name}' is assigned to the following agents: '{agent_names}'. Please delete or update the associated agents first.",
            )
        try:
            self.db.delete(agent_tool)
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return False

    # def paginated_get_all_agent_tools(
    #     self,
    #     page: int = 1,
    #     page_size: int = 10,
    #     filters: Optional[Dict[str, any]] = None,
    #     sort_by: str = "updated_at",
    #     sort_order: str = "desc",
    # ) -> Tuple[List[AgentTool], int]:
    #     skip = (page - 1) * page_size
    #     query = self.db.query(AgentTool)

    #     # Apply filters
    #     if filters:
    #         for key, values in filters.items():
    #             if hasattr(AgentTool, key):
    #                 if isinstance(values, list):
    #                     # Handle multiple values for the same filter key
    #                     condition = or_(
    #                         *(getattr(AgentTool, key) == value for value in values)
    #                     )
    #                     query = query.filter(condition)
    #                 else:
    #                     query = query.filter(getattr(AgentTool, key) == values)

    #     # Apply sorting
    #     if hasattr(AgentTool, sort_by):
    #         order = (
    #             asc(getattr(AgentTool, sort_by))
    #             if sort_order == "asc"
    #             else desc(getattr(AgentTool, sort_by))
    #         )
    #         query = query.order_by(order)

    #     try:
    #         agent_tools = query.offset(skip).limit(page_size).all()
    #         total = query.count()
    #         return agent_tools, total
    #     except SQLAlchemyError as e:
    #         logger.error(f"SQLAlchemy Error: {e}")
    #         return [], 0

    # def paginated_search_agent_tool(
    #     self,
    #     keyword: str = None,
    #     page: int = 1,
    #     page_size: int = 10,
    #     filters: Optional[Dict[str, any]] = None,
    #     sort_by: str = "created_at",
    #     sort_order: str = "asc",
    # ) -> Tuple[List[AgentTool], int]:
    #     skip = (page - 1) * page_size
    #     query = self.db.query(AgentTool)

    #     # Apply filters
    #     if filters:
    #         for key, values in filters.items():
    #             if hasattr(AgentTool, key):
    #                 if isinstance(values, list):
    #                     # Handle multiple values for the same filter key
    #                     condition = or_(
    #                         *(getattr(AgentTool, key) == value for value in values)
    #                     )
    #                     query = query.filter(condition)
    #                 else:
    #                     query = query.filter(getattr(AgentTool, key) == values)

    #     # Apply search
    #     if keyword:
    #         query = query.filter(
    #             or_(
    #                 AgentTool.name.ilike(f"%{keyword}%"),
    #                 AgentTool.description.ilike(f"%{keyword}%"),
    #                 AgentTool.action.ilike(f"%{keyword}%"),
    #             )
    #         )

    #     # Apply sorting
    #     if hasattr(AgentTool, sort_by):
    #         order = (
    #             asc(getattr(AgentTool, sort_by))
    #             if sort_order == "asc"
    #             else desc(getattr(AgentTool, sort_by))
    #         )
    #         query = query.order_by(order)

    #     try:
    #         agent_tools = query.offset(skip).limit(page_size).all()
    #         total = query.count()
    #         return agent_tools, total
    #     except SQLAlchemyError as e:
    #         logger.error(f"SQLAlchemy Error: {e}")
    #         return []
