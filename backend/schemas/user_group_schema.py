# Default libraries
from datetime import datetime
from typing import Optional, List
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints


class UserGroupBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    description: Optional[str] = None
    data_access: Optional[dict] = None
    app_access: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class UserGroupCreate(UserGroupBase):
    pass


class UserGroupUpdate(UserGroupBase):
    name: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore
    key: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore


class UserGroupDetail(UserGroupBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class UserGroupResponse(BaseModel):
    user_groups: List[UserGroupDetail]
    total: int
