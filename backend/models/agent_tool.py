from sqlalchemy import ARRAY, String, Text, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from db_pool import Base
from datetime import datetime
from typing import Optional
import uuid


class AgentTool(
    Base
):  # NOTE: This model is heavily inspired from API requests, we shold consider refactoring it for better compatiblity with new type of tools.
    __tablename__ = "agent_tools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    tags: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    action: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    integration_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    api_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    method: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    endpoint: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    headers: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    path_params: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    query_params: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    body_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auth_type: Mapped[Optional[str]] = mapped_column(
        String, default=None, nullable=True
    )
    auth_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    tool_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


"""
Comments:
=========
Added columns:
- tags

Removed columns:
- tool_type
"""


"""
Put all of this into a single json b field in the database.
    api_type = Column(String)
    method = Column(String)
    endpoint = Column(String)
    content_type = Column(String)
    headers = Column(JSONB)
    path_params = Column(JSONB)
    query_params = Column(JSONB)
    body_template = Column(Text)
Simplify the inputs in webapp
"""

"""
The 'headers' column contains a dynamic JSONB object representing HTTP headers to be included in the API request. 
Each key-value pair in this object corresponds to a header name and its value.

Example:
{
    "Content-Type": "application/json",
    "Authorization": "Bearer {token}",
    "User-Agent": "MyApp/1.0"
}
----------------------------------------------------------
The 'path_params' column stores a dynamic JSONB object representing parameters to be interpolated into the API endpoint path.
Each key in this object corresponds to a placeholder in the endpoint, and its value will replace that placeholder.

Example (for an endpoint like "/api/v1/{resource}/{id}"):
{
    "resource": "users",
    "id": "{user_id}"
}
----------------------------------------------------------
The 'query_params' column contains a dynamic JSONB object representing query parameters to be appended to the API request URL.
Each key-value pair in this object will be converted to a query parameter in the URL.

Example:
{
    "limit": 10,
    "offset": 0,
    "sort": "created_at",
    "order": "desc"
}

Note: Values in these JSONB columns can include placeholders (e.g., "{token}", "{user_id}") which may be replaced 
with actual values at runtime, depending on the implementation of the API request logic.
----------------------------------------------------------
The 'api_type' column specifies the type of API this tool interacts with. It corresponds to the APIType enum and can have the following values:
- REST: Representational State Transfer API
- GraphQL: Graph Query Language API
- SOAP: Simple Object Access Protocol API
- gRPC: gRPC Remote Procedure Call API
- OData: Open Data Protocol API

Example: "REST"
----------------------------------------------------------
The 'method' column indicates the HTTP method used for the API request. It corresponds to the HTTPMethod enum and can have the following values:
- GET: Retrieve a resource
- POST: Create a new resource
- PUT: Update an existing resource (usually by replacing it entirely)
- DELETE: Remove a resource
- PATCH: Partially update an existing resource

Example: "POST"
----------------------------------------------------------
The 'auth_type' column specifies the authentication method used for the API. It corresponds to the AuthType enum and can have the following values:
- None: No authentication required
- Basic: Basic HTTP authentication (username and password)
- Bearer: Bearer token authentication
- OAuth2: OAuth 2.0 authentication flow
- APIKey: Authentication using an API key

Example: "Bearer"
----------------------------------------------------------
The 'auth_config' column is a JSONB field that stores the configuration details for the specified authentication type. The structure of this object varies depending on the auth_type:

For Basic auth:
{
    "username": "user",
    "password": "pass"
}

For Bearer auth:
{
    "token": "your_bearer_token_here"
}

For OAuth2 auth:
{
    "client_id": "your_client_id",
    "client_secret": "your_client_secret",
    "token_url": "https://api.example.com/oauth/token",
    "scopes": ["read", "write"]
}

For APIKey auth:
{
    "key": "your_api_key_here",
    "in": "header",  // or "query" if the API key should be sent as a query parameter
    "name": "X-API-Key"  // name of the header or query parameter
}
"""
