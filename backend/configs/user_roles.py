# Access control hierarchy: higher level includes all lower levels
# none < view < edit < full
ACCESS_HIERARCHY = {"none": 0, "view": 1, "edit": 2, "full": 3}

# HTTP method → minimum access level required
HTTP_METHOD_TO_LEVEL = {
    "GET": "view",
    "POST": "edit",
    "PUT": "edit",
    "PATCH": "edit",
    "DELETE": "full",
}

# Routes that don't require authentication (publicly accessible)
OPEN_ROUTES = [
    "/",
    "/favicon.ico",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/icons",
    "/login",
    "/token",
    "/logout",
    "/authorize",
    "/platform/root-user",
    "/changelog",
    "/version",
    "/grafana-alerts",
    "/auth/login",
    "/auth/logout",
    "/auth/token",
    "/auth/discover",
    "/auth/sso/authorize",
    "/auth/sso/callback",
    "/auth/sso/exchange",
    "/auth/teams",
]

# Routes that only ROOT user can access (system bootstrapping/seeding)
ROOT_ONLY_ROUTES = [
    "/platform",
]

# Routes that require authentication but no specific module permission
AUTH_ONLY_ROUTES = [
    "/tool-bindings",
    "/task-sources",
    "/profile",
    "/profile/office365",
    "/tags",
    "/tags/search",
    "/notifications",
]

# Module definitions and feature flags are in configs/module_registry.py
# Re-export PLATFORM_MODULES for backward compatibility
from configs.module_registry import PLATFORM_MODULES  # noqa: F401

# Default roles for new platform setup
DEFAULT_ROLES = [
    {
        "name": "Account Admin",
        "role_key": "account_admin",
        "description": "Account admin with complete permissions",
        "default_role": True,
        "role_permissions": {
            "modules": {
                "agents": {"level": "edit"},
                "agent_tools": {"level": "full"},
                "api_keys": {"level": "full"},
                "assistant": {"level": "full"},
                "class_groups": {"level": "full"},
                "dashboards": {"level": "view"},
                "data_templates": {"level": "full"},
                "integrations": {"level": "full"},
                # "intents": {"level": "full"},
                "knowledge": {"level": "full"},
                "mailbox_pollings": {"level": "full"},
                "organizations": {"level": "edit"},
                "task_inbox": {"level": "full"},
                "task_issues": {"level": "full"},
                "user_management": {"level": "full"},
            }
        },
    },
    {
        "name": "System Admin",
        "role_key": "system_admin",
        "description": "System admin with high level permissions",
        "default_role": True,
        "role_permissions": {
            "modules": {
                "agents": {"level": "view"},
                "agent_tools": {"level": "view"},
                "api_keys": {"level": "full"},
                "assistant": {"level": "full"},
                "class_groups": {"level": "view"},
                "dashboards": {"level": "view"},
                "data_templates": {"level": "view"},
                "integrations": {"level": "edit"},
                # "intents": {"level": "view"},
                "knowledge": {"level": "view"},
                "mailbox_pollings": {"level": "edit"},
                "organizations": {"level": "edit"},
                "task_inbox": {"level": "edit"},
                "task_issues": {"level": "edit"},
                "user_management": {"level": "edit"},
            }
        },
    },
    {
        "name": "Group Admin",
        "role_key": "group_admin",
        "description": "Group admin in the organization",
        "default_role": True,
        "role_permissions": {
            "modules": {
                "agents": {"level": "view"},
                "agent_tools": {"level": "view"},
                "assistant": {"level": "full"},
                "dashboards": {"level": "view"},
                "integrations": {"level": "view"},
                "organizations": {"level": "view"},
                "task_inbox": {"level": "edit"},
                "task_issues": {"level": "edit"},
            }
        },
    },
    {
        "name": "Group Staff",
        "role_key": "group_staff",
        "description": "Group staff in the organization",
        "default_role": True,
        "role_permissions": {
            "modules": {
                "assistant": {"level": "full"},
                "dashboards": {"level": "view"},
                "integrations": {"level": "view"},
                "organizations": {"level": "view"},
                "task_inbox": {"level": "edit"},
                "task_issues": {"level": "edit"},
            }
        },
    },
    {
        "name": "Standard User",
        "role_key": "standard_user",
        "description": "Standard user with limited access",
        "default_role": True,
        "role_permissions": {
            "modules": {
                "assistant": {"level": "full"},
                "dashboards": {"level": "view"},
                "integrations": {"level": "view"},
                "organizations": {"level": "view"},
                "task_inbox": {"level": "view"},
                "task_issues": {"level": "view"},
            }
        },
    },
]
