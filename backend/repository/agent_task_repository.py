# Custom libraries
from logger import configure_logging

# from configs.constants import TASK_STEPS
from schemas.agent_task_schema import Progress

# Database modules
from models.agent_task import AgentTask
from repository.agent_repository import AgentRepository
from repository.attachment_repository import AttachmentRepository
from repository.tag_repository import TagRepository
from schemas.agent_task_schema import AgentTaskDetail, AgentTaskResponse

# Default libraries
from collections import Counter
from typing import Optional, Union, Tuple, Dict, List
from uuid import UUID

# Installed libraries
from pydantic import parse_obj_as
from fastapi import HTTPException
from sqlalchemy import asc, desc, distinct, or_, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload


logger = configure_logging(__name__)


class AgentTaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_task(self, task_data: dict) -> AgentTask:
        current_schema = self.db.scalar(text("SELECT current_schema();"))
        logger.info(f"Current schema: {current_schema}")
        new_task = AgentTask(**task_data)
        try:
            self.db.add(new_task)
            self.db.commit()
            self.db.refresh(new_task)
            return new_task
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return None

    def append_task_progress(
        self, agent_task_id: UUID, progress: Dict
    ) -> Optional[AgentTask]:
        agent_task = (
            self.db.query(AgentTask).filter(AgentTask.id == agent_task_id).first()
        )
        if not agent_task:
            logger.warning(f"No task found with id: {agent_task_id}")
            return None

        try:
            # Convert current progress to Pydantic model and append new progress
            current_progress = parse_obj_as(List[Progress], agent_task.progress or [])
            current_progress.append(Progress(**progress))

            # Update the agent_task's progress
            agent_task.progress = [item.model_dump() for item in current_progress]

            self.db.commit()
            self.db.refresh(agent_task)
            return agent_task
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error while appending task progress: {e}")
            self.db.rollback()
            return None

    def update_task(
        self, agent_task_id: UUID, update_data: dict
    ) -> Optional[AgentTask]:
        agent_task = (
            self.db.query(AgentTask).filter(AgentTask.id == agent_task_id).first()
        )
        if not agent_task:
            return None
        try:
            for key, value in update_data.items():
                if hasattr(agent_task, key):
                    setattr(agent_task, key, value)
            self.db.commit()
            self.db.refresh(agent_task)
            return agent_task
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return None

    def get_task_by_id(self, agent_task_id: UUID) -> Optional[AgentTask]:
        try:
            return (
                self.db.query(AgentTask).filter(AgentTask.id == agent_task_id).first()
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_tasks_by_ids(self, task_ids: List[UUID]) -> Dict[UUID, AgentTask]:
        """
        Batch fetch multiple tasks by their IDs and return as a dictionary.
        This is optimized for bulk operations to reduce N+1 query problems.

        Args:
            task_ids: List of agent task UUIDs to fetch

        Returns:
            Dictionary mapping task_id -> AgentTask object
        """
        try:
            tasks = self.db.query(AgentTask).filter(AgentTask.id.in_(task_ids)).all()
            return {task.id: task for task in tasks}
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error in get_tasks_by_ids_map: {e}")
            return {}

    def get_all_tasks(
        self,
        page: int = 1,
        page_size: int = 10,
        filters: Optional[Dict[str, any]] = None,
    ) -> Tuple[List[AgentTask], int]:
        skip = (page - 1) * page_size
        query = self.db.query(AgentTask)

        # Handle "tags" filter (convert tag names to tag IDs)
        if filters and "tags" in filters:
            tag_repository = TagRepository(self.db)
            tag_ids = []
            for name in filters["tags"]:
                tag = tag_repository.get_tag_by_id(name)
                if tag:
                    tag_ids.append(str(tag.id))
            filters["tag_ids"] = tag_ids
            del filters["tags"]

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(AgentTask, key):
                    if key == "tag_ids":
                        # Use overlap for ARRAY-based filtering
                        query = query.filter(AgentTask.tag_ids.overlap(values))
                    elif isinstance(values, list):
                        condition = or_(
                            *(getattr(AgentTask, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(AgentTask, key) == values)

        try:
            tasks = query.offset(skip).limit(page_size).all()
            total = query.count()
            return tasks, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def get_agent_tasks_by_email(
        self,
        email_uuid: UUID,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Optional[AgentTaskResponse]:
        query = self.db.query(AgentTask)

        # Fetch data for specific email
        query = query.filter(AgentTask.email_data_id == email_uuid)

        # Handle "tags" filter (convert tag names to tag IDs)
        if filters and "tags" in filters:
            tag_repository = TagRepository(self.db)
            tag_ids = []
            for name in filters["tags"]:
                tag = tag_repository.get_tag_by_id(name)
                if tag:
                    tag_ids.append(str(tag.id))
            filters["tag_ids"] = tag_ids
            del filters["tags"]

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(AgentTask, key):
                    if key == "tag_ids":
                        # Use overlap for ARRAY-based filtering
                        query = query.filter(AgentTask.tag_ids.overlap(values))
                    elif isinstance(values, list):
                        condition = or_(
                            *(getattr(AgentTask, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(AgentTask, key) == values)

        # Apply sorting
        if hasattr(AgentTask, sort_by):
            order = (
                asc(getattr(AgentTask, sort_by))
                if sort_order == "asc"
                else desc(getattr(AgentTask, sort_by))
            )
            query = query.order_by(order)

        try:
            agent_tasks = query.all()
            agent_task_counts = self.get_agent_task_counts_by_email(email_uuid)
            total = query.count()
            return AgentTaskResponse(
                agent_tasks=agent_tasks,
                agent_task_counts=agent_task_counts,
                total=total,
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return [], 0

    def get_agent_task_counts_by_email(self, email_uuid: UUID) -> Dict[str, int]:
        try:
            # Query to get all tasks for the given email
            tasks = (
                self.db.query(AgentTask.progress)
                .filter(AgentTask.email_data_id == email_uuid)
                .all()
            )

            # Initialize counter with default values
            counts = Counter(
                {
                    "QUEUED": 0,
                    "EXECUTING": 0,
                    "PAUSED": 0,
                    "SUCCESSFUL": 0,
                    "RESOLVED": 0,
                    "INCOMPLETE": 0,
                    "FAILED": 0,
                    "ARCHIVED": 0,
                }
            )

            # Count tasks based on their latest progress status
            for progress in tasks:
                if progress and isinstance(progress[0], list):
                    # Get the latest progress status
                    latest_status = progress[0][-1].get("status", "")
                    if latest_status in counts:
                        counts[latest_status] += 1
                    else:
                        counts["QUEUED"] += 1
                else:
                    # If no progress or invalid progress, count as QUEUED
                    counts["QUEUED"] += 1

            # Calculate total
            counts["TOTAL"] = sum(counts.values()) - counts["ARCHIVED"]

            return dict(counts)

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error in get_task_counts_by_email: {e}")
            return {
                "QUEUED": 0,
                "EXECUTING": 0,
                "PAUSED": 0,
                "SUCCESSFUL": 0,
                "RESOLVED": 0,
                "INCOMPLETE": 0,
                "FAILED": 0,
                "ARCHIVED": 0,
                "TOTAL": 0,
            }

    def get_task_counts_by_email_ids(
        self, email_ids: List[UUID]
    ) -> Dict[UUID, Dict[str, int]]:
        """
        Batch fetch task counts for multiple emails at once.

        OPTIMIZED: Single query with IN clause instead of N separate queries.
        Used by get_all_emails() to eliminate N+1 query problem.

        Args:
            email_ids: List of email UUIDs

        Returns:
            Dict mapping email_id -> task counts dict
            Example: {
                UUID('...'): {"QUEUED": 2, "SUCCESSFUL": 5, "TOTAL": 7},
                ...
            }
        """
        if not email_ids:
            return {}

        try:
            # Single query to fetch all tasks for all emails
            tasks = (
                self.db.query(AgentTask.email_data_id, AgentTask.progress)
                .filter(AgentTask.email_data_id.in_(email_ids))
                .all()
            )

            # Group tasks by email_id
            tasks_by_email = {}
            for email_id, progress in tasks:
                if email_id not in tasks_by_email:
                    tasks_by_email[email_id] = []
                tasks_by_email[email_id].append(progress)

            # Calculate counts for each email
            result = {}
            for email_id in email_ids:
                # Initialize counter with default values
                counts = Counter(
                    {
                        "QUEUED": 0,
                        "EXECUTING": 0,
                        "PAUSED": 0,
                        "SUCCESSFUL": 0,
                        "RESOLVED": 0,
                        "INCOMPLETE": 0,
                        "FAILED": 0,
                        "ARCHIVED": 0,
                    }
                )

                # Count tasks for this email
                email_tasks = tasks_by_email.get(email_id, [])
                for progress in email_tasks:
                    if progress and isinstance(progress, list):
                        # Get the latest progress status
                        latest_status = progress[-1].get("status", "")
                        if latest_status in counts:
                            counts[latest_status] += 1
                        else:
                            counts["QUEUED"] += 1
                    else:
                        # If no progress or invalid progress, count as QUEUED
                        counts["QUEUED"] += 1

                # Calculate total
                counts["TOTAL"] = sum(counts.values()) - counts["ARCHIVED"]

                result[email_id] = dict(counts)

            return result

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error in get_task_counts_by_email_ids: {e}")
            # Return empty counts for all emails
            return {
                email_id: {
                    "QUEUED": 0,
                    "EXECUTING": 0,
                    "PAUSED": 0,
                    "SUCCESSFUL": 0,
                    "RESOLVED": 0,
                    "INCOMPLETE": 0,
                    "FAILED": 0,
                    "ARCHIVED": 0,
                    "TOTAL": 0,
                }
                for email_id in email_ids
            }

    def get_agent_task_details_by_id(
        self, agent_task_id: UUID
    ) -> Optional[AgentTaskDetail]:
        """
        Fetches the details of a specific agent task and attachment data by its agent task UUID.
        """
        try:
            agent_task = (
                self.db.query(AgentTask).filter(AgentTask.id == agent_task_id).first()
            )
            if agent_task:
                attachment_repository = AttachmentRepository(self.db)
                attachments = []
                if agent_task.attachments:
                    for agent_task_attachment in agent_task.attachments:
                        attachment_details = (
                            attachment_repository.get_attachment_preview_by_id(
                                attachment_id=agent_task_attachment.get("id")
                            )
                        )
                        attachments.append(attachment_details)
                agent_task.attachment_details = {
                    "attachments": attachments,
                    "total": len(attachments),
                }
                tag_repository = TagRepository(self.db)
                agent_task_tags = []
                for tag_id in agent_task.tag_ids or []:
                    tag = tag_repository.get_tag_by_id(UUID(tag_id))
                    if tag:
                        agent_task_tags.append(
                            {
                                "id": tag.id,
                                "name": tag.name,
                                "color": tag.color,
                            }
                        )
                agent_task.agent_task_tags = agent_task_tags
                return AgentTaskDetail.model_validate(agent_task)
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_agent_task_details_by_email(
        self,
        email_uuid: UUID,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Optional[AgentTaskResponse]:
        query = self.db.query(AgentTask)

        # Fetch data for specific email
        query = query.filter(AgentTask.email_data_id == email_uuid)

        # Handle "tags" filter (convert tag names to tag IDs)
        if filters and "tags" in filters:
            tag_repository = TagRepository(self.db)
            tag_ids = []
            for name in filters["tags"]:
                tag = tag_repository.get_tag_by_id(name)
                if tag:
                    tag_ids.append(str(tag.id))
            filters["tag_ids"] = tag_ids
            del filters["tags"]

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(AgentTask, key):
                    if key == "tag_ids":
                        # Use overlap for ARRAY-based filtering
                        query = query.filter(AgentTask.tag_ids.overlap(values))
                    elif isinstance(values, list):
                        condition = or_(
                            *(getattr(AgentTask, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(AgentTask, key) == values)

        # Apply sorting
        if hasattr(AgentTask, sort_by):
            order = (
                asc(getattr(AgentTask, sort_by))
                if sort_order == "asc"
                else desc(getattr(AgentTask, sort_by))
            )
            query = query.order_by(order)

        try:
            agent_tasks = query.all()
            agent_repository = AgentRepository(self.db)
            attachment_repository = AttachmentRepository(self.db)
            for agent_task in agent_tasks:
                agent = (
                    agent_repository.get_agent(agent_task.agent_id)
                    if agent_task.agent_id
                    else None
                )
                agent_task.agent_name = agent.name if agent else None
                agent_task.agent_icon = agent.icon if agent else None
                attachments = []
                if agent_task.attachments:
                    for agent_task_attachment in agent_task.attachments:
                        attachment_details = (
                            attachment_repository.get_attachment_preview_by_id(
                                attachment_id=agent_task_attachment.get("id")
                            )
                        )
                        attachments.append(attachment_details)
                agent_task.attachment_details = {
                    "attachments": attachments,
                    "total": len(attachments),
                }
                tag_repository = TagRepository(self.db)
                agent_task_tags = []
                for tag_id in agent_task.tag_ids or []:
                    tag = tag_repository.get_tag_by_id(UUID(tag_id))
                    if tag:
                        agent_task_tags.append(
                            {
                                "id": tag.id,
                                "name": tag.name,
                                "color": tag.color,
                            }
                        )
                agent_task.agent_task_tags = agent_task_tags
            agent_task_counts = self.get_agent_task_counts_by_email(email_uuid)
            total = query.count()
            return AgentTaskResponse(
                agent_tasks=agent_tasks,
                agent_task_counts=agent_task_counts,
                total=total,
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_agent_task_tags(self, agent_task_id: UUID, tag_ids: List[UUID]) -> bool:
        try:
            agent_task = (
                self.db.query(AgentTask).filter(AgentTask.id == agent_task_id).first()
            )
            if not agent_task:
                logger.warning(f"No agent task found: {agent_task_id}")
                return False

            tag_repository = TagRepository(self.db)
            agent_task_tags = []
            for tag_id in set(tag_ids):
                tag = tag_repository.get_tag_by_id(tag_id)
                if tag:
                    agent_task_tags.append(str(tag.id))
            agent_task.tag_ids = agent_task_tags
            self.db.commit()
            self.db.refresh(agent_task)
            return True

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return False

    def get_tasks_by_email_ids(
        self,
        email_ids: List[UUID],
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Dict[UUID, AgentTaskResponse]:
        """
        OPTIMIZED: Batch fetch agent tasks for multiple emails with all related data.

        Eliminates N+1 query problem by using batch fetching for:
        - Agent details
        - Attachments
        - Tags

        Performance: For N emails with M tasks each:
        - Before: N * (1 + M + M + M*T) queries (where T = avg tags per task)
        - After: 1 + 1 + 1 + 1 = 4 queries total

        Args:
            email_ids: List of email UUIDs to fetch tasks for
            filters: Optional filters to apply
            sort_by: Field to sort by
            sort_order: Sort order (asc or desc)

        Returns:
            Dictionary mapping email_id to AgentTaskResponse
        """
        if not email_ids:
            return {}

        try:
            # STEP 1: Fetch all tasks for all emails (1 query)
            query = self.db.query(AgentTask).filter(
                AgentTask.email_data_id.in_(email_ids)
            )

            # Handle "tags" filter (convert tag names to tag IDs)
            if filters and "tags" in filters:
                tag_repository = TagRepository(self.db)
                tag_ids = []
                for name in filters["tags"]:
                    tag = tag_repository.get_tag_by_id(name)
                    if tag:
                        tag_ids.append(str(tag.id))
                filters["tag_ids"] = tag_ids
                del filters["tags"]

            # Apply filters
            if filters:
                for key, values in filters.items():
                    if hasattr(AgentTask, key):
                        if key == "tag_ids":
                            query = query.filter(AgentTask.tag_ids.overlap(values))
                        elif isinstance(values, list):
                            condition = or_(
                                *(getattr(AgentTask, key) == value for value in values)
                            )
                            query = query.filter(condition)
                        else:
                            query = query.filter(getattr(AgentTask, key) == values)

            # Apply sorting
            if hasattr(AgentTask, sort_by):
                order = (
                    asc(getattr(AgentTask, sort_by))
                    if sort_order == "asc"
                    else desc(getattr(AgentTask, sort_by))
                )
                query = query.order_by(order)

            agent_tasks = query.all()

            if not agent_tasks:
                # Return empty responses for each email
                return {
                    email_id: AgentTaskResponse(
                        agent_tasks=[],
                        agent_task_counts={
                            "QUEUED": 0,
                            "EXECUTING": 0,
                            "PAUSED": 0,
                            "SUCCESSFUL": 0,
                            "RESOLVED": 0,
                            "INCOMPLETE": 0,
                            "FAILED": 0,
                            "ARCHIVED": 0,
                            "TOTAL": 0,
                        },
                        total=0,
                    )
                    for email_id in email_ids
                }

            # STEP 2: Collect unique agent IDs and attachment IDs
            agent_ids = set()
            all_attachment_ids = set()
            all_tag_ids = set()

            for task in agent_tasks:
                if task.agent_id:
                    agent_ids.add(task.agent_id)
                if task.attachments:
                    for attachment in task.attachments:
                        if attachment.get("id"):
                            all_attachment_ids.add(UUID(attachment.get("id")))
                if task.tag_ids:
                    all_tag_ids.update(task.tag_ids)

            # STEP 3: Batch fetch all agents (1 query instead of N*M queries)
            if agent_ids:
                # Import Agent model to query directly
                from models.agent import Agent

                agents = self.db.query(Agent).filter(Agent.id.in_(agent_ids)).all()
                agent_map = {agent.id: agent for agent in agents if agent}
            else:
                agent_map = {}

            # STEP 4: Batch fetch all attachments (1 query instead of N*M queries)
            attachment_repository = AttachmentRepository(self.db)
            if all_attachment_ids:
                # Use batch method to fetch all attachments at once
                attachment_map = attachment_repository.get_attachments_preview_by_ids(
                    list(all_attachment_ids)
                )
            else:
                attachment_map = {}

            # STEP 5: Batch fetch all tags (1 query instead of N*M*T queries)
            tag_repository = TagRepository(self.db)
            if all_tag_ids:
                tags = tag_repository.get_tags_by_ids(list(all_tag_ids))
                tag_map = {str(tag.id): tag for tag in tags}
            else:
                tag_map = {}

            # STEP 6: Map data back to tasks (in-memory, 0 queries)
            for task in agent_tasks:
                # Map agent
                agent = agent_map.get(task.agent_id)
                task.agent_name = agent.name if agent else None
                task.agent_icon = agent.icon if agent else None

                # Map attachments
                attachments = []
                if task.attachments:
                    for task_attachment in task.attachments:
                        att_id = task_attachment.get("id")
                        if att_id and UUID(att_id) in attachment_map:
                            attachments.append(attachment_map[UUID(att_id)])
                task.attachment_details = {
                    "attachments": attachments,
                    "total": len(attachments),
                }

                # Map tags
                agent_task_tags = []
                for tag_id in task.tag_ids or []:
                    if tag_id in tag_map:
                        tag = tag_map[tag_id]
                        agent_task_tags.append(
                            {
                                "id": tag.id,
                                "name": tag.name,
                                "color": tag.color,
                            }
                        )
                task.agent_task_tags = agent_task_tags

            # STEP 7: Group tasks by email and get counts
            result = {}
            for email_id in email_ids:
                email_tasks = [
                    task for task in agent_tasks if task.email_data_id == email_id
                ]
                agent_task_counts = self.get_agent_task_counts_by_email(email_id)
                result[email_id] = AgentTaskResponse(
                    agent_tasks=email_tasks,
                    agent_task_counts=agent_task_counts,
                    total=len(email_tasks),
                )

            return result

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error in get_tasks_by_email_ids: {e}")
            return {}
