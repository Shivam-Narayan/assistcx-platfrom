# Default libraries
from datetime import datetime
from typing import Optional, List, Dict
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints


class ModuleAccess(BaseModel):
    level: str = "none"  # none, view, edit, full


class RolePermissions(BaseModel):
    modules: Dict[str, ModuleAccess] = {}


class UserRoleBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    role_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    description: Optional[str] = None
    default_role: Optional[bool] = False
    role_permissions: Optional[dict] = None


class DefaultUserRole(BaseModel):
    name: str
    role_key: str
    description: Optional[str] = None
    default_role: Optional[bool] = False
    role_permissions: Optional[dict] = None


class UserRoleCreate(UserRoleBase):
    pass


class UserRoleUpdate(UserRoleBase):
    pass


class UserRoleDetail(UserRoleBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class UserRoleResponse(BaseModel):
    user_roles: List[UserRoleDetail]
    total: int
