# Custom libraries
from logger import configure_logging
from configs.agent_llms import AGENT_LLMS
from configs.agent_tools_data import BASIC_AGENT_TOOLS
from configs.integrations import INTEGRATIONS
from configs.user_roles import DEFAULT_ROLES
from schemas.agent_llm_schema import DefaultAgentLLM
from schemas.agent_tool_schema import DefaultAgentTool
from schemas.integration_schema import DefaultIntegration

from schemas.user_role_schema import DefaultUserRole
from schemas.user_schema import Message
from utils.common_utils import restructure_agent_llms
from utils.permissions import Permissions
from utils.schema_utils import get_schema_db, set_schema

# Database modules
from repository.agent_llm_repository import AgentLLMRepository
from repository.agent_tool_repository import AgentToolRepository
from repository.data_collection_repository import DataCollectionRepository
from repository.integration_repository import IntegrationRepository
from repository.organization_repository import OrganizationRepository
from repository.permission_repository import PermissionRepository
from repository.user_repository import UserRepository
from repository.user_role_repository import UserRoleRepository
from sqlalchemy.orm import Session

# Default libraries
from uuid import UUID
import os
import uuid

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException


logger = configure_logging(__name__)

root_router = APIRouter(tags=["Root Routes"], include_in_schema=False)


@root_router.post("/platform/root-user", response_model=Message)
def create_root_user():
    """
    Creates platform ROOT user.
    """
    try:
        # Set schema public for ROOT user
        with set_schema("public") as public_db:
            # Create ROOT user role
            user_role_repository = UserRoleRepository(public_db)
            root_role_data = {
                "name": "ROOT",
                "role_key": "root",
                "description": "System ROOT user with highest access privilege.",
                "default_role": True,
                "role_permissions": {},
            }
            root_role = user_role_repository.create_user_role(
                DefaultUserRole(**root_role_data).model_dump()
            )
            root_role_id = root_role.id

            # Create ROOT user
            user_repository = UserRepository(public_db)
            root_user_data = {
                "email": os.getenv("PLATFORM_ROOT_USER"),
                "password": os.getenv("PLATFORM_ROOT_PASSWORD"),
                "role_id": root_role_id,
                # "app_access": {
                #     "web_application": True,
                # },
                "first_name": "ROOT",
                "last_name": "User",
            }
            root_user = user_repository.create_user(root_user_data)

            logger.info(f"Root user created successfully: {root_user.id}")
            return {"message": "Root user created successfully."}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@root_router.post("/platform/root-data-folder", response_model=Message)
def create_root_data_folder(
    db: Session = Depends(get_schema_db),
):
    """
    Creates ROOT data folder.
    """
    try:
        # Create ROOT data folder
        data_folder_repository = DataCollectionRepository(db)
        root_data_folder = {
            "name": "ROOT",
            "index_name": "root",
            "description": "System ROOT data folder.",
            "status": "ACTIVE",
            "is_root": True,
            "parent_id": None,
        }
        data_folder = data_folder_repository.create_data_collection(root_data_folder)

        logger.info(f"Root Data Folder created successfully: {data_folder.id}")
        return {"message": "Root Data Folder created successfully."}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@root_router.post("/platform/public-organization", response_model=Message)
def create_public_organization():
    """
    Creates PUBLIC organization.
    """
    try:
        # Set schema public for PUBLIC organization
        with set_schema("public") as public_db:
            # Create PUBLIC organization
            organization_repository = OrganizationRepository(public_db)
            public_organization = {
                "id": uuid.uuid4(),
                "name": "Public",
                "tenant_code": "public",
                "db_schema": "public",
            }
            organization = organization_repository.create_organization(
                public_organization
            )

            logger.info(f"Public Organization created successfully: {organization.id}")
            return {"message": "Public Organization created successfully."}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@root_router.post("/platform/system-permissions", response_model=Message)
def create_system_permissions(
    db: Session = Depends(get_schema_db),
):
    """
    Creates system permissions from PLATFORM_MODULES config.
    """
    try:
        permission_repository = PermissionRepository(db)
        permissions = Permissions(db).restructure_permissions_v2()
        permission_repository.create_permissions(permissions)
        logger.info("System permissions created successfully")
        return {"message": "System permissions created successfully."}

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_system_permissions: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@root_router.put("/platform/system-permissions", response_model=Message)
def update_system_permissions(
    db: Session = Depends(get_schema_db),
):
    """
    Updates system permissions from PLATFORM_MODULES config.
    """
    try:
        permission_repository = PermissionRepository(db)
        permissions = Permissions(db).restructure_permissions_v2()
        permission_repository.update_permissions(permissions)
        logger.info("System permissions updated successfully")
        return {"message": "System permissions updated successfully."}

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_system_permissions: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@root_router.post("/platform/default-roles", response_model=Message)
def create_default_roles(
    db: Session = Depends(get_schema_db),
):
    """
    Creates default user roles from config.
    """
    try:
        user_role_repository = UserRoleRepository(db)
        for user_role in DEFAULT_ROLES:
            user_role_data = Permissions(db).compress_role_permissions(
                DefaultUserRole(**user_role).model_dump()
            )
            user_role_repository.create_user_role(user_role_data)
        logger.info("Default roles created successfully")
        return {"message": "Default roles created successfully."}

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_default_roles: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@root_router.put("/platform/default-roles", response_model=Message)
def update_default_roles(
    db: Session = Depends(get_schema_db),
):
    """
    Updates default roles from config.
    """
    try:
        user_role_repository = UserRoleRepository(db)
        for user_role in DEFAULT_ROLES:
            user_role_data = Permissions(db).compress_role_permissions(
                DefaultUserRole(**user_role).model_dump()
            )
            user_role_repository.update_user_role(user_role_data)
        logger.info("Default roles updated successfully")
        return {"message": "Default roles updated successfully."}

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_default_roles: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@root_router.post("/platform/agent-tools", response_model=Message, deprecated=True)
def create_agent_tools(
    db: Session = Depends(get_schema_db),
):
    """
    Creates multiple new basic agent tools.
    """
    try:
        # Create agent tools
        agent_tool_repository = AgentToolRepository(db)
        for agent_tool in BASIC_AGENT_TOOLS:
            agent_tool_repository.create_agent_tool(
                DefaultAgentTool(**agent_tool).model_dump()
            )
        logger.info(f"Agent tools created successfully")
        return {"message": "Agent tools created successfully."}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_agent_tools: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@root_router.put("/platform/agent-tools", response_model=Message, deprecated=True)
def update_agent_tools(
    db: Session = Depends(get_schema_db),
):
    """
    Updates multiple basic agent tools.
    """
    try:
        # Update agent tools
        agent_tool_repository = AgentToolRepository(db)
        for agent_tool in BASIC_AGENT_TOOLS:
            agent_tool_repository.update_agent_tool(
                DefaultAgentTool(**agent_tool).model_dump()
            )
        logger.info(f"Agent tools updated successfully")
        return {"message": "Agent tools updated successfully."}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_agent_tools: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@root_router.post("/platform/integrations", response_model=Message, deprecated=True)
def create_integrations(
    db: Session = Depends(get_schema_db),
):
    """
    Creates multiple new integrations.
    """
    try:
        # Create integrations
        integration_repository = IntegrationRepository(db)
        for integration in INTEGRATIONS:
            integration_repository.create_integration(
                DefaultIntegration(**integration).model_dump()
            )
        logger.info(f"Integrations created successfully")
        return {"message": "Integrations created successfully."}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_integrations: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@root_router.put("/platform/integrations", response_model=Message, deprecated=True)
def update_integrations(
    db: Session = Depends(get_schema_db),
):
    """
    Updates multiple integrations.
    """
    try:
        # Update integrations
        integration_repository = IntegrationRepository(db)
        for integration in INTEGRATIONS:
            integration_repository.update_integration(
                DefaultIntegration(**integration).model_dump()
            )
        logger.info(f"Integrations updated successfully")
        return {"message": "Integrations updated successfully."}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_integrations: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@root_router.post("/platform/setup", response_model=Message)
def setup_platform(
    db: Session = Depends(get_schema_db),
):
    """
    Sets up the system platform.
    """
    try:
        # Create ROOT data folder
        data_folder_repository = DataCollectionRepository(db)
        root_data_folder = {
            "name": "ROOT",
            "index_name": "root",
            "description": "System ROOT data folder.",
            "status": "ACTIVE",
            "is_root": True,
            "parent_id": None,
        }
        data_folder = data_folder_repository.create_data_collection(root_data_folder)
        logger.info(f"Root Data Folder created successfully: {data_folder.id}")

        # Create PUBLIC organization
        organization_repository = OrganizationRepository(db)
        public_organization = {
            "id": uuid.uuid4(),
            "name": "Public",
            "tenant_code": "public",
            "db_schema": "public",
        }
        organization = organization_repository.create_organization(public_organization)
        logger.info(f"Public Organization created successfully: {organization.id}")

        # Create system permissions from PLATFORM_MODULES config
        permission_repository = PermissionRepository(db)
        permissions_util = Permissions(db)
        permissions = permissions_util.restructure_permissions_v2()
        permission_repository.create_permissions(permissions)
        logger.info("System permissions created successfully")

        # Create default user roles
        user_role_repository = UserRoleRepository(db)
        for user_role in DEFAULT_ROLES:
            user_role_data = permissions_util.compress_role_permissions(
                DefaultUserRole(**user_role).model_dump()
            )
            user_role_repository.create_user_role(user_role_data)
        logger.info("Default roles created successfully")

        # Create agent tools
        agent_tool_repository = AgentToolRepository(db)
        for agent_tool in BASIC_AGENT_TOOLS:
            agent_tool_repository.create_agent_tool(
                DefaultAgentTool(**agent_tool).model_dump()
            )
        logger.info(f"Agent tools created successfully")

        # Create integrations
        integration_repository = IntegrationRepository(db)
        for integration in INTEGRATIONS:
            integration_repository.create_integration(
                DefaultIntegration(**integration).model_dump()
            )
        logger.info(f"Integrations created successfully")

        # Create agent LLMs
        agent_llm_repository = AgentLLMRepository(db)
        agent_llms = restructure_agent_llms(AGENT_LLMS)
        for agent_llm in agent_llms:
            agent_llm_repository.create_agent_llm(
                DefaultAgentLLM(**agent_llm).model_dump()
            )
        logger.info(f"Agent LLMs created successfully")

        return {"message": "System Platform setup done successfully."}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@root_router.put("/platform/update", response_model=Message)
def update_platform(
    db: Session = Depends(get_schema_db),
):
    """
    Updates the system platform.
    """
    try:
        # Update system permissions from PLATFORM_MODULES config
        permission_repository = PermissionRepository(db)
        permissions_util = Permissions(db)
        permissions = permissions_util.restructure_permissions_v2()
        permission_repository.update_permissions(permissions)
        logger.info("System permissions updated successfully")

        # Update default user roles
        user_role_repository = UserRoleRepository(db)
        for user_role in DEFAULT_ROLES:
            user_role_data = permissions_util.compress_role_permissions(
                DefaultUserRole(**user_role).model_dump()
            )
            user_role_repository.update_user_role(user_role_data)
        logger.info("Default roles updated successfully")

        # Update agent tools
        agent_tool_repository = AgentToolRepository(db)
        for agent_tool in BASIC_AGENT_TOOLS:
            agent_tool_repository.update_agent_tool(
                DefaultAgentTool(**agent_tool).model_dump()
            )
        logger.info(f"Agent tools updated successfully")

        # Update integrations
        integration_repository = IntegrationRepository(db)
        for integration in INTEGRATIONS:
            integration_repository.update_integration(
                DefaultIntegration(**integration).model_dump()
            )
        logger.info(f"Integrations updated successfully")

        # Update agent LLMs
        agent_llm_repository = AgentLLMRepository(db)
        agent_llms = restructure_agent_llms(AGENT_LLMS)
        for agent_llm in agent_llms:
            agent_llm_repository.create_or_update_agent_llm(
                DefaultAgentLLM(**agent_llm).model_dump()
            )
        logger.info(f"Agent LLMs updated successfully")

        return {"message": "System Platform updated successfully."}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@root_router.delete(
    "/permissions/{permission_uuid}", response_model=Message
)
def delete_permission(
    permission_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Deletes an existing permission based on its UUID.
    """
    try:
        permission_repository = PermissionRepository(db)

        deleted_permission = permission_repository.delete_permission(permission_uuid)

        if deleted_permission:
            logger.info(f"Permission deleted successfully: {permission_uuid}")
            return {"message": "Permission deleted successfully."}
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete Permission. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_permission: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
