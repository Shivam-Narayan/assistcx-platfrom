# Default libraries
from datetime import datetime
from typing import Optional, List, Union, Dict, Any
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict


class AgentOutputBase(BaseModel):
    thread_id: Optional[str] = None
    output: Optional[Union[str, Dict[str, Any]]] = None
    agent_actions: Optional[Union[List[Dict[str, Any]], str]] = None
    execution_log: Optional[Union[List[Dict[str, Any]], str]] = None
    task_summary: Optional[str] = None
    credits_used: Optional[int] = None
    token_usage: Optional[Dict[str, Any]] = None



class AgentOutputDetail(AgentOutputBase):
    id: UUID
    agent_task_id: UUID
    agent_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class AgentOutputAttempt(BaseModel):
    id: UUID
    agent_task_id: UUID
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class AgentOutputUsageResponse(BaseModel):
    agent_task_uuid: UUID
    agent_output_uuid: Optional[UUID] = None
    credits_used: Optional[int] = None
    token_usage: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(protected_namespaces=())


class AgentOutputResponse(BaseModel):
    agent_outputs: List[AgentOutputDetail]
    attempts: Optional[List[AgentOutputAttempt]] = None
    total: int
