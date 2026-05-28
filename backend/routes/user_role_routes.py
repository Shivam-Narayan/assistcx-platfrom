# Custom libraries
from configs.module_registry import PLATFORM_MODULES, ENABLED_MODULES
from logger import configure_logging
from schemas.user_role_schema import (
    UserRoleCreate,
    UserRoleDetail,
    UserRoleResponse,
    UserRoleUpdate,
)
from schemas.user_schema import Message
from schemas.permission_schema import (
    AppAccessResponse,
    DataAccessPermissionResponse,
    ModuleDetail,
    PermissionResponse,
)
from utils.permissions import Permissions
from utils.schema_utils import get_schema_db

# Database modules
from repository.user_role_repository import UserRoleRepository
from repository.permission_repository import PermissionRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request


logger = configure_logging(__name__)

user_role_router = APIRouter(tags=["User Roles"])


@user_role_router.get("/app-access", response_model=AppAccessResponse)
def get_app_access():
    """
    Retrieves app access information for all app access.
    """
    try:
        return AppAccessResponse(app_access=[], total=0)

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_role_router.get("/permissions", response_model=PermissionResponse)
def get_permissions(
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves module permission definitions from config.
    """
    try:
        modules = []
        for module_key, module_config in PLATFORM_MODULES.items():
            if module_key not in ENABLED_MODULES:
                continue

            modules.append(
                ModuleDetail(
                    key=module_key,
                    name=module_config["name"],
                    description=module_config.get("description"),
                    access_levels=module_config.get("access_levels", []),
                    web_routes=module_config.get("web_routes", []),
                    data_filters=module_config.get("data_filters", []),
                )
            )

        return PermissionResponse(modules=modules, total=len(modules))

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_role_router.get(
    "/permissions/data-access", response_model=DataAccessPermissionResponse
)
def get_data_access(
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves permission information for all permissions having field_restrictions.
    """
    try:
        permission_repository = PermissionRepository(db)

        # Fetch all permissions
        permissions = permission_repository.get_all_permissions(field_restrictions=True)

        return DataAccessPermissionResponse(
            features=permissions, total=len(permissions)
        )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_role_router.get(
    "/user-roles/{user_role_uuid}/data-access-permissions",
    response_model=DataAccessPermissionResponse,
)
def get_user_role_data_access_permissions(
    user_role_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves data access permission information for a specific user role based on its user_role_uuid.
    """
    try:
        user_role_repository = UserRoleRepository(db)
        permission_repository = PermissionRepository(db)

        user_role = user_role_repository.get_role_by_id(user_role_uuid)

        if not user_role:
            raise HTTPException(
                status_code=404,
                detail="User Role not found. Please check and retry.",
            )

        # Fetch all permissions
        permissions = permission_repository.get_user_role_permissions(
            user_role_id=user_role_uuid, field_restrictions=True
        )

        return DataAccessPermissionResponse(
            features=permissions, total=len(permissions)
        )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_role_router.get("/user-roles", response_model=UserRoleResponse)
def get_user_roles(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves user role information for all user roles.
    """
    try:
        user_role_repository = UserRoleRepository(db)

        filters = request.state.filters

        # Fetch all user roles
        user_roles, total = user_role_repository.get_all_user_roles(
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        updated_user_roles = Permissions(db).decompress_role_permissions(db, user_roles)

        return UserRoleResponse(user_roles=updated_user_roles, total=total)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_role_router.get("/user-roles/search", response_model=UserRoleResponse)
def search_user_roles(
    keyword: str = Query(None, description="Search keyword"),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Searches and retrieves user role information based on specified keyword.
    """
    try:
        user_role_repository = UserRoleRepository(db)

        filters = request.state.filters

        # Search user roles
        if keyword:
            user_roles, total = user_role_repository.search_user_roles(
                keyword=keyword,
                filters=filters,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            if user_roles:
                updated_user_roles = Permissions(db).decompress_role_permissions(
                    db, user_roles
                )

                return UserRoleResponse(user_roles=updated_user_roles, total=total)
            else:
                return UserRoleResponse(user_roles=[], total=0)
        else:
            raise HTTPException(
                status_code=400,
                detail="No keyword provided.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_role_router.post("/user-roles", response_model=UserRoleDetail)
def create_user_role(
    user_role_data: UserRoleCreate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Creates a new user role.
    """
    try:
        user_role_repository = UserRoleRepository(db)

        compressed_user_role = Permissions(db).compress_role_permissions(
            user_role_data.model_dump()
        )
        saved_user_role = user_role_repository.create_user_role(compressed_user_role)

        if saved_user_role:
            logger.info(f"User Role created successfully: {saved_user_role.id}")
            return Permissions(db).decompress_role_permissions(db, [saved_user_role])[0]
        else:
            raise HTTPException(status_code=400, detail="Failed to create User Role.")

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_user_role: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_role_router.patch("/user-roles/{user_role_uuid}", response_model=UserRoleDetail)
def update_user_role(
    user_role_uuid: UUID,
    user_role_data: UserRoleUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Updates an existing user role based on its UUID.
    """
    try:
        user_role_repository = UserRoleRepository(db)
        update_data = {
            k: v for k, v in user_role_data.model_dump().items() if v is not None
        }
        compressed_user_role = Permissions(db).compress_role_permissions(update_data)
        compressed_user_role["user_role_uuid"] = user_role_uuid
        updated_user_role = user_role_repository.update_user_role_by_id(
            compressed_user_role
        )

        if updated_user_role:
            logger.info(f"User Role updated successfully: {updated_user_role.id}")
            return Permissions(db).decompress_role_permissions(db, [updated_user_role])[0]
        else:
            raise HTTPException(status_code=404, detail="User role not found.")

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_user_roles: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_role_router.delete("/user-roles/{user_role_uuid}", response_model=Message)
def delete_user_role(
    user_role_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Deletes an existing user role based on its UUID. Only allowed for root user.
    """
    try:
        user_role_repository = UserRoleRepository(db)

        deleted_user_role = user_role_repository.delete_user_role_by_id(user_role_uuid)

        if deleted_user_role:
            logger.info(f"User role deleted successfully: {user_role_uuid}")
            return {"message": "User role deleted successfully."}
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete user role. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_user_role: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
