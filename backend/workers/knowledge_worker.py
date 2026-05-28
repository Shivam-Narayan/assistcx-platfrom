from celery import shared_task
import os
from typing import Dict, Any
from datetime import datetime
from logger import configure_logging
import time

from db_pool import DatabasePoolManager
from repository.data_file_repository import DataFileRepository

# Initialize the DatabasePoolManager
db_pool = DatabasePoolManager()
logger = configure_logging(__name__)


@shared_task(
    name="index_document",
    queue="knowledge_queue",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def index_document(self, organization_schema: str, document_record: dict):
    """
    Document indexing task: parse, embed, and store in vector database.

    Pipeline: Download → Parse → Embed → Index → Trigger extraction (if enabled)
    """
    data_file_uuid = document_record.get("data_file_uuid")
    start_time = time.time()

    logger.info(
        f"Received new worker task: index-document, data_file_uuid={data_file_uuid}"
    )
    try:
        if (
            document_record.get("data_file_uuid")
            and os.environ.get("SERVICE_TYPE") == "knowledge-worker"
        ):
            from knowledge.indexer import DocumentIndexer

            with db_pool.get_session(organization_schema) as db:
                document_indexer = DocumentIndexer(
                    db=db, organization_schema=organization_schema
                )
                result = document_indexer.process_document(document_record)

                # After successful indexing, trigger AI processing if enabled
                if (
                    result
                    and not result.get("error")
                    and document_record.get("knowledge_extraction")
                ):
                    logger.info(
                        f"Triggering advanced knowledge extraction for document {document_record.get('data_file_uuid')}"
                    )

                    # Prepare document_record with required fields for extraction
                    # Transform collection_id to data_collection_uuid as expected by KnowledgeExtractor
                    extraction_document_record = {
                        "data_file_uuid": document_record.get("data_file_uuid"),
                        "data_file_name": document_record.get("data_file_name"),
                        "collection_index": document_record.get("collection_index"),
                        "collection_name": document_record.get("collection_name"),
                        "data_collection_uuid": str(
                            document_record.get("collection_id")
                        ),
                    }

                    # Queue extraction with HIGHEST priority (0) - lower number = higher priority
                    # This ensures extraction tasks jump ahead of queued index_document tasks (priority 9)
                    extract_knowledge.apply_async(
                        kwargs={
                            "organization_schema": organization_schema,
                            "extraction_data": {
                                "document_record": extraction_document_record
                                # extraction_job is None for new documents (extract all fields/topics)
                            },
                        },
                        priority=0,  # High priority (0=high, 9=low)
                    )

        elapsed_time = time.time() - start_time

        logger.info(
            f"Document indexing successful: data_file_uuid={data_file_uuid}, total_time={elapsed_time:.2f}s"
        )

        return {
            "status": "SUCCESS",
            "summary": f"Document indexed, extraction: {bool(document_record.get('knowledge_extraction'))}",
            "data": {
                "data_file_uuid": document_record.get("data_file_uuid"),
                "collection_id": document_record.get("collection_id"),
                "extraction_triggered": bool(
                    document_record.get("knowledge_extraction")
                ),
            },
        }
    except Exception as e:
        elapsed_time = time.time() - start_time

        logger.error(
            f"Document indexing failed: data_file_uuid={data_file_uuid}, total_time={elapsed_time:.2f}s, error={str(e)}"
        )

        # Retry if attempts remaining
        if self.request.retries < self.max_retries:
            logger.warning(
                f"Document indexing failed, retrying: data_file_uuid={data_file_uuid}, "
                f"retry={self.request.retries + 1}/{self.max_retries + 1}, error={str(e)}"
            )
            raise self.retry(exc=e)

        # Final failure - retries exhausted
        logger.error(
            f"Document indexing failed after all retries: data_file_uuid={data_file_uuid}, "
            f"retries={self.request.retries}/{self.max_retries}"
        )
        return {
            "status": "FAILED",
            "summary": f"Document indexing failed",
            "data": {
                "data_file_uuid": document_record.get("data_file_uuid"),
                "collection_id": document_record.get("collection_id"),
            },
            "error": str(e),
        }


@shared_task(
    name="extract_knowledge",
    queue="knowledge_queue",  # Same queue as index_document — priority=0 ensures extraction runs first
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def extract_knowledge(self, organization_schema: str, extraction_data: Dict[str, Any]):
    """
    Universal AI extraction task using unified processor.

    Handles:
    - New documents: Extract all fields and topics (extraction_job=None)
    - New fields/topics: Extract specific field/topic (extraction_job provided)

    Args:
        organization_schema: Organization schema for tenant isolation
        extraction_data: Contains document_record and optional extraction_job
        extraction_data={
            "document_record": {
                "data_file_uuid": doc_id,
                "collection_name": str(collection_uuid)
            },
            "extraction_job": {
                "job_type": "smart_field",
                "field_config": {
                    "name": "field_name",
                    "description": "field_description",
                    "keywords": ["field_keywords"],
                }
            }
        }
    """
    document_id = None
    document_record = None
    start_time = time.time()
    try:
        document_record = extraction_data["document_record"]
        extraction_job = extraction_data.get("extraction_job")  # None for new documents
        document_id = document_record.get("data_file_uuid")

        logger.info(
            f"Received new worker task: knowledge-worker-extract, data_file_uuid={document_id}"
        )
        # Validate document_id before proceeding
        if not document_id:
            raise ValueError("Missing required data_file_uuid in document_record")

        # Import and initialize knowledge extractor
        from knowledge.extractor import KnowledgeExtractor

        with db_pool.get_session(organization_schema) as db:
            data_file_repo = DataFileRepository(db=db)

            # Set EXTRACTING status at the beginning
            status = {
                "status": "EXTRACTING",
                "timestamp": str(datetime.now()),
            }
            data_file_repo.append_data_file_status(
                data_file_id=document_id, status=status
            )

            knowledge_extractor = KnowledgeExtractor(db=db, organization_schema=organization_schema)
            result = knowledge_extractor.process_extraction(
                document_record, extraction_job
            )

            # Update final status
            final_status = {
                "status": "SUCCESSFUL",
                "timestamp": str(datetime.now()),
            }
            data_file_repo.append_data_file_status(
                data_file_id=document_id, status=final_status
            )

        elapsed_time = time.time() - start_time

        logger.info(
            f"Knowledge extraction successful: data_file_uuid={document_id}, total_time={elapsed_time:.2f}s"
        )

        return {
            "status": "SUCCESS",
            "summary": f"AI extraction: {result.get('status', 'completed')}",
            "data": {
                "data_file_uuid": document_id,
                "data_collection_uuid": document_record.get("data_collection_uuid"),
                "extraction_status": result.get("status", "completed"),
                "job_type": (
                    extraction_job.get("job_type") if extraction_job else "full"
                ),
            },
        }
    except Exception as e:
        elapsed_time = time.time() - start_time

        logger.error(
            f"Knowledge extraction failed: data_file_uuid={document_id}, total_time={elapsed_time:.2f}s, error={str(e)}"
        )

        # Retry if attempts remaining
        if self.request.retries < self.max_retries:
            logger.warning(
                f"Knowledge extraction failed, retrying: data_file_uuid={document_id}, "
                f"retry={self.request.retries + 1}/{self.max_retries + 1}, error={str(e)}"
            )
            raise self.retry(exc=e)

        # Final failure - retries exhausted
        logger.error(
            f"Knowledge extraction failed after all retries: data_file_uuid={document_id}, "
            f"retries={self.request.retries}/{self.max_retries}"
        )
        # Intentionally set SUCCESSFUL even on failure — extraction is non-critical
        # and should not block the document pipeline or user experience
        if document_id:
            try:
                with db_pool.get_session(organization_schema) as db:
                    data_file_repo = DataFileRepository(db=db)
                    status = {
                        "status": "SUCCESSFUL",
                        "timestamp": str(datetime.now()),
                    }
                    data_file_repo.append_data_file_status(
                        data_file_id=document_id, status=status
                    )
            except Exception as status_error:
                logger.error(f"Failed to update status on error: {status_error}")

        return {
            "status": "FAILED",
            "summary": f"AI extraction failed",
            "data": {
                "data_file_uuid": document_id,
                "data_collection_uuid": (
                    document_record.get("data_collection_uuid")
                    if document_record
                    else None
                ),
            },
            "error": str(e),
        }
