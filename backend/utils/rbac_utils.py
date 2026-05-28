import json
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Request

from configs.user_roles import (
    ACCESS_HIERARCHY,
    AUTH_ONLY_ROUTES,
    HTTP_METHOD_TO_LEVEL,
)
from configs.module_registry import PLATFORM_MODULES, ENABLED_MODULES
from logger import configure_logging

logger = configure_logging(__name__)


def parse_filters_query_params(request: Request) -> Optional[Dict[str, Any]]:
    """Parse ?filters=<json>; strings become single-element lists (RBAC filter shape)."""
    raw = request.query_params.get("filters") if request.query_params else None
    if not raw or not str(raw).strip():
        return None
    try:
        incoming = json.loads(raw)
        if not isinstance(incoming, dict):
            return None
        return {
            key: [value] if isinstance(value, str) else value
            for key, value in incoming.items()
        }
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning("Invalid filters query param: %s", e)
        return None


def has_access(user_level: str, required_level: str) -> bool:
    """Check if user's access level meets or exceeds the required level."""
    return ACCESS_HIERARCHY.get(user_level, 0) >= ACCESS_HIERARCHY.get(
        required_level, 0
    )


# --- Route index built once at import time ---

# All module route prefixes sorted by length (longest first for greedy matching)
_sorted_prefixes: List[Tuple[str, str]] = []  # (prefix, module_key)


def _build_index():
    """Build reverse route index from PLATFORM_MODULES config. Called once at import time."""
    global _sorted_prefixes

    all_prefixes = []
    for module_key, module_config in PLATFORM_MODULES.items():
        for route in module_config.get("routes", []):
            all_prefixes.append((route, module_key))

    # Sort by length descending for greedy matching
    _sorted_prefixes = sorted(set(all_prefixes), key=lambda x: len(x[0]), reverse=True)


_build_index()


def find_matching_modules(path: str) -> List[str]:
    """Find all modules whose routes match the given path using prefix matching."""
    modules = set()

    for prefix, module_key in _sorted_prefixes:
        # Route patterns with {} are wildcard segment matches
        if "{}" in prefix:
            pattern_segments = prefix.strip("/").split("/")
            path_segments = path.strip("/").split("/")
            if len(path_segments) >= len(pattern_segments):
                match = True
                for pat_seg, path_seg in zip(pattern_segments, path_segments):
                    if pat_seg == "{}":
                        continue
                    if pat_seg != path_seg:
                        match = False
                        break
                if match:
                    modules.add(module_key)
        else:
            # Standard prefix match
            if path == prefix or path.startswith(prefix + "/"):
                modules.add(module_key)

    return list(modules)


def is_auth_only_route(path: str) -> bool:
    """Check if path matches an auth-only route."""
    for route in AUTH_ONLY_ROUTES:
        if path == route or path.startswith(route + "/"):
            return True
    return False


def check_access(role_permissions: dict, method: str, path: str) -> bool:
    """
    Check if user with given role_permissions can access method + path.

    Args:
        role_permissions: The user's role permissions dict, e.g.
            {"modules": {"agents": {"level": "edit"}, ...}}
        method: HTTP method (GET, POST, etc.)
        path: Request path (e.g. "/agents/some-uuid")

    Returns:
        True if access is allowed, False otherwise.
    """
    # Auth-only routes: any authenticated user
    if is_auth_only_route(path):
        return True

    modules = role_permissions.get("modules", {})

    # Find all modules that include this route
    matching_modules = find_matching_modules(path)
    if not matching_modules:
        return False  # Secure by default: unknown route denied

    # Determine required level from HTTP method
    required_level = HTTP_METHOD_TO_LEVEL.get(method, "view")

    # OR logic: user needs required level on ANY enabled matching module
    for module_key in matching_modules:
        if module_key not in ENABLED_MODULES:
            continue
        user_module = modules.get(module_key, {})
        user_level = user_module.get("level", "none")
        if has_access(user_level, required_level):
            return True

    return False


def is_core_route(path: str, module_key: str) -> bool:
    """Check if path is a core route of the module (not a cross-module read).

    The first route in a module's config is its primary entity route.
    A path is "core" if its first segment shares the same prefix as that
    primary route.  Cross-module reads like /integrations-llms or
    /storage-mounts listed under "agents" should not inherit its data_filters.
    """
    module_config = PLATFORM_MODULES.get(module_key, {})
    routes = module_config.get("routes", [])
    if not routes:
        return False

    # First route's leading segment is the module's entity prefix
    primary_prefix = routes[0].strip("/").split("/")[0]
    path_segment = path.strip("/").split("/")[0]

    return path_segment.startswith(primary_prefix)


def get_data_filter_module(path: str) -> Optional[str]:
    """
    Get the primary module for data filter lookup.
    Only returns a module with data_filters if the path is a core route
    of that module — cross-module read routes should not inherit data filters.

    Returns None when no module's data_filters should apply (causes the
    caller to skip data-level filtering and just pass through query filters).
    """
    matching_modules = find_matching_modules(path)

    for module_key in matching_modules:
        module_config = PLATFORM_MODULES.get(module_key, {})
        if module_config.get("data_filters") and is_core_route(path, module_key):
            return module_key

    return None


def get_web_routes(role_permissions: dict) -> List[str]:
    """
    Get list of web routes the user can access based on their role permissions.
    Used for frontend page visibility (replaces old WEB/ endpoint entries).
    """
    modules = role_permissions.get("modules", {})
    web_routes = []

    for module_key, user_module in modules.items():
        if module_key not in ENABLED_MODULES:
            continue
        user_level = user_module.get("level", "none")
        if ACCESS_HIERARCHY.get(user_level, 0) > 0:
            module_config = PLATFORM_MODULES.get(module_key, {})
            web_routes.extend(module_config.get("web_routes", []))

    return web_routes
