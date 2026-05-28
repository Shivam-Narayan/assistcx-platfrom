# Default libraries
from datetime import datetime
from typing import Any, Dict, Optional, List
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints


class AgentLLMBase(BaseModel):
    llm_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    data: Dict[str, Any]

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

class DefaultAgentLLM(AgentLLMBase):
    pass


class AgentLLMCreate(AgentLLMBase):
    pass


class AgentLLMUpdate(AgentLLMBase):
    llm_key: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore
    data: Optional[Dict[str, Any]] = None


class AgentLLMDetail(BaseModel):
    id: UUID
    llm_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    name: Optional[str] = None
    description: Optional[str] = None
    integration_key: Optional[str] = None
    model_name: Optional[str] = None
    provider: Optional[str] = None
    llm_config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class AgentLLMResponse(BaseModel):
    agent_llms: List[AgentLLMDetail]

