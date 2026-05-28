# Default libraries
from datetime import datetime
from typing import Optional, Dict, List
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict


class ModuleDetail(BaseModel):
    key: str
    name: str
    description: Optional[str] = None
    access_levels: List[str] = []
    web_routes: List[str] = []
    data_filters: List[str] = []


class PermissionResponse(BaseModel):
    modules: List[ModuleDetail]
    total: int


class DataAccessPermission(BaseModel):
    key: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    data_filters: Optional[Dict[str, List[str]]] = None
    module: Optional[str] = None
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class DataAccessPermissionResponse(BaseModel):
    features: List[DataAccessPermission]
    total: int


class AppAccess(BaseModel):
    key: str
    name: str
    description: Optional[str] = None


class AppAccessResponse(BaseModel):
    app_access: List[AppAccess]
    total: int
