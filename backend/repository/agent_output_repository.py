# Custom libraries
from logger import configure_logging
from schemas.agent_output_schema import AgentOutputResponse

# Database modules
from models.agent_output import AgentOutput

# Default libraries
from typing import Optional, Dict, List
from uuid import UUID

# Installed libraries
from sqlalchemy import asc, desc, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


logger = configure_logging(__name__)


class AgentOutputRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_agent_output(self, output_data: dict) -> Optional[AgentOutput]:
        new_output = AgentOutput(**output_data)
        try:
            self.db.add(new_output)
            self.db.commit()
            self.db.refresh(new_output)
            return new_output
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_agent_output(
        self, output_uuid: UUID, update_data: dict
    ) -> Optional[AgentOutput]:
        output = (
            self.db.query(AgentOutput).filter(AgentOutput.id == output_uuid).first()
        )
        if not output:
            return None

        try:
            for key, value in update_data.items():
                setattr(output, key, value)
            self.db.commit()
            self.db.refresh(output)
            return output
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_agent_output_by_id(
        self, output_uuid: UUID
    ) -> Optional[AgentOutputResponse]:
        try:
            agent_output = (
                self.db.query(AgentOutput).filter(AgentOutput.id == output_uuid).first()
            )

            if agent_output:
                attempts = (
                    self.db.query(
                        AgentOutput.id,
                        AgentOutput.agent_task_id,
                        AgentOutput.created_at,
                    )
                    .filter(AgentOutput.agent_task_id == agent_output.agent_task_id)
                    .order_by(AgentOutput.created_at.desc())
                    .all()
                )
            else:
                attempts = []

            return {
                "agent_output": agent_output,
                "attempts": attempts,
                "total": len(attempts),
            }
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_agent_output_by_agent_task(
        self, agent_task_id: UUID
    ) -> Optional[AgentOutputResponse]:
        """
        Retrieves agent output and attempts for a specific agent task.
        """
        try:
            query = (
                self.db.query(AgentOutput)
                .filter(AgentOutput.agent_task_id == agent_task_id)
                .order_by(AgentOutput.created_at.desc())
            )

            # Fetch the latest agent output
            agent_output = query.first()

            # Fetch all attempts for the agent task
            attempts = query.with_entities(
                AgentOutput.id, AgentOutput.agent_task_id, AgentOutput.created_at
            ).all()

            return {
                "agent_output": agent_output,
                "attempts": attempts,
                "total": len(attempts),
            }
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_agent_outputs_by_agent_task_and_agent(
        self,
        agent_task_id: UUID,
        agent_id: Optional[UUID] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> List[AgentOutput]:
        query = self.db.query(AgentOutput)

        # Fetch data for specific email
        query = query.filter(AgentOutput.agent_task_id == agent_task_id)

        # Fetch data for specific agent if agent_id
        if agent_id:
            query = query.filter(AgentOutput.agent_id == agent_id)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(AgentOutput, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(AgentOutput, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(AgentOutput, key) == values)

        # Apply sorting
        if hasattr(AgentOutput, sort_by):
            order = (
                asc(getattr(AgentOutput, sort_by))
                if sort_order == "asc"
                else desc(getattr(AgentOutput, sort_by))
            )
            query = query.order_by(order)

        try:
            agent_outputs = query.all()
            return agent_outputs
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def update_output_by_task_id(
        self,
        task_id: UUID,
        output: str,
        execution_log: List[Dict],
        new_credits: int,
        new_token_usage: Dict,
        thread_id: str = None,
    ) -> Optional[AgentOutput]:
        """
        Updates the AgentOutput record for a given task_id and thread_id.

        - Overwrites: output, execution_log
        - Accumulates: credits_used, token_usage

        Args:
            task_id: Agent task UUID
            output: New output string (overwrites existing)
            execution_log: New execution log (overwrites existing)
            new_credits: Credits to add to existing credits_used
            new_token_usage: Token usage to merge with existing
            thread_id: Thread ID to scope the update to the current execution

        Returns:
            Updated AgentOutput or None if not found/error
        """
        try:
            # Get the output for this task, scoped to the current thread if provided
            query = self.db.query(AgentOutput).filter(
                AgentOutput.agent_task_id == task_id
            )
            if thread_id:
                query = query.filter(AgentOutput.thread_id == thread_id)
            existing_output = query.order_by(AgentOutput.created_at.desc()).first()

            if not existing_output:
                logger.warning(f"No existing output found for task_id: {task_id}")
                return None

            # Accumulate credits
            existing_credits = existing_output.credits_used or 0
            accumulated_credits = existing_credits + new_credits

            # Accumulate token usage
            existing_tokens = existing_output.token_usage or {}
            accumulated_tokens = {
                "total_input_tokens": existing_tokens.get("total_input_tokens", 0)
                + new_token_usage.get("total_input_tokens", 0),
                "total_output_tokens": existing_tokens.get("total_output_tokens", 0)
                + new_token_usage.get("total_output_tokens", 0),
                "total_tokens": existing_tokens.get("total_tokens", 0)
                + new_token_usage.get("total_tokens", 0),
                "llm_calls_count": existing_tokens.get("llm_calls_count", 0)
                + new_token_usage.get("llm_calls_count", 0),
                # Append new token details to existing
                "token_details": existing_tokens.get("token_details", [])
                + new_token_usage.get("token_details", []),
            }

            # Update fields
            existing_output.output = output
            existing_output.execution_log = execution_log
            existing_output.credits_used = accumulated_credits
            existing_output.token_usage = accumulated_tokens

            self.db.commit()
            self.db.refresh(existing_output)

            logger.info(
                f"Updated output for task_id={task_id}: "
                f"credits={existing_credits}+{new_credits}={accumulated_credits}"
            )
            return existing_output

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error in update_output_by_task_id: {e}")
            return None

    def get_outputs_by_task_ids(
        self, task_ids: List[UUID]
    ) -> Dict[UUID, AgentOutputResponse]:
        """
        OPTIMIZED: Batch fetch agent outputs for multiple agent tasks.

        Eliminates N+1 query problem by fetching all outputs in a single query.

        Performance: For N tasks:
        - Before: N queries (1 per task)
        - After: 1 query total

        Args:
            task_ids: List of agent task UUIDs to fetch outputs for

        Returns:
            Dictionary mapping task_id to AgentOutputResponse with:
                - agent_output: Latest output for the task
                - attempts: List of all attempts for the task
                - total: Number of attempts
        """
        if not task_ids:
            return {}

        try:
            # STEP 1: Batch fetch all outputs for all tasks (1 query)
            all_outputs = (
                self.db.query(AgentOutput)
                .filter(AgentOutput.agent_task_id.in_(task_ids))
                .order_by(AgentOutput.agent_task_id, AgentOutput.created_at.desc())
                .all()
            )

            # STEP 2: Group outputs by task_id (in-memory operation)
            result = {}
            for task_id in task_ids:
                # Get all outputs for this task
                task_outputs = [
                    output for output in all_outputs if output.agent_task_id == task_id
                ]

                # Latest output is the first one (due to desc ordering)
                latest_output = task_outputs[0] if task_outputs else None

                # Create attempts list with minimal data
                attempts = [
                    {
                        "id": output.id,
                        "agent_task_id": output.agent_task_id,
                        "created_at": output.created_at,
                    }
                    for output in task_outputs
                ]

                result[task_id] = {
                    "agent_output": latest_output,
                    "attempts": attempts,
                    "total": len(attempts),
                }

            return result

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error in get_outputs_by_task_ids: {e}")
            return {}
