# backend/configs/integrations_v4.py
"""
Integrations Configuration (v4)
===============================
Integration definitions with support for multiple auth schemas per integration.

Each integration defines:
- key: Unique identifier (used in code)
- name: Display name for UI
- description: What this integration does
- logo_url: Icon for UI
- tags: Categorization
- supported_auth_schemas: Array of auth schema keys from auth_schemas_v4.py
- integration_config: Metadata (type, supports_triggers, supports_actions)
- service_types: What services this provides (email, storage, llm, etc.)

Auth schemas are defined in auth_schemas_v4.py
Triggers are defined in triggers_v4.py
"""

from typing import Dict, Any, List


# =============================================================================
# INTEGRATIONS
# =============================================================================

INTEGRATIONS: List[Dict[str, Any]] = [
    # =========================================================================
    # MICROSOFT 365
    # =========================================================================
    {
        "key": "outlook",
        "name": "Outlook",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/outlook.svg",
        "tags": ["email", "calendar", "productivity"],
        "description": "Microsoft Outlook integration for email management, calendar sync, and task automation through Microsoft Graph API.",
        "supported_auth_schemas": [
            "microsoft_graph_client_credentials",  # App-only (for background services, triggers)
            "microsoft_graph_mail",  # User delegated (for personal mailbox)
        ],
        "integration_config": {
            "integration_type": "tool",
            "supports_triggers": True,
            "supports_actions": True,
        },
        "service_types": ["email", "calendar"],
    },
    # =========================================================================
    # LLM PROVIDERS
    # =========================================================================
    {
        "key": "openai",
        "name": "OpenAI",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/openai.svg",
        "tags": ["language_model", "ai"],
        "description": "OpenAI API integration for GPT models, embeddings, and AI capabilities.",
        "supported_auth_schemas": ["openai_auth"],
        "integration_config": {
            "integration_type": "agent_llm",
            "supports_triggers": False,
            "supports_actions": True,
        },
        "service_types": ["llm"],
    },
    # =========================================================================
    # AWS S3
    # =========================================================================
    {
        "key": "aws_s3",
        "name": "AWS S3",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/s3_bucket.svg",
        "tags": ["storage", "files", "aws"],
        "description": "AWS S3 integration for object storage. Upload, download, and manage files in S3 buckets using connection-based credentials.",
        "supported_auth_schemas": ["aws_s3_auth"],
        "integration_config": {
            "integration_type": "tool",
            "supports_triggers": True,
            "supports_actions": True,
        },
        "service_types": ["storage"],
    },
    # =========================================================================
    # EXA SEARCH
    # =========================================================================
    {
        "key": "exa",
        "name": "Exa",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/exa.svg",
        "tags": ["search", "web"],
        "description": "Exa web search API for AI applications. Retrieve high-quality, relevant web content using natural language queries.",
        "supported_auth_schemas": ["exa_auth"],
        "integration_config": {
            "integration_type": "tool",
            "supports_triggers": False,
            "supports_actions": True,
        },
        "service_types": ["search"],
    },
    # =========================================================================
    # Add more integrations as needed:
    # - sharepoint (supported_auth_schemas: ["microsoft_graph_client_credentials"])
    # - aws_s3 (supported_auth_schemas: ["aws_s3_auth"])
    # - openai (supported_auth_schemas: ["openai_auth"])
    # - anthropic (supported_auth_schemas: ["anthropic_auth"])
    # - gemini (supported_auth_schemas: ["gemini_auth"])
    # =========================================================================
]
