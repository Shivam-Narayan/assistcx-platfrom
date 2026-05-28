# Custom libraries
from utils.collection_utils import create_private_data_collection
from logger import configure_logging
from integrations.minio_storage.client import MinIOStorage
from schemas.data_file_schema import (
    DataFileBulkAction,
    DataFileDetail,
    DataFileDownload,
    DataFileRename,
    DataFileResponse,
    DataFileUpload,
    KnowledgeItem,
    KnowledgeResponse,
    ChunksAndContentResponse,
)
from schemas.user_schema import Message
from utils.document_file import DocumentFile
from utils.schema_utils import get_current_schema, get_schema_db
from knowledge.milvus_store import MilvusStore

# Database modules
from repository.data_collection_repository import DataCollectionRepository
from repository.data_file_repository import DataFileRepository
from sqlalchemy.orm import Session

# Default libraries
from datetime import datetime
from typing import List
from uuid import UUID
import base64
import json
import mimetypes
import os
import re

# Installed libraries
from celery_worker import celery
from fastapi import (
    APIRouter,
    Body,
    HTTPException,
    UploadFile,
    Depends,
    File,
    Form,
)
from fastapi.security import OAuth2PasswordBearer
from jwt import decode


logger = configure_logging(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")

data_file_router = APIRouter(tags=["Data Files"])


@data_file_router.get("/data-files/{data_file_uuid}", response_model=DataFileResponse)
@data_file_router.get(
    "/assistant/data-files/{data_file_uuid}", response_model=DataFileResponse
)
def get_data_file(
    data_file_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves data file information based on data_file_uuid.
    """
    try:
        data_file_repository = DataFileRepository(db)

        # Check if data file exists using data_file_uuid
        data_file = data_file_repository.get_data_file_by_id(data_file_uuid)

        if not data_file:
            raise HTTPException(
                status_code=404,
                detail="Data File not found. Please check and retry.",
            )

        # Convert to response model
        data_file_dict = DataFileDetail.model_validate(data_file).model_dump()

        return DataFileResponse(data_files=[data_file_dict], total=1)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in get_data_file: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_file_router.get(
    "/data-files/{data_file_uuid}/knowledge", response_model=KnowledgeResponse
)
@data_file_router.get(
    "/assistant/data-files/{data_file_uuid}/knowledge", response_model=KnowledgeResponse
)
def get_data_file_knowledge(
    data_file_uuid: UUID,
    db: Session = Depends(get_schema_db),
    milvus_store: MilvusStore = Depends(lambda: MilvusStore()),
):
    """
    Retrieves document knowledge from Milvus for a specific data file.
    """
    try:
        data_file_repository = DataFileRepository(db)

        # Check if data file exists
        data_file = data_file_repository.get_data_file_by_id(data_file_uuid)
        if not data_file:
            raise HTTPException(
                status_code=404,
                detail="Data File not found. Please check and retry.",
            )

        # Get the collection for this data file
        collection_repository = DataCollectionRepository(db)
        data_collection = collection_repository.get_data_collection_by_id(
            data_file.collection_id
        )
        if not data_collection:
            raise HTTPException(
                status_code=404,
                detail="Data Collection not found for this file.",
            )

        # Query Milvus for document knowledge
        documents = milvus_store.fetch_documents_with_filter(
            collection_name=data_collection.index_name,
            file_uuid=str(data_file_uuid),
            record_type="document_knowledge",
        )

        # Convert to KnowledgeItem format
        knowledge_items = []
        for doc in documents:
            knowledge_topic = None
            if doc.metadata and isinstance(doc.metadata, dict):
                knowledge_topic = doc.metadata.get("knowledge_topic")

            knowledge_items.append(
                KnowledgeItem(
                    id=doc.metadata.get("id", ""),
                    document_id=doc.metadata.get("file_uuid", str(data_file_uuid)),
                    record_type=doc.metadata.get("record_type", "document_knowledge"),
                    knowledge_topic=knowledge_topic,
                    content=doc.page_content,
                    created_at=doc.metadata.get("created_at"),
                    metadata=doc.metadata,
                )
            )

        logger.info(
            f"Retrieved {len(knowledge_items)} knowledge items for file {data_file_uuid}"
        )
        return KnowledgeResponse(knowledge=knowledge_items, total=len(knowledge_items))

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_data_file_knowledge: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_file_router.get(
    "/data-files/{data_file_uuid}/chunks", response_model=ChunksAndContentResponse
)
@data_file_router.get(
    "/assistant/data-files/{data_file_uuid}/chunks",
    response_model=ChunksAndContentResponse,
)
def get_data_file_chunks_and_content(
    data_file_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves document chunks and extracted content from storage for a specific data file.
    """
    try:
        data_file_repository = DataFileRepository(db)

        # Check if data file exists
        data_file = data_file_repository.get_data_file_by_id(data_file_uuid)
        if not data_file:
            raise HTTPException(
                status_code=404,
                detail="Data File not found. Please check and retry.",
            )

        # Get the collection for this data file
        collection_repository = DataCollectionRepository(db)
        data_collection = collection_repository.get_data_collection_by_id(
            data_file.collection_id
        )
        if not data_collection:
            raise HTTPException(
                status_code=404,
                detail="Data Collection not found for this file.",
            )

        # Get file paths from metadata
        chunks_file_path = None
        content_file_path = None
        if data_file.file_metadata:
            chunks_file_path = data_file.file_metadata.get("chunks_file_path")
            content_file_path = data_file.file_metadata.get(
                "extracted_content_file_path"
            )

        # Get data_store from collection config
        data_store = data_collection.collection_config.get("data_store")
        if not data_store:
            raise HTTPException(
                status_code=500,
                detail="Data store configuration not found for this collection.",
            )

        # Initialize DocumentFile for downloading
        org_schema = get_current_schema(db)
        document_file = DocumentFile(org_schema, db)

        # Initialize response variables
        chunks = []
        extracted_content = ""

        # Fetch chunks if path exists
        if chunks_file_path:
            try:
                chunks_content = document_file.download_processed_file(
                    data_store, chunks_file_path
                )
                if chunks_content:
                    chunks = json.loads(chunks_content)
            except Exception as e:
                logger.warning(f"Failed to load chunks: {e}")

        # Fetch extracted content if path exists
        if content_file_path:
            try:
                extracted_content = (
                    document_file.download_processed_file(data_store, content_file_path)
                    or ""
                )
            except Exception as e:
                logger.warning(f"Failed to load extracted content: {e}")

        logger.info(
            f"Retrieved {len(chunks)} chunks and content (length: {len(extracted_content)}) for file {data_file_uuid}"
        )
        return ChunksAndContentResponse(
            chunks=chunks,
            extracted_content=extracted_content,
        )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_data_file_chunks_and_content: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_file_router.get(
    "/data-files/{data_file_uuid}/download", response_model=DataFileDownload
)
@data_file_router.get(
    "/assistant/data-files/{data_file_uuid}/download", response_model=DataFileDownload
)
def download_data_file(
    data_file_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Downloads a data file by retrieving it from SharePoint, local storage or S3 bucket.
    """
    try:
        data_file_repository = DataFileRepository(db)

        existing_data_file = data_file_repository.get_data_file_by_id(data_file_uuid)
        if not existing_data_file:
            raise HTTPException(
                status_code=404,
                detail="Data File not found. Please check and retry.",
            )

        organization_schema = get_current_schema(db)

        document_file = DocumentFile(organization_schema=organization_schema)
        file_content = document_file.download_file_from_minio(
            file_path=existing_data_file.source_metadata.get("file_path")
        )

        if file_content:
            mime_type, _ = mimetypes.guess_type(existing_data_file.name)
            return {
                "mime_type": mime_type or "application/octet-stream",
                "file_name": existing_data_file.name,
                "content": base64.b64encode(file_content).decode(),
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to download Data File. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in download_data_file: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_file_router.post("/data-files", response_model=DataFileUpload)
@data_file_router.post("/assistant/data-files", response_model=DataFileUpload)
def upload_data_files(
    data_files: List[UploadFile] = File(...),
    collection_id: UUID = Form(),
    db: Session = Depends(get_schema_db),
):
    """
    Uploads and creates multiple new data files.
    """
    try:
        organization_schema = get_current_schema(db)

        document_file = DocumentFile(organization_schema=organization_schema, db=db)
        uploaded_data_files = document_file.upload_data_files(
            data_files=data_files, source="local", data_collection_id=collection_id
        )

        if uploaded_data_files:
            logger.info(
                f"Data Files uploaded successfully: {len(uploaded_data_files['upload_successes'])} of {len(data_files)}"
            )
            return DataFileUpload(
                successful_uploads=DataFileResponse(
                    data_files=uploaded_data_files["upload_successes"],
                    total=len(uploaded_data_files["upload_successes"]),
                ),
                unsuccessful_uploads=uploaded_data_files["upload_failures"],
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to upload Data Files.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in upload_data_files: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_file_router.patch(
    "/data-files/{data_file_uuid}/rename", response_model=DataFileDetail
)
@data_file_router.patch(
    "/assistant/data-files/{data_file_uuid}/rename", response_model=DataFileDetail
)
def rename_data_file(
    data_file_uuid: UUID,
    update_data: DataFileRename = Body(...),
    db: Session = Depends(get_schema_db),
    milvus_store: MilvusStore = Depends(lambda: MilvusStore()),
):
    """
    Renames a data file by updating its name.
    """
    try:
        data_file_repository = DataFileRepository(db)

        # Check if data file exists using data_file_uuid
        existing_data_file = data_file_repository.get_data_file_by_id(data_file_uuid)

        if existing_data_file:
            # Extract the previous file extension if it exists
            previous_extension = (
                existing_data_file.name.split(".")[-1]
                if "." in existing_data_file.name
                else ""
            )

            new_file_name = (
                f"{update_data.name}.{previous_extension}"
                if "." not in update_data.name and previous_extension
                else update_data.name
            )

            # Update the data file name
            update_data = {"data_file_uuid": data_file_uuid, "name": new_file_name}

            renamed_data_file = data_file_repository.update_data_file(update_data)
            collection_repository = DataCollectionRepository(db)
            data_collection = collection_repository.get_data_collection_by_id(
                renamed_data_file.collection_id
            )

            # Update metadata in Milvus
            milvus_store.update_file_name(
                collection_name=data_collection.index_name,
                file_uuid=str(data_file_uuid),
                new_file_name=new_file_name,
            )
            if renamed_data_file:
                logger.info(f"Data File renamed successfully: {renamed_data_file.id}")
                return DataFileDetail.model_validate(renamed_data_file)
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to rename Data File. Please check and retry.",
                )
        else:
            raise HTTPException(
                status_code=404,
                detail="Data File not found. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in rename_data_file: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_file_router.post("/data-files/reindex", response_model=Message)
@data_file_router.post("/assistant/data-files/reindex", response_model=Message)
def reindex_data_files(
    reindex_data: DataFileBulkAction = Body(...),
    db: Session = Depends(get_schema_db),
    milvus_store: MilvusStore = Depends(lambda: MilvusStore()),
):
    """
    Reindexes multiple data files by removing old Milvus documents, clearing metadata,
    and queueing for knowledge extraction based on their data_file_ids.
    """
    try:
        if not reindex_data.data_file_ids:
            raise HTTPException(status_code=400, detail="No data files provided.")

        data_file_repository = DataFileRepository(db)
        data_collection_repository = DataCollectionRepository(db)
        organization_schema = get_current_schema(db)
        reindexed_count = 0

        metadata_fields_to_remove = [
            "doc_title",
            "doc_type",
            "doc_overview",
            "doc_keywords",
            "doc_entities",
            "doc_filename",
            "doc_page_count",
            "doc_word_count",
            "chunks_file_path",
            "extracted_content_file_path",
        ]

        for data_file_id in reindex_data.data_file_ids:
            data_file = data_file_repository.get_data_file_by_id(data_file_id)
            if not data_file:
                logger.warning(f"Data File {data_file_id} not found, skipping.")
                continue

            data_collection = data_collection_repository.get_data_collection_by_id(
                data_file.collection_id
            )
            if not data_collection:
                logger.warning(
                    f"Data Collection not found for file {data_file_id}, skipping."
                )
                continue

            try:
                result = milvus_store.delete_documents_with_filter(
                    collection_name=data_collection.index_name,
                    file_uuid=str(data_file_id),
                )
                logger.info(f"Milvus delete result for file {data_file_id}: {result}")
            except Exception as milvus_err:
                logger.error(
                    f"Milvus delete failed for file {data_file_id}: {milvus_err}"
                )

            if data_file.file_metadata:
                data_store = data_collection.collection_config.get("data_store")
                if data_store:
                    chunks_path = data_file.file_metadata.get("chunks_file_path")
                    content_path = data_file.file_metadata.get(
                        "extracted_content_file_path"
                    )

                    if chunks_path:
                        try:
                            MinIOStorage(data_store).delete_file(chunks_path)
                            logger.info(f"Deleted old chunks file: {chunks_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete old chunks file: {e}")

                    if content_path:
                        try:
                            MinIOStorage(data_store).delete_file(content_path)
                            logger.info(f"Deleted old content file: {content_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete old content file: {e}")

            data_file_repository.update_file_metadata(
                data_file_id=data_file_id,
                fields_to_remove=metadata_fields_to_remove,
            )

            data_file = data_file_repository.update_data_file(
                {
                    "data_file_uuid": data_file_id,
                    "status": [
                        {
                            "status": "QUEUED",
                            "timestamp": str(datetime.now()),
                        }
                    ],
                }
            )

            document_record = {
                "data_file_uuid": data_file.id,
                "data_file_name": data_file.name,
                "data_file_size": data_file.size,
                "source_metadata": data_file.source_metadata,
                "data_file_path": data_file.source_metadata.get("file_path"),
                "data_file_source": data_file.source_type,
                "collection_name": data_collection.name,
                "collection_index": data_collection.index_name,
                "collection_id": data_file.collection_id,
                "knowledge_extraction": data_collection.collection_config.get(
                    "advanced_knowledge_extraction", False
                ),
            }

            celery.send_task(
                "index_document",
                args=[organization_schema, document_record],
                queue="knowledge_queue",
            )

            reindexed_count += 1
            logger.info(f"Data File reindexing queued: {data_file_id}")

        if reindexed_count > 0:
            logger.info(
                f"{reindexed_count} of {len(reindex_data.data_file_ids)} Data Files reindexing started"
            )
            return {
                "message": f"{reindexed_count} Data File(s) reindexing started successfully."
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="No valid Data Files found to reindex.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in reindex_data_files: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_file_router.delete("/data-files", response_model=Message)
@data_file_router.delete("/assistant/data-files", response_model=Message)
def delete_data_files(
    delete_data: DataFileBulkAction = Body(...),
    db: Session = Depends(get_schema_db),
    milvus_store: MilvusStore = Depends(lambda: MilvusStore()),
):
    """
    Deletes multiple existing data files based on their data_file_ids.
    """
    try:
        if not delete_data.data_file_ids:
            raise HTTPException(status_code=400, detail="No data files provided.")

        data_file_repository = DataFileRepository(db)
        collection_repository = DataCollectionRepository(db)
        deleted_count = 0

        for data_file_id in delete_data.data_file_ids:
            data_file = data_file_repository.get_data_file_by_id(data_file_id)
            if data_file:
                # Check if the data file is associated with a collection
                data_collection = collection_repository.get_data_collection_by_id(
                    data_file.collection_id
                )
                if data_collection:
                    try:
                        # Delete documents by file_uuid
                        res = milvus_store.delete_documents_by_file_uuid(
                            data_collection.index_name, str(data_file_id)
                        )
                        logger.info(
                            f"Milvus delete result for file_uuid {data_file_id}: {res}"
                        )
                    except Exception as milvus_error:
                        logger.error(
                            f"Failed to delete Milvus documents for file_uuid {data_file_id}: {milvus_error}"
                        )
                        continue

                deleted_data_file = data_file_repository.delete_data_file(data_file_id)
                if deleted_data_file:
                    deleted_count += 1

        if deleted_count > 0:
            logger.info(
                f"{deleted_count} of {len(delete_data.data_file_ids)} Data Files deleted successfully"
            )
            return {"message": "Data File deleted successfully."}
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete Data Files. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_data_files: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@data_file_router.post("/assistant/private-data-files", response_model=DataFileUpload)
def upload_private_data_files(
    data_files: List[UploadFile] = File(...),
    milvus_store: MilvusStore = Depends(lambda: MilvusStore()),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """
    Uploads and creates multiple new private data files.
    """
    try:
        # Extract user_id from the token
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_uuid = decoded_token["sub"]

        data_collection_repository = DataCollectionRepository(db)
        private_data_collection = (
            data_collection_repository.get_private_data_collection_by_owner_id(
                user_uuid
            )
            or create_private_data_collection(db, milvus_store, user_uuid)
        )

        organization_schema = get_current_schema(db)
        data_file = DocumentFile(organization_schema, db)
        uploaded_data_files = data_file.upload_data_files(
            data_files=data_files,
            source="local",
            data_collection_id=private_data_collection.id,
        )

        if uploaded_data_files:
            logger.info(
                f"Data Files uploaded successfully: {len(uploaded_data_files['upload_successes'])} of {len(data_files)}"
            )
            return DataFileUpload(
                successful_uploads=DataFileResponse(
                    data_files=uploaded_data_files["upload_successes"],
                    total=len(uploaded_data_files["upload_successes"]),
                ),
                unsuccessful_uploads=uploaded_data_files["upload_failures"],
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to upload Data Files.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in upload_private_data_files: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
