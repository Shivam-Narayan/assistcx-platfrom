# Default libraries
from datetime import datetime
from enum import Enum
from typing import Optional, Union, Any, Dict, List
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class AuthType(str, Enum):
    NONE = "None"
    BASIC = "Basic"
    BEARER = "Bearer"
    OAUTH2 = "OAuth2"
    API_KEY = "APIKey"


class BaseAuthConfig(BaseModel):
    pass


class BasicAuthConfig(BaseAuthConfig):
    username: str
    password: str


class BearerAuthConfig(BaseAuthConfig):
    token: str


class OAuth2AuthConfig(BaseAuthConfig):
    client_id: str
    client_secret: str
    token_url: str
    scope: Optional[str] = None


class APIKeyAuthConfig(BaseAuthConfig):
    api_key_name: str
    api_key: str
    api_key_location: str = Field(
        ..., description="Where to put the API key: 'header', 'query', or 'cookie'"
    )


class AuthConfig(BaseModel):
    auth_type: AuthType
    config: Union[
        BaseAuthConfig,
        BasicAuthConfig,
        BearerAuthConfig,
        OAuth2AuthConfig,
        APIKeyAuthConfig,
    ]


class AgentToolBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6)]  # type: ignore
    action: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6)]  # type: ignore
    description: Optional[str] = None
    icon: Optional[str] = "pencil-ruler"
    integration_key: Optional[str] = "api_tool"
    tags: Optional[List[str]] = None
    is_default: Optional[bool] = False
    is_enabled: Optional[bool] = False
    api_type: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore
    method: Optional[str] = None
    endpoint: Optional[str] = None
    content_type: Optional[str] = None
    headers: Optional[Dict[str, Any]] = None
    path_params: Optional[Dict[str, Any]] = None
    query_params: Optional[Dict[str, Any]] = None
    body_template: Optional[str] = None
    auth_type: Optional[str] = None
    auth_config: Optional[Dict[str, Any]] = None
    tool_config: Optional[Dict[str, Any]] = None


class DefaultAgentTool(AgentToolBase):
    pass


class AgentToolCreate(AgentToolBase):
    api_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]


class AgentToolUpdate(AgentToolBase):
    icon: Optional[str] = None
    name: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=6)]] = None  # type: ignore
    action: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=6)]] = None  # type: ignore

    @field_validator("action", mode="before")
    def force_action_none(cls, v):
        # Always set action to None to avoid updating it
        return None


class AgentToolDetail(AgentToolBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    input_schema: Optional[Dict[str, Any]] = None
    tool_call_schema: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class AgentToolResponse(BaseModel):
    agent_tools: List[AgentToolDetail]
    total: int


class AgentToolBulkUpdate(BaseModel):
    agent_tool_ids: List[UUID]


class AgentToolFilters(BaseModel):
    integrations: Optional[List[Dict[str, Any]]] = []


"""
class APIType:
    REST = "REST"
    GraphQL = "GraphQL"
    SOAP = "SOAP"
    gRPC = "gRPC"
    OData = "OData"


class HTTPMethod:
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class AuthType:
    None_ = "None"
    Basic = "Basic"
    Bearer = "Bearer"
    OAuth2 = "OAuth2"
    APIKey = "APIKey"


class RESTFields(BaseModel):
    endpoint: str
    method: HTTPMethod


class GraphQLFields(BaseModel):
    endpoint: str
    query: str


class SOAPFields(BaseModel):
    endpoint: str
    action: str
    xml_namespace: str


class gRPCFields(BaseModel):
    host: str
    port: int
    service: str
    method: str


class ODataFields(BaseModel):
    service_root: str
    entity_set: str


class NoneAuthConfig(BaseModel):
    pass


class BasicAuthConfig(BaseModel):
    username: str
    password: str


class BearerAuthConfig(BaseModel):
    token: str


class OAuth2AuthConfig(BaseModel):
    client_id: str
    client_secret: str
    token_url: HttpUrl
    scopes: List[str] = Field(default_factory=list)
    refresh_token: Optional[str] = None
    access_token: Optional[str] = None
    expires_at: Optional[int] = None


class APIKeyAuthConfig(BaseModel):
    key: str
    in_: str = Field(..., alias="in")  # 'header' or 'query'
    name: str
"""
