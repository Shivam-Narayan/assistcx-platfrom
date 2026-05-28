# Default libraries
from datetime import datetime
from typing import Optional, List, Any
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

# Custom libraries
from configs.integrations_v4 import INTEGRATIONS
from configs.agent_tools_data import BASIC_AGENT_TOOLS


def _valid_tool_keys() -> set:
    return {t.get("action") for t in BASIC_AGENT_TOOLS if t.get("action")}


def _valid_provider_keys() -> set:
    return {i.get("key") for i in INTEGRATIONS if i.get("key")}


class ToolBindingBase(BaseModel):
    agent_id: UUID
    connection_id: UUID
    provider_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=64)]
    tool_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=128)]

    @field_validator("provider_key")
    @classmethod
    def validate_provider_key(cls, v: str) -> str:
        if v not in _valid_provider_keys():
            raise ValueError(f"Invalid provider_key. Must be one of: {', '.join(sorted(_valid_provider_keys()))}")
        return v

    @field_validator("tool_key")
    @classmethod
    def validate_tool_key(cls, v: str) -> str:
        valid = _valid_tool_keys()
        if v not in valid:
            raise ValueError(f"Invalid tool_key. Must be one of (e.g.): {', '.join(sorted(valid)[:8])}...")
        return v

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ToolBindingCreate(ToolBindingBase):
    pass


class ToolBindingUpdate(ToolBindingBase):
    agent_id: Optional[UUID] = None
    connection_id: Optional[UUID] = None
    provider_key: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=64)]] = None
    tool_key: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=128)]] = None

    @field_validator("provider_key")
    @classmethod
    def validate_provider_key(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in _valid_provider_keys():
            raise ValueError(f"Invalid provider_key. Must be one of: {', '.join(sorted(_valid_provider_keys()))}")
        return v

    @field_validator("tool_key")
    @classmethod
    def validate_tool_key(cls, v: str) -> str:
        valid = _valid_tool_keys()
        if v not in valid:
            raise ValueError(f"Invalid tool_key. Must be one of (e.g.): {', '.join(sorted(valid)[:8])}...")
        return v

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ToolBindingDetail(ToolBindingBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ToolBindingResponse(BaseModel):
    tool_bindings: List[ToolBindingDetail]