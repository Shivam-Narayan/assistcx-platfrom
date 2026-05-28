# Standard library imports
import asyncio
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from sqlalchemy.orm import Session

# Project imports
from logger import configure_logging
from repository.data_file_repository import DataFileRepository
from repository.data_collection_repository import DataCollectionRepository
from utils.document_file import DocumentFile

# Local imports
from .llm_extractor import LLMExtractor
from .milvus_store import MilvusStore
from .section_generator import SectionGenerator

logger = configure_logging(__name__)


class KnowledgeExtractor:
    """
    Main orchestrator for smart field and knowledge topic extraction.

    This class handles:
    - Processing new documents for smart field and topic extraction (after initial indexing)
    - Coordinating extraction of smart fields and knowledge topics
    - Managing the overall extraction workflow
    - Integration with queue system for scalable processing
    """

    # Maximum number of parallel extractions
    MAX_PARALLEL_FIELDS = 10
    MAX_PARALLEL_TOPICS = 10

    def __init__(self, db: Session, organization_schema: str):
        self.db = db
        self.organization_schema = organization_schema
        self.data_file_repo = DataFileRepository(db=db)
        self.data_collection_repo = DataCollectionRepository(db=db)
        self.llm_extractor = LLMExtractor(
            db=db, organization_schema=organization_schema
        )
        self._milvus_store = None
        self._section_generator = None

    @property
    def milvus_store(self) -> MilvusStore:
        """Lazy-loaded MilvusStore client (single instance for all collections)."""
        if self._milvus_store is None:
            self._milvus_store = MilvusStore()
        return self._milvus_store

    @property
    def section_generator(self) -> SectionGenerator:
        """Lazy-loaded SectionGenerator (single instance per extractor)."""
        if self._section_generator is None:
            self._section_generator = SectionGenerator(
                db=self.db, organization_schema=self.organization_schema
            )
        return self._section_generator

    def process_extraction(
        self,
        document_record: Dict[str, Any],
        extraction_job: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Unified extraction processor for documents.

        Two scenarios:
        1. New document (extraction_job=None): Extract all fields and topics
        2. New field/topic (extraction_job provided): Extract only specified item

        Args:
            document_record: Document metadata with data_file_uuid, collection_name
            extraction_job: Optional job with job_type and field/topic config

        Returns:
            Dict with extraction results and status
        """
        try:
            # Validate input parameters
            document_id = document_record.get("data_file_uuid")
            collection_name = document_record.get("collection_index")
            data_collection_id = document_record.get("data_collection_uuid")

            if not document_id or not collection_name or not data_collection_id:
                return {
                    "error": "Missing required document metadata",
                    "status": "failed",
                }

            logger.info(f"Processing AI extraction for document {document_id}")

            # Get knowledge configuration (handles both extraction_job and full extraction)
            knowledge_config = self.get_knowledge_config(
                data_collection_id, extraction_job
            )

            if not knowledge_config:
                return {"error": "No knowledge configuration found", "status": "failed"}

            # Look up embedding model once for the entire extraction
            embedding_model = self.data_collection_repo.get_embedding_model(
                collection_name
            )

            results = {"status": "success", "extracted_count": 0, "errors": []}

            # Process smart fields and knowledge topics with async concurrency
            smart_fields = knowledge_config.get("smart_fields", [])
            topic_configs = knowledge_config.get("knowledge_topics", [])

            if smart_fields or topic_configs:
                field_results, topic_results = asyncio.run(
                    self._process_extractions_async(
                        collection_name=collection_name,
                        document_id=document_id,
                        document_record=document_record,
                        smart_fields=smart_fields,
                        topic_configs=topic_configs,
                        embedding_model=embedding_model,
                    )
                )

                # Collect successful field extractions, then batch index once
                field_extractions = []
                for fr in field_results:
                    if fr["success"]:
                        field_extractions.append(
                            (fr["field_name"], fr["field_value"])
                        )
                    else:
                        results["errors"].append(fr.get("error", ""))

                if field_extractions:
                    indexed = self._batch_index_smart_fields(
                        collection_name=collection_name,
                        document_record=document_record,
                        field_extractions=field_extractions,
                        embedding_model=embedding_model,
                    )
                    if indexed:
                        results["extracted_count"] += len(field_extractions)
                    else:
                        results["errors"].append("Failed to index smart fields")

                for topic_result in topic_results:
                    if topic_result["success"]:
                        results["extracted_count"] += 1
                    else:
                        results["errors"].append(
                            topic_result.get("error", "Unknown topic extraction error")
                        )

            # Generate sections (full extraction only, non-fatal)
            if knowledge_config.get("generate_document_sections") and not extraction_job:
                section_result = self._generate_and_upload_sections(document_record)
                if not section_result.get("success"):
                    results["errors"].append(
                        f"Section generation: {section_result.get('error', 'unknown error')}"
                    )

            # Set final status
            if results["extracted_count"] > 0:
                results["status"] = (
                    "success" if not results["errors"] else "partial_success"
                )
            else:
                results["status"] = (
                    "failed" if results["errors"] else "no_extraction_needed"
                )

            logger.info(
                f"AI extraction completed for document {document_id}: {results['status']}"
            )
            return results

        except Exception as e:
            error_msg = f"Unexpected error in AI extraction: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg, "status": "failed"}

    def _generate_and_upload_sections(
        self,
        document_record: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Fetch all chunks for a document from Milvus, generate section titles and
        descriptions via LLM in batches, and upload the result as a _sections.json
        artifact to MinIO.

        Returns:
            Dict with 'success' bool and optional 'error' message.
        """
        document_id = document_record.get("data_file_uuid")
        collection_name = document_record.get("collection_index")
        data_collection_id = document_record.get("data_collection_uuid")
        original_filename = document_record.get("data_file_name", "")

        try:
            # 1. Fetch all document_chunk records from Milvus
            chunks = self.milvus_store.fetch_documents_with_filter(
                collection_name=collection_name,
                file_uuid=document_id,
                record_type="document_chunk",
            )

            if not chunks:
                logger.warning(
                    f"No chunks found for document {document_id}, "
                    "skipping section generation"
                )
                return {"success": False, "error": "No chunks found"}

            logger.info(
                f"Generating sections for {len(chunks)} chunks "
                f"in document {document_id}"
            )

            # 2. Run section generation
            sections = self.section_generator.generate_sections(
                chunks=chunks,
                source_file=original_filename,
            )

            # 3. Serialize output to JSON
            sections_json = json.dumps(sections, indent=2, ensure_ascii=False)

            # 4. Resolve data_store from collection config
            collection_data = self.data_collection_repo.get_data_collection_by_id(
                UUID(data_collection_id)
            )
            if not collection_data:
                return {"success": False, "error": "Collection not found"}

            data_store = collection_data.collection_config.get("data_store")
            if not data_store:
                logger.warning(
                    f"No data_store configured for collection {data_collection_id}, "
                    "skipping section artifact upload"
                )
                return {"success": False, "error": "No data_store configured"}

            # 5. Upload artifact to MinIO
            document_file = DocumentFile(self.organization_schema, self.db)
            sections_file_path = document_file.upload_processed_file(
                data_store=data_store,
                content=sections_json,
                collection_name=document_record.get("collection_name", ""),
                original_filename=original_filename,
                file_suffix="_sections.json",
            )

            if not sections_file_path:
                return {"success": False, "error": "Artifact upload failed"}

            # 6. Persist artifact path in DB file metadata
            self.data_file_repo.update_file_metadata(
                data_file_id=document_id,
                metadata_updates={"sections_file_path": sections_file_path},
            )

            logger.info(
                f"Section generation complete for document {document_id}: "
                f"{sections_file_path}"
            )
            return {"success": True}

        except Exception as e:
            error_msg = (
                f"Error in section generation for document {document_id}: {str(e)}"
            )
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    def _batch_index_smart_fields(
        self,
        collection_name: str,
        document_record: Dict[str, Any],
        field_extractions: List[Tuple[str, Any]],
        embedding_model: str,
    ) -> bool:
        """
        Index all extracted smart fields into the document_context record in a single operation.

        Reads existing context once, applies all field values, then writes back once.
        This avoids N separate re-embed cycles for N fields.

        Args:
            collection_name: Milvus collection name
            document_record: Document metadata
            field_extractions: List of (field_name, field_value) tuples
            embedding_model: Dense embedding model name

        Returns:
            True if indexing succeeded
        """
        try:
            file_uuid = document_record.get("data_file_uuid")
            if not file_uuid:
                logger.error("Missing data_file_uuid in document_record")
                return False

            # Read existing document_context once
            metadata = self._build_base_metadata(document_record)
            existing_content, existing_metadata = self._get_milvus_context(
                collection_name, file_uuid, "document_context"
            )
            metadata.update(existing_metadata)

            # Fallback to DB if no Milvus content exists
            if not existing_content:
                doc_context = self._get_document_context(file_uuid) or {}
                existing_content = "\n".join(
                    [
                        f"Title: {doc_context.get('doc_title', '')}",
                        f"Overview: {doc_context.get('doc_overview', '')}",
                        f"Type: {doc_context.get('doc_type', '')}",
                        f"Keywords: {', '.join(doc_context.get('doc_keywords', []))}",
                        f"Entities: {', '.join(doc_context.get('doc_entities', []))}",
                        f"Filename: {doc_context.get('doc_filename', '')}",
                    ]
                ).strip()
                metadata.update(doc_context)

            # Apply all field values to content + metadata in one pass
            content_text = existing_content
            for field_name, field_value in field_extractions:
                # Convert list values to comma-separated strings for Milvus storage
                # (app DB still stores original lists via update_document_metadata below)
                milvus_value = (
                    ", ".join(str(item) for item in field_value)
                    if isinstance(field_value, list)
                    else field_value
                )
                metadata[field_name] = milvus_value

                # Update field in content text (replace, append, or remove)
                field_pattern = f"^{re.escape(field_name)}: .*$"
                if field_value is not None:
                    new_field_line = f"{field_name}: {milvus_value}"
                    if re.search(field_pattern, content_text, re.MULTILINE):
                        content_text = re.sub(
                            field_pattern,
                            new_field_line,
                            content_text,
                            flags=re.MULTILINE,
                        )
                    else:
                        content_text = f"{content_text}\n{new_field_line}".strip()
                else:
                    content_text = re.sub(
                        field_pattern + r"\n?",
                        "",
                        content_text,
                        flags=re.MULTILINE,
                    ).strip()

            # Single embed + insert for all fields
            indexed = self._insert_to_milvus(
                collection_name=collection_name,
                file_uuid=file_uuid,
                content_text=content_text,
                metadata=metadata,
                record_type="document_context",
                embedding_model=embedding_model,
            )

            if indexed:
                # Update DB metadata for all fields
                for field_name, field_value in field_extractions:
                    self.update_document_metadata(file_uuid, field_name, field_value)
                logger.info(
                    f"Batch indexed {len(field_extractions)} smart fields for document {file_uuid}"
                )

            return indexed

        except Exception as e:
            logger.error(f"Error batch indexing smart fields: {e}")
            return False

    def process_topic_extraction(
        self,
        collection_name: str,
        document_record: Dict[str, Any],
        topic_config: Dict[str, Any],
        embedding_model: str,
    ) -> Dict[str, Any]:
        """
        Process extraction of a single knowledge topic.

        Args:
            collection_name: Milvus collection name
            document_record: Document metadata
            topic_config: Topic configuration
            embedding_model: Dense embedding model name

        Returns:
            Dict with success status and error info
        """
        try:
            document_id = document_record.get("data_file_uuid")
            topic_name = topic_config.get("name", "unknown_topic")

            # Extract knowledge topic using vector search + AI
            topic_result = self.llm_extractor.extract_knowledge_topic(
                collection_name=collection_name,
                document_id=document_id,
                topic_config=topic_config,
                embedding_model=embedding_model,
            )

            if topic_result is not None:
                # Index the extracted topic knowledge in Milvus
                indexed = self._index_knowledge_topic(
                    collection_name=collection_name,
                    document_record=document_record,
                    extracted_data={
                        "topic_name": topic_name,
                        "knowledge": topic_result,
                    },
                    embedding_model=embedding_model,
                )

                if indexed:
                    logger.info(
                        f"Successfully extracted and indexed topic: {topic_name}"
                    )
                    return {"success": True}
                else:
                    return {
                        "success": False,
                        "error": f"Failed to index topic: {topic_name}",
                    }
            else:
                logger.warning(f"No knowledge extracted for topic: {topic_name}")
                return {
                    "success": False,
                    "error": f"No knowledge found for topic: {topic_name}",
                }

        except Exception as e:
            error_msg = f"Error extracting topic {topic_config.get('name')}: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    def get_knowledge_config(
        self, data_collection_id: str, extraction_job: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get smart fields and knowledge topics configuration.

        Args:
            data_collection_id: UUID of the data collection
            extraction_job: Optional specific extraction job (for single field/topic)

        Returns:
            Dict with smart_fields and knowledge_topics arrays
        """
        try:
            # If extraction_job provided, create config from it
            if extraction_job:
                job_type = extraction_job.get("job_type")
                field_config = extraction_job.get("field_config")

                if not job_type or not field_config:
                    logger.error(
                        "Invalid extraction_job format - missing job_type or field_config"
                    )
                    return None

                logger.info(f"Creating config for specific {job_type} extraction")

                if job_type == "smart_field":
                    return {"smart_fields": [field_config], "knowledge_topics": []}
                elif job_type == "knowledge_topic":
                    return {"smart_fields": [], "knowledge_topics": [field_config]}
                else:
                    logger.error(
                        f"Unknown job_type: {job_type}. Expected 'smart_field' or 'knowledge_topic'"
                    )
                    return None

            # Otherwise get full config from database
            collection_data = self.data_collection_repo.get_data_collection_by_id(
                UUID(data_collection_id)
            )
            if not collection_data:
                logger.error(f"Collection not found: {data_collection_id}")
                return None

            smart_fields = collection_data.smart_fields
            knowledge_topics = collection_data.knowledge_topics

            # Check if section generation is enabled in collection config
            generate_document_sections = False
            if collection_data.collection_config:
                generate_document_sections = collection_data.collection_config.get(
                    "generate_document_sections", False
                )

            logger.info(
                f"Found {len(smart_fields)} smart fields and {len(knowledge_topics)} knowledge topics"
            )
            return {
                "smart_fields": smart_fields,
                "knowledge_topics": knowledge_topics,
                "generate_document_sections": generate_document_sections,
            }

        except Exception as e:
            logger.error(f"Error getting knowledge configuration: {e}")
            return None

    def update_document_metadata(
        self, data_file_uuid: UUID, field_name: str, field_value: Any
    ) -> bool:
        """
        Update document metadata with extracted smart field data.

        Args:
            data_file_uuid: UUID of the document to update
            field_name: Name of the smart field
            field_value: Extracted field value

        Returns:
            bool: True if successful
        """
        try:
            metadata_updates = {field_name: field_value}
            updated_file = self.data_file_repo.update_file_metadata(
                data_file_id=data_file_uuid,
                metadata_updates=metadata_updates,
            )

            if updated_file:
                logger.info(
                    f"Successfully saved smart field '{field_name}' metadata for file {data_file_uuid}"
                )
                return True
            else:
                logger.error(
                    f"Failed to update smart field '{field_name}' metadata for file {data_file_uuid}"
                )
                return False

        except Exception as e:
            logger.error(
                f"Error updating document metadata for file {data_file_uuid}: {e}"
            )
            return False

    def _build_base_metadata(self, document_record: Dict[str, Any]) -> Dict[str, Any]:
        """Build base metadata dict from document record."""
        return {
            "file_name": document_record.get("data_file_name", ""),
            "file_uuid": str(document_record.get("data_file_uuid", "")),
            "collection_name": document_record.get("collection_name", ""),
        }

    def _insert_to_milvus(
        self,
        collection_name: str,
        file_uuid: str,
        content_text: str,
        metadata: Dict[str, Any],
        record_type: str,
        embedding_model: str,
        document_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Insert a single record into Milvus with the specified embedding model."""
        try:
            inserted_ids = self.milvus_store.insert_documents(
                file_uuid=file_uuid,
                collection_name=collection_name,
                texts=[content_text],
                metadata=[metadata],
                dense_model=embedding_model,
                organization_schema=self.organization_schema,
                record_type=record_type,
                document_context=document_context,
            )
            if inserted_ids:
                logger.info(
                    f"Successfully indexed {record_type} for document {file_uuid}"
                )
                return True
            logger.error(f"Failed to index {record_type} for document {file_uuid}")
            return False
        except Exception as e:
            logger.error(f"Error indexing {record_type} for {file_uuid}: {e}")
            return False

    def _index_knowledge_topic(
        self,
        collection_name: str,
        document_record: Dict[str, Any],
        extracted_data: Dict[str, Any],
        embedding_model: str,
        document_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Index a knowledge topic as a document_knowledge record in Milvus."""
        try:
            file_uuid = document_record.get("data_file_uuid")
            if not file_uuid:
                logger.error("Missing data_file_uuid in document_record")
                return False

            topic_name = extracted_data.get("topic_name", "Unknown Topic")
            knowledge_data = extracted_data.get("knowledge", "")

            # Build metadata with document context from DB
            metadata = self._build_base_metadata(document_record)
            doc_context = self._get_document_context(file_uuid) or {}
            metadata.update(doc_context)
            metadata["knowledge_topic"] = topic_name

            # Backfill empty base fields from document context
            if not metadata.get("file_name"):
                metadata["file_name"] = doc_context.get("doc_filename", "")
            if not metadata.get("collection_name"):
                metadata["collection_name"] = document_record.get("collection_index", "")

            # Convert list values to comma-separated strings (same format as document_context record)
            for key, value in metadata.items():
                if isinstance(value, list):
                    metadata[key] = ", ".join(str(item) for item in value)

            content_text = f"**Knowledge Topic - {topic_name.replace('_', ' ').title()}**  \n{knowledge_data}"

            return self._insert_to_milvus(
                collection_name=collection_name,
                file_uuid=file_uuid,
                content_text=content_text,
                metadata=metadata,
                record_type="document_knowledge",
                embedding_model=embedding_model,
                document_context=document_context,
            )

        except Exception as e:
            logger.error(f"Error indexing knowledge_topic: {e}")
            return False

    def _get_document_context(self, file_uuid: UUID) -> Optional[Dict[str, Any]]:
        """
        Get existing document context from database metadata.

        Returns:
            Optional[Dict]: Document context fields (doc_ prefixed) or None
        """
        try:
            file_data = self.data_file_repo.get_data_file_by_id(file_uuid)
            if not file_data or not file_data.file_metadata:
                return None

            document_context = {
                key: value
                for key, value in file_data.file_metadata.items()
                if key.startswith("doc_")
            }
            return document_context if document_context else None

        except Exception as e:
            logger.warning(f"Could not retrieve document context for {file_uuid}: {e}")
            return None

    def _get_milvus_context(
        self, collection_name: str, file_uuid: str, record_type: str
    ) -> tuple[str, dict]:
        """Get existing content and metadata from Milvus record to preserve extracted data."""
        try:
            records = self.milvus_store.fetch_documents_with_filter(
                collection_name=collection_name,
                file_uuid=file_uuid,
                record_type=record_type,
                result_limit=1,
            )
            if records:
                record = records[0]
                # Clean system fields from metadata
                metadata = {
                    k: v
                    for k, v in record.metadata.items()
                    if k
                    not in {
                        "id",
                        "document_id",
                        "record_type",
                        "created_at",
                        "distance",
                    }
                }
                return record.page_content, metadata
        except Exception as e:
            logger.warning(
                f"Could not retrieve existing {record_type} for {file_uuid}: {e}"
            )
        return "", {}

    async def _process_extractions_async(
        self,
        collection_name: str,
        document_id: str,
        document_record: Dict[str, Any],
        smart_fields: List[Dict[str, Any]],
        topic_configs: List[Dict[str, Any]],
        embedding_model: str,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Process smart fields and knowledge topics concurrently.

        Smart fields are extracted in parallel (up to MAX_PARALLEL_FIELDS),
        then batch-indexed in a single write by the caller.
        Knowledge topics are extracted and indexed in parallel (up to MAX_PARALLEL_TOPICS).

        Returns:
            Tuple of (field_results, topic_results)
        """
        loop = asyncio.get_running_loop()
        field_semaphore = asyncio.Semaphore(self.MAX_PARALLEL_FIELDS)
        topic_semaphore = asyncio.Semaphore(self.MAX_PARALLEL_TOPICS)

        async def extract_single_field(field_config: Dict[str, Any]) -> Dict[str, Any]:
            field_name = field_config.get("name", "unknown_field")
            async with field_semaphore:
                try:
                    field_value = await loop.run_in_executor(
                        None,
                        self.llm_extractor.extract_smart_field,
                        collection_name,
                        document_id,
                        field_config,
                        embedding_model,
                    )
                    return {
                        "success": True,
                        "field_name": field_name,
                        "field_value": field_value,
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "field_name": field_name,
                        "error": f"Error extracting field {field_name}: {e}",
                    }

        async def extract_single_topic(topic_config: Dict[str, Any]) -> Dict[str, Any]:
            async with topic_semaphore:
                return await loop.run_in_executor(
                    None,
                    self.process_topic_extraction,
                    collection_name,
                    document_record,
                    topic_config,
                    embedding_model,
                )

        # Run all field and topic extractions concurrently
        field_tasks = [extract_single_field(fc) for fc in smart_fields]
        topic_tasks = [extract_single_topic(tc) for tc in topic_configs]

        all_results = await asyncio.gather(*field_tasks, *topic_tasks)

        # Split results back into fields and topics (gather preserves order)
        field_results = list(all_results[: len(field_tasks)])
        topic_results = list(all_results[len(field_tasks) :])

        return field_results, topic_results


# Example test code
if __name__ == "__main__":
    import uuid
    from pathlib import Path
    from db_pool import DatabasePoolManager

    db_pool = DatabasePoolManager()
    db_session = db_pool.get_session(schema_name="public")

    # Configure test data
    collection_name = "test_collection"
    test_file_uuid = str(uuid.uuid4())

    print(f"Testing AI knowledge extraction for document: {test_file_uuid}")

    # Create test document record
    document_record = {
        "data_file_uuid": test_file_uuid,
        "data_file_name": "Employee_Benefits_Policy_2024.pdf",
        "collection_index": collection_name,
        "collection_name": collection_name,
        "data_collection_uuid": str(uuid.uuid4()),
    }

    # Test with specific extraction job
    extraction_job = {
        "job_type": "smart_field",
        "field_config": {
            "name": "employee_count",
            "description": "Number of employees covered by the benefits policy",
            "keywords": ["employees", "staff", "workforce", "headcount"],
        },
    }

    with db_session:
        extractor = KnowledgeExtractor(db=db_session, organization_schema="public")

        # Test full extraction (no extraction_job)
        print("\n=== Testing Full Knowledge Extraction ===")
        results = extractor.process_extraction(
            document_record=document_record
        )

        # Test specific field extraction
        print("\n=== Testing Specific Field Extraction ===")
        field_results = extractor.process_extraction(
            document_record=document_record, extraction_job=extraction_job
        )

    # Report results
    print(f"\nFull extraction results: {results}")
    print(f"Field extraction results: {field_results}")

    if results.get("status") == "success":
        print(f"Extracted {results.get('extracted_count', 0)} items")
    else:
        print(f"Extraction failed: {results.get('error', 'Unknown error')}")
