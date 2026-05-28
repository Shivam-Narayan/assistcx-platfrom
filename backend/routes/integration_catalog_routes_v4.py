# Custom libraries
from logger import configure_logging
from repository.integration_catalog_repository_v4 import IntegrationCatalogRepository
from schemas.integration_catalog_schema_v4 import (
    IntegrationCatalogItem,
    AuthSchemaCatalogItem,
    TriggerCatalogItem,
)

# Default libraries
from typing import List, Optional

# Installed libraries
from fastapi import APIRouter, HTTPException, Query, Request


logger = configure_logging(__name__)

integration_catalog_router = APIRouter(tags=["Integration Catalog"])


@integration_catalog_router.get(
    "/providers", response_model=List[IntegrationCatalogItem]
)
async def get_integration_catalog(
    keyword: Optional[str] = Query(
        None, description="Search by name, description, key, or tags"
    ),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Items per page"),
    request: Request = None,
):
    """Returns list of integration config details, with triggers and tools scoped to each provider key. Supports keyword search and pagination."""
    try:
        integration_catalog_repository = IntegrationCatalogRepository()

        filters = request.state.filters

        integrations = integration_catalog_repository.get_all_integrations(
            keyword=keyword,
            filters=filters,
            page=page,
            page_size=page_size,
        )
        return [IntegrationCatalogItem.model_validate(i) for i in integrations]
    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@integration_catalog_router.get(
    "/auth-schema-catalog", response_model=List[AuthSchemaCatalogItem]
)
async def get_auth_schema_catalog(
    keyword: Optional[str] = Query(
        None, description="Search by key, display_name, or description"
    ),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Items per page"),
    request: Request = None,
):
    """Returns list of auth schema config details. Key is the config dict key (not in config data). Supports keyword search and pagination."""
    try:
        integration_catalog_repository = IntegrationCatalogRepository()

        filters = request.state.filters

        auth_schemas = integration_catalog_repository.get_all_auth_schemas(
            keyword=keyword,
            filters=filters,
            page=page,
            page_size=page_size,
        )
        return [AuthSchemaCatalogItem.model_validate(i) for i in auth_schemas]
    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@integration_catalog_router.get(
    "/trigger-catalog", response_model=List[TriggerCatalogItem]
)
async def get_trigger_catalog(
    keyword: Optional[str] = Query(
        None, description="Search by name, description, slug, or integration_key"
    ),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Items per page"),
    request: Request = None,
):
    """Returns list of trigger config details. Supports keyword search and pagination."""
    try:
        integration_catalog_repository = IntegrationCatalogRepository()

        filters = request.state.filters

        triggers = integration_catalog_repository.get_all_triggers(
            keyword=keyword,
            filters=filters,
            page=page,
            page_size=page_size,
        )
        return [TriggerCatalogItem.model_validate(i) for i in triggers]
    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
