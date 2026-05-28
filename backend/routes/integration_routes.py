# Custom libraries
from configs.integrations import (
    INTEGRATIONS,
    AUTH_SCHEMA_FIELDS,
)  # sharepoint is used dynamically, Hence Pylance can't detect its usage and marks it as unused (gray).
from integrations.anthropic.integration_config import anthropic
from integrations.aws.integration_config import aws_s3
from integrations.gemini.integration_config import gemini
from integrations.office_365.integration_config import sharepoint, outlook
from integrations.openai.integration_config import openai
from logger import configure_logging
from schemas.integration_schema import (
    IntegrationActivate,
    IntegrationBindings,
    IntegrationCredentials,
    IntegrationDetail,
    IntegrationResponse,
    IntegrationTags,
)
from schemas.agent_llm_schema import AgentLLMResponse
from utils.common_utils import get_integration_actions, parse_identifier
from utils.integration_utils import IntegrationValidator
from utils.schema_utils import get_schema_db

# Database modules
from repository.agent_tool_repository import AgentToolRepository
from repository.integration_repository import IntegrationRepository
from repository.mailbox_polling_repository import MailboxPollingRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional, Union
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request


logger = configure_logging(__name__)

integration_router = APIRouter(tags=["Integrations"])


@integration_router.get("/integrations", response_model=IntegrationResponse)
def get_integrations(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves integration information based on specified criteria.
    """
    try:
        integration_repository = IntegrationRepository(db)

        filters = request.state.filters

        # Fetch all integrations with filters and sorting
        integrations, total = integration_repository.get_all_integrations(
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return IntegrationResponse(integrations=integrations, total=total)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@integration_router.get("/integrations/search", response_model=IntegrationResponse)
def search_integrations(
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
    Searches and retrieves integration information based on specified keyword.
    """
    try:
        integration_repository = IntegrationRepository(db)

        filters = request.state.filters

        # Search integrations with sorting
        if keyword:
            integrations, total = integration_repository.search_integrations(
                keyword=keyword,
                filters=filters,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            if integrations:
                return IntegrationResponse(integrations=integrations, total=total)
            else:
                return IntegrationResponse(integrations=[], total=0)
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


@integration_router.get("/integrations/tags", response_model=IntegrationTags)
def get_integration_tags(
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves all unique integration tags.
    """
    try:
        integration_repository = IntegrationRepository(db)

        tags = integration_repository.get_integration_tags()

        return IntegrationTags(tags=tags)

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@integration_router.get("/integrations/llms", response_model=AgentLLMResponse)
def get_active_agent_llms(
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves active agent LLMs with complete configuration objects.
    Returns only LLMs from active and validated integrations.
    """
    try:
        integration_repository = IntegrationRepository(db)
        active_llms = integration_repository.get_active_agent_llm()

        return AgentLLMResponse(agent_llms=active_llms)

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error fetching active agent LLMs: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while fetching active agent LLMs: {e}",
        )


@integration_router.get(
    "/integrations/{integration_identifier}", response_model=IntegrationResponse
)
def get_integration(
    integration_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves integration information based on integration_identifier.
    """
    try:
        integration_repository = IntegrationRepository(db)

        if integration_identifier:
            # Fetch a single integration by integration_identifier
            integration = integration_repository.get_integration(
                parse_identifier(integration_identifier)
            )
            if integration is not None:
                return IntegrationResponse(
                    integrations=[integration],
                    markdown_content=globals().get(integration.key, None),
                    total=1,
                )
            # globals() checks the global namespace of the current Python file
            # It allows access to variables and imports defined at the top level of this file,
            # and can be used to dynamically retrieve the corresponding markdown content based on the integration key

            else:
                raise HTTPException(
                    status_code=404,
                    detail="Integration not found. Please check and retry.",
                )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@integration_router.get(
    "/integrations/{integration_identifier}/bindings",
    response_model=IntegrationBindings,
)
def get_integration_bindings(
    integration_identifier: Union[UUID, str],
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves all agent tools and agent LLMs bound to a specific integration.
    """
    try:
        # Initialize repositories
        integration_repository = IntegrationRepository(db)

        # Get integration using existing repository function
        integration = integration_repository.get_integration(
            parse_identifier(integration_identifier)
        )

        if not integration:
            raise HTTPException(
                status_code=404,
                detail="Integration not found. Please check and retry.",
            )

        integration_type = integration.integration_config["integration_type"]
        actions = get_integration_actions(db, integration_type, integration.key)

        response_data = {
            "id": integration.id,
            "key": integration.key,
            "integration_type": integration.integration_config["integration_type"],
            "actions": [
                {
                    "id": action.get("id"),
                    "name": action.get("name"),
                    "description": action.get("description"),
                    "icon": action.get("icon"),
                    "action": action.get("action"),
                    "type": action.get("type"),
                }
                for action in actions
            ],
        }
        return IntegrationBindings.model_validate(response_data)
    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@integration_router.get(
    "/integrations/{integration_identifier}/credentials",
    response_model=IntegrationCredentials,
)
def get_integration_credentials(
    integration_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves integration credentials information based on its integration_identifier.
    """
    try:
        integration_repository = IntegrationRepository(db)

        if integration_identifier:
            # Fetch a single integration by integration_identifier
            integration = integration_repository.get_integration(
                identifier=parse_identifier(integration_identifier),
                decrypt_credentials=True,
            )
            if integration is not None:
                integration_data = {
                    "id": integration.id,
                    "key": integration.key,
                    "preset": integration.auth_schema_fields["preset"],
                    "credentials": integration.credentials,
                }
                return IntegrationCredentials(**integration_data)

            else:
                raise HTTPException(
                    status_code=404,
                    detail="Integration not found. Please check and retry.",
                )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@integration_router.post(
    "/integrations/{integration_uuid}/activate", response_model=IntegrationDetail
)
def activate_integration(
    integration_uuid: UUID,
    integration_data: IntegrationActivate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Updates an existing integration based on its integration_uuid.
    """
    try:
        validator = IntegrationValidator(
            auth_schema=AUTH_SCHEMA_FIELDS,
            preset=integration_data.preset,
            integrations=INTEGRATIONS,
        )

        # Validate credentials
        is_valid, error_message = validator.validate_credentials(
            integration_data.key, integration_data.credentials
        )

        if not is_valid:
            raise HTTPException(status_code=400, detail=f"{error_message}")

        integration_repository = IntegrationRepository(db=db)

        update_data = {
            k: v for k, v in integration_data.model_dump().items() if v is not None
        }

        # Append integration_uuid to update_data
        update_data["integration_uuid"] = integration_uuid
        update_data["is_active"] = True

        integration = integration_repository.update_integration_by_id(update_data)

        if not integration:
            raise HTTPException(
                status_code=404,
                detail="Integration not found. Please check and retry.",
            )

        integration_type = integration.integration_config.get("integration_type")
        if integration_type == "tool":
            agent_tool_repository = AgentToolRepository(db=db)
            activated_tools = agent_tool_repository.update_agent_tool_by_integration(
                integration_key=integration.key, status="enable"
            )
            for agent_tool in activated_tools:
                logger.info(f"Activated {agent_tool.name} tool")
            logger.info(f"Integration activated successfully: {integration.id}")
            return IntegrationDetail.model_validate(integration)
        elif integration_type == "agent_llm":
            logger.info(f"Integration activated successfully: {integration.id}")
            return IntegrationDetail.model_validate(integration)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to activate Integration. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@integration_router.post(
    "/integrations/{integration_uuid}/deactivate", response_model=IntegrationDetail
)
def deactivate_integration(
    integration_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Deactivate an existing integration based on its integration_uuid.
    """
    try:
        integration_repository = IntegrationRepository(db)
        integration = integration_repository.get_integration(
            identifier=integration_uuid
        )
        if integration is None:
            raise HTTPException(
                status_code=404,
                detail="Integration not found. Please check and retry.",
            )

        # Specific check for Outlook integration
        if integration.name == "Outlook":
            mailbox_polling_repository = MailboxPollingRepository(db)
            mailbox_pollings, total = (
                mailbox_polling_repository.get_all_mailbox_pollings()
            )
            if any(mailbox.status == "RUNNING" for mailbox in mailbox_pollings):
                raise HTTPException(
                    status_code=400,
                    detail="One or more mailbox polling is active. Please deactivate it first.",
                )

        update_data = {
            "integration_uuid": integration_uuid,
            "credentials": None,  # Set credentials to None to clear the field
            "is_active": False,
        }

        integration = integration_repository.update_integration_by_id(update_data)

        integration_type = integration.integration_config.get("integration_type")
        if integration_type == "tool":
            agent_tool_repository = AgentToolRepository(db=db)
            deacivated_tools = agent_tool_repository.update_agent_tool_by_integration(
                integration_key=integration.key, status="disable"
            )
            for agent_tool in deacivated_tools:
                logger.info(f"Deactivated {agent_tool.name} tool")
            logger.info(f"Integration deactivated successfully: {integration.id}")
            return IntegrationDetail.model_validate(integration)
        elif integration_type == "agent_llm":
            logger.info(f"Integration deactivated successfully: {integration.id}")
            return IntegrationDetail.model_validate(integration)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to deactivate Integration. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
