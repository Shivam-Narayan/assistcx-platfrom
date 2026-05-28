# Custom libraries
from logger import configure_logging
from schemas.user_schema import Message
from schemas.smart_field_schema import SmartField
from utils.schema_utils import get_schema_db, get_current_schema
from utils.common_utils import get_new_items

# Database modules
from repository.smart_field_repository import SmartFieldRepository
from repository.data_collection_repository import DataCollectionRepository
from repository.data_file_repository import DataFileRepository

# Default libraries
from typing import List
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

logger = configure_logging(__name__)

smart_field_router = APIRouter(tags=["Smart Fields"])


def _identify_field_changes(
    existing_fields: List[dict], new_fields: List[dict]
) -> dict:
    """
    Identify which smart fields were added, modified, or deleted by comparing
    existing and new field definitions.

    Args:
        existing_fields (List[dict]): Current smart fields from database
        new_fields (List[dict]): New smart fields from user request

    Returns:
        dict: Dictionary with keys 'added', 'modified', 'deleted' containing
              lists of field dictionaries for each category
    """
    existing_names = {f["name"]: f for f in existing_fields}
    new_names = {f["name"]: f for f in new_fields}

    # New fields (not in existing)
    added = [f for f in new_fields if f["name"] not in existing_names]

    # Deleted fields (in existing but not in new)
    deleted = [f for f in existing_fields if f["name"] not in new_names]

    # Modified fields (description, keywords, or data_type changed)
    modified = []
    for new_field in new_fields:
        name = new_field["name"]
        if name in existing_names:
            old_field = existing_names[name]
            if (
                old_field.get("description") != new_field.get("description")
                or old_field.get("keywords") != new_field.get("keywords")
                or old_field.get("data_type") != new_field.get("data_type")
            ):
                modified.append(new_field)

    logger.info(
        f"Field changes identified: {len(added)} added, "
        f"{len(modified)} modified, {len(deleted)} deleted"
    )
    return {"added": added, "modified": modified, "deleted": deleted}


@smart_field_router.post(
    "/collections/{collection_uuid}/smart-fields", response_model=List[SmartField]
)
def create_smart_fields(
    collection_uuid: UUID,
    smart_fields_data: List[SmartField] = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Create smart fields for a data collection.
    """
    try:
        smart_field_repository = SmartFieldRepository(db)

        # Convert Pydantic models to dict
        smart_fields_dict = [field.model_dump() for field in smart_fields_data]

        smart_fields = smart_field_repository.create_smart_fields(
            collection_id=collection_uuid, smart_fields_data=smart_fields_dict
        )

        if smart_fields is not None:
            logger.info(
                f"Smart fields created successfully for collection: {collection_uuid}"
            )

            # TODO: Trigger AI extraction for new smart fields
            # Create extraction jobs for each new field and each document in collection
            from celery_worker import celery

            organization_schema = get_current_schema(db=db)

            # Get collection data to enrich document metadata
            data_collection_repo = DataCollectionRepository(db)
            collection_data = data_collection_repo.get_data_collection_by_id(
                collection_uuid
            )

            if not collection_data:
                raise HTTPException(
                    status_code=404, detail="Collection not found for AI extraction"
                )

            data_file_repo = DataFileRepository(db)
            collection_documents = data_file_repo.get_collection_documents(
                collection_uuid
            )
            document_ids = (
                [
                    str(document["id"])
                    for document in collection_documents
                    if isinstance(document.get("status"), list)
                    and len(document["status"]) > 0
                    and document["status"][-1].get("status") == "SUCCESSFUL"
                ]
                if collection_documents
                else []
            )

            for field in smart_fields:
                for doc_id in document_ids:
                    celery.send_task(
                        "extract_knowledge",
                        args=[
                            organization_schema,
                            {
                                "document_record": {
                                    "data_file_uuid": doc_id,
                                    "collection_index": collection_data.index_name,
                                    "data_collection_uuid": str(collection_data.id),
                                },
                                "extraction_job": {
                                    "job_type": "smart_field",
                                    "field_config": field,
                                },
                            },
                        ],
                        queue="knowledge_queue",
                        priority=0,  # High priority (0=high, 9=low)
                    )

            return [SmartField(**field) for field in smart_fields]
        else:
            raise HTTPException(
                status_code=500, detail="Failed to create smart fields."
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_smart_fields: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@smart_field_router.get(
    "/collections/{collection_uuid}/smart-fields", response_model=List[SmartField]
)
def get_smart_fields(
    collection_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Get all smart fields for a data collection.
    """
    try:
        smart_field_repository = SmartFieldRepository(db)
        smart_fields = smart_field_repository.get_smart_fields(
            collection_id=collection_uuid
        )

        return [SmartField(**field) for field in smart_fields]

    except Exception as e:
        logger.error(f"Error in get_smart_fields: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@smart_field_router.put(
    "/collections/{collection_uuid}/smart-fields", response_model=List[SmartField]
)
def update_smart_fields(
    collection_uuid: UUID,
    smart_fields_data: List[SmartField] = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Update smart fields for a data collection.
    Handles added, modified, and deleted fields intelligently.
    """
    try:
        smart_field_repository = SmartFieldRepository(db)
        data_file_repo = DataFileRepository(db)

        # Get existing fields before updating
        existing_fields = smart_field_repository.get_smart_fields(
            collection_id=collection_uuid
        )

        # Convert Pydantic models to dict
        smart_fields_dict = [field.model_dump() for field in smart_fields_data]

        # Identify what changed using helper function
        changes = _identify_field_changes(existing_fields, smart_fields_dict)

        # Handle deleted fields BEFORE updating database
        if changes["deleted"]:
            data_collection_repo = DataCollectionRepository(db)
            collection = data_collection_repo.get_data_collection_by_id(
                collection_uuid
            )

            if collection:
                from knowledge.milvus_store import MilvusStore

                # Get organization schema
                organization_schema = get_current_schema(db=db)

                # Get embedding model from collection config
                embedding_model = collection.collection_config.get("embedding_model")

                logger.info(f"Using embedding model: {embedding_model}")

                milvus_store = MilvusStore()

                # Get all document IDs in collection
                collection_documents = data_file_repo.get_collection_documents(
                    collection_uuid
                )
                document_ids = (
                    [str(document["id"]) for document in collection_documents]
                    if collection_documents
                    else []
                )

                # Track cleanup success for rollback
                cleanup_errors = []

                # STEP 1: Clean up Milvus FIRST (most likely to fail)
                for field in changes["deleted"]:
                    field_name = field["name"]
                    try:
                        # Remove from Milvus document_context records
                        for doc_id in document_ids:
                            if not milvus_store.remove_field_from_document_context(
                                collection_name=collection.index_name,
                                file_uuid=str(doc_id),
                                field_name=field_name,
                                dense_model=embedding_model,
                                organization_schema=organization_schema,
                            ):
                                cleanup_errors.append(
                                    f"Failed to remove field '{field_name}' from Milvus for document {doc_id}"
                                )
                    except Exception as e:
                        cleanup_errors.append(
                            f"Error cleaning up field '{field_name}' from Milvus: {str(e)}"
                        )
                        logger.error(
                            f"Milvus cleanup error for field '{field_name}': {e}"
                        )

                # If Milvus cleanup failed, abort BEFORE touching database
                if cleanup_errors:
                    error_message = "; ".join(cleanup_errors[:3])  # Show first 3 errors
                    if len(cleanup_errors) > 3:
                        error_message += f" (and {len(cleanup_errors) - 3} more errors)"

                    logger.error(
                        f"Milvus cleanup failed, aborting update: {error_message}"
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to cleanup deleted fields from Milvus: {error_message}",
                    )

                # STEP 2: Only if Milvus cleanup succeeded, update database metadata
                for field in changes["deleted"]:
                    field_name = field["name"]
                    try:
                        # Remove from database metadata for all documents
                        for doc_id in document_ids:
                            data_file_repo.update_file_metadata(
                                data_file_id=doc_id, fields_to_remove=[field_name]
                            )
                    except Exception as e:
                        # This is less likely to fail, but log it
                        logger.error(
                            f"Database metadata cleanup failed for field '{field_name}': {e}. "
                            f"Milvus cleanup already completed."
                        )
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to cleanup field '{field_name}' from database metadata: {str(e)}",
                        )

        # Update smart fields in database
        smart_fields = smart_field_repository.update_smart_fields(
            collection_id=collection_uuid, smart_fields_data=smart_fields_dict
        )

        if smart_fields is None:
            raise HTTPException(
                status_code=404,
                detail="Failed to update smart fields. Collection not found.",
            )
        # Trigger re-extraction for added AND modified fields
        fields_to_process = changes["added"] + changes["modified"]

        if fields_to_process:
            from celery_worker import celery

            organization_schema = get_current_schema(db=db)

            data_collection_repo = DataCollectionRepository(db)
            collection = data_collection_repo.get_data_collection_by_id(
                collection_uuid
            )

            if not collection:
                raise HTTPException(
                    status_code=404, detail="Collection not found for AI extraction"
                )

            collection_documents = data_file_repo.get_collection_documents(
                collection_uuid
            )
            document_ids = (
                [
                    str(document["id"])
                    for document in collection_documents
                    if isinstance(document.get("status"), list)
                    and len(document["status"]) > 0
                    and document["status"][-1].get("status") == "SUCCESSFUL"
                ]
                if collection_documents
                else []
            )

            # Queue extraction jobs for each field + document
            for field in fields_to_process:
                for doc_id in document_ids:
                    celery.send_task(
                        "extract_knowledge",
                        args=[
                            organization_schema,
                            {
                                "document_record": {
                                    "data_file_uuid": doc_id,
                                    "collection_index": collection.index_name,
                                    "data_collection_uuid": str(collection.id),
                                },
                                "extraction_job": {
                                    "job_type": "smart_field",
                                    "field_config": field,
                                },
                            },
                        ],
                        queue="knowledge_queue",
                        priority=0,  # High priority (0=high, 9=low)
                    )

        return [SmartField(**field) for field in smart_fields]

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_smart_fields: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@smart_field_router.delete(
    "/collections/{collection_uuid}/smart-fields", response_model=Message
)
def delete_smart_fields(
    collection_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Delete all smart fields for a data collection.
    """
    try:
        smart_field_repository = SmartFieldRepository(db)

        success = smart_field_repository.delete_smart_fields(
            collection_id=collection_uuid
        )

        if success:
            logger.info(
                f"Smart fields deleted successfully for collection: {collection_uuid}"
            )
            return {"message": "Smart fields deleted successfully."}
        else:
            raise HTTPException(
                status_code=404,
                detail="Collection not found or no smart fields to delete.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_smart_fields: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
