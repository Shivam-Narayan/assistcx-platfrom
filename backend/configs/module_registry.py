import os

from logger import configure_logging

logger = configure_logging(__name__)

# Platform module definitions: single source of truth for all module configuration
# Used by RBAC, feature flags, and route registration
PLATFORM_MODULES = {
    "agents": {
        "name": "Agents",
        "description": "Create, configure, and manage AI agents",
        "routes": [
            "/agents",
            "/agents/search",
            "/agents/export",
            "/agents/import",
            "/agents/build",
            "/agents/archive",
            "/version-histories",
            # Cross-module reads needed for agent creation/editing
            "/agent-tools",
            "/agent-tools/search",
            "/agent-tools/filters",
            "/collections",
            "/collections/search",
            "/data-files",
            "/embedding-models",
            "/sharepoint",
            "/data-templates",
            "/data-templates/search",
            # "/intents",
            # "/intents-search",
            "/pollings",
            "/pollings/search",
            "/storage-mounts",
            "/agent-llms",
            "/integrations/llms",
            "/class-groups",
            "/users",
            "/configurations",
        ],
        "web_routes": ["/agents"],
        "access_levels": ["view", "edit"],
        "data_filters": ["name"],
    },
    "agent_tools": {
        "name": "Agent Tools",
        "description": "Manage tools and functions available to agents",
        "routes": ["/agent-tools", "/agent-tools/search", "/agent-tools/filters"],
        "web_routes": ["/tools"],
        "access_levels": ["view", "edit", "full"],
        "data_filters": [],
    },
    "api_keys": {
        "name": "API Keys",
        "description": "Manage API keys for external access",
        "routes": ["/api-keys", "/api-keys/search"],
        "web_routes": ["/settings/api-keys"],
        "access_levels": ["view", "edit", "full"],
        "data_filters": [],
    },
    "assistant": {
        "name": "Assistant",
        "description": "AI assistant for knowledge research and tasks",
        "routes": [
            "/assistant",
            "/research",
            "/assistant/query",
            "/assistant/stream",
            "/assistant/chat-threads",
            "/assistant/chat-messages",
            "/assistant/private-data-collection",
            "/assistant/private-data-files",
            "/assistant/collections",
            "/assistant/data-files",
            "/assistant/tasks",
            "/assistant/tasks/search",
            "/configurations",
            # Cross-module reads
            "/embedding-models",
            "/data-files",
            "/collections",
        ],
        "web_routes": [],
        "access_levels": ["full"],
        "data_filters": [],
    },
    "class_groups": {
        "name": "Class Groups",
        "description": "Manage classification groups used by agents",
        "routes": ["/class-groups", "/class-groups/search"],
        "web_routes": ["/settings/class-group"],
        "access_levels": ["view", "edit", "full"],
        "data_filters": [],
    },
    "dashboards": {
        "name": "Dashboards",
        "description": "View platform analytics and statistics",
        "routes": [
            "/email-counts",
            "/email-monthly-stats",
            "/task-agent-stats",
            "/count-by-mailbox",
            "/task-counts",
            "/task-monthly-stats",
            "/task-volume-stats",
            # Cross-module reads
            "/emails/filters",
        ],
        "web_routes": ["/"],
        "access_levels": ["view"],
        "data_filters": [],
        "inherited_data_filters": {
            "agent": {"module": "agents", "key": "name"},
        },
    },
    "data_templates": {
        "name": "Data Templates",
        "description": "Manage templates for structured data extraction",
        "routes": [
            "/data-templates",
            "/data-templates/search",
            "/data-templates/build-schema",
            "/version-histories",
        ],
        "web_routes": ["/settings/data-template"],
        "access_levels": ["view", "edit", "full"],
        "data_filters": [],
    },
    "integrations": {
        "name": "Integrations",
        "description": "Manage integrations, connections, and credentials",
        "routes": [
            "/integrations",
            "/integrations/search",
            "/integrations/tags",
            "/integrations/{}/credentials",
            # Connections
            "/connections",
            # Integration catalog
            "/providers",
            "/auth-schema-catalog",
            "/trigger-catalog",
        ],
        "web_routes": ["/integrations", "/connections", "/integration-catalog"],
        "access_levels": ["view", "edit", "full"],
        "data_filters": [],
    },
    # "intents": {
    #     "name": "Intents",
    #     "description": "Manage intent classifications used by agents",
    #     "routes": ["/intents", "/intents-search"],
    #     "web_routes": ["/settings/intent-class"],
    #     "access_levels": ["view", "edit", "full"],
    #     "data_filters": [],
    # },
    "knowledge": {
        "name": "Knowledge Base",
        "description": "Manage document collections and knowledge files",
        "routes": [
            "/collections",
            "/collections/search",
            "/data-files",
            "/sharepoint",
            # Cross-module reads
            "/embedding-models",
            "/storage-mounts",
        ],
        "web_routes": ["/knowledge"],
        "access_levels": ["view", "edit", "full"],
        "data_filters": ["name"],
    },
    "mailbox_pollings": {
        "name": "Mailbox Pollings",
        "description": "Configure email mailbox polling and schedules",
        "routes": [
            "/pollings",
            "/pollings/search",
            # Cross-module reads
            "/storage-mounts",
        ],
        "web_routes": ["/settings/mailbox-polling"],
        "access_levels": ["view", "edit", "full"],
        "data_filters": [],
    },
    "organizations": {
        "name": "Organization",
        "description": "Manage organization settings and preferences",
        "routes": [
            "/organizations/current",
            "/configurations",
            "/storage-mounts",
            "/integrations/llms",
            "/agent-llms",
            "/auth/settings",
        ],
        "web_routes": ["/settings/account"],
        "access_levels": ["view", "edit"],
        "data_filters": [],
    },
    "task_inbox": {
        "name": "Task Inbox",
        "description": "View and manage tasks, emails, and agent outputs",
        "routes": [
            "/emails",
            "/emails/search",
            "/emails/export",
            "/emails/archive",
            "/agent-tasks",
            "/agent-tasks/export",
            "/agent-tasks/stream",
            "/task-outputs",
            "/agent-outputs",
            "/task-progress",
            "/task-progress-search",
            "/agent-tasks/status",
            "/emails/filters",
            "/agents/preview",
            "/attachments",
            "/activity-logs",
            "/entities/{}/activity-logs",
            "/event-inboxes",
            # Cross-module reads
            "/data-templates",
            "/issues",
            "/issues/search",
            "/issues/filters",
            "/issues/filters/search",
            "/comments",
            "/version-histories",
        ],
        "web_routes": ["/inbox", "/event-inbox"],
        "access_levels": ["view", "edit", "full"],
        "data_filters": [],
        "inherited_data_filters": {
            "agent": {"module": "agents", "key": "name"},
        },
    },
    "task_issues": {
        "name": "Task Issues",
        "description": "Track issues and comments on tasks",
        "routes": [
            "/issues",
            "/issues/search",
            "/issues/filters",
            "/issues/filters/search",
            "/emails/{}/issues",
            "/agent-tasks/{}/issues",
            "/comments",
        ],
        "web_routes": ["/issues"],
        "access_levels": ["view", "edit", "full"],
        "data_filters": [],
    },
    "user_management": {
        "name": "User Management",
        "description": "Manage users, roles, and groups for the organization",
        "routes": [
            "/users",
            "/users/search",
            "/user-roles",
            "/user-roles/search",
            "/user-groups",
            "/user-groups/search",
            "/permissions",
            "/app-access",
        ],
        "web_routes": ["/settings/manage-user"],
        "access_levels": ["view", "edit", "full"],
        "data_filters": [],
    },
}


# --- Edition presets ---
# Each edition defines which modules are enabled by default.
# Per-module env var overrides (FEATURE_{MODULE_KEY}=on|off) take precedence.

EDITION_DEFAULTS = {
    "full": frozenset(PLATFORM_MODULES.keys()),
    "btp": frozenset(PLATFORM_MODULES.keys())
    - {"knowledge", "assistant", "mailbox_pollings"},
}


def _resolve_enabled_modules() -> frozenset:
    """Resolve enabled modules based on edition preset + per-module overrides.

    Resolution order:
    1. Start with the edition's default set (PLATFORM_EDITION env var)
    2. Apply per-module overrides (FEATURE_{MODULE_KEY}=on|off)
    """
    edition = os.getenv("PLATFORM_EDITION", "full").lower()
    defaults = EDITION_DEFAULTS.get(edition)

    if defaults is None:
        logger.warning(f"Unknown PLATFORM_EDITION '{edition}', falling back to 'full'")
        defaults = EDITION_DEFAULTS["full"]

    enabled = set(defaults)

    for module_key in PLATFORM_MODULES:
        override = os.getenv(f"FEATURE_{module_key.upper()}", "").lower()
        if override == "off":
            enabled.discard(module_key)
        elif override == "on":
            enabled.add(module_key)

    disabled = set(PLATFORM_MODULES.keys()) - enabled
    if disabled:
        logger.info(f"Disabled modules: {sorted(disabled)}")

    return frozenset(enabled)


ENABLED_MODULES = _resolve_enabled_modules()


def is_module_enabled(key: str) -> bool:
    """Check if a module is enabled in the current edition."""
    return key in ENABLED_MODULES
