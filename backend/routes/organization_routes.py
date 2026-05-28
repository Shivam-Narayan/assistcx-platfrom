# Custom libraries
from agents.shared_utils.checkpointer import run_checkpointer_migrations
from logger import configure_logging
from schemas.organization_schema import (
    OrganizationCreate,
    OrganizationDetail,
    OrganizationResponse,
    OrganizationUpdate,
    OrganizationAlembicMigration,
)
from schemas.user_schema import Message
from utils.authentication import Authentication
from utils.schema_utils import (
    get_organization_schemas,
    get_schema_db,
    get_session_for_role,
    run_alembic_migration,
    set_schema,
)

# Database modules
from repository.organization_repository import OrganizationRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import List, Optional
from uuid import UUID
import json
import os
import uuid

# Installed libraries
from asgiref.sync import async_to_sync
from fastapi import APIRouter, HTTPException, Request, Body, Depends, Query
from fastapi.security import OAuth2PasswordBearer
from jwt import decode


logger = configure_logging(__name__)

authentication = Authentication()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")

organization_router = APIRouter(tags=["Organizations"])


@organization_router.get("/organizations", response_model=OrganizationResponse)
def get_organizations(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
    request: Request = None,
):
    """
    Retrieves organization information based on specified criteria.
    """
    try:
        # Decode JWT token and extract information from decoded payload
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_role = decoded_token["user_role"]

        # Get appropriate session based on user role
        with get_session_for_role(user_role, db) as session:
            organization_repository = OrganizationRepository(session)
            filters = request.state.filters

            organizations = organization_repository.get_all_organizations(
                filters=filters, sort_by=sort_by, sort_order=sort_order
            )

            return OrganizationResponse(
                organizations=organizations, total=len(organizations)
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@organization_router.get("/organizations/current", response_model=OrganizationResponse)
def get_current_organization(
    db: Session = Depends(get_schema_db), token: str = Depends(oauth2_scheme)
):
    """
    Retrieves current organization information.
    """
    try:
        # Decode JWT token and extract information from decoded payload
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        organization_id = decoded_token["org_id"]

        # Override schema and set to public
        with set_schema("public") as public_db:
            organization_repository = OrganizationRepository(public_db)

            organization = organization_repository.get_organization_by_db_schema(
                organization_id
            )

            return OrganizationResponse(organizations=[organization], total=1)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@organization_router.get("/organizations/schemas", response_model=List[str])
def organization_schemas():
    """
    Retrieves organization_schemas information.
    """
    try:
        return get_organization_schemas()

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@organization_router.post("/organizations/migrations", response_model=Message)
def apply_alembic_migration(
    alembic_migration_data: OrganizationAlembicMigration = Body(...),
):
    """
    Applies alembic migration to all or specified organization schemas.
    """
    try:
        if not alembic_migration_data.organization_schemas:
            raise HTTPException(
                status_code=400, detail="No organization schemas provided."
            )

        schemas = (
            get_organization_schemas()
            if "ALL" in alembic_migration_data.organization_schemas
            else alembic_migration_data.organization_schemas
        )

        for i in schemas:
            run_alembic_migration(i)
            async_to_sync(run_checkpointer_migrations)(i)

        logger.info(f"Applied alembic migration to organization schemas: {schemas}")
        return {"message": "Alembic migration applied successfully."}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@organization_router.post("/organizations", response_model=OrganizationDetail)
def create_organization(
    organization_data: OrganizationCreate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Creates a new organization.
    """
    try:
        organization_repository = OrganizationRepository(db)

        # Generate Organization ID
        organization_id = uuid.uuid4()

        # Prepare data with organization ID and tenant code
        organization = organization_data.model_dump()
        organization["id"] = organization_id
        organization["db_schema"] = str(organization_id)

        result_organization = organization_repository.create_organization(organization)

        if result_organization:
            logger.info(f"Organization created successfully: {result_organization.id}")
            return OrganizationDetail.model_validate(result_organization)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create Organization.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@organization_router.patch(
    "/organizations/{organization_uuid}", response_model=OrganizationDetail
)
def update_organization(
    organization_uuid: UUID,
    organization_data: OrganizationUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Updates an existing organization based on its organization_uuid.
    """
    try:
        organization_repository = OrganizationRepository(db)

        update_data = {
            k: v for k, v in organization_data.model_dump().items() if v is not None
        }

        # Append organization_uuid to update_data
        update_data["organization_uuid"] = organization_uuid

        updated_organization = organization_repository.update_organization(update_data)

        if updated_organization:
            logger.info(f"Organization updated successfully: {updated_organization.id}")
            return OrganizationDetail.model_validate(updated_organization)
        else:
            raise HTTPException(
                status_code=404,
                detail="Organization UUID not found or incorrect. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@organization_router.patch("/organizations/current", response_model=OrganizationDetail)
def update_current_organization(
    organization_data: OrganizationUpdate = Body(...),
    token: str = Depends(oauth2_scheme),
):
    """
    Updates the current organization information.
    """
    try:
        # Decode JWT token and extract information from decoded payload
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_role = decoded_token["user_role"]
        organization_id = decoded_token["org_id"]

        # Override schema and set to public
        with set_schema("public") as public_db:
            organization_repository = OrganizationRepository(public_db)

            update_data = {
                k: v
                for k, v in organization_data.model_dump().items()
                if v is not None
                and (user_role == "ROOT" or k in {"contact_info", "address"})
            }

            # Append organization_id to update_data
            update_data["organization_uuid"] = organization_id

            updated_organization = organization_repository.update_organization(
                update_data
            )

            if updated_organization:
                logger.info(
                    f"Organization updated successfully: {updated_organization.id}"
                )
                return OrganizationDetail.model_validate(updated_organization)
            else:
                raise HTTPException(
                    status_code=404,
                    detail="Organization not found. Please check and retry.",
                )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
