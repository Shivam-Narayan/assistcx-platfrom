# Default libraries
from datetime import datetime
from typing import Dict, Optional, List
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints


class OrganizationBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    tenant_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    address: Optional[Dict] = None
    contact_info: Optional[Dict] = None
    active: Optional[bool] = True


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(OrganizationBase):
    name: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore
    tenant_code: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore


class OrganizationDetail(OrganizationBase):
    id: UUID
    db_schema: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class OrganizationResponse(BaseModel):
    organizations: List[OrganizationDetail]
    total: int


class OrganizationAlembicMigration(BaseModel):
    organization_schemas: List[str]
