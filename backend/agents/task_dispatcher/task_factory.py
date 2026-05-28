# Custom libraries
from logger import configure_logging

# Default libraries
from datetime import datetime
from uuid import UUID
from typing import List, Dict, Optional, Any

# Database modules
from sqlalchemy.orm import Session
from repository.attachment_repository import AttachmentRepository
from repository.email_repository import EmailRepository
from repository.agent_task_repository import AgentTaskRepository
from schemas.email_schema import EmailDetail
from schemas.attachment_schema import AttachmentDetail

# Installed libraris
from sqlalchemy import text

logger = configure_logging(__name__)

AGENT_CONFIG_PRESET = {
    "split_task_by_records": True,
    "split_task_by_attachments": True,
}


class TaskFactory:

    def __init__(self, db: Session, agent: dict, email: dict):
        self.db = db
        self.agent = agent
        self.email = email
        self.agent_config = self.agent.get("agent_config") or AGENT_CONFIG_PRESET

    def _get_attachments(self) -> List[AttachmentDetail]:
        try:
            email_data_id = self.email.get("id")
            attachment_repository = AttachmentRepository(db=self.db)
            attachments = attachment_repository.get_attachment_by_email(
                email_data_id=email_data_id
            )
            return [
                AttachmentDetail.model_validate(attachment)
                for attachment in attachments
            ]
        except Exception as e:
            logger.error(f"Error in fetching attachments: {e}")
            return []

    def _generate_task_data(
        self,
        base_task_data: dict,
        task_order: str,
        attachments: List[AttachmentDetail],
        records: List[dict],
    ) -> dict:
        """Generate task data with non-empty values."""
        task_data = base_task_data.copy()
        task_data["task_order"] = task_order

        # Append counter to title if multiple tasks (not "1 of 1")
        if task_order != "1 of 1":
            task_data["title"] = f"{base_task_data['title']} - Task {task_order}"

        if attachments:
            task_data["attachments"] = [
                {
                    "id": str(attachment.id),
                    "name": attachment.file_name,
                    "type": attachment.file_type,
                    "size": attachment.size,
                }
                for attachment in attachments
            ]

        if records:
            task_data["additional_data"] = {"records": records}

        return task_data

    def _generate_attachment_tasks(
        self,
        task_repository: AgentTaskRepository,
        attachments: List[AttachmentDetail],
        base_task_data: dict,
    ) -> List[UUID]:
        """Generate attachment tasks."""
        task_list = []
        for idx, attachment in enumerate(attachments, 1):
            task_data = self._generate_task_data(
                base_task_data,
                f"{idx} of {len(attachments)}",
                [attachment],
                [],
            )
            task = task_repository.create_task(task_data)
            if task:
                task_list.append(task.id)
        return task_list

    def _generate_record_tasks(
        self,
        task_repository: AgentTaskRepository,
        records: List[dict],
        base_task_data: dict,
    ) -> List[UUID]:
        """Generate record tasks."""
        task_list = []
        for idx, record in enumerate(records, 1):
            task_data = self._generate_task_data(
                base_task_data, f"{idx} of {len(records)}", [], [record]
            )
            task = task_repository.create_task(task_data)
            if task:
                task_list.append(task.id)
        return task_list

    def _generate_single_task(
        self,
        task_repository: AgentTaskRepository,
        attachments: List[AttachmentDetail],
        records: List[dict],
        base_task_data: dict,
    ) -> List[UUID]:
        """Generate a single task."""
        task_data = self._generate_task_data(
            base_task_data,
            "1 of 1",
            attachments,
            records,
        )
        task = task_repository.create_task(task_data)
        return [task.id] if task else []

    def generate_tasks(self) -> List[UUID]:
        """
        Generate tasks for the agent.
        """
        attachments = self._get_attachments()
        records = self.email.get("records", [])

        task_repository = AgentTaskRepository(self.db)

        base_task_data = {
            "email_data_id": self.email.get("id"),
            "title": self.email.get("subject"),
            "description": f"{self.email.get('email_body')}",
            "progress": [
                {
                    "status": "QUEUED",
                    "timestamp": str(datetime.now()),
                }
            ],
            "agent_id": self.email.get("agent_id"),
        }

        if self.agent_config.get("split_task_by_attachments") and attachments:
            return self._generate_attachment_tasks(
                task_repository, attachments, base_task_data
            )
        elif self.agent_config.get("split_task_by_records") and records:
            return self._generate_record_tasks(task_repository, records, base_task_data)
        else:
            return self._generate_single_task(
                task_repository, attachments, records, base_task_data
            )
