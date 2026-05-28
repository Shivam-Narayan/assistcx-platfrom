## 12. Registry Query & Search Helpers

Common helper functions for querying, filtering, and searching across the flat dict registries. These live in a shared utility module and are used by API endpoints, UI backends, and the trigger runtime.

### 12.1 Helper Function Patterns (Abstract)

The registry helpers follow consistent patterns across all entity types (Integration, Auth Schema, Trigger, Tool). Each entity type implements a minimal set of essential functions:

#### Core Operations

- **`get_<entity>(key)`** — O(1) lookup with full details including provider context and schemas
- **`get_<entities>_for_provider(provider_key)`** — Filter by provider
- **`search_<entities>(query)`** — Text search across key, label, description

#### Listing

- **`list_<entities>(provider_key?)`** — List with all essential details including provider info
- **`list_<entities>_paginated(page, page_size, provider_key?, filters?)`** — Paginated list with metadata

#### Runtime Operations

- **`load_<entity>_handler(key)`** — Resolve and load handler for runtime dispatch (triggers and tools only)

---

### 12.2 Pagination Helper (Shared Utility)

Common pagination utility used by all `list_<entities>_paginated` functions:

```python
from typing import Dict, Any, List, TypeVar, Callable
from math import ceil

T = TypeVar('T')

def paginate(
    items: List[T],
    page: int = 1,
    page_size: int = 20,
    max_page_size: int = 100
) -> Dict[str, Any]:
    """
    Paginate a list of items and return with metadata.

    Args:
        items: List of items to paginate
        page: Page number (1-indexed)
        page_size: Number of items per page
        max_page_size: Maximum allowed page size

    Returns:
        Dict with paginated results and metadata
    """
    # Validate and cap page_size
    page_size = min(page_size, max_page_size)
    page_size = max(1, page_size)

    # Validate page number
    page = max(1, page)

    # Calculate pagination
    total_count = len(items)
    total_pages = ceil(total_count / page_size) if total_count > 0 else 1

    # Ensure page is within bounds
    page = min(page, total_pages)

    # Calculate slice indices
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    # Get page items
    page_items = items[start_idx:end_idx]

    return {
        "items": page_items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }
    }
```

---

### 12.3 Integration Helpers

```python
# integrations/configs/registry.py

from typing import Dict, Any, Optional, List


# Core Lookup
def get_integration(provider_key: str) -> Optional[Dict[str, Any]]:
    """O(1) lookup by provider key with full details including counts and auth schemas."""
    integration = ALL_INTEGRATIONS.get(provider_key)
    if not integration:
        return None

    return {
        **integration,
        "trigger_count": len(get_triggers_for_provider(provider_key)),
        "tool_count": len(get_tools_for_provider(provider_key)),
        "auth_schemas": [
            ALL_AUTH_SCHEMAS[schema_key]
            for schema_key in integration.get("supported_auth_schemas", [])
            if schema_key in ALL_AUTH_SCHEMAS
        ],
    }


# Filter by Field
def get_integrations_by_tag(tag: str) -> Dict[str, Any]:
    """Filter integrations by tag (email, storage, crm, …)."""
    return {k: v for k, v in ALL_INTEGRATIONS.items() if tag in v.get("tags", [])}


def get_enabled_integrations() -> Dict[str, Any]:
    """Get all enabled integrations."""
    return {k: v for k, v in ALL_INTEGRATIONS.items() if v.get("is_enabled", True)}


# Search
def search_integrations(query: str) -> Dict[str, Any]:
    """Search integrations by key, name, description, or tags (case-insensitive)."""
    q = query.lower()
    return {
        k: v for k, v in ALL_INTEGRATIONS.items()
        if q in k.lower()
        or q in v.get("name", "").lower()
        or q in v.get("description", "").lower()
        or any(q in tag.lower() for tag in v.get("tags", []))
    }


# Listing for API Responses
def list_integrations() -> List[Dict[str, Any]]:
    """List integrations for the integrations catalog page."""
    return [
        {
            "key": k,
            "name": v["name"],
            "icon": v.get("icon"),
            "tags": v.get("tags", []),
            "description": v.get("description"),
            "auth_schema_count": len(v.get("supported_auth_schemas", [])),
            "trigger_count": len(get_triggers_for_provider(k)),
            "tool_count": len(get_tools_for_provider(k)),
        }
        for k, v in ALL_INTEGRATIONS.items()
        if v.get("is_enabled", True)
    ]


def list_integrations_paginated(
    page: int = 1,
    page_size: int = 20,
    search_query: str = None,
    tag: str = None
) -> Dict[str, Any]:
    """Paginated list of integrations with optional filtering."""
    # Start with all integrations
    items = list_integrations()

    # Apply filters
    if search_query:
        q = search_query.lower()
        items = [
            item for item in items
            if q in item["key"].lower()
            or q in item["name"].lower()
            or q in item.get("description", "").lower()
            or any(q in t.lower() for t in item.get("tags", []))
        ]

    if tag:
        items = [item for item in items if tag in item.get("tags", [])]

    # Paginate
    return paginate(items, page, page_size)
```

---

### 12.4 Auth Schema Helpers

```python
# Core Lookup
def get_auth_schema(auth_schema_key: str) -> Optional[Dict[str, Any]]:
    """O(1) lookup by auth schema key."""
    return ALL_AUTH_SCHEMAS.get(auth_schema_key)


# Filter by Provider
def get_auth_schemas_for_provider(provider_key: str) -> Dict[str, Any]:
    """All auth schemas supported by a provider."""
    integration = ALL_INTEGRATIONS.get(provider_key, {})
    schema_keys = set(integration.get("supported_auth_schemas", []))
    return {k: v for k, v in ALL_AUTH_SCHEMAS.items() if k in schema_keys}


# Search
def search_auth_schemas(query: str) -> Dict[str, Any]:
    """Search auth schemas by key or display name (case-insensitive)."""
    q = query.lower()
    return {
        k: v for k, v in ALL_AUTH_SCHEMAS.items()
        if q in k.lower() or q in v.get("display_name", "").lower()
    }


# Listing for API Responses
def list_auth_schemas(provider_key: str = None) -> List[Dict[str, Any]]:
    """List auth schemas for auth schema selection."""
    source = (
        get_auth_schemas_for_provider(provider_key) if provider_key else ALL_AUTH_SCHEMAS
    )
    return [
        {
            "key": k,
            "display_name": v["display_name"],
            "auth_type": v.get("auth_type"),
            "flow": v.get("flow"),
            "description": v.get("description"),
        }
        for k, v in source.items()
    ]


def list_auth_schemas_paginated(
    page: int = 1,
    page_size: int = 20,
    provider_key: str = None,
    search_query: str = None,
    auth_type: str = None
) -> Dict[str, Any]:
    """Paginated list of auth schemas with optional filtering."""
    # Get base items
    items = list_auth_schemas(provider_key)

    # Apply filters
    if search_query:
        q = search_query.lower()
        items = [
            item for item in items
            if q in item["key"].lower()
            or q in item["display_name"].lower()
            or q in item.get("description", "").lower()
        ]

    if auth_type:
        items = [item for item in items if item.get("auth_type") == auth_type]

    # Paginate
    return paginate(items, page, page_size)
```

---

### 12.5 Trigger Helpers

```python
import importlib


# Core Lookup
def get_trigger(trigger_key: str) -> Optional[Dict[str, Any]]:
    """O(1) lookup by trigger key with full details including provider context.
    Trigger already contains resource_schema, filter_schema, schedule_schema, processing_schema."""
    trigger = ALL_TRIGGERS.get(trigger_key)
    if not trigger:
        return None

    provider = ALL_INTEGRATIONS[trigger["provider"]]

    return {
        **trigger,
        "provider": {
            "key": trigger["provider"],
            "name": provider["name"],
            "icon": provider.get("icon"),
            "tags": provider.get("tags", []),
        }
    }


# Filter by Provider
def get_triggers_for_provider(provider_key: str) -> Dict[str, Any]:
    """All triggers belonging to a provider."""
    return {k: v for k, v in ALL_TRIGGERS.items() if v["provider"] == provider_key}


# Search
def search_triggers(query: str) -> Dict[str, Any]:
    """Search triggers by key, label, or description (case-insensitive)."""
    q = query.lower()
    return {
        k: v for k, v in ALL_TRIGGERS.items()
        if q in k.lower()
        or q in v.get("label", "").lower()
        or q in v.get("description", "").lower()
    }


# Listing for API Responses
def list_triggers(provider_key: str = None) -> List[Dict[str, Any]]:
    """List triggers for trigger selection with provider details."""
    source = (
        get_triggers_for_provider(provider_key) if provider_key else ALL_TRIGGERS
    )
    return [
        {
            "key": k,
            "label": v["label"],
            "description": v.get("description"),
            "provider_key": v["provider"],
            "provider_name": ALL_INTEGRATIONS[v["provider"]]["name"],
            "provider_icon": ALL_INTEGRATIONS[v["provider"]].get("icon"),
            "delivery_mode": v.get("delivery_mode"),
        }
        for k, v in source.items()
    ]


def list_triggers_paginated(
    page: int = 1,
    page_size: int = 20,
    provider_key: str = None,
    search_query: str = None,
    delivery_mode: str = None
) -> Dict[str, Any]:
    """Paginated list of triggers with optional filtering."""
    # Get base items
    items = list_triggers(provider_key)

    # Apply filters
    if search_query:
        q = search_query.lower()
        items = [
            item for item in items
            if q in item["key"].lower()
            or q in item["label"].lower()
            or q in item.get("description", "").lower()
        ]

    if delivery_mode:
        items = [item for item in items if item.get("delivery_mode") == delivery_mode]

    # Paginate
    return paginate(items, page, page_size)


# Runtime Dispatch
def load_trigger_handler(trigger_key: str):
    """Resolve handler from trigger config and return a callable.
    Returns: bound method ready to call with (cursor, resource_config, filters)."""
    trigger = ALL_TRIGGERS[trigger_key]
    handler = trigger["handler"]

    module = importlib.import_module(handler["module"])
    cls = getattr(module, handler["class"])
    instance = cls()
    return getattr(instance, handler["method"])


# Usage in poll cycle:
# handler = load_trigger_handler(task_source.trigger_key)
# result = handler(cursor=task_source.cursor,
#                  resource_config=task_source.resource_config,
#                  filter_config=task_source.filter_config)
```

---

### 12.6 Tool Helpers

```python
# Core Lookup
def get_tool(tool_key: str) -> Optional[Dict[str, Any]]:
    """O(1) lookup by tool key with full details including provider and schemas."""
    tool = ALL_TOOLS.get(tool_key)
    if not tool:
        return None

    provider = ALL_INTEGRATIONS[tool["provider"]]

    return {
        **tool,
        "provider": {
            "key": tool["provider"],
            "name": provider["name"],
            "icon": provider.get("icon"),
            "tags": provider.get("tags", []),
        },
    }


# Filter by Provider
def get_tools_for_provider(provider_key: str) -> Dict[str, Any]:
    """All tools belonging to a provider."""
    return {k: v for k, v in ALL_TOOLS.items() if v["provider"] == provider_key}


# Search
def search_tools(query: str) -> Dict[str, Any]:
    """Search tools by key, label, or description (case-insensitive)."""
    q = query.lower()
    return {
        k: v for k, v in ALL_TOOLS.items()
        if q in k.lower()
        or q in v.get("label", "").lower()
        or q in v.get("description", "").lower()
    }


# Listing for API Responses
def list_tools(provider_key: str = None) -> List[Dict[str, Any]]:
    """List tools for tool selection with provider details."""
    source = (
        get_tools_for_provider(provider_key) if provider_key else ALL_TOOLS
    )
    return [
        {
            "key": k,
            "label": v["label"],
            "description": v.get("description"),
            "provider_key": v["provider"],
            "provider_name": ALL_INTEGRATIONS[v["provider"]]["name"],
            "provider_icon": ALL_INTEGRATIONS[v["provider"]].get("icon"),
        }
        for k, v in source.items()
    ]


def list_tools_paginated(
    page: int = 1,
    page_size: int = 20,
    provider_key: str = None,
    search_query: str = None
) -> Dict[str, Any]:
    """Paginated list of tools with optional filtering."""
    # Get base items
    items = list_tools(provider_key)

    # Apply filters
    if search_query:
        q = search_query.lower()
        items = [
            item for item in items
            if q in item["key"].lower()
            or q in item["label"].lower()
            or q in item.get("description", "").lower()
        ]

    # Paginate
    return paginate(items, page, page_size)


# Runtime Dispatch
def load_tool_handler(tool_key: str):
    """Resolve handler from tool config and return a callable.
    Returns: bound method ready to call with input parameters."""
    tool = ALL_TOOLS[tool_key]
    handler = tool["handler"]

    module = importlib.import_module(handler["module"])
    cls = getattr(module, handler["class"])
    instance = cls()
    return getattr(instance, handler["method"])


# Usage in agent execution:
# handler = load_tool_handler(agent_tool.tool_key)
# result = handler(connection=connection, **input_params)
```
