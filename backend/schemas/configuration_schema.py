# Default libraries
from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID
from zoneinfo import available_timezones

# Installed libraries
from pydantic import BaseModel, ConfigDict, field_validator


# class DataStore(BaseModel):
#     storage_type: Annotated[str, StringConstraints(strip_whitespace=True)]
#     storage_bucket: Annotated[str, StringConstraints(strip_whitespace=True)]
#     storage_folder: Optional[
#         Annotated[str, StringConstraints(strip_whitespace=True)]
#     ] = "files"
#     storage_region: Optional[
#         Annotated[str, StringConstraints(strip_whitespace=True)]
#     ] = ""


class PreferencesInput(BaseModel):
    """Schema for configuration input - excludes assistant_enabled"""

    default_llm: Optional[str] = None
    fast_llm: Optional[str] = None
    default_email: Optional[str] = None
    timezone: Optional[str] = "UTC"
    theme: Optional[str] = None
    platform_alert_recipients: Optional[List[Any]] = []
    # data_store: DataStore

    @field_validator("timezone")
    def validate_timezone(cls, v):
        if v not in available_timezones():
            raise ValueError(f"Invalid timezone: {v}")
        return v


class Preferences(PreferencesInput):
    """Full preferences schema including assistant_enabled - used for responses"""

    assistant_enabled: Optional[bool] = False


class ConfigurationBase(BaseModel):
    preferences: Preferences

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ConfigurationCreate(BaseModel):
    """Schema for creating/updating configuration - uses PreferencesInput to exclude assistant_enabled"""

    preferences: PreferencesInput

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ConfigurationDetail(ConfigurationBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ConfigurationResponse(BaseModel):
    configurations: List[ConfigurationDetail]
    total: int


class StorageMount(BaseModel):
    storage_mount_points: Optional[List[str]] = []


class GrafanaAlertRequest(BaseModel):
    """Schema for receiving Grafana alert webhooks"""

    model_config = ConfigDict(extra="allow")

    # Accept any JSON payload from Grafana
    # The entire payload will be forwarded to email as-is
