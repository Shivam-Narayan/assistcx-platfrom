# Custom libraries
from logger import configure_logging
from utils.schema_utils import set_schema
from utils.rbac_utils import (
    get_data_filter_module,
    parse_filters_query_params,
    find_matching_modules,
)

# Database modules
from configs.module_registry import PLATFORM_MODULES
from repository.user_group_repository import UserGroupRepository
from repository.user_access_repository import UserAccessRepository

# Default libraries
from typing import Any, Dict, List, Optional, Union
import os

# Installed libraries
from dotenv import load_dotenv
from fastapi import HTTPException, Request, status
import json


logger = configure_logging(__name__)

load_dotenv()


class Permissions:
    def __init__(self, db=None):
        self.jwt_secret = os.getenv("JWT_SECRET")

        if db:
            from repository.configuration_repository import ConfigurationRepository

            config = ConfigurationRepository(db).get_configuration()
            self._assistant_enabled = (
                config.preferences.get("assistant_enabled", False)
                if config and config.preferences
                else False
            )
        else:
            self._assistant_enabled = False

    def compress_role_permissions(self, user_role_data: Dict[str, Any]) -> dict:
        """
        Validate and prepare role permissions for storage.
        New format: {"modules": {"agents": {"level": "edit"}, ...}}
        """
        try:
            result = {
                "name": user_role_data.get("name"),
                "role_key": user_role_data.get("role_key"),
                "description": user_role_data.get("description"),
                "default_role": user_role_data.get("default_role", False),
                "role_permissions": user_role_data.get("role_permissions", {}),
            }

            # Filter out assistant module if not enabled
            if not self._assistant_enabled:
                modules = result.get("role_permissions", {}).get("modules", {})
                modules.pop("assistant", None)

            return result
        except Exception as e:
            logger.error(f"An error occurred in compress_role_permissions: {e}")
            return {}

    def decompress_role_permissions(self, db, user_roles) -> list:
        """
        Expand role permissions for API response.
        Returns role details with module permissions expanded against available modules.
        """
        try:
            from schemas.user_role_schema import UserRoleDetail, ModuleAccess

            user_role_details = []
            for user_role in user_roles:
                role_perms = user_role.role_permissions or {}
                user_modules = role_perms.get("modules", {})

                # Build expanded permissions: all modules with user's level
                module_permissions = {}
                for module_key, module_config in PLATFORM_MODULES.items():
                    user_module = user_modules.get(module_key, {})
                    module_permissions[module_key] = ModuleAccess(
                        level=user_module.get("level", "none"),
                    )

                user_role_details.append(
                    UserRoleDetail(
                        id=user_role.id,
                        name=user_role.name,
                        role_key=user_role.role_key,
                        description=user_role.description,
                        default_role=getattr(user_role, "default_role", False),
                        role_permissions={
                            "modules": {
                                k: v.model_dump() for k, v in module_permissions.items()
                            }
                        },
                        created_at=user_role.created_at,
                        updated_at=user_role.updated_at,
                    )
                )
            return user_role_details

        except Exception as e:
            logger.error(f"An error occurred in decompress_role_permissions: {e}")
            return []

    def restructure_permissions_v2(self) -> List[Dict[str, Any]]:
        """
        Convert PLATFORM_MODULES config to flat permission list for DB seeding.
        Each module becomes one permission row.
        """
        try:
            return [
                {
                    "key": module_key,
                    "name": module_config["name"],
                    "description": module_config["description"],
                    "module": module_key,
                    "access_levels": module_config.get("access_levels", []),
                    "web_routes": module_config.get("web_routes", []),
                    "data_filters": module_config.get("data_filters", []),
                }
                for module_key, module_config in PLATFORM_MODULES.items()
                if module_key != "assistant" or self._assistant_enabled
            ]
        except Exception as e:
            logger.error(f"An error occurred in restructure_permissions_v2: {e}")
            return []

    async def _get_group_data_permissions(self, org_db, user_access, module_key: str):
        """
        Get data permissions from user groups.
        Batch fetch all user groups in single query instead of N queries.
        """
        try:
            if not user_access or not user_access.user_group_ids:
                return None

            user_group_repository = UserGroupRepository(org_db)
            scoped_data_permissions = {}

            user_groups = await user_group_repository.get_user_groups_by_ids(
                user_access.user_group_ids
            )

            for user_group in user_groups:
                value = (user_group.data_access or {}).get(module_key)

                if isinstance(value, dict):
                    for k, v in value.items():
                        if v is True:
                            scoped_data_permissions[k] = True
                        elif v is False:
                            scoped_data_permissions[k] = False
                        elif isinstance(v, list):
                            scoped_data_permissions.setdefault(k, set()).update(v)

            if scoped_data_permissions:
                return {
                    k: (list(v) if isinstance(v, set) else v)
                    for k, v in scoped_data_permissions.items()
                }
            return None

        except Exception as e:
            logger.error(f"An error occurred in _get_group_data_permissions: {e}")
            return None

    async def _resolve_inherited_data_filters(
        self,
        path: str,
        user_uuid: str,
        organization_schema: str,
        query_filters: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Resolve inherited data filters from a source module's data_access.

        Some modules (e.g. task_inbox) don't have their own data_filters but
        inherit restrictions from another module (e.g. agents).  The mapping
        is declared in PLATFORM_MODULES[module]["inherited_data_filters"].

        Behaviour by source value:
          - list  → restrict to those values (e.g. ["Agent1"])
          - True  → unrestricted, no filter injected
          - False / [] / None / missing → skip (don't block the inheriting module)

        Returns merged filters dict, or None when nothing to inject.
        """
        # Find the module that owns this path and has inherited config
        matching_modules = find_matching_modules(path)
        inherited_config = None
        for mod_key in matching_modules:
            cfg = PLATFORM_MODULES.get(mod_key, {}).get("inherited_data_filters")
            if cfg:
                inherited_config = cfg
                break

        if not inherited_config:
            return None

        try:
            with set_schema(organization_schema) as org_db:
                user_access_repo = UserAccessRepository(org_db)
                user_access = user_access_repo.get_user_access_by_user_id(user_uuid)

                if not user_access:
                    return None

                data_permissions = {}

                for filter_key, source in inherited_config.items():
                    source_module = source["module"]
                    source_key = source["key"]

                    # --- Resolve from user's data_access ---
                    user_source = (user_access.data_access or {}).get(source_module)
                    user_value = (
                        user_source.get(source_key)
                        if isinstance(user_source, dict)
                        else None
                    )

                    # --- Resolve from groups ---
                    group_value = None
                    if user_access.user_group_ids:
                        group_repo = UserGroupRepository(org_db)
                        groups = await group_repo.get_user_groups_by_ids(
                            user_access.user_group_ids
                        )
                        for group in groups:
                            gs = (group.data_access or {}).get(source_module)
                            gv = gs.get(source_key) if isinstance(gs, dict) else None
                            if gv is True:
                                group_value = True
                                break
                            elif isinstance(gv, list):
                                if group_value is None:
                                    group_value = gv[:]
                                elif isinstance(group_value, list):
                                    group_value = list(set(group_value + gv))

                    # --- Merge user + group (union) ---
                    merged_value = None
                    saw_explicit_denial = False
                    for v in (user_value, group_value):
                        if v is True:
                            merged_value = True
                            break
                        elif isinstance(v, list):
                            if v:
                                if merged_value is None:
                                    merged_value = v[:]
                                elif isinstance(merged_value, list):
                                    merged_value = list(set(merged_value + v))
                            else:
                                saw_explicit_denial = True
                        elif v is False:
                            saw_explicit_denial = True

                    # True           → unrestricted, skip injection (show everything).
                    # non-empty list → restrict to those values.
                    # explicit False/[] across all sources → block the inheriting module.
                    # None everywhere → source key never configured, leave unhandled.
                    if merged_value is True:
                        continue
                    if isinstance(merged_value, list) and merged_value:
                        data_permissions[filter_key] = merged_value
                    elif saw_explicit_denial:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Data access denied.",
                        )

                if not data_permissions:
                    return None

                # Resolve agent names to agent_ids so downstream consumers
                # (dashboard, email, mailbox-filters) all receive IDs directly.
                if "agent" in data_permissions:
                    from repository.agent_repository import AgentRepository

                    agent_repo = AgentRepository(org_db)
                    agent_ids = []
                    for name in data_permissions["agent"]:
                        agent = agent_repo.get_agent_by_name(name)
                        if agent:
                            agent_ids.append(str(agent.id))
                    del data_permissions["agent"]
                    if agent_ids:
                        data_permissions["agent_id"] = agent_ids

                if not data_permissions:
                    return None

                # Merge with incoming query filters
                result = {**(query_filters or {})}
                for key, allowed in data_permissions.items():
                    if key in result and isinstance(result[key], list):
                        # Intersect: user can only narrow within allowed set
                        result[key] = list(set(allowed) & set(result[key]))
                    else:
                        result[key] = allowed

                return result

        except Exception as e:
            logger.error(f"Error resolving inherited data filters: {e}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Data access denied.",
            )

    async def verify_user_data_access(self, decoded_token: dict, request: Request):
        """
        Verify user has data-level access permissions.
        Uses module key for data_access lookup instead of old permission keys.
        """
        data_access_exception = HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Data access denied.",
        )
        try:
            user_uuid = decoded_token["sub"]
            organization_id = decoded_token["org_id"]
            user_role = decoded_token["user_role"]

            organization_schema = "public" if user_role == "ROOT" else organization_id
            query_filters = parse_filters_query_params(request)
            module_key = get_data_filter_module(request.url.path)
            if not module_key or not PLATFORM_MODULES.get(module_key, {}).get(
                "data_filters"
            ):
                # No direct data filters — check for inherited data filters
                inherited = await self._resolve_inherited_data_filters(
                    request.url.path,
                    user_uuid,
                    organization_schema,
                    query_filters,
                )
                return inherited if inherited is not None else query_filters

            with set_schema(organization_schema) as org_db:
                user_access_repository = UserAccessRepository(org_db)
                user_access = user_access_repository.get_user_access_by_user_id(
                    user_uuid
                )

                # Create variables for storing data permissions and incoming filters
                data_permissions = {}

                # Get user data permissions for the module
                if user_access:
                    user_data_permissions = (user_access.data_access or {}).get(
                        module_key
                    )
                    group_data_permissions = await self._get_group_data_permissions(
                        org_db, user_access, module_key
                    )

                    # Merge user + group permissions
                    merged_data_permissions = {}
                    for source in (user_data_permissions, group_data_permissions):
                        if not isinstance(source, dict):
                            continue
                        for k, v in source.items():
                            if isinstance(v, list):
                                if k not in merged_data_permissions:
                                    merged_data_permissions[k] = v[:]
                                else:
                                    if merged_data_permissions[k] is True:
                                        merged_data_permissions[k] = True
                                    elif isinstance(merged_data_permissions[k], list):
                                        merged_data_permissions[k] = list(
                                            set(merged_data_permissions[k] + v)
                                        )
                                    elif merged_data_permissions[k] is False:
                                        merged_data_permissions[k] = v[:]

                            elif v is True:
                                if k not in merged_data_permissions:
                                    merged_data_permissions[k] = True
                                else:
                                    if isinstance(merged_data_permissions[k], list):
                                        merged_data_permissions[k] = True

                            elif v is False:
                                if k not in merged_data_permissions:
                                    merged_data_permissions[k] = False

                    if merged_data_permissions:
                        raw_data_permissions = {
                            k: (list(v) if isinstance(v, set) else v)
                            for k, v in merged_data_permissions.items()
                        }
                    else:
                        raw_data_permissions = (
                            user_data_permissions
                            if isinstance(user_data_permissions, dict)
                            else (
                                group_data_permissions
                                if isinstance(group_data_permissions, dict)
                                else None
                            )
                        )

                    # Normalize permissions
                    if isinstance(raw_data_permissions, dict):
                        allowed_data_permissions = {
                            key: [value] if isinstance(value, str) else value
                            for key, value in raw_data_permissions.items()
                        }
                        for key, value in allowed_data_permissions.items():
                            if value is True:
                                pass  # unrestricted for this key
                            elif value is False:
                                data_permissions[key] = []
                            else:
                                data_permissions[key] = value

                # Deny early if any data_permission key is empty (= no access),
                # regardless of what query filters are passed.
                if data_permissions and any(
                    isinstance(v, list) and not v for v in data_permissions.values()
                ):
                    raise data_access_exception

                filters = {**(query_filters or {})}

                if data_permissions and filters:
                    common_dict = {
                        key: (
                            (
                                list(
                                    set(data_permissions.get(key, []))
                                    & set(filters.get(key, []))
                                )
                                if isinstance(data_permissions.get(key), list)
                                and isinstance(filters.get(key), list)
                                and key in filters
                                else [data_permissions.get(key)]
                            )
                            if key in filters
                            else (
                                [data_permissions.get(key)]
                                if key in data_permissions
                                else (
                                    [filters.get(key)]
                                    if key not in data_permissions
                                    else []
                                )
                            )
                        )
                        for key in set(data_permissions) | set(filters)
                    }

                    different_dict = {
                        key: (
                            data_permissions[key]
                            if key in data_permissions
                            else filters[key]
                        )
                        for key in set(data_permissions) ^ set(filters)
                    }

                    data_permission_filters = {**common_dict, **different_dict}

                    if any(not value for value in common_dict.values()):
                        raise data_access_exception
                elif data_permissions and not filters:
                    data_permission_filters = data_permissions

                    if any(not value for value in data_permissions.values()):
                        raise data_access_exception
                elif filters and not data_permissions:
                    data_permission_filters = filters
                else:
                    return None

                return data_permission_filters
        except Exception as e:
            logger.error(f"No data access permission: {str(e)}")
            raise data_access_exception
