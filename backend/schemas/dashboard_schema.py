# Default libraries
from typing import Optional

# Installed libraries
from pydantic import BaseModel
from uuid import UUID


class EmailCounts(BaseModel):
    email_count: int
    successful_count: int
    executing_count: int
    incomplete_count: int
    failed_count: int
    queued_count: int
    archived_count: int


class EmailMonthlyStats(BaseModel):
    month: str
    year: int
    count: int


class AgentTaskStats(BaseModel):
    agent_name: str
    count: int
    success_rate: float
    average_time: Optional[float] = None 


class EmailMailboxStats(BaseModel):
    mailbox_email: Optional[str] = None
    count: int


class TaskCounts(BaseModel):
    email_count: int
    task_count: int
    successful_count: int
    resolved_count: int
    executing_count: int
    incomplete_count: int
    failed_count: int
    queued_count: int
    archived_count: int
    success_rate: float  # percentage of successful tasks
    time_saved: Optional[float] = None  # in hours, include for now


class TaskMonthlyStats(BaseModel):
    month: str
    year: int
    count: int

class TaskVolumeStats(BaseModel):
    time_period: str
    count: int
