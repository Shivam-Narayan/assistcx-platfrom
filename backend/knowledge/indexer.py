# Standard library imports
import os
import json
import tempfile
import time
import gc
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import UUID

# Third-party imports
from dotenv import load_dotenv
from jinja2 import Template
from sqlalchemy.orm import Session

# Project imports
from logger import configure_logging
from docling_core.transforms.chunker import DocChunk
from repository.data_file_repository import DataFileRepository
from repository.data_collection_repository import DataCollectionRepository
from agents.shared_utils import LLMProvider
from utils.document_file import DocumentFile

# Local imports
from .document_parser import DocumentParser
from .milvus_store import MilvusStore
from .utils import DocumentContext, format_document_context
from .prompts import DOCUMENT_CONTEXT_PROMPT


load_dotenv()
logger = configure_logging(__name__)


def _lowercase_metadata(metadata: Dict[str, Any]) -> None:
    """Lowercase all text values in metadata dict in-place for case-insensitive filtering.

    Preserves special characters (dots, hyphens, underscores) unlike normalize_text
    which strips them. This is appropriate for document context fields like file_name
    and title where special chars are meaningful.
    Skips non-text values (numbers, dates, None, booleans) automatically.
    """
    for key, value in metadata.items():
        if isinstance(value, str):
            metadata[key] = value.lower()
        elif isinstance(value, list):
            metadata[key] = [v.lower() if isinstance(v, str) else v for v in value]


class DocumentIndexer:
    """
    Main entry point for document indexing.
    Handles input validation, file downloads, and orchestrates the
    document parsing and vector database operations.
    """

    def __init__(self, db: Session, organization_schema: str):
        self.db = db
        self.organization_schema = organization_schema
        self.document_parser = DocumentParser()
        self.milvus_store = (
            None  # Initialized per-document with collection's embedding model
        )
        self.data_file_repo = DataFileRepository(self.db)
        self.data_collection_repo = DataCollectionRepository(self.db)
        self.llm_provider = LLMProvider(self.organization_schema, self.db)
        self.default_llm = self.llm_provider.get_llm()

    def validate_input(self, document_record: Dict[str, Any]) -> None:
        """
        Validate that required keys are present in message_data.

        Args:
            document_record (Dict[str, Any]): Metadata for the file to process.

        Raises:
            ValueError: If required keys are missing.
        """
        required_keys = [
            "data_file_path",
            "data_file_name",
            "data_file_uuid",
            "collection_name",
        ]
        missing_keys = [key for key in required_keys if key not in document_record]
        if missing_keys:
            raise ValueError(f"Missing required data: {', '.join(missing_keys)}")

    def _update_status(self, file_uuid, status_str: str) -> None:
        """Update the processing status of a data file."""
        self.data_file_repo.append_data_file_status(
            data_file_id=file_uuid,
            status={"status": status_str, "timestamp": str(datetime.now())},
        )

    def _download_file(
        self,
        file_name: str,
        file_source: str,
        source_metadata: dict,
        temp_dir: str,
    ) -> Optional[str]:
        try:
            document_file = DocumentFile(
                organization_schema=self.organization_schema, db=self.db
            )
            file_path = source_metadata.get("file_path")
            file_content = document_file.download_file_from_minio(file_path)
            if file_content:
                temp_file_path = os.path.join(temp_dir, file_name)
                with open(temp_file_path, "wb") as f:
                    f.write(file_content)
                logger.info(f"Downloaded file to: {temp_file_path}")
                return temp_file_path
            return None

        except Exception as e:
            logger.error(f"Unexpected error downloading file {file_name}: {e}")
            return None

    def create_document_context(
        self,
        file_name: str,
        doc_chunks: List[DocChunk],
        max_chunks: int = 5,
        max_words: int = 800,
    ) -> str:
        """
        Create the document context using LLM.
        Uses up to max_chunks document chunks with a maximum of max_words total.

        Args:
            file_name (str): Name of the file being summarized.
            doc_chunks (List[DocChunk]): List of document chunks to consider.
            max_chunks (int): Maximum number of chunks to use (default: 3).
            max_words (int): Maximum total word count for content (default: 500).

        Returns:
            DocumentContext or None: Structured document context.
        """
        try:
            # Extract and combine chunk texts up to limits
            content_parts = []
            word_count = 0

            for chunk in doc_chunks[:max_chunks]:
                chunk_text = (
                    chunk.text.strip() if hasattr(chunk, "text") else str(chunk).strip()
                )
                chunk_words = chunk_text.split()

                # Add full chunk if within limit, or truncate if needed
                if word_count + len(chunk_words) <= max_words:
                    content_parts.append(chunk_text)
                    word_count += len(chunk_words)
                elif word_count < max_words:  # Partial chunk fits
                    remaining_words = max_words - word_count
                    content_parts.append(" ".join(chunk_words[:remaining_words]))
                    word_count = max_words
                    break
                else:  # No more words can fit
                    break

            combined_content = "\n\n".join(content_parts) + "\n\n..."

            logger.debug(
                f"Using {len(content_parts)} chunks with {word_count} words for document context"
            )

            context_prompt = Template(DOCUMENT_CONTEXT_PROMPT).render(
                filename=file_name, content=combined_content
            )

            # Create the LLM with structured output
            struct_llm = self.default_llm.with_structured_output(DocumentContext)

            # Invoke the LLM with structured output
            response = struct_llm.invoke(context_prompt)
            document_context = response.model_dump() if response else None
            logger.debug(f"Document context: {document_context}")
            return document_context
        except Exception as e:
            logger.error(f"Error creating document context for {file_name}: {e}")
            return None

    def update_document_metadata(
        self,
        data_file_uuid: UUID,
        document_context: Optional[Dict[str, Any]],
    ) -> bool:
        """
        Helper function to update file metadata with document context.

        Args:
            data_file_uuid (UUID): UUID of the data file to update
            document_context (Optional[Dict[str, Any]]): Document context to save

        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            if not document_context:
                logger.info(f"No document context to save for file {data_file_uuid}")
                return True

            # Prepare document context for metadata storage with prefix
            document_context_metadata = {
                f"doc_{key}": value for key, value in document_context.items()
            }

            # Update file metadata with document context
            updated_file = self.data_file_repo.update_file_metadata(
                data_file_id=data_file_uuid,
                metadata_updates=document_context_metadata,
            )

            if updated_file:
                logger.info(
                    f"Successfully saved document context to database for file {data_file_uuid}"
                )
                return True
            else:
                logger.warning(
                    f"Failed to save document context to database for file {data_file_uuid}"
                )
                return False

        except Exception as e:
            logger.error(
                f"Error updating document metadata for file {data_file_uuid}: {e}"
            )
            return False

    def index_chunks(
        self,
        file_uuid: str,
        collection_name: str,
        document_chunks: List[DocChunk],
        metadata_list: List[Dict[str, Any]],
        embedding_model: str,
        document_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Store document chunks in Milvus vector database.

        Args:
            file_uuid (str): Unique identifier for the document.
            collection_name (str): Name of the collection.
            document_chunks (List[DocChunk]): List of document chunks.
            metadata_list (List[Dict]): List of metadata dictionaries for each chunk.
            embedding_model (str): Model name for dense embeddings.
            document_context (Optional[Dict[str, Any]]): Document context for enhanced embedding.

        Returns:
            bool: True if storage is successful, False otherwise.
        """
        try:
            if not document_chunks:
                logger.warning(
                    f"No chunks to store for file {file_uuid} in collection {collection_name}"
                )
                return False

            # Extract text from chunks
            chunk_texts = [chunk.text.strip() for chunk in document_chunks]

            # Insert document context first if provided
            if document_context:
                context_text = format_document_context(document_context)

                # Convert list values to comma-separated strings for Milvus metadata
                milvus_metadata = document_context.copy()
                for key, value in milvus_metadata.items():
                    if isinstance(value, list):
                        milvus_metadata[key] = ", ".join(str(item) for item in value)

                # Insert document context
                context_result = self.milvus_store.insert_documents(
                    file_uuid=str(file_uuid),
                    collection_name=collection_name,
                    texts=[context_text],
                    metadata=[milvus_metadata],
                    dense_model=embedding_model,
                    organization_schema=self.organization_schema,
                    record_type="document_context",
                )

                if context_result:
                    logger.info(f"Inserted document context for {file_uuid}")

            # Store chunks in Milvus with document_context for embedding enhancement
            result = self.milvus_store.insert_documents(
                file_uuid=str(file_uuid),
                collection_name=collection_name,
                texts=chunk_texts,
                metadata=metadata_list,
                dense_model=embedding_model,
                organization_schema=self.organization_schema,
                record_type="document_chunk",
                document_context=document_context,
            )
            logger.info(
                f"Successfully stored {len(result)} chunks in Milvus collection {collection_name} for file {file_uuid}"
            )
            return True

        except Exception as e:
            logger.error(f"Error storing data for file {file_uuid} in Milvus: {e}")
            return False

    def _upload_artifacts(
        self,
        document_record: Dict[str, Any],
        collection,
        doc_chunks: List,
        metadata_list: List[Dict[str, Any]],
        parsed_text: str,
    ) -> None:
        """Upload chunks and extracted content files to storage. Non-fatal on failure."""
        try:
            data_store = collection.collection_config.get("data_store")
            if not data_store:
                logger.warning(
                    f"No data_store configured for collection {document_record['collection_name']}"
                )
                return

            chunks_data = [
                {"text": chunk.text.strip(), "metadata": meta}
                for chunk, meta in zip(doc_chunks, metadata_list)
            ]
            chunks_json = json.dumps(chunks_data, indent=2)

            document_file = DocumentFile(self.organization_schema, self.db)

            chunks_file_path = document_file.upload_processed_file(
                data_store=data_store,
                content=chunks_json,
                collection_name=document_record["collection_name"],
                original_filename=document_record["data_file_name"],
                file_suffix="_chunks.json",
            )

            extracted_content_file_path = document_file.upload_processed_file(
                data_store=data_store,
                content=parsed_text,
                collection_name=document_record["collection_name"],
                original_filename=document_record["data_file_name"],
                file_suffix="_content.txt",
            )

            metadata_updates = {}
            if chunks_file_path:
                metadata_updates["chunks_file_path"] = chunks_file_path
            if extracted_content_file_path:
                metadata_updates["extracted_content_file_path"] = extracted_content_file_path

            if metadata_updates:
                self.data_file_repo.update_file_metadata(
                    data_file_id=document_record["data_file_uuid"],
                    metadata_updates=metadata_updates,
                )
                logger.info(f"Saved processed files to storage for {document_record['data_file_name']}")

        except Exception as e:
            logger.error(f"Error saving processed files for {document_record['data_file_name']}: {e}")

    def process_document(self, document_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main function to process a document file:
        1. Validate input → 2. Download → 3. Parse & chunk → 4. Index in Milvus → 5. Return result.
        """
        start_time = time.time()
        time_logs = {}
        file_uuid = document_record["data_file_uuid"]

        try:
            self._update_status(file_uuid, "PROCESSING")

            # Step 1: Validate input
            self.validate_input(document_record)
            logger.info(f"Processing document: {document_record.get('data_file_name')}")

            # Get collection config to determine embedding model
            collection = self.data_collection_repo.get_data_collection_by_id(
                document_record["collection_id"]
            )
            if not collection:
                raise ValueError(f"Collection not found: {document_record['collection_id']}")

            embedding_model = collection.collection_config.get("embedding_model")
            logger.info(f"Using embedding model: {embedding_model}")

            # Initialize MilvusStore
            self.milvus_store = MilvusStore()

            file_extension = (
                Path(document_record.get("data_file_name", "")).suffix.lstrip(".").lower()
            )
            base_metadata = {
                "file_name": document_record.get("data_file_name"),
                "file_extension": file_extension,
                "file_uuid": str(file_uuid),
                "collection_name": document_record.get("collection_name"),
            }

            with tempfile.TemporaryDirectory() as temp_dir:
                # Step 2: Download file
                step_start = time.time()
                temp_file_path = self._download_file(
                    file_name=document_record["data_file_name"],
                    file_source=document_record["data_file_source"],
                    source_metadata=document_record["source_metadata"],
                    temp_dir=temp_dir,
                )
                if not temp_file_path:
                    self._update_status(file_uuid, "FAILED")
                    return {"error": "Failed to download file"}
                time_logs["download"] = time.time() - step_start

                # Step 3: Parse document and create chunks
                step_start = time.time()
                self._update_status(file_uuid, "PARSING")

                parse_result = self.document_parser.parse_document(
                    temp_file_path, base_metadata
                )
                time_logs["parsing"] = time.time() - step_start
                logger.info(parse_result)

                if "error" in parse_result:
                    self._update_status(file_uuid, "FAILED")
                    return {
                        "error": f"Document parsing failed: {parse_result['error']}",
                        "time_logs": time_logs,
                    }

                logger.info(f"Successfully parsed document, total chunks: {parse_result['chunk_count']}")

                # Extract needed data and cleanup parse_result early
                doc_chunks = parse_result["doc_chunks"]
                metadata_list = parse_result["metadata_list"]
                chunk_count = parse_result["chunk_count"]
                file_path = parse_result["file_path"]
                page_count = parse_result["page_count"]
                word_count = parse_result["word_count"]
                parsed_text = parse_result.get("parsed_text", "")

                del parse_result
                gc.collect()

                # Create document context
                document_context = self.create_document_context(
                    file_name=document_record["data_file_name"],
                    doc_chunks=doc_chunks[:10],
                )
                document_context["page_count"] = page_count
                document_context["word_count"] = word_count

                # Normalize text metadata to lowercase for case-insensitive filtering
                _lowercase_metadata(document_context)

                # Save document context to database
                self.update_document_metadata(
                    data_file_uuid=file_uuid,
                    document_context=document_context,
                )

                # Upload artifacts (non-fatal)
                self._upload_artifacts(
                    document_record, collection, doc_chunks, metadata_list, parsed_text
                )

                # Enhance each chunk's metadata with document context
                # Use same format as document_context record: lists → comma-separated strings, lowercased
                enhanced_metadata_list = []
                for meta in metadata_list:
                    enhanced_meta = meta.copy()
                    if document_context:
                        keywords = document_context.get("keywords", [])
                        entities = document_context.get("entities", [])
                        enhanced_meta.update(
                            {
                                "doc_title": document_context.get("title", ""),
                                "doc_type": document_context.get("type", ""),
                                "doc_keywords": ", ".join(str(k) for k in keywords) if isinstance(keywords, list) else keywords,
                                "doc_entities": ", ".join(str(e) for e in entities) if isinstance(entities, list) else entities,
                                "doc_overview": document_context.get("overview", ""),
                            }
                        )
                    enhanced_metadata_list.append(enhanced_meta)

                # Step 4: Store chunks in Milvus
                step_start = time.time()
                self._update_status(file_uuid, "INDEXING")

                is_indexed = self.index_chunks(
                    file_uuid=file_uuid,
                    collection_name=document_record["collection_index"],
                    document_chunks=doc_chunks,
                    metadata_list=enhanced_metadata_list,
                    embedding_model=embedding_model,
                    document_context=document_context,
                )
                time_logs["indexing"] = time.time() - step_start

                if not is_indexed:
                    raise Exception("Milvus indexing failed with unexpected error")

                del doc_chunks, metadata_list, enhanced_metadata_list
                gc.collect()

                # Step 5: Prepare result
                total_time = time.time() - start_time
                time_logs["total_time"] = total_time
                logger.info(f"Total document processing time: {total_time:.2f}s")

                self._update_status(file_uuid, "SUCCESSFUL")
                logger.info(f"Document processed successfully: {document_record.get('data_file_name')}")
                return {
                    "file_path": file_path,
                    "chunk_count": chunk_count,
                    "indexed": is_indexed,
                    "time_logs": time_logs,
                }

        except ValueError as e:
            self._update_status(file_uuid, "FAILED")
            logger.error(f"Validation error: {e}")
            gc.collect()
            return {"error": str(e), "time_logs": time_logs}
        except Exception as e:
            self._update_status(file_uuid, "FAILED")
            logger.error(f"Error processing document {document_record.get('data_file_name')}: {e}")
            gc.collect()
            return {"error": f"Processing failed: {e}", "time_logs": time_logs}


"""
Chunk Metadata (For reference):
{
    // File-level metadata
    "file_name": "Employee_Benefits_Policy_2024.pdf",
    "file_uuid": "12345678-1234-5678-9abc-123456789abc",
    "collection_name": "hr_documents",
    
    // Document parser metadata
    "source_file": "Employee_Benefits_Policy_2024.pdf",
    "mime_type": "application/pdf",
    "source_uri": "/path/to/file.pdf",
    "headings": ["Benefits Overview", "Healthcare Plans", "Enrollment"],
    "page_bboxes": [
        {"page": 1, "bbox": [72.0, 100.0, 500.0, 700.0]},
        {"page": 2, "bbox": [72.0, 150.0, 500.0, 650.0]}
    ],
    
    // Document context fields
    "doc_title": "Employee Benefits Policy Manual 2024",
    "doc_type": "policy",
    "doc_keywords": ["employee benefits", "healthcare", "enrollment", "HR policy"],
    "doc_entities": ["XYZ Corporation", "January 1, 2024", "HR Department"],
    "doc_filename": "Employee_Benefits_Policy_2024.pdf"

    // Document knowledge fields
    "knowledge_topic": "Employee Benefits",
}
"""


# Example test code
if __name__ == "__main__":
    import uuid
    from pathlib import Path
    from db_pool import DatabasePoolManager

    db_pool = DatabasePoolManager()
    db_session = db_pool.get_session(schema_name="public")

    # Configure test file path
    file_path = Path("./data/10k-apple-2024.pdf")
    collection_name = "test_collection"

    print(f"Testing document processing on: {file_path.name}")

    # Create test message data
    document_record = {
        "data_file_path": str(file_path.absolute()),
        "data_file_name": file_path.name,
        "data_file_uuid": str(uuid.uuid4()),
        "collection_name": collection_name,
    }

    with db_session:
        document_indexer = DocumentIndexer(
            db=db_session, organization_schema="public"
        )
        results = document_indexer.process_document(document_record)

    # Report results
    if "error" in results:
        print(f"\nERROR: {results['error']}")
    else:
        print("\nSUCCESS!")
        print(f"Proceesing time: {results.get('time_logs', {})}")
        print(f"Chunk count: {results.get('chunk_count', 0)}")
