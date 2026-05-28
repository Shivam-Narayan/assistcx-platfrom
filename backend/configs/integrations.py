AUTH_SCHEMA_FIELDS = {
    "sharepoint_auth": {
        "preset": {
            "token_url": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            "scope": "https://graph.microsoft.com/.default",
        },
        "user": {
            "CLIENT_ID": {
                "name": "client_id",
                "label": "Client ID",
                "description": "The application (client) ID registered in Azure AD",
                "type": "text",
                "required": True,
                "example": "123e4567-e89b-12d3-a456-426614174000",
            },
            "CLIENT_SECRET": {
                "name": "client_secret",
                "label": "Client Secret",
                "description": "The client secret generated for the application in Azure AD",
                "type": "text",
                "required": True,
                "example": "your-client-secret-value",
            },
            "TENANT_ID": {
                "name": "tenant_id",
                "label": "Tenant ID",
                "description": "The directory (tenant) ID from Azure AD",
                "type": "text",
                "required": True,
                "example": "123e4567-e89b-12d3-a456-426614174000",
            },
        },
    },
    "openai_auth": {
        "preset": {},
        "user": {
            "API_KEY": {
                "name": "api_key",
                "label": "OpenAI API Key",
                "description": "Your secret API key from OpenAI",
                "type": "text",
                "required": True,
                "example": "sk-proj-your-actual-openai-api-key",
            }
        },
    },
    "aws_s3_auth": {
        "preset": {},
        "user": {
            "AWS_ACCESS_KEY_ID": {
                "name": "aws_access_key_id",
                "label": "AWS Access Key ID",
                "description": "The AWS access key ID for authentication",
                "type": "text",
                "required": True,
                "example": "AKIAIOSFODNN7EXAMPLE",
            },
            "AWS_SECRET_ACCESS_KEY": {
                "name": "aws_secret_access_key",
                "label": "AWS Secret Access Key",
                "description": "The AWS secret access key for authentication",
                "type": "text",
                "required": True,
                "example": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            },
        },
    },
    "outlook_auth": {
        "preset": {
            "token_url": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            "scope": "https://graph.microsoft.com/.default",
        },
        "user": {
            "CLIENT_ID": {
                "name": "client_id",
                "label": "Client ID",
                "description": "The application (client) ID registered in Azure AD",
                "type": "text",
                "required": True,
                "example": "123e4567-e89b-12d3-a456-426614174000",
            },
            "CLIENT_SECRET": {
                "name": "client_secret",
                "label": "Client Secret",
                "description": "The client secret generated for the application in Azure AD",
                "type": "text",
                "required": True,
                "example": "your-client-secret-value",
            },
            "TENANT_ID": {
                "name": "tenant_id",
                "label": "Tenant ID",
                "description": "The directory (tenant) ID from Azure AD",
                "type": "text",
                "required": True,
                "example": "123e4567-e89b-12d3-a456-426614174000",
            },
        },
    },
    "anthropic_auth": {
        "preset": {},
        "user": {
            "API_KEY": {
                "name": "api_key",
                "label": "Anthropic API Key",
                "description": "Your secret API key from Anthropic",
                "type": "text",
                "required": True,
                "example": "sk-proj-your-actual-anthropic-api-key",
            }
        },
    },
    "gemini_auth": {
        "preset": {},
        "user": {
            "API_KEY": {
                "name": "api_key",
                "label": "Gemini API Key",
                "description": "Your secret API key from Google for Gemini",
                "type": "text",
                "required": True,
                "example": "your-actual-gemini-api-key",
            }
        },
    },
}

INTEGRATIONS = [
    {
        "name": "Sharepoint",
        "key": "sharepoint",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/sharepoint.svg",
        "tags": ["file_management", "data_storage"],
        "description": "Share and manage content, knowledge, and applications to empower teamwork, quickly find information, and seamlessly collaborate across the organization.",
        "auth_type": "OAuth2",
        "auth_schema": "sharepoint_auth",
        "integration_config": {"integration_type": "tool"},
    },
    {
        "name": "OpenAI",
        "key": "openai",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/openai.svg",
        "tags": ["language_model"],
        "description": "Powerful AI models for natural language processing.",
        "auth_type": "API Key",
        "auth_schema": "openai_auth",
        "integration_config": {"integration_type": "agent_llm"},
    },
    {
        "name": "AWS S3",
        "key": "aws_s3",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/s3_bucket.svg",
        "tags": ["cloud_storage"],
        "description": "Scalable object storage service for storing and retrieving any amount of data from anywhere on the web.",
        "auth_type": "API Key",
        "auth_schema": "aws_s3_auth",
        "integration_config": {"integration_type": "tool"},
    },
    {
        "name": "Outlook",
        "key": "outlook",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/outlook.svg",
        "tags": ["email"],
        "description": "Microsoft Outlook integration for email management through Microsoft Graph API.",
        "auth_type": "OAuth2",
        "auth_schema": "outlook_auth",
        "integration_config": {"integration_type": "tool"},
    },
    {
        "name": "Anthropic",
        "key": "anthropic",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/anthropic.svg",
        "tags": ["language_model"],
        "description": "Anthropic models for natural language processing.",
        "auth_type": "API Key",
        "auth_schema": "anthropic_auth",
        "integration_config": {"integration_type": "agent_llm"},
    },
    {
        "name": "Gemini",
        "key": "gemini",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/gemini.svg",
        "tags": ["language_model"],
        "description": "Google's Gemini models for advanced natural language processing and multimodal AI capabilities.",
        "auth_type": "API Key",
        "auth_schema": "gemini_auth",
        "integration_config": {"integration_type": "agent_llm"},
    },
]
