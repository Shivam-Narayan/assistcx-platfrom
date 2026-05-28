# Default libraries
from datetime import datetime
from typing import Optional, Dict, List
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator


class UserBase(BaseModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6)]  # type: ignore
    first_name: Optional[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    ] = None
    last_name: Optional[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    ] = None
    user_id: Optional[str] = None
    password: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=6)]] = None  # type: ignore
    user_config: Optional[Dict] = None
    role_id: Optional[UUID] = None
    data_access: Optional[Dict] = None
    # app_access: Optional[Dict] = None
    user_group_ids: Optional[List[str]] = None

    @field_validator("email", mode="before")
    def lowercase_email(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return v.strip().lower()
        return v

    @field_validator("first_name", "last_name")
    def validate_name(cls, v):
        # Check if contains only letters, numbers, underscores, hyphens, and periods
        if v and not all(c.isalnum() or c in ("_", "-", ".", " ") for c in v):
            raise ValueError(
                "Name can only contain letters, numbers, underscores, hyphens, and periods"
            )
        return v


class UserCreate(UserBase):
    first_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    last_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    password: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6)]  # type: ignore
    role_id: UUID


class UserUpdate(UserBase):
    email: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=6)]] = None  # type: ignore


class UserDetail(UserBase):
    id: UUID
    role_key: Optional[str] = None
    user_group_keys: Optional[List[str]] = None
    account_status: Optional[str] = None
    last_login: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True, protected_namespaces=(), exclude={"password"}
    )


class UserResponse(BaseModel):
    users: List[UserDetail]
    total: int


class UserLogin(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    db_schema: Optional[str] = None

    @field_validator("email", mode="before")
    def lowercase_email(cls, v: str) -> str:
        if v:
            return v.strip().lower()
        return v


class UserAuthentication(BaseModel):
    token_type: str = "Bearer"
    user_uuid: Optional[UUID] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


class Message(BaseModel):
    message: str


# ── SSO Schemas ────────────────────────────────────────────────────────


class EmailDiscoverRequest(BaseModel):
    email: str

    @field_validator("email", mode="before")
    def lowercase_email(cls, v: str) -> str:
        if v:
            return v.strip().lower()
        return v


class EmailDiscoverResponse(BaseModel):
    auth_method: str = "password"
    sso_provider: Optional[str] = None
    sso_provider_name: Optional[str] = None


class SSOExchangeRequest(BaseModel):
    code: str


class TeamsAuthRequest(BaseModel):
    teams_token: str


class SSOSettingsResponse(BaseModel):
    auth_method: str = "password"
    sso_provider: Optional[str] = None
    sso_provider_name: Optional[str] = None
    sso_client_id: Optional[str] = None
    sso_tenant_id: Optional[str] = None
    sso_well_known_url: Optional[str] = None
    sso_scopes: str = "openid email profile"
    client_secret_set: bool = False
    callback_url: Optional[str] = None


class SSOSettingsUpdate(BaseModel):
    auth_method: Optional[str] = None
    sso_provider: Optional[str] = None
    sso_provider_name: Optional[str] = None
    sso_client_id: Optional[str] = None
    sso_client_secret: Optional[str] = None
    sso_tenant_id: Optional[str] = None
    sso_well_known_url: Optional[str] = None
    sso_scopes: Optional[str] = None

    @field_validator("auth_method")
    def validate_auth_method(cls, v):
        if v is not None and v not in ("password", "sso", "flexible"):
            raise ValueError("auth_method must be 'password', 'sso', or 'flexible'")
        return v

    @field_validator("sso_provider")
    def validate_sso_provider(cls, v):
        if v is not None and v not in ("microsoft", "google", "oidc"):
            raise ValueError("sso_provider must be 'microsoft', 'google', or 'oidc'")
        return v
