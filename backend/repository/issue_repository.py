# Custom libraries
from logger import configure_logging
from schemas.issue_schema import IssueCreate, IssueUpdate, IssueProgressUpdate
from schemas.issue_comment_schema import IssueCommentCreate, IssueCommentUpdate

# Database modules
from models.issue import Issue
from models.issue_comment import IssueComment
from models.user import User
from models.agent import Agent
from models.agent_task import AgentTask

# Default libraries
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import asc, desc, func, or_, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload


logger = configure_logging(__name__)


class IssueRepository:
    def __init__(self, db: Session):
        self.db = db

    # ==================== Issue Functions ====================

    def create_issue(
        self,
        issue_data: IssueCreate,
        user_id: UUID,
        user_name: str,
    ) -> Optional[Issue]:
        data = issue_data.model_dump()

        # Set created_by from authenticated user
        data["created_by"] = user_id

        # Auto-create initial progress entry with status "active"
        data["progress"] = [
            {
                "status": "ACTIVE",
                "reason": None,
                "user_id": str(user_id) if user_id else None,
                "user_name": user_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ]

        # Auto-subscribe the creator
        data["subscribed"] = [str(user_id)]

        new_issue = Issue(**data)
        try:
            self.db.add(new_issue)
            self.db.commit()
            self.db.refresh(new_issue)
            return new_issue
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return None

    def update_issue(
        self,
        issue_uuid: UUID,
        issue_data: IssueUpdate,
        user_id: UUID,
        user_name: str,
    ) -> Optional[Issue]:
        issue = self.db.query(Issue).filter(Issue.id == issue_uuid).first()
        if not issue:
            return None
        try:
            update_data = {
                k: v for k, v in issue_data.model_dump().items() if v is not None
            }

            append_fields = {"agent_task_ids"}
            replace_fields = {"tag_ids"}
            new_tasks_added = False

            for key, value in update_data.items():
                if hasattr(issue, key):
                    if key in append_fields and value:
                        existing = getattr(issue, key) or []
                        new_ids = [str(v) for v in value]
                        if key == "agent_task_ids":
                            new_tasks_added = any(id not in existing for id in new_ids)
                        setattr(issue, key, list(dict.fromkeys(existing + new_ids)))
                    elif key in replace_fields and value is not None:
                        # Replace entire list (allows empty list to remove all tags)
                        new_ids = [str(v) for v in value]
                        setattr(issue, key, new_ids)
                    else:
                        setattr(issue, key, value)

            self._auto_reopen_if_resolved(
                issue, new_tasks_added, user_id=user_id, user_name=user_name
            )

            # Auto-subscribe the user who edited the issue
            self._add_subscriber(issue, user_id)

            self.db.commit()
            self.db.refresh(issue)
            return issue
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def _auto_reopen_if_resolved(
        self,
        issue: Issue,
        new_tasks_added: bool,
        user_id: UUID,
        user_name: str,
    ) -> None:
        """Auto-reopen issue if new tasks are added to a resolved issue."""
        if not new_tasks_added:
            return
        if not issue.progress:
            return
        if issue.progress[-1].get("status", "").upper() != "RESOLVED":
            return

        issue.progress = list(issue.progress) + [{
            "status": "ACTIVE",
            "reason": "Auto-reopened: New task(s) added",
            "user_id": str(user_id) if user_id else None,
            "user_name": user_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]

    def update_issue_progress(
        self,
        issue_uuid: UUID,
        progress_data: IssueProgressUpdate,
        user_id: UUID,
        user_name: str,
    ) -> Optional[Issue]:
        issue = self.db.query(Issue).filter(Issue.id == issue_uuid).first()
        if not issue:
            return None
        try:
            # Build progress entry
            progress_entry = {
                "status": progress_data.status,
                "reason": progress_data.reason,
                "user_id": str(user_id) if user_id else None,
                "user_name": user_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Get existing progress and append new entry
            existing_progress = issue.progress or []
            issue.progress = existing_progress + [progress_entry]

            # Auto-subscribe the user who updated progress (resolve/reopen)
            self._add_subscriber(issue, user_id)

            self.db.commit()
            self.db.refresh(issue)
            return issue
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    # ==================== Helper Functions ====================

    def _apply_issue_filters(
        self,
        query,
        issue_model,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: Optional[str] = "updated_at",
        sort_order: Optional[str] = "desc",
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ):
        """
        Shared Issue filtering/sorting logic used by repositories.

        Note: preserves existing behavior of mutating `filters` by popping "status" if present.
        """
        # Handle status filter specially (nested in progress JSON)
        if filters and "status" in filters:
            status_value = filters.pop("status")
            if isinstance(status_value, list):
                placeholders = ", ".join([f"'{s}'" for s in status_value])
                query = query.filter(text(f"progress->-1->>'status' IN ({placeholders})"))
            else:
                query = query.filter(
                    text("progress->-1->>'status' = :status").bindparams(
                        status=status_value
                    )
                )

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(issue_model, key):
                    if key == "tag_ids":
                        # Use overlap for ARRAY-based filtering
                        if not isinstance(values, list):
                            values = [values]
                        query = query.filter(issue_model.tag_ids.overlap(values))
                    elif isinstance(values, list):
                        condition = or_(
                            *(getattr(issue_model, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(issue_model, key) == values)

        # Apply date filtering
        if from_date:
            query = query.filter(issue_model.created_at >= from_date)
        if to_date:
            query = query.filter(issue_model.created_at <= to_date + timedelta(seconds=1))

        # Apply sorting
        if sort_by and hasattr(issue_model, sort_by):
            order = (
                asc(getattr(issue_model, sort_by))
                if sort_order == "asc"
                else desc(getattr(issue_model, sort_by))
            )
            query = query.order_by(order)

        return query

    def _populate_user_names(self, issues: List[Issue]) -> None:
        """
        Batch populate user_name for issues and their comments.
        Uses ONE query instead of N+1 queries.
        """
        if not issues:
            return

        # Step 1: Collect ALL unique user UUIDs
        user_ids = set()
        for issue in issues:
            if issue.created_by:
                user_ids.add(issue.created_by)
            if issue.comments:
                for comment in issue.comments:
                    if comment.user_id:
                        user_ids.add(comment.user_id)

        if not user_ids:
            return

        # Step 2: ONE query to fetch all users
        users = self.db.query(User).filter(User.id.in_(user_ids)).all()
        user_cache = {}
        for user in users:
            names = filter(None, [user.first_name, user.last_name])
            user_cache[user.id] = " ".join(names)

        # Step 3: Populate from cache
        for issue in issues:
            if issue.created_by:
                issue.user_name = user_cache.get(issue.created_by)
            if issue.comments:
                for comment in issue.comments:
                    if comment.user_id:
                        comment.user_name = user_cache.get(comment.user_id)

    def _populate_comment_user_names(self, comments: List[IssueComment]) -> None:
        """
        Batch populate user_name for comments.
        Uses ONE query instead of N queries.
        """
        if not comments:
            return

        # Collect unique user IDs
        user_ids = {c.user_id for c in comments if c.user_id}
        if not user_ids:
            return

        # ONE query to fetch all users
        users = self.db.query(User).filter(User.id.in_(user_ids)).all()
        user_cache = {
            u.id: " ".join(filter(None, [u.first_name, u.last_name])) for u in users
        }

        # Populate from cache
        for comment in comments:
            if comment.user_id:
                comment.user_name = user_cache.get(comment.user_id)

    # ==================== Subscription Helpers ====================

    def _add_subscriber(self, issue: Issue, user_id: UUID) -> None:
        """
        Add a user to the issue's subscribed list if not already present.
        Prevents duplicate entries.
        """
        user_id_str = str(user_id)
        existing = issue.subscribed or []
        if user_id_str not in existing:
            issue.subscribed = existing + [user_id_str]

    def _remove_subscriber(self, issue: Issue, user_id: UUID) -> None:
        """
        Remove a user from the issue's subscribed list.
        """
        user_id_str = str(user_id)
        existing = issue.subscribed or []
        if user_id_str in existing:
            issue.subscribed = [uid for uid in existing if uid != user_id_str]

    def set_issue_subscription(
        self,
        issue_uuid: UUID,
        user_id: UUID,
        subscribed: bool,
    ) -> Optional[Issue]:
        """
        Subscribe or unsubscribe a user from an issue based on `subscribed`.
        """
        issue = self.db.query(Issue).filter(Issue.id == issue_uuid).first()
        if not issue:
            return None
        try:
            if subscribed:
                self._add_subscriber(issue, user_id)
            else:
                self._remove_subscriber(issue, user_id)
            self.db.commit()
            self.db.refresh(issue)
            self._populate_user_names([issue])
            return issue
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_issue_by_id(self, identifier: UUID) -> Optional[Issue]:
        try:
            issue = self.db.query(Issue).options(selectinload(Issue.comments)).filter(Issue.id == identifier).first()
            if issue:
                self._populate_user_names([issue])
            return issue
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_all_issues(
        self,
        page: int = 1,
        page_size: int = 10,
        filters: Optional[Dict[str, any]] = None,
        sort_by: Optional[str] = "updated_at",
        sort_order: Optional[str] = "desc",
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Issue]:
        skip = (page - 1) * page_size
        query = self.db.query(Issue).options(selectinload(Issue.comments))

        query = self._apply_issue_filters(
            query=query,
            issue_model=Issue,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
            from_date=from_date,
            to_date=to_date,
        )

        try:
            issues = query.offset(skip).limit(page_size).all()
            self._populate_user_names(issues)
            return issues
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def search_all_issues(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 10,
        filters: Optional[Dict[str, any]] = None,
        sort_by: Optional[str] = "updated_at",
        sort_order: Optional[str] = "desc",
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Issue]:
        skip = (page - 1) * page_size
        query = self.db.query(Issue).options(selectinload(Issue.comments))

        query = self._apply_issue_filters(
            query=query,
            issue_model=Issue,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
            from_date=from_date,
            to_date=to_date,
        )

        # Apply search
        if keyword:
            query = query.filter(
                or_(
                    Issue.title.ilike(f"%{keyword}%"),
                    Issue.description.ilike(f"%{keyword}%"),
                )
            )

        try:
            issues = query.offset(skip).limit(page_size).all()
            self._populate_user_names(issues)
            return issues
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_issues_by_agent_task_id(
        self,
        agent_task_id: UUID,
        page: int = 1,
        page_size: int = 10,
        filters: Optional[Dict[str, any]] = None,
        sort_by: Optional[str] = "updated_at",
        sort_order: Optional[str] = "desc",
        keyword: Optional[str] = None,
    ) -> List[Issue]:
        skip = (page - 1) * page_size
        query = self.db.query(Issue).options(selectinload(Issue.comments)).filter(Issue.agent_task_ids.contains([str(agent_task_id)]))

        query = self._apply_issue_filters(
            query=query,
            issue_model=Issue,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Apply keyword search (optional)
        if keyword:
            query = query.filter(
                or_(
                    Issue.title.ilike(f"%{keyword}%"),
                    Issue.description.ilike(f"%{keyword}%"),
                )
            )

        try:
            issues = query.offset(skip).limit(page_size).all()
            self._populate_user_names(issues)
            return issues
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_issues_by_email_id(
        self,
        email_uuid: UUID,
        page: int = 1,
        page_size: int = 10,
        filters: Optional[Dict[str, any]] = None,
        sort_by: Optional[str] = "updated_at",
        sort_order: Optional[str] = "desc",
        keyword: Optional[str] = None,
    ) -> List[Issue]:
        skip = (page - 1) * page_size

        # Step 1: Get all task IDs for this email
        task_ids = self.db.query(AgentTask.id).filter(
            AgentTask.email_data_id == email_uuid
        ).all()
        task_id_list = [str(t.id) for t in task_ids]

        if not task_id_list:
            return []

        # Step 2: Find issues that contain any of these task IDs
        query = self.db.query(Issue).options(selectinload(Issue.comments)).filter(Issue.agent_task_ids.overlap(task_id_list))

        query = self._apply_issue_filters(
            query=query,
            issue_model=Issue,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Apply keyword search
        if keyword:
            query = query.filter(
                or_(
                    Issue.title.ilike(f"%{keyword}%"),
                    Issue.description.ilike(f"%{keyword}%"),
                )
            )

        try:
            issues = query.offset(skip).limit(page_size).all()
            self._populate_user_names(issues)
            return issues
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_agent_tasks_details_by_issue_id(self, issue_uuid: UUID) -> List[AgentTask]:
        try:
            issue = self.db.query(Issue).filter(Issue.id == issue_uuid).first()
            if not issue or not issue.agent_task_ids:
                return []

            tasks = (
                self.db.query(AgentTask)
                .filter(AgentTask.id.in_(issue.agent_task_ids))
                .all()
            )

            # Batch fetch agent details
            agent_ids = {task.agent_id for task in tasks if task.agent_id}
            agent_cache = {}
            if agent_ids:
                agents = self.db.query(Agent).filter(Agent.id.in_(agent_ids)).all()
                agent_cache = {a.id: {"name": a.name, "icon": a.icon} for a in agents}

            # Populate agent_name and agent_icon
            for task in tasks:
                if task.agent_id and task.agent_id in agent_cache:
                    task.agent_name = agent_cache[task.agent_id]["name"]
                    task.agent_icon = agent_cache[task.agent_id]["icon"]

            return tasks
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_issue_filters(
        self,
        page: int = 1,
        page_size: int = 10,
        sort_by: Optional[str] = "issue_count",
        sort_order: Optional[str] = "desc",
    ) -> Dict:
        skip = (page - 1) * page_size
        try:
            # Query to group by created_by and count issues
            query = (
                self.db.query(
                    Issue.created_by.label("user_id"),
                    func.count(Issue.id).label("issue_count"),
                )
                .filter(Issue.created_by.isnot(None))
                .group_by(Issue.created_by)
            )

            # Apply sorting
            if sort_by == "issue_count":
                order = (
                    asc(func.count(Issue.id))
                    if sort_order == "asc"
                    else desc(func.count(Issue.id))
                )
            else:
                order = desc(func.count(Issue.id))
            query = query.order_by(order)

            results = query.offset(skip).limit(page_size).all()

            # Batch fetch user names in ONE query
            user_ids = {row.user_id for row in results if row.user_id}
            user_cache = {}
            if user_ids:
                users = self.db.query(User).filter(User.id.in_(user_ids)).all()
                user_cache = {
                    u.id: " ".join(filter(None, [u.first_name, u.last_name]))
                    for u in users
                }

            # Build response with user names from cache
            users = []
            for row in results:
                users.append(
                    {
                        "user_id": row.user_id,
                        "user_name": user_cache.get(row.user_id),
                        "issue_count": row.issue_count,
                    }
                )

            return {"users": users}

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return {"users": []}

    def search_issue_filters(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 10,
        filters: Optional[Dict[str, any]] = None,
        sort_by: Optional[str] = "issue_count",
        sort_order: Optional[str] = "desc",
    ) -> Dict:
        skip = (page - 1) * page_size
        try:
            # Query to group by created_by and count issues
            query = (
                self.db.query(
                    Issue.created_by.label("user_id"),
                    func.count(Issue.id).label("issue_count"),
                )
                .join(User, Issue.created_by == User.id)
                .filter(Issue.created_by.isnot(None))
            )

            query = self._apply_issue_filters(
                query=query,
                issue_model=Issue,
                filters=filters,
                sort_by=None,  # keep this method's existing count-based sorting
            )

            # Apply search by user name
            if keyword:
                query = query.filter(
                    or_(
                        User.first_name.ilike(f"%{keyword}%"),
                        User.last_name.ilike(f"%{keyword}%"),
                    )
                )

            # Group by after filtering
            query = query.group_by(Issue.created_by)

            # Apply sorting
            if sort_by == "issue_count":
                order = (
                    asc(func.count(Issue.id))
                    if sort_order == "asc"
                    else desc(func.count(Issue.id))
                )
            else:
                order = desc(func.count(Issue.id))
            query = query.order_by(order)

            results = query.offset(skip).limit(page_size).all()

            # Batch fetch user names in ONE query
            user_ids = {row.user_id for row in results if row.user_id}
            user_cache = {}
            if user_ids:
                users = self.db.query(User).filter(User.id.in_(user_ids)).all()
                user_cache = {
                    u.id: " ".join(filter(None, [u.first_name, u.last_name]))
                    for u in users
                }

            # Build response with user names from cache
            users = []
            for row in results:
                users.append(
                    {
                        "user_id": row.user_id,
                        "user_name": user_cache.get(row.user_id),
                        "issue_count": row.issue_count,
                    }
                )

            return {"users": users}

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return {"users": []}

    def delete_issue(self, issue_uuid: UUID) -> bool:
        issue = self.db.query(Issue).filter(Issue.id == issue_uuid).first()
        if not issue:
            return False
        try:
            self.db.delete(issue)
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return False

    # ==================== Issue Comment Functions ====================

    def create_issue_comment(
        self,
        comment_data: IssueCommentCreate,
        user_id: UUID,
    ) -> Optional[IssueComment]:
        # Validate issue existence for clearer API errors than FK failures.
        if comment_data.issue_id:
            issue_exists = self.db.query(Issue.id).filter(Issue.id == comment_data.issue_id).first()
            if not issue_exists:
                raise HTTPException(
                    status_code=404,
                    detail="Issue not found. Cannot create comment for non-existent issue.",
                )

        data = comment_data.model_dump()
        data["user_id"] = user_id

        new_comment = IssueComment(**data)
        try:
            self.db.add(new_comment)

            # Auto-subscribe the commenter to the issue
            if comment_data.issue_id:
                issue = self.db.query(Issue).filter(Issue.id == comment_data.issue_id).first()
                if issue:
                    self._add_subscriber(issue, user_id)

            self.db.commit()
            self.db.refresh(new_comment)
            return new_comment
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return None

    def update_issue_comment(
        self,
        comment_uuid: UUID,
        comment_data: IssueCommentUpdate,
    ) -> Optional[IssueComment]:
        comment = (
            self.db.query(IssueComment).filter(IssueComment.id == comment_uuid).first()
        )
        if not comment:
            return None
        try:
            update_fields = {
                k: v for k, v in comment_data.model_dump().items() if v is not None
            }
            for key, value in update_fields.items():
                if hasattr(comment, key):
                    setattr(comment, key, value)
            self.db.commit()
            self.db.refresh(comment)
            return comment
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_issue_comment_by_id(self, identifier: UUID) -> Optional[IssueComment]:
        try:
            comment = (
                self.db.query(IssueComment)
                .filter(IssueComment.id == identifier)
                .first()
            )
            if comment:
                self._populate_comment_user_names([comment])
            return comment
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_comments_by_issue_id(
        self,
        issue_id: UUID,
        page: int = 1,
        page_size: int = 10,
        sort_by: Optional[str] = "created_at",
        sort_order: Optional[str] = "asc",
    ) -> List[IssueComment]:
        skip = (page - 1) * page_size
        query = self.db.query(IssueComment).filter(IssueComment.issue_id == issue_id)

        # Apply sorting
        if hasattr(IssueComment, sort_by):
            order = (
                asc(getattr(IssueComment, sort_by))
                if sort_order == "asc"
                else desc(getattr(IssueComment, sort_by))
            )
            query = query.order_by(order)

        try:
            comments = query.offset(skip).limit(page_size).all()
            self._populate_comment_user_names(comments)
            return comments
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def delete_issue_comment(self, comment_uuid: UUID) -> bool:
        comment = (
            self.db.query(IssueComment).filter(IssueComment.id == comment_uuid).first()
        )
        if not comment:
            return False
        try:
            self.db.delete(comment)
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return False
