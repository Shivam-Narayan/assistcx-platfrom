# Default libraries
from datetime import datetime
from typing import Optional, Dict, Any, List
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, Field

# Custom libraries
from configs.integrations_v4 import INTEGRATIONS
from configs.auth_schemas_v4 import AUTH_SCHEMAS


class ConnectionBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=128)]
    provider_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=64)]
    auth_schema_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=64)]
    encrypted_token: Optional[str] = None
    connection_config: Optional[Dict[str, Any]] = None
    connection_metadata: Optional[Dict[str, Any]] = None
    is_active: bool = True
    auth_status: str = Field(default="valid", max_length=32)
    created_by: Optional[UUID] = None

    @field_validator('provider_key')
    @classmethod
    def validate_provider_key(cls, v: str) -> str:
        provider_keys = [integration.get("key") for integration in INTEGRATIONS]
        if v not in provider_keys:
            raise ValueError(f"Invalid provider_key. Must be one of: {', '.join(provider_keys)}")
        return v

    @field_validator('auth_schema_key')
    @classmethod
    def validate_auth_schema_key(cls, v: str) -> str:
        if v not in AUTH_SCHEMAS:
            available_schemas = ', '.join(AUTH_SCHEMAS.keys())
            raise ValueError(f"Invalid auth_schema_key. Must be one of: {available_schemas}")
        return v


    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ConnectionCreate(ConnectionBase):
    credentials: Dict[str, Any] = Field(..., min_length=1, description="Dict of credential key-value pairs (values encrypted server-side)")


class ConnectionUpdate(ConnectionBase):
    name: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=128)]] = None
    provider_key: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=64)]] = None
    auth_schema_key: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=64)]] = None
    credentials: Optional[Dict[str, Any]] = None

    @field_validator('provider_key')
    @classmethod
    def validate_provider_key(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        provider_keys = [integration.get("key") for integration in INTEGRATIONS]
        if v not in provider_keys:
            raise ValueError(f"Invalid provider_key. Must be one of: {', '.join(provider_keys)}")
        return v

    @field_validator('auth_schema_key')
    @classmethod
    def validate_auth_schema_key(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in AUTH_SCHEMAS:
            available_schemas = ', '.join(AUTH_SCHEMAS.keys())
            raise ValueError(f"Invalid auth_schema_key. Must be one of: {available_schemas}")
        return v

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ConnectionDetail(ConnectionBase):
    id: UUID
    user_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None
    last_validated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ConnectionResponse(BaseModel):
    connections: List[ConnectionDetail]


class ConnectionCredentials(BaseModel):
    id: UUID
    key: str
    preset: Dict[str, Any]
    credentials: Dict[str, Any]


class ConnectionHealthCheckResponse(BaseModel):
    id: UUID
    auth_status: str
    is_healthy: bool
    message: str
    error: Optional[str] = None