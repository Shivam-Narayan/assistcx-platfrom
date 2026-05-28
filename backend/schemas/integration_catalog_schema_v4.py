# Default libraries
from typing import Optional, Dict, Any, List

# Installed libraries
from pydantic import BaseModel, ConfigDict, Field


class IntegrationCatalogItem(BaseModel):
    """Single integration config for catalog API (list of details only)."""

    key: str
    name: str
    logo_url: Optional[str] = None
    tags: List[str] = []
    description: Optional[str] = None
    supported_auth_schemas: List[str] = []
    integration_config: Optional[Dict[str, Any]] = None
    service_types: List[str] = []
    # Lists of trigger/tool configs (same shape as trigger-catalog / agent tool entries).
    triggers: List[Dict[str, Any]] = Field(default_factory=list)
    tools: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class AuthSchemaCatalogItem(BaseModel):
    """Single auth schema config for catalog API. Config has no 'key' field; key is the config dict key and is added in the repository."""

    key: str
    auth_type: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    docs_url: Optional[str] = None
    preset: Optional[Dict[str, Any]] = None
    input_fields: Optional[Dict[str, Any]] = None
    token_fields: Optional[Dict[str, Any]] = None
    connection_config_fields: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class TriggerCatalogItem(BaseModel):
    """Single trigger config for catalog API (list of details only)."""

    slug: str
    name: str
    description: Optional[str] = None
    integration_key: Optional[str] = None
    is_enabled: Optional[bool] = None
    handler: Optional[Dict[str, Any]] = None
    trigger_config: Optional[Dict[str, Any]] = None
    input_schema: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
