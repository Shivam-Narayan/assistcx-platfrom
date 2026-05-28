# Default libraries
from datetime import datetime
from typing import Optional, Dict, List
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints


class IntegrationBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    description: Optional[str] = None
    logo_url: Optional[str] = None
    tags: List
    auth_type: Optional[str] = None
    auth_schema: Optional[str] = None
    integration_config: Optional[Dict] = None


class DefaultIntegration(IntegrationBase):
    pass


class IntegrationDetail(IntegrationBase):
    id: UUID
    auth_schema_fields: Optional[Dict] = None
    is_active: Optional[bool] = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class IntegrationResponse(BaseModel):
    integrations: List[IntegrationDetail]
    markdown_content: Optional[str] = None
    total: int


class IntegrationTags(BaseModel):
    tags: List[str]


class Action(BaseModel):
    id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    action: Optional[str] = None
    type: Optional[str] = None


class IntegrationBindings(BaseModel):
    id: UUID
    key: str
    integration_type: str
    actions: List[Action]


class IntegrationCredentials(BaseModel):
    id: UUID
    key: str
    preset: Optional[Dict] = None
    credentials: Optional[Dict] = None


class IntegrationActivate(BaseModel):
    key: str
    preset: Dict
    credentials: Dict
