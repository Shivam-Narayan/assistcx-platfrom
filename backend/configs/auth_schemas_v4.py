# backend/configs/auth_schemas.py
"""
Auth Schemas Configuration (v4)
===============================
Centralized authentication schema definitions for integrations.

Each schema defines:
- auth_type: How authentication works (OAuth2App, OAuth2User, APIKey, etc.)
- display_name: Human-readable name for UI
- description: What this auth method does
- docs_url: Link to official API documentation
- preset: System-provided values (URLs, scopes, grant types)
- input_fields: What the user provides when creating a connection
- token_fields: What OAuth returns (for OAuth2User flows)
- provider_key: The integration key this auth schema belongs to (must match a key in integrations_v4.py)
- connection_config_fields: Optional non-sensitive config (e.g., AWS region)

Field Structure:
- label: Display label for UI
- description: Help text
- type: Input type (text, password, select)
- required: Whether field is required
- sensitive: Whether field should be encrypted
- example: Example value for UI hints
- default: Default value if not provided
- options: List of options for SELECT type
"""

from enum import Enum
from typing import Dict, Any, List, Optional


class AuthType(str, Enum):
    """Supported authentication types."""

    API_KEY = "APIKey"
    OAUTH2_APP = "OAuth2App"  # Client credentials (app-only, no user consent)
    OAUTH2_USER = "OAuth2User"  # Authorization code (user consent, redirect flow)
    AWS_SIGV4 = "AWSSignV4"
    BEARER = "Bearer"


class FieldType(str, Enum):
    """Input field types for UI rendering."""

    TEXT = "text"
    PASSWORD = "password"
    SELECT = "select"
    URL = "url"
    TEXTAREA = "textarea"


# =============================================================================
# AUTH SCHEMA DEFINITIONS
# =============================================================================

AUTH_SCHEMAS: Dict[str, Dict[str, Any]] = {
    # =========================================================================
    # MICROSOFT GRAPH (Outlook, SharePoint, etc.)
    # =========================================================================
    "microsoft_graph_client_credentials": {
        "provider_key": "outlook",
        "auth_type": AuthType.OAUTH2_APP.value,
        "display_name": "Microsoft Graph (App-Only)",
        "description": "OAuth2 client credentials for Microsoft Graph API. For background services like mailbox polling, sending emails from shared mailboxes. Does not require user consent.",
        "docs_url": "https://learn.microsoft.com/en-us/graph/auth-v2-service",
        "preset": {
            "token_url": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        "input_fields": {
            "client_id": {
                "label": "Client ID",
                "description": "Application (client) ID from Azure AD App Registration",
                "type": FieldType.TEXT.value,
                "required": True,
                "sensitive": False,
                "example": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            },
            "client_secret": {
                "label": "Client Secret",
                "description": "Client secret value from Azure AD",
                "type": FieldType.PASSWORD.value,
                "required": True,
                "sensitive": True,
            },
            "tenant_id": {
                "label": "Tenant ID",
                "description": "Directory (tenant) ID from Azure AD",
                "type": FieldType.TEXT.value,
                "required": True,
                "sensitive": False,
                "example": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            },
        },
    },
    # =========================================================================
    # LLM PROVIDERS
    # =========================================================================
    "openai_auth": {
        "provider_key": "openai",
        "auth_type": AuthType.API_KEY.value,
        "display_name": "OpenAI",
        "description": "API key authentication for OpenAI services (GPT-4, GPT-5, etc.)",
        "docs_url": "https://platform.openai.com/docs/api-reference/authentication",
        "preset": {
            "header_name": "Authorization",
            "header_prefix": "Bearer",
            "base_url": "https://api.openai.com/v1",
        },
        "input_fields": {
            "api_key": {
                "label": "OpenAI API Key",
                "description": "Your secret API key from OpenAI dashboard",
                "type": FieldType.PASSWORD.value,
                "required": True,
                "sensitive": True,
                "example": "sk-proj-xxxxxxxxxxxxxxxxxxxxxx",
            },
        },
    },
    # =========================================================================
    # MICROSOFT GRAPH - USER DELEGATED (One schema per feature)
    # =========================================================================
    "microsoft_graph_mail": {
        "provider_key": "outlook",
        "auth_type": AuthType.OAUTH2_USER.value,
        "display_name": "Microsoft Graph - Mail",
        "description": "OAuth2 delegated flow for Outlook Mail. Requires user consent. Use for personal mailbox access, sending emails as the signed-in user.",
        "docs_url": "https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview",
        "preset": {
            "authorization_url": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize",
            "token_url": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            "scope": "Mail.ReadWrite Mail.Send offline_access",
        },
        "input_fields": {
            "client_id": {
                "label": "Client ID",
                "description": "Application (client) ID from Azure AD App Registration",
                "type": FieldType.TEXT.value,
                "required": True,
                "sensitive": False,
                "example": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            },
            "client_secret": {
                "label": "Client Secret",
                "description": "Client secret value from Azure AD",
                "type": FieldType.PASSWORD.value,
                "required": True,
                "sensitive": True,
            },
            "tenant_id": {
                "label": "Tenant ID",
                "description": "Directory (tenant) ID from Azure AD. Use 'common' for multi-tenant apps.",
                "type": FieldType.TEXT.value,
                "required": True,
                "sensitive": False,
                "example": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                "default": "common",
            },
        },
        "token_fields": {
            "access_token": {"sensitive": True},
            "refresh_token": {"sensitive": True},
            "expires_at": {"type": "number"},
            "token_type": {"type": "text"},
        },
    },
    # =========================================================================
    # AWS S3
    # =========================================================================
    "aws_s3_auth": {
        "provider_key": "aws_s3",
        "auth_type": AuthType.AWS_SIGV4.value,
        "display_name": "AWS S3 (Access Keys)",
        "description": "AWS access key and secret for S3 bucket access. Use IAM user credentials with s3:GetObject, s3:PutObject, s3:ListBucket, s3:DeleteObject permissions.",
        "docs_url": "https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html",
        "input_fields": {
            "AWS_ACCESS_KEY_ID": {
                "label": "AWS Access Key ID",
                "description": "Access key ID from IAM user or role",
                "type": FieldType.TEXT.value,
                "required": True,
                "sensitive": False,
            },
            "AWS_SECRET_ACCESS_KEY": {
                "label": "AWS Secret Access Key",
                "description": "Secret access key from IAM user",
                "type": FieldType.PASSWORD.value,
                "required": True,
                "sensitive": True,
            },
        },
    },
    # =========================================================================
    # EXA SEARCH
    # =========================================================================
    "exa_auth": {
        "provider_key": "exa",
        "auth_type": AuthType.API_KEY.value,
        "display_name": "Exa",
        "description": "API key authentication for Exa web search API.",
        "docs_url": "https://docs.exa.ai/reference/search",
        "preset": {
            "header_name": "x-api-key",
            "base_url": "https://api.exa.ai",
        },
        "input_fields": {
            "api_key": {
                "label": "Exa API Key",
                "description": "Your secret API key from the Exa dashboard",
                "type": FieldType.PASSWORD.value,
                "required": True,
                "sensitive": True,
                "example": "your-exa-api-key",
            },
        },
    },
    # NOTE: Add more feature-specific schemas as needed:
    # - microsoft_graph_calendar: Calendars.ReadWrite offline_access
    # - microsoft_graph_sharepoint: Sites.Read.All Sites.ReadWrite.All offline_access
    # - microsoft_graph_onedrive: Files.ReadWrite.All offline_access
    # - microsoft_graph_teams: Chat.ReadWrite ChannelMessage.Send offline_access
}
