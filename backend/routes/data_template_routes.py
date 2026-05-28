# Custom libraries
from builders.data_schema_builder.service import DataSchemaBuilderService
from builders.data_schema_builder.schemas import DataSchemaBuilderInput
from logger import configure_logging
from schemas.data_template_schema import (
    DataSchemaBuilder,
    DataSchemaBuilderDetail,
    DataTemplateCreate,
    DataTemplateDetail,
    DataTemplateResponse,
    DataTemplateUpdate,
)
from schemas.user_schema import Message
from utils.common_utils import parse_identifier
from utils.schema_utils import get_schema_db, get_current_schema

# Database modules
from repository.data_template_repository import DataTemplateRepository
from repository.version_history_repository import VersionHistoryRepository
from sqlalchemy.orm import Session

# Default libraries
import asyncio
from typing import Optional, Union
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordBearer
from jwt import decode
import os


logger = configure_logging(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")

data_template_router = APIRouter(tags=["Data Templates"])


@data_template_router.get("/data-templates", response_model=DataTemplateResponse)
def get_data_templates(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves data template information based on specified criteria.
    """
    try:
        data_template_repository = DataTemplateRepository(db)

        filters = request.state.filters

        # Fetch all data templates without pagination and with filtering
        templates, total = data_template_repository.get_all_data_templates(
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return DataTemplateResponse(data_templates=templates, total=total)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_template_router.get("/data-templates/search", response_model=DataTemplateResponse)
def search_data_templates(
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
    Searches and retrieves data template information based on specified keyword.
    """
    try:
        data_template_repository = DataTemplateRepository(db)

        filters = request.state.filters

        # Search data templates
        if keyword:
            templates, total = data_template_repository.search_data_templates(
                keyword=keyword,
                filters=filters,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )
            if templates:
                return DataTemplateResponse(data_templates=templates, total=total)
            else:
                return DataTemplateResponse(data_templates=[], total=0)
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


@data_template_router.get(
    "/data-templates/{data_template_identifier}", response_model=DataTemplateResponse
)
def get_data_template(
    data_template_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves data template information based on its data_template_identifier.
    """
    try:
        data_template_repository = DataTemplateRepository(db)

        if data_template_identifier:
            # Fetch a single data template by ID
            data_template = data_template_repository.get_template(
                parse_identifier(data_template_identifier)
            )
            if data_template is not None:
                return DataTemplateResponse(data_templates=[data_template], total=1)
            else:
                raise HTTPException(
                    status_code=404,
                    detail="Data Template not found. Please check and retry.",
                )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_template_router.post("/data-templates", response_model=DataTemplateDetail)
def create_data_template(
    template_data: DataTemplateCreate = Body(...),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """
    Creates a new data template.
    """
    try:
        data_template_repository = DataTemplateRepository(db)

        result_template = data_template_repository.create_template(template_data)

        if result_template:
            # Extract user from token
            decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
            user_id = UUID(decoded_token["sub"])

            # Prepare config data for data template version history excluding some fields
            config_data = DataTemplateDetail.model_validate(result_template).model_dump(
                exclude={"id", "created_at", "updated_at"}
            )

            # Create a version history for the new data template
            version_history_repository = VersionHistoryRepository(db)
            version_history = version_history_repository.create_version_history(
                {
                    "entity_type": "data_template",
                    "entity_id": result_template.id,
                    "config_data": config_data,
                    "user_id": user_id,
                }
            )
            if not version_history:
                logger.error(
                    f"Failed to create version history for data template: {result_template.id}"
                )

            logger.info(f"Data Template created successfully: {result_template.id}")
            return DataTemplateDetail.model_validate(result_template)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create Data Template.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_template_router.patch(
    "/data-templates/{data_template_uuid}", response_model=DataTemplateDetail
)
def update_data_template(
    data_template_uuid: UUID,
    template_data: DataTemplateUpdate = Body(...),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """
    Updates an existing data template based on its data_template_uuid.
    """
    try:
        data_template_repository = DataTemplateRepository(db)

        # Get existing template state before update
        existing_template = data_template_repository.get_template(data_template_uuid)
        if not existing_template:
            raise HTTPException(
                status_code=404,
                detail="Data Template not found. Please check and retry.",
            )

        # Capture old config data for comparison
        old_config_data = DataTemplateDetail.model_validate(
            existing_template
        ).model_dump(exclude={"id", "created_at", "updated_at"})

        update_data = {
            k: v for k, v in template_data.model_dump().items() if v is not None
        }

        # Append template_uuid to update_data
        update_data["template_uuid"] = data_template_uuid

        result_template = data_template_repository.update_template(update_data)

        if result_template:
            # Extract user from token
            decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
            user_id = UUID(decoded_token["sub"])

            # Prepare config data for data template version history excluding some fields
            config_data = DataTemplateDetail.model_validate(result_template).model_dump(
                exclude={"id", "created_at", "updated_at"}
            )

            # Only create version history if there are actual changes
            if config_data != old_config_data:
                version_history_repository = VersionHistoryRepository(db)
                version_history = version_history_repository.create_version_history(
                    {
                        "entity_type": "data_template",
                        "entity_id": result_template.id,
                        "config_data": config_data,
                        "user_id": user_id,
                    }
                )
                if not version_history:
                    logger.error(
                        f"Failed to create version history for data template: {result_template.id}"
                    )

            logger.info(f"Data Template updated successfully: {result_template.id}")
            return DataTemplateDetail.model_validate(result_template)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Data Template. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_template_router.post(
    "/data-templates/build-schema", response_model=DataSchemaBuilderDetail
)
def build_data_schema(
    template_data: DataSchemaBuilder = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Generates the data schema for a data template based on its name and description.
    """
    try:
        organization_schema = get_current_schema(db)

        data_schema_builder_service = DataSchemaBuilderService(organization_schema, db)
        result = asyncio.run(
            data_schema_builder_service.generate_data_schema(
                DataSchemaBuilderInput(
                    name=template_data.name,
                    description=template_data.description,
                    previous_schema=(
                        [field.model_dump() for field in template_data.previous_schema]
                        if template_data.previous_schema
                        else None
                    ),
                    user_instructions=template_data.user_instructions,
                )
            )
        )

        if result:
            return DataSchemaBuilderDetail.model_validate(result)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to generate data schema for data template.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in build_data_schema: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_template_router.delete(
    "/data-templates/{data_template_identifier}", response_model=Message
)
def delete_data_template(
    data_template_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Deletes an existing data_template based on its data_template_identifier. Only allowed for ROOT user.
    """
    try:
        data_template_repository = DataTemplateRepository(db)

        deleted_data_template = data_template_repository.delete_data_template(
            parse_identifier(data_template_identifier)
        )

        if deleted_data_template:
            logger.info(
                f"Data Template deleted successfully: {data_template_identifier}"
            )
            return {"message": "Data Template deleted successfully."}
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete Data Template. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_data_template: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# Deprecated
# @data_template_router.get("/v1/data-templates", response_model=DataTemplateResponse)
# def get_paginated_data_templates(
#     page: int = Query(1, description="Page number", gt=0),
#     page_size: int = Query(10, description="Number of items per page", gt=0),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Retrieves paginated data template information based on specified criteria.
#     """
#     try:
#         data_template_repository = DataTemplateRepository(db)

#         filters = request.state.filters

#         # Fetch paginated data templates
#         templates, total = data_template_repository.paginated_data_templates(
#             page=page,
#             page_size=page_size,
#             filters=filters,
#             sort_by=sort_by,
#             sort_order=sort_order,
#         )

#         return DataTemplateResponse(data_templates=templates, total=total)

#     except HTTPException as http_error:
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @data_template_router.get(
#     "/v1/data-templates-search", response_model=DataTemplateResponse
# )
# def search_paginated_data_templates(
#     keyword: str = Query(None, description="Search keyword"),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     page: int = Query(1, description="Page number", gt=0),
#     page_size: int = Query(10, description="Number of items per page", gt=0),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves paginated data template information based on specified keyword.
#     """
#     try:
#         data_template_repository = DataTemplateRepository(db)

#         filters = request.state.filters

#         # Search and paginate data templates
#         if keyword:
#             templates, total = data_template_repository.paginated_search_templates(
#                 keyword=keyword,
#                 page=page,
#                 page_size=page_size,
#                 filters=filters,
#                 sort_by=sort_by,
#                 sort_order=sort_order,
#             )

#             if templates:
#                 return DataTemplateResponse(data_templates=templates, total=total)
#             else:
#                 return DataTemplateResponse(data_templates=[], total=0)
#         else:
#             raise HTTPException(
#                 status_code=400,
#                 detail="No keyword provided.",
#             )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @data_template_router.get(
#     "/data-templates/search", response_model=DataTemplatesResponse
# )
# def search_data_templates(
#     keyword: str = Query(None, description="Search keyword"),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves data template information based on specified keyword.
#     """
#     try:
#         data_template_repository = DataTemplateRepository(db)

#         filters = request.state.filters

#         # Search data templates
#         if keyword:
#             templates, total = data_template_repository.search_templates(
#                 keyword=keyword,
#                 filters=filters,
#                 sort_by=sort_by,
#                 sort_order=sort_order,
#             )
#             if templates:
#                 return DataTemplatesResponse(data_templates=templates, total=total)
#             else:
#                 return DataTemplatesResponse(data_templates=[], total=0)
#         else:
#             raise HTTPException(
#                 status_code=400,
#                 detail="No keyword provided.",
#             )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @data_template_router.get(
#     "/v1/data-templates/search", response_model=DataTemplatesResponse
# )
# def search_paginated_data_templates(
#     keyword: str = Query(None, description="Search keyword"),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     page: int = Query(1, description="Page number", gt=0),
#     page_size: int = Query(10, description="Number of items per page", gt=0),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves paginated data template information based on specified keyword.
#     """
#     try:
#         data_template_repository = DataTemplateRepository(db)

#         filters = request.state.filters

#         # Search and paginate data templates
#         if keyword:
#             templates, total = data_template_repository.paginated_search_templates(
#                 keyword=keyword,
#                 page=page,
#                 page_size=page_size,
#                 filters=filters,
#                 sort_by=sort_by,
#                 sort_order=sort_order,
#             )

#             if templates:
#                 return DataTemplatesResponse(data_templates=templates, total=total)
#             else:
#                 return DataTemplatesResponse(data_templates=[], total=0)
#         else:
#             raise HTTPException(
#                 status_code=400,
#                 detail="No keyword provided.",
#             )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
