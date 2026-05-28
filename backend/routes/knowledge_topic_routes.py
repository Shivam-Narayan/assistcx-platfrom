# Custom libraries
from logger import configure_logging
from schemas.user_schema import Message
from schemas.knowledge_topic_schema import KnowledgeTopic
from utils.schema_utils import get_schema_db, get_current_schema
from utils.common_utils import get_new_items

# Database modules
from repository.knowledge_topics_repository import KnowledgeTopicsRepository
from repository.data_collection_repository import DataCollectionRepository
from repository.data_file_repository import DataFileRepository

# Default libraries
from typing import List
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

logger = configure_logging(__name__)

knowledge_topics_router = APIRouter(tags=["Knowledge Topics"])


def _identify_topic_changes(
    existing_topics: List[dict], new_topics: List[dict]
) -> dict:
    """
    Identify which knowledge topics were added, modified, or deleted by comparing
    existing and new topic definitions.

    Args:
        existing_topics (List[dict]): Current knowledge topics from database
        new_topics (List[dict]): New knowledge topics from user request

    Returns:
        dict: Dictionary with keys 'added', 'modified', 'deleted' containing
              lists of topic dictionaries for each category
    """
    existing_names = {t["name"]: t for t in existing_topics}
    new_names = {t["name"]: t for t in new_topics}

    # New topics (not in existing)
    added = [t for t in new_topics if t["name"] not in existing_names]

    # Deleted topics (in existing but not in new)
    deleted = [t for t in existing_topics if t["name"] not in new_names]

    # Modified topics (description or keywords changed)
    modified = []
    for new_topic in new_topics:
        name = new_topic["name"]
        if name in existing_names:
            old_topic = existing_names[name]
            if old_topic.get("description") != new_topic.get(
                "description"
            ) or old_topic.get("keywords") != new_topic.get("keywords"):
                modified.append(new_topic)

    logger.info(
        f"Topic changes identified: {len(added)} added, "
        f"{len(modified)} modified, {len(deleted)} deleted"
    )
    return {"added": added, "modified": modified, "deleted": deleted}


@knowledge_topics_router.post(
    "/collections/{collection_uuid}/knowledge-topics",
    response_model=List[KnowledgeTopic],
)
def create_knowledge_topics(
    collection_uuid: UUID,
    knowledge_topics_data: List[KnowledgeTopic] = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Create knowledge topics for a data collection.
    """
    try:
        knowledge_topics_repository = KnowledgeTopicsRepository(db)

        # Convert Pydantic models to dict
        knowledge_topics_dict = [topic.model_dump() for topic in knowledge_topics_data]

        knowledge_topics = knowledge_topics_repository.create_knowledge_topics(
            collection_id=collection_uuid, knowledge_topics_data=knowledge_topics_dict
        )

        if knowledge_topics is not None:
            logger.info(
                f"Knowledge topics created successfully for collection: {collection_uuid}"
            )

            # TODO: Trigger AI extraction for new knowledge topics
            # Create extraction jobs for each new topic and each document in collection
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

            for topic in knowledge_topics:
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
                                    "job_type": "knowledge_topic",
                                    "field_config": topic,
                                },
                            },
                        ],
                        queue="knowledge_queue",
                        priority=0,  # High priority (0=high, 9=low)
                    )

            return [KnowledgeTopic(**topic) for topic in knowledge_topics]
        else:
            raise HTTPException(
                status_code=500, detail="Failed to create knowledge topics."
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_knowledge_topics: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@knowledge_topics_router.get(
    "/collections/{collection_uuid}/knowledge-topics",
    response_model=List[KnowledgeTopic],
)
def get_knowledge_topics(
    collection_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Get all knowledge topics for a data collection.
    """
    try:
        knowledge_topics_repository = KnowledgeTopicsRepository(db)
        knowledge_topics = knowledge_topics_repository.get_knowledge_topics(
            collection_id=collection_uuid
        )

        return [KnowledgeTopic(**topic) for topic in knowledge_topics]

    except Exception as e:
        logger.error(f"Error in get_knowledge_topics: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@knowledge_topics_router.put(
    "/collections/{collection_uuid}/knowledge-topics",
    response_model=List[KnowledgeTopic],
)
def update_knowledge_topics(
    collection_uuid: UUID,
    knowledge_topics_data: List[KnowledgeTopic] = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Update knowledge topics for a data collection.
    Handles added, modified, and deleted topics intelligently.
    """
    try:
        knowledge_topics_repository = KnowledgeTopicsRepository(db)
        data_file_repo = DataFileRepository(db)

        # Get existing topics before updating
        existing_topics = knowledge_topics_repository.get_knowledge_topics(
            collection_id=collection_uuid
        )

        # Convert Pydantic models to dict
        knowledge_topics_dict = [topic.model_dump() for topic in knowledge_topics_data]

        # Identify what changed using helper function
        changes = _identify_topic_changes(existing_topics, knowledge_topics_dict)

        # Handle deleted topics BEFORE updating database
        if changes["deleted"]:
            logger.info(f"Cleaning up {len(changes['deleted'])} deleted topics")

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

                # Clean up Milvus document_knowledge records
                # Note: Topics are ONLY stored in Milvus, not in database metadata
                for topic in changes["deleted"]:
                    topic_name = topic["name"]
                    try:
                        # Remove from Milvus document_knowledge records
                        for doc_id in document_ids:
                            if not milvus_store.remove_topic_from_document_knowledge(
                                collection_name=collection.index_name,
                                file_uuid=str(doc_id),
                                topic_name=topic_name,
                            ):
                                cleanup_errors.append(
                                    f"Failed to remove topic '{topic_name}' from Milvus for document {doc_id}"
                                )
                    except Exception as e:
                        cleanup_errors.append(
                            f"Error cleaning up topic '{topic_name}' from Milvus: {str(e)}"
                        )
                        logger.error(
                            f"Milvus cleanup error for topic '{topic_name}': {e}"
                        )

                # If Milvus cleanup failed, abort BEFORE updating database
                if cleanup_errors:
                    error_message = "; ".join(cleanup_errors[:3])  # Show first 3 errors
                    if len(cleanup_errors) > 3:
                        error_message += f" (and {len(cleanup_errors) - 3} more errors)"

                    logger.error(
                        f"Milvus cleanup failed, aborting update: {error_message}"
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to cleanup deleted topics from Milvus: {error_message}",
                    )

        # Update knowledge topics in database
        knowledge_topics = knowledge_topics_repository.update_knowledge_topics(
            collection_id=collection_uuid, knowledge_topics_data=knowledge_topics_dict
        )

        if knowledge_topics is None:
            raise HTTPException(
                status_code=404,
                detail="Failed to update knowledge topics. Collection not found.",
            )

        # Trigger re-extraction for added AND modified topics
        topics_to_process = changes["added"] + changes["modified"]

        if topics_to_process:
            logger.info(
                f"Triggering extraction for {len(topics_to_process)} topics "
                f"({len(changes['added'])} added, {len(changes['modified'])} modified)"
            )

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

            # Clean up modified topics BEFORE re-extraction to prevent duplicates
            if changes["modified"]:
                from knowledge.milvus_store import MilvusStore

                # Get organization schema
                organization_schema = get_current_schema(db=db)

                # Get embedding model from collection config
                embedding_model = collection.collection_config.get("embedding_model")

                logger.info(f"Using embedding model: {embedding_model}")

                milvus_store = MilvusStore()

                # Track cleanup success for rollback
                cleanup_errors = []

                # Remove old extraction data for modified topics
                for topic in changes["modified"]:
                    topic_name = topic["name"]
                    try:
                        # Remove from Milvus document_knowledge records
                        for doc_id in document_ids:
                            if not milvus_store.remove_topic_from_document_knowledge(
                                collection_name=collection.index_name,
                                file_uuid=str(doc_id),
                                topic_name=topic_name,
                            ):
                                cleanup_errors.append(
                                    f"Failed to remove modified topic '{topic_name}' from Milvus for document {doc_id}"
                                )
                    except Exception as e:
                        cleanup_errors.append(
                            f"Error cleaning up modified topic '{topic_name}' from Milvus: {str(e)}"
                        )
                        logger.error(
                            f"Milvus cleanup error for modified topic '{topic_name}': {e}"
                        )

                # If Milvus cleanup failed, abort BEFORE triggering re-extraction
                if cleanup_errors:
                    error_message = "; ".join(cleanup_errors[:3])  # Show first 3 errors
                    if len(cleanup_errors) > 3:
                        error_message += f" (and {len(cleanup_errors) - 3} more errors)"

                    logger.error(
                        f"Modified topic cleanup failed, aborting re-extraction: {error_message}"
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to cleanup modified topics from Milvus: {error_message}",
                    )

            # Queue extraction jobs for each topic + document
            for topic in topics_to_process:
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
                                    "job_type": "knowledge_topic",
                                    "field_config": topic,
                                },
                            },
                        ],
                        queue="knowledge_queue",
                        priority=0,  # High priority (0=high, 9=low)
                    )

        return [KnowledgeTopic(**topic) for topic in knowledge_topics]

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_knowledge_topics: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@knowledge_topics_router.delete(
    "/collections/{collection_uuid}/knowledge-topics", response_model=Message
)
def delete_knowledge_topics(
    collection_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Delete all knowledge topics for a data collection.
    """
    try:
        knowledge_topics_repository = KnowledgeTopicsRepository(db)

        success = knowledge_topics_repository.delete_knowledge_topics(
            collection_id=collection_uuid
        )

        if success:
            logger.info(
                f"Knowledge topics deleted successfully for collection: {collection_uuid}"
            )
            return {"message": "Knowledge topics deleted successfully."}
        else:
            raise HTTPException(
                status_code=404,
                detail="Collection not found or no knowledge topics to delete.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_knowledge_topics: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
