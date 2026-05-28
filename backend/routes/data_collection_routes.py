# Custom libraries
from configs.embedding_models import get_embedding_config
from knowledge.milvus_store import MilvusStore
from logger import configure_logging
from integrations.office_365.sharepoint import Sharepoint
from schemas.data_collection_schema import (
    DataCollectionCreate,
    DataCollectionDataFileResponse,
    DataCollectionDetail,
    DataCollectionResponse,
    DataCollectionSiteUpdate,
    DataCollectionUpdate,
)
from schemas.data_file_schema import DataFileResponse
from schemas.user_schema import Message
from utils.common_utils import (
    generate_short_id,
    sanitize_data_store,
)
from utils.collection_utils import get_default_knowledge_data_store, collection_in_allowed_tree
from utils.schema_utils import get_schema_db

# Database modules
from repository.data_file_repository import DataFileRepository
from repository.data_collection_repository import DataCollectionRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional
from uuid import UUID
import os

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordBearer
from jwt import decode
import re


logger = configure_logging(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")

data_collection_router = APIRouter(tags=["Data Collections"])


@data_collection_router.get(
    "/collections", response_model=DataCollectionDataFileResponse
)
@data_collection_router.get(
    "/assistant/collections", response_model=DataCollectionDataFileResponse
)
def get_data_collections(
    collection_id: Optional[UUID] = Query(None, description="Data Collection ID"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves data collections information based on specified criteria.
    """
    try:
        data_collection_repository = DataCollectionRepository(db)

        filters = request.state.filters

        # If drilling into a collection, verify access via ancestor chain and
        # don't apply the collection-name RBAC filter inside the tree.
        target_collection = None
        inner_filters = filters
        if collection_id:
            target_collection = data_collection_repository.get_data_collection_by_id(
                collection_id
            )
            if not target_collection:
                raise HTTPException(status_code=404, detail="Data Collection not found.")
            if filters and "name" in filters:
                if not collection_in_allowed_tree(
                    target_collection, filters["name"], data_collection_repository
                ):
                    raise HTTPException(status_code=403, detail="Access denied.")
                inner_filters = {k: v for k, v in filters.items() if k != "name"} or None

        # Fetch all data collections (children of target, or top-level if no target)
        data_collections, total = data_collection_repository.get_all_data_collections(
            collection_id=collection_id,
            page=page,
            page_size=page_size,
            filters=inner_filters if collection_id else filters,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Fetch data files only if collection_id is provided
        data_files = []
        if collection_id:
            data_file_repository = DataFileRepository(db)
            # RBAC filter is on collection.name, not file.name — scope via collection_id only
            data_files, total = data_file_repository.get_all_data_files(
                collection_id=collection_id,
                page=page,
                page_size=page_size,
                filters=inner_filters,
                sort_by=sort_by,
                sort_order=sort_order,
            )

        return DataCollectionDataFileResponse.from_data_collections_and_data_files(
            data_collections=data_collections, data_files=data_files, total=total
        )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in get_data_collections: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_collection_router.get(
    "/collections/search", response_model=DataCollectionDataFileResponse
)
@data_collection_router.get(
    "/assistant/collections/search", response_model=DataCollectionDataFileResponse
)
def search_data_collections_and_files(
    keyword: str = Query(..., description="Search keyword"),
    collection_id: Optional[UUID] = Query(None, description="Data Collection ID"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Searches and retrieves data collection information based on specified keyword.
    """
    try:
        data_collection_repository = DataCollectionRepository(db)
        data_file_repository = DataFileRepository(db)

        filters = request.state.filters

        # Search data collections
        if keyword:
            # If drilling into a collection, verify access via ancestor chain
            # and don't apply the collection-name RBAC filter inside the tree.
            inner_filters = filters
            if collection_id:
                target_collection = data_collection_repository.get_data_collection_by_id(
                    collection_id
                )
                if not target_collection:
                    raise HTTPException(
                        status_code=404, detail="Data Collection not found."
                    )
                if filters and "name" in filters:
                    if not collection_in_allowed_tree(
                        target_collection,
                        filters["name"],
                        data_collection_repository,
                    ):
                        raise HTTPException(status_code=403, detail="Access denied.")
                    inner_filters = {
                        k: v for k, v in filters.items() if k != "name"
                    } or None

            data_collections, total = (
                data_collection_repository.search_data_collections(
                    keyword=keyword,
                    collection_id=collection_id,
                    page=page,
                    page_size=page_size,
                    filters=inner_filters if collection_id else filters,
                    sort_by=sort_by,
                    sort_order=sort_order,
                )
            )

            # Only when collection_id is present, we should return respective files.
            data_files = []
            if collection_id:
                # RBAC filter is on collection.name, not file.name — scope via collection_id only
                data_files, total = data_file_repository.search_data_files(
                    keyword=keyword,
                    collection_id=collection_id,
                    page=page,
                    page_size=page_size,
                    filters=inner_filters,
                    sort_by=sort_by,
                    sort_order=sort_order,
                )

            return DataCollectionDataFileResponse.from_data_collections_and_data_files(
                data_collections=data_collections, data_files=data_files, total=total
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="No keyword provided",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in search_data_collections_and_files: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_collection_router.get(
    "/collections/{data_collection_uuid}", response_model=DataCollectionResponse
)
@data_collection_router.get(
    "/assistant/collections/{data_collection_uuid}", response_model=DataCollectionResponse
)
def get_data_collection(
    data_collection_uuid: UUID, db: Session = Depends(get_schema_db)
):
    """
    Retrieves data collection information based on data_collection_uuid.
    """
    try:
        data_collection_repository = DataCollectionRepository(db)

        # Check if data collection exists using data_collection_uuid
        data_collection = data_collection_repository.get_data_collection_by_id(
            data_collection_uuid
        )

        if data_collection:
            return DataCollectionResponse(data_collections=[data_collection], total=1)
        else:
            raise HTTPException(
                status_code=404,
                detail="Data Collection not found. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_data_collection: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_collection_router.post("/collections", response_model=DataCollectionDetail)
@data_collection_router.post("/assistant/collections", response_model=DataCollectionDetail)
def create_data_collection(
    data_collection_data: DataCollectionCreate = Body(...),
    db: Session = Depends(get_schema_db),
    milvus_store: MilvusStore = Depends(lambda: MilvusStore()),
    token: str = Depends(oauth2_scheme),
):
    """
    Creates a new data collection.
    """
    try:
        # Extract user_id from the token
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_id = UUID(decoded_token["sub"])

        # Inject default data_store (same as private_data_collection)
        data_store = sanitize_data_store(get_default_knowledge_data_store())

        data_collection_repository = DataCollectionRepository(db)

        # Look up embedding model dimensions from config (O(1) lookup)
        embedding_model = data_collection_data.collection_config.embedding_model
        embedding_config = get_embedding_config(embedding_model)
        if not embedding_config:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid embedding model: {embedding_model}",
            )
        dense_dim = embedding_config["dimensions"]

        index_name = (
            re.sub(r"[^a-zA-Z0-9_]", "_", data_collection_data.name).lower()
            + "_"
            + generate_short_id(4)
        )
        if milvus_store.create_collection(collection_name=index_name, dense_dim=dense_dim):
            collection_data = data_collection_data.model_dump()
            collection_data["index_name"] = index_name
            collection_data["owner_id"] = user_id
            # Inject default data_store 
            if collection_data.get("collection_config") is None:
                collection_data["collection_config"] = {}
            collection_data["collection_config"]["data_store"] = data_store
            new_data_collection = data_collection_repository.create_data_collection(
                collection_data
            )
            if new_data_collection:
                logger.info(
                    f"Data Collection created successfully: {new_data_collection.id}"
                )
                return DataCollectionDetail.model_validate(new_data_collection)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create Data Collection.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_collection_router.patch(
    "/collections/{data_collection_uuid}", response_model=DataCollectionDetail
)
@data_collection_router.patch(
    "/assistant/collections/{data_collection_uuid}", response_model=DataCollectionDetail
)
def update_data_collection(
    data_collection_uuid: UUID,
    data_collection_data: DataCollectionUpdate,
    db: Session = Depends(get_schema_db),
    # milvus_store: MilvusStore = Depends(lambda: MilvusStore()),
):
    """
    Updates an existing data collection based on its data_collection_uuid.
    """
    try:
        data_collection_repository = DataCollectionRepository(db)

        update_data = data_collection_data.model_dump(exclude_unset=True)

        # Append data_collection_uuid to update_data
        update_data["data_collection_uuid"] = data_collection_uuid

        # # If name is provided, update Milvus data collection name
        # if "name" in update_data:
        #     update_data["index_name"] = re.sub(
        #         r"[^a-zA-Z0-9_]", "_", update_data.get("name")
        #     ).lower()
        #     data_collection = data_collection_repository.get_data_collection_by_id(
        #         data_collection_uuid
        #     )
        #     if not data_collection:
        #         raise HTTPException(
        #             status_code=404, detail="Data Collection not found."
        #         )
        #     old_name = data_collection.name
        #     new_name = update_data["name"]
        #     if old_name != new_name:
        #         old_index_name = re.sub(r"[^a-zA-Z0-9_]", "_", old_name).lower()
        #         new_index_name = re.sub(r"[^a-zA-Z0-9_]", "_", new_name).lower()
        #         success = milvus_store.rename_collection(old_index_name, new_index_name)
        #         if not success:
        #             raise HTTPException(
        #                 status_code=500,
        #                 detail=f"Failed to rename Milvus collection from {old_index_name} to {new_index_name}.",
        #             )

        updated_data_collection = data_collection_repository.update_data_collection(
            update_data
        )

        if updated_data_collection:
            logger.info(
                f"Data Collection updated successfully: {updated_data_collection.id}"
            )
            return DataCollectionDetail.model_validate(updated_data_collection)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Data Collection. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_data_collection: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_collection_router.delete(
    "/collections/{data_collection_uuid}", response_model=Message
)
@data_collection_router.delete(
    "/assistant/collections/{data_collection_uuid}", response_model=Message
)
def delete_data_collection(
    data_collection_uuid: UUID,
    db: Session = Depends(get_schema_db),
    milvus_store: MilvusStore = Depends(lambda: MilvusStore()),
):
    """
    Deletes an existing data collection based on its UUID.

    Args:
        data_collection_uuid: The UUID of the data collection to delete
        db: Database session dependency

    Returns:
        Message confirming successful deletion

    Raises:
        HTTPException: If data collection not found (404) or deletion fails (400, 500)
    """
    logger.info(f"Attempting to delete data collection: {data_collection_uuid}")

    try:
        # Get data collection from database
        data_collection_repository = DataCollectionRepository(db)
        data_collection = data_collection_repository.get_data_collection_by_id(
            data_collection_uuid
        )

        if not data_collection:
            logger.warning(f"Collection not found: {data_collection_uuid}")
            raise HTTPException(
                status_code=404,
                detail="Collection not found. Please check and retry.",
            )

        # Delete from Milvus first
        if not milvus_store.delete_collection(
            collection_name=data_collection.index_name
        ):
            logger.error(
                f"Failed to delete collection from Milvus: {data_collection.index_name}"
            )
            raise HTTPException(
                status_code=400,
                detail="Failed to delete data collection from vector database.",
            )

        # If Milvus deletion successful, delete from repository
        deleted_collection = data_collection_repository.delete_data_collection(
            data_collection_uuid
        )
        if not deleted_collection:
            logger.error(f"Failed to delete data collection: {data_collection_uuid}")
            raise HTTPException(
                status_code=500,
                detail="Data Collection removed from vector database but failed to delete metadata.",
            )

        logger.info(f"Data Collection deleted successfully: {data_collection_uuid}")
        return {"message": "Data Collection deleted successfully."}

    except HTTPException:
        # Pass through HTTP exceptions without wrapping
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in delete_data_collection: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while deleting the data collection.",
        )


@data_collection_router.post(
    "/collections/{collection_uuid}/sharepoint-sites", response_model=Message
)
@data_collection_router.post(
    "/assistant/collections/{collection_uuid}/sharepoint-sites", response_model=Message
)
def connect_disconnect_sharepoint_site(
    collection_uuid: str,
    collection_site_data: DataCollectionSiteUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """Connects or disconnects a SharePoint site to/from a data collection based on its collection_uuid."""
    try:
        sharepoint = Sharepoint(db)

        if collection_site_data.action == "connect":
            sharepoint_site = sharepoint.connect_site_to_data_collection(
                collection_uuid, collection_site_data.site_url
            )
        else:  # action == "disconnect"
            sharepoint_site = sharepoint.disconnect_sites_from_data_collection(
                collection_uuid, collection_site_data.site_url
            )

        if not sharepoint_site:
            raise HTTPException(
                status_code=404,
                detail=f"Failed to {collection_site_data.action} SharePoint Site. Please check and retry.",
            )

        return {
            "message": f"SharePoint Site {collection_site_data.site_url} {collection_site_data.action}ed successfully."
        }

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in connect_disconnect_sharepoint_site: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@data_collection_router.get(
    "/assistant/private-data-collection", response_model=DataFileResponse
)
def get_private_data_collection(
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
    request: Request = None,
):
    """
    Retrieves private data file information for a specific user based on specified criteria.
    """
    try:
        # Extract user_id from the token
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_uuid = decoded_token["sub"]

        data_collection_repository = DataCollectionRepository(db)
        data_file_repository = DataFileRepository(db)

        filters = request.state.filters

        private_data_collection = (
            data_collection_repository.get_private_data_collection_by_owner_id(
                user_uuid
            )
        )

        private_data_files = []
        total = 0
        if private_data_collection:
            private_data_files, total = data_file_repository.get_all_data_files(
                collection_id=private_data_collection.id,
                page=page,
                page_size=page_size,
                filters=filters,
                sort_by=sort_by,
                sort_order=sort_order,
            )

        return DataFileResponse(data_files=private_data_files, total=total)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in get_data_collections: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_collection_router.get(
    "/assistant/private-data-collection/search", response_model=DataFileResponse
)
def search_private_data_collection(
    keyword: str = Query(..., description="Search keyword"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
    request: Request = None,
):
    """
    Searches and retrieves private data file information for a specific user based on specified criteria.
    """
    try:
        # Extract user_id from the token
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_uuid = decoded_token["sub"]

        data_collection_repository = DataCollectionRepository(db)
        data_file_repository = DataFileRepository(db)

        filters = request.state.filters

        if keyword:
            private_data_collection = (
                data_collection_repository.get_private_data_collection_by_owner_id(
                    user_uuid
                )
            )

            private_data_files = []
            total = 0
            if private_data_collection:
                private_data_files, total = data_file_repository.search_data_files(
                    keyword=keyword,
                    collection_id=private_data_collection.id,
                    page=page,
                    page_size=page_size,
                    filters=filters,
                    sort_by=sort_by,
                    sort_order=sort_order,
                )

            return DataFileResponse(data_files=private_data_files, total=total)

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
        logger.error(f"Error in get_data_collections: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
