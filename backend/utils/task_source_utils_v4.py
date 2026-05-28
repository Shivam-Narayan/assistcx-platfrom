"""
Task source helpers (v4): trigger registry, event dedupe, and defaults.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable, Dict, Optional, Tuple
from uuid import UUID

from configs.triggers_v4 import ALL_TRIGGERS
from logger import configure_logging

logger = configure_logging(__name__)

_TRIGGER_REGISTRY: Optional[Dict[str, Tuple[type, str]]] = None


def _build_trigger_registry() -> Dict[str, Tuple[type, str]]:
    registry: Dict[str, Tuple[type, str]] = {}
    for trigger_def in ALL_TRIGGERS:
        slug = trigger_def["slug"]
        if not trigger_def.get("is_enabled", True):
            continue
        handler = trigger_def.get("handler")
        if not handler:
            continue
        try:
            module = importlib.import_module(handler["module"])
            cls = getattr(module, handler["class"])
            registry[slug] = (cls, handler["method"])
        except Exception:
            logger.warning("Failed to register trigger handler for slug=%s", slug, exc_info=True)
    return registry


def resolve_trigger(trigger_key: str) -> Optional[Callable]:
    """
    Look up a trigger handler by its key.
    Returns a bound async method ready to call, or None if not found.
    """
    global _TRIGGER_REGISTRY
    if _TRIGGER_REGISTRY is None:
        _TRIGGER_REGISTRY = _build_trigger_registry()

    entry = _TRIGGER_REGISTRY.get(trigger_key)
    if not entry:
        return None

    cls, method_name = entry
    instance = cls()
    return getattr(instance, method_name)


def build_event_inbox_dedupe_key(task_source_id: UUID, external_event_id: str) -> str:
    """
    Stable dedupe key for ``event_inbox.dedupe_key`` (max 255 chars).
    Dedupe scope is per-task-source by design.
    """
    raw = f"task_source:{task_source_id}:{external_event_id}"
    return raw[:255]


def default_event_inbox_status() -> Dict[str, Any]:
    """Default ``event_inbox.status`` JSON for new events."""
    return {"state": "pending", "attempts": 0}
