# Default libraries
from typing import Optional, List, Dict, Any

# Custom libraries
from configs.agent_tools_data import BASIC_AGENT_TOOLS
from configs.integrations_v4 import INTEGRATIONS
from configs.auth_schemas_v4 import AUTH_SCHEMAS
from configs.triggers_v4 import ALL_TRIGGERS
from logger import configure_logging


logger = configure_logging(__name__)


class IntegrationCatalogRepository:
    """
    Read-only catalog from config (integrations, auth schemas, triggers).
    One get_all per config with keyword search and pagination. Returns list of details only (no count).
    """

    def get_all_integrations(
        self,
        keyword: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return list of integration config details. Optional keyword search, filters, pagination."""
        try:
            integrations = list(INTEGRATIONS)

            if keyword:
                k = keyword.lower()
                integrations = [
                    i
                    for i in integrations
                    if k in (i.get("name") or "").lower()
                    or k in (i.get("description") or "").lower()
                    or k in (i.get("key") or "").lower()
                    or any(k in (t or "").lower() for t in (i.get("tags") or []))
                ]

            if filters:
                integrations = [
                    item
                    for item in integrations
                    if all(
                        item.get(k) in v if isinstance(v, list) else item.get(k) == v
                        for k, v in filters.items()
                    )
                ]

            if (
                page is not None
                and page_size is not None
                and page >= 1
                and page_size >= 1
            ):
                skip = (page - 1) * page_size
                integrations = integrations[skip : skip + page_size]

            return [
                {
                    **item,
                    "triggers": [
                        dict(t)
                        for t in ALL_TRIGGERS
                        if t.get("integration_key") == item.get("key")
                    ],
                    "tools": [
                        dict(t)
                        for t in BASIC_AGENT_TOOLS
                        if t.get("integration_key") == item.get("key")
                    ],
                }
                for item in integrations
            ]
        except Exception as e:
            logger.error(f"Error in get_all_integrations: {e}")
            return []

    def get_all_auth_schemas(
        self,
        keyword: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return list of auth schema config details.
        Config has no 'key' field; key is the dict key and is added to each item for the API.
        Optional keyword search, filters, and pagination.
        """
        try:
            auth_schemas = [{"key": k, **v} for k, v in AUTH_SCHEMAS.items()]

            # Apply keyword search
            if keyword:
                k = keyword.lower()
                auth_schemas = [
                    i
                    for i in auth_schemas
                    if k in (i.get("key") or "").lower()
                    or k in (i.get("auth_type") or "").lower()
                    or k in (i.get("display_name") or "").lower()
                    or k in (i.get("description") or "").lower()
                ]

            # Apply filters
            if filters:
                auth_schemas = [
                    item
                    for item in auth_schemas
                    if all(
                        item.get(k) in v if isinstance(v, list) else item.get(k) == v
                        for k, v in filters.items()
                    )
                ]

            # Apply pagination
            if (
                page is not None
                and page_size is not None
                and page >= 1
                and page_size >= 1
            ):
                skip = (page - 1) * page_size
                auth_schemas = auth_schemas[skip : skip + page_size]
            return auth_schemas
        except Exception as e:
            logger.error(f"Error in get_all_auth_schemas: {e}")
            return []

    def get_all_triggers(
        self,
        keyword: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return list of trigger config details. Optional keyword search, filters, pagination."""
        try:
            triggers = list(ALL_TRIGGERS)

            if keyword:
                k = keyword.lower()
                triggers = [
                    i
                    for i in triggers
                    if k in (i.get("name") or "").lower()
                    or k in (i.get("description") or "").lower()
                    or k in (i.get("slug") or "").lower()
                    or k in (i.get("integration_key") or "").lower()
                ]

            if filters:
                triggers = [
                    item
                    for item in triggers
                    if all(
                        item.get(k) in v if isinstance(v, list) else item.get(k) == v
                        for k, v in filters.items()
                    )
                ]

            if (
                page is not None
                and page_size is not None
                and page >= 1
                and page_size >= 1
            ):
                skip = (page - 1) * page_size
                triggers = triggers[skip : skip + page_size]
            return triggers
        except Exception as e:
            logger.error(f"Error in get_all_triggers: {e}")
            return []
