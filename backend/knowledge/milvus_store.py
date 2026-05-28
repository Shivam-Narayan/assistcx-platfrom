import gc
import json
import re
import uuid
import time
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from pymilvus import (
    MilvusClient,
    DataType,
    Function,
    FunctionType,
)
from logger import configure_logging
from .milvus_base import MilvusBase
from .utils import format_document_context

logger = configure_logging(__name__)


class MilvusStore(MilvusBase):
    """
    Milvus vector store for document management and insertion.

    Handles collection creation, document insertion with embeddings
    (dense + BM25 text), document context, deletion, and updates.

    For search functionality, use MilvusSearch class.
    """

    def __init__(self):
        super().__init__()

    def create_collection(self, collection_name: str, dense_dim: int) -> bool:
        """
        Create a unified Milvus collection with schema and indexes for both
        document summaries and chunks using record_type discrimination.

        Args:
            collection_name: Name of the collection to create.
            dense_dim: Dimension of dense embedding vectors.

        Returns:
            bool: True if collection created successfully, False otherwise.
        """
        try:
            if self.client.has_collection(collection_name):
                logger.info(f"Collection {collection_name} already exists")
                return True

            # Create unified schema for both document summaries and chunks
            schema = MilvusClient.create_schema(
                auto_id=False,
                enable_dynamic_field=True,
                description="Unified collection for document summaries and chunks",
            )

            # Primary key - unique identifier for each record
            schema.add_field(
                field_name="id",
                datatype=DataType.VARCHAR,
                max_length=64,
                is_primary=True,
                description="Unique record identifier",
            )

            # Record type discriminator - KEY ADDITION
            schema.add_field(
                field_name="record_type",
                datatype=DataType.VARCHAR,
                max_length=30,
                description="Record type: 'document_context', 'document_chunk', or 'document_knowledge'",
            )

            # File reference - keeping original field name
            schema.add_field(
                field_name="document_id",
                datatype=DataType.VARCHAR,
                max_length=64,
                description="Document ID this record belongs to",
            )

            # Content field - used for both document context text and chunk text
            schema.add_field(
                field_name="content",
                datatype=DataType.VARCHAR,
                max_length=16384,
                description="Text content (document context or chunk text)",
            )

            # Metadata - flexible JSON for both record types
            schema.add_field(
                field_name="metadata",
                datatype=DataType.JSON,
                description="Record metadata (structure varies by record_type)",
            )

            # Dense vector - used by both document summaries and chunks
            schema.add_field(
                field_name="dense_vector",
                datatype=DataType.FLOAT_VECTOR,
                dim=dense_dim,
                description="Dense embedding vector",
            )

            # Search content field - enhanced text (chunk + context) for BM25 full-text search
            schema.add_field(
                field_name="search_content",
                datatype=DataType.VARCHAR,
                max_length=16384,
                enable_analyzer=True,
                analyzer_params={"type": "standard"},
                enable_match=True,
                description="Enhanced text content for BM25 full-text search",
            )

            # Sparse vector field - output of BM25 function
            schema.add_field(
                field_name="sparse_vector",
                datatype=DataType.SPARSE_FLOAT_VECTOR,
                description="BM25 sparse vector (auto-generated)",
            )

            # Timestamp - renamed for clarity
            schema.add_field(
                field_name="timestamp",
                datatype=DataType.INT64,
                description="Creation timestamp",
            )

            # Add BM25 function to convert text to sparse vector
            bm25_function = Function(
                name="bm25_fn",
                input_field_names=["search_content"],
                output_field_names=["sparse_vector"],
                function_type=FunctionType.BM25,
            )
            schema.add_function(bm25_function)

            # Create optimized indexes for unified collection
            index_params = self.client.prepare_index_params()

            # Dense vector index - used by both record types
            index_params.add_index(
                field_name="dense_vector",
                index_name="dense_vector_idx",
                index_type="IVF_FLAT",
                metric_type="IP",
                params={"nlist": 2048},
            )

            # BM25 sparse vector index
            index_params.add_index(
                field_name="sparse_vector",
                index_name="sparse_vector_idx",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="BM25",
            )

            # CRITICAL: Record type index for efficient filtering
            index_params.add_index(
                field_name="record_type",
                index_name="record_type_idx",
                index_type="INVERTED",
            )

            # File reference index for document-based filtering
            index_params.add_index(
                field_name="document_id",
                index_name="document_id_idx",
                index_type="INVERTED",
            )

            # Create the collection with schema and indexes
            self.client.create_collection(
                collection_name=collection_name,
                schema=schema,
                index_params=index_params,
            )

            logger.info(f"Created unified collection: {collection_name}")
            logger.info(
                f"Schema supports: document_context, document_chunk, and document_knowledge record types"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to create collection {collection_name}: {e}")
            return False

    def delete_collection(self, collection_name: str) -> bool:
        """
        Drop a collection from Milvus.

        Args:
            collection_name: Name of the collection to drop.
        """
        try:
            if self.client.has_collection(collection_name):
                self.client.drop_collection(collection_name)
                logger.info(f"Dropped collection: {collection_name}")
                return True
            else:
                logger.info(f"Collection {collection_name} does not exist")
                return False
        except Exception as e:
            logger.error(f"Failed to drop collection {collection_name}: {e}")
            return False

    def insert_documents(
        self,
        file_uuid: str,
        collection_name: str,
        texts: List[str],
        metadata: List[Dict[str, Any]],
        dense_model: str,
        organization_schema: Optional[str] = None,
        record_type: str = "document_chunk",
        document_context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Insert documents with metadata in batches.

        Args:
            collection_name: Name of the collection.
            texts: List of text documents.
            metadata: List of metadata dicts.
            file_uuid: Unique identifier for the document.
            dense_model: Model name for dense embeddings (e.g., "Alibaba-NLP/gte-multilingual-base" or "openai/text-embedding-3-small").
            organization_schema: Organization schema for API-based models (required for OpenAI).
            record_type: Type of record to insert ("document_chunk", "document_context", "document_knowledge").
            document_context: Optional document context for enhanced embedding.
        Returns:
            List of all inserted document IDs.
        """
        if not dense_model:
            raise ValueError(
                "dense_model is required for insert operations. "
                "Please provide dense_model parameter."
            )

        logger.info(f"Inserting {len(texts)} docs into '{collection_name}'")

        if len(texts) != len(metadata):
            raise ValueError("Length of texts and metadata must match")

        # Verify the collection exists (must be created beforehand with correct dense_dim)
        if not self.client.has_collection(collection_name):
            raise ValueError(
                f"Collection '{collection_name}' does not exist. "
                "Create it first via create_collection() with the correct dense_dim."
            )

        # Handle document_context uniqueness: delete existing document_context records for this file_uuid
        if record_type == "document_context":
            deleted = self.delete_documents_with_filter(
                collection_name=collection_name,
                file_uuid=file_uuid,
                record_type="document_context",
            )
            if deleted:
                logger.info(
                    f"Successfully deleted existing document_context records for file_uuid {file_uuid}"
                )
            else:
                logger.debug(
                    f"No existing document_context records found for file_uuid {file_uuid}"
                )

        all_ids: List[str] = []
        batch_size = self.INSERT_BATCH_SIZE

        try:
            # Compute once before batching (constant across all batches)
            context = format_document_context(document_context) if document_context else None
            dense_ef, _ = self._get_dense_embedder(dense_model, organization_schema)

            # Process in batches for efficient insertion
            for start in range(0, len(texts), batch_size):
                end = min(start + batch_size, len(texts))
                batch_texts = texts[start:end]
                batch_meta = metadata[start:end]

                logger.info(f"Processing batch {start}-{end}")

                t0 = time.time()  # Batch start time

                # Create enhanced texts for dense embedding: chunk + context
                if context:
                    enhanced_texts = [f"{chunk}\n\n{context}" for chunk in batch_texts]
                else:
                    enhanced_texts = batch_texts

                # Generate dense embeddings for enhanced texts
                dense_vecs = dense_ef.encode_documents(enhanced_texts)

                t1 = time.time()  # Dense embedding end time
                logger.debug(
                    f"Batch {start}-{end}: generated {len(dense_vecs)} dense embeddings in {t1-t0:.2f}s"
                )

                # Build batch data - sparse vector is auto-generated by Milvus from search_content
                batch_data = []
                for i, (text, meta, dense_vec, enhanced_text) in enumerate(
                    zip(batch_texts, batch_meta, dense_vecs, enhanced_texts)
                ):
                    doc_id = str(uuid.uuid4())
                    all_ids.append(doc_id)

                    batch_data.append(
                        {
                            "id": doc_id,
                            "record_type": record_type,
                            "document_id": str(file_uuid),
                            "content": text,  # Original chunk text only
                            "metadata": meta,
                            "dense_vector": dense_vec,
                            "search_content": enhanced_text,  # Enhanced text for BM25 search
                            "timestamp": int(time.time()),
                        }
                    )

                # Clean up
                del enhanced_texts, batch_texts, dense_vecs, batch_meta
                gc.collect()

                t2 = time.time()  # Insert start time

                # Insert the entire batch at once for efficiency
                self.client.insert(
                    collection_name=collection_name,
                    data=batch_data,
                )

                t3 = time.time()  # Insert end time
                logger.info(
                    f"Batch {start}-{end}: "
                    f"dense={t1-t0:.2f}s, insert={t3-t2:.2f}s, "
                    f"inserted {len(batch_data)} docs"
                )

                # Clean up batch data immediately after insertion
                del batch_data
                gc.collect()

            # Flush once at the end
            self.client.flush(collection_name)
            logger.info(
                f"Flushed collection: {collection_name}; total inserted = {len(all_ids)}"
            )

            return all_ids

        except Exception as e:
            logger.error(f"Unexpected error during insert_documents: {e}")
            # Clean up on error
            gc.collect()
            raise

    def list_collections(self) -> List[str]:
        """
        List all collections in the Milvus database.

        Returns:
            List of collection names.
        """
        try:
            return self.client.list_collections()
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            raise

    def rename_collection(self, old_name: str, new_name: str) -> bool:
        """
        Rename a Milvus collection.

        Args:
            old_name: Current name of the collection.
            new_name: New name for the collection.

        Returns:
            bool: True if renaming was successful, False otherwise.
        """
        try:
            if not self.client.has_collection(old_name):
                logger.error(f"Collection {old_name} does not exist")
                return False
            if self.client.has_collection(new_name):
                logger.error(f"Collection {new_name} already exists")
                return False
            self.client.rename_collection(old_name, new_name)
            logger.info(f"Renamed collection from {old_name} to {new_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to rename collection {old_name} to {new_name}: {e}")
            return False

    def fetch_documents_with_filter(
        self,
        collection_name: str,
        file_uuid: Optional[str] = None,
        record_type: Optional[str] = None,
        filter_expr: Optional[str] = None,
        result_limit: Optional[int] = None,
        output_fields: Optional[List[str]] = None,
    ) -> List[Document]:
        """
        Fetch documents by flexible criteria (file_uuid, record_type, or custom filter).

        Args:
            collection_name: Name of the collection
            file_uuid: Optional file UUID to filter by
            record_type: Optional record type to filter by
            filter_expr: Optional filter expression to filter by
            result_limit: Optional limit on number of results
            output_fields: Optional list of fields to return. If None, returns all standard fields.

        Returns:
            List[Document]: List of matching documents as LangChain Document objects

        Filter Examples:
            # Filter by record type
            filter_expr='record_type == "document_chunk"'
            filter_expr='record_type == "document_context"'
            filter_expr='record_type == "document_knowledge"'

            # Filter by document ID
            filter_expr='document_id == "doc123"'
            filter_expr='document_id in ["doc1", "doc2", "doc3"]'

            # Filter by metadata fields (JSON)
            filter_expr='metadata["knowledge_topic"] == "finance"'
            filter_expr='metadata["filename"] like "%.pdf"'
            filter_expr='metadata["created_at"] > "2024-01-01"'

            # Combined filters
            filter_expr='record_type == "document_chunk" && document_id in ["doc1", "doc2"]'
            filter_expr='record_type == "document_chunk" && metadata["knowledge_topic"] == "finance"'
        """
        try:
            # Set default output fields if not provided
            if output_fields is None:
                output_fields = [
                    "id",
                    "record_type",
                    "document_id",
                    "content",
                    "metadata",
                    "timestamp",
                ]

            # Build filter expression
            filter_parts = []

            if file_uuid:
                filter_parts.append(f'document_id == "{file_uuid}"')

            if record_type:
                filter_parts.append(f'record_type == "{record_type}"')

            if filter_expr:
                filter_parts.append(filter_expr)

            if not filter_parts:
                logger.error("No filter criteria provided for fetch")
                return []

            filter_query = " AND ".join(filter_parts)
            logger.debug(f"Fetch query filter: {filter_query}")

            # Query for matching records
            with self.collection_loader(collection_name):
                query_params = {
                    "collection_name": collection_name,
                    "filter": filter_query,
                    "output_fields": output_fields,
                }

                if result_limit:
                    query_params["limit"] = result_limit

                logger.debug(f"Query parameters: {query_params}")

                matching_records = self.client.query(**query_params)

                logger.debug(
                    f"Found {len(matching_records)} records matching filter: {filter_query}"
                )

                # Convert to Document objects for consistency with hybrid search
                documents = []
                for record in matching_records:
                    # Parse metadata safely
                    base_meta = {}
                    if meta_str := record.get("metadata"):
                        if isinstance(meta_str, (str, bytes, bytearray)):
                            try:
                                base_meta = json.loads(meta_str)
                            except json.JSONDecodeError:
                                pass
                        else:
                            base_meta = meta_str

                    # Add search metadata
                    # Map Milvus document_id field to file_uuid for consistent naming
                    base_meta.update(
                        {
                            "id": record.get("id"),
                            "file_uuid": record.get("document_id"),
                            "record_type": record.get("record_type"),
                            "created_at": record.get("timestamp"),
                        }
                    )

                    documents.append(
                        Document(
                            page_content=record.get("content", ""), metadata=base_meta
                        )
                    )

                return documents

        except Exception as e:
            logger.error(f"Error fetching records with filter: {e}")
            return []

    def delete_documents_with_filter(
        self,
        collection_name: str,
        file_uuid: Optional[str] = None,
        record_type: Optional[str] = None,
        filter_expr: Optional[str] = None,
    ) -> bool:
        """
        Delete documents by flexible criteria (file_uuid, record_type, or custom filter).

        Args:
            collection_name: Name of the collection
            file_uuid: Optional file UUID to filter by
            record_type: Optional record type to filter by
            filter_expr: Optional additional filter expression

        Returns:
            bool: True if documents were deleted, False if no documents found or error
        """
        try:
            # Build filter expression
            filter_parts = []

            if file_uuid:
                filter_parts.append(f'document_id == "{file_uuid}"')

            if record_type:
                filter_parts.append(f'record_type == "{record_type}"')

            if filter_expr:
                filter_parts.append(filter_expr)

            if not filter_parts:
                logger.error("No filter criteria provided for deletion")
                return False

            filter_query = " AND ".join(filter_parts)
            logger.debug(f"Delete filter: {filter_query}")

            # Query for matching records
            with self.collection_loader(collection_name):
                matching_records = self.client.query(
                    collection_name=collection_name,
                    filter=filter_query,
                    output_fields=["id"],
                )

                if not matching_records:
                    logger.info(f"No records found matching filter: {filter_query}")
                    return True

                # Extract IDs and delete
                record_ids = [record["id"] for record in matching_records]
                self.client.delete(collection_name=collection_name, pks=record_ids)

                logger.info(
                    f"Deleted {len(record_ids)} records matching filter: {filter_query}"
                )
                return True

        except Exception as e:
            logger.error(f"Error deleting records with filter: {e}")
            return False

    def delete_documents_by_file_uuid(
        self,
        collection_name: str,
        file_uuid: str,
    ) -> bool:
        """
        Delete every row whose document_id == file_uuid.
        """
        return self.delete_documents_with_filter(
            collection_name=collection_name, file_uuid=file_uuid
        )

    def remove_field_from_document_context(
        self,
        collection_name: str,
        file_uuid: str,
        field_name: str,
        dense_model: str,
        organization_schema: Optional[str] = None,
    ) -> bool:
        """
        Remove a specific smart field from a document's context record in Milvus.
        Fetches the existing document_context, removes the field from both content
        text and metadata, then re-inserts the updated record.

        Args:
            collection_name (str): Name of the Milvus collection
            file_uuid (str): UUID of the document to update
            field_name (str): Name of the smart field to remove
            dense_model (str): Model name for dense embeddings
            organization_schema (Optional[str]): Organization schema for API-based models

        Returns:
            bool: True if field was successfully removed or didn't exist,
                False if an error occurred
        """
        try:
            # Fetch existing document_context record
            records = self.fetch_documents_with_filter(
                collection_name=collection_name,
                file_uuid=file_uuid,
                record_type="document_context",
                result_limit=1,
            )

            if not records:
                logger.debug(
                    f"No document_context found for file {file_uuid}, "
                    f"field '{field_name}' removal skipped"
                )
                return True

            record = records[0]
            content = record.page_content
            metadata = record.metadata.copy()

            # Remove field from metadata if exists
            field_removed_from_metadata = False
            if field_name in metadata:
                del metadata[field_name]
                field_removed_from_metadata = True
                logger.debug(f"Removed field '{field_name}' from metadata")

            # Remove field from content text using regex pattern matching
            field_pattern = f"^{re.escape(field_name)}: .*$"
            updated_content = re.sub(
                field_pattern + r"\n?", "", content, flags=re.MULTILINE
            ).strip()

            field_removed_from_content = updated_content != content

            # Only re-insert if something actually changed
            if field_removed_from_metadata or field_removed_from_content:
                # Re-insert updated record (automatically handles document_context uniqueness)
                self.insert_documents(
                    file_uuid=file_uuid,
                    collection_name=collection_name,
                    texts=[updated_content],
                    metadata=[metadata],
                    dense_model=dense_model,
                    organization_schema=organization_schema,
                    record_type="document_context",
                )

                logger.info(
                    f"Successfully removed field '{field_name}' from document_context "
                    f"for file {file_uuid}"
                )
            else:
                logger.debug(
                    f"Field '{field_name}' not found in document_context "
                    f"for file {file_uuid} (already removed or never existed)"
                )

            return True

        except Exception as e:
            logger.error(
                f"Error removing field '{field_name}' from document_context "
                f"for file {file_uuid}: {e}"
            )
            return False

    def remove_topic_from_document_knowledge(
        self,
        collection_name: str,
        file_uuid: str,
        topic_name: str,
    ) -> bool:
        """
        Remove a specific knowledge topic from document_knowledge records in Milvus.
        Uses metadata filtering to delete only the specific topic's record.

        Args:
            collection_name (str): Name of the Milvus collection
            file_uuid (str): UUID of the document to update
            topic_name (str): Name of the knowledge topic to remove

        Returns:
            bool: True if topic was successfully removed or didn't exist,
                False if an error occurred
        """
        try:
            # Build filter to match specific topic
            # Format: document_id == "uuid" && record_type == "document_knowledge" && metadata["knowledge_topic"] == "topic_name"
            filter_expr = f'metadata["knowledge_topic"] == "{topic_name}"'

            # Delete matching document_knowledge records
            success = self.delete_documents_with_filter(
                collection_name=collection_name,
                file_uuid=file_uuid,
                record_type="document_knowledge",
                filter_expr=filter_expr,
            )

            if success:
                logger.info(
                    f"Successfully removed topic '{topic_name}' from document_knowledge "
                    f"for file {file_uuid}"
                )
            else:
                logger.debug(
                    f"Topic '{topic_name}' not found in document_knowledge "
                    f"for file {file_uuid} (already removed or never extracted)"
                )

            return True

        except Exception as e:
            logger.error(
                f"Error removing topic '{topic_name}' from document_knowledge "
                f"for file {file_uuid}: {e}"
            )
            return False

    def update_file_name(
        self,
        collection_name: str,
        file_uuid: str,
        new_file_name: str,
    ) -> bool:
        """
        Find every row with document_id == file_uuid, pull all required fields,
        update origin.filename in metadata, then upsert back.
        """
        try:
            output_fields = [
                "id",
                "document_id",
                "content",
                "metadata",
                "sparse_vector",
                "dense_vector",
                "timestamp",
                "record_type",
            ]

            with self.collection_loader(collection_name, fields=output_fields):
                rows = self.client.query(
                    collection_name=collection_name,
                    filter=f'document_id == "{file_uuid}"',
                    output_fields=output_fields,
                )

                if not rows:
                    logger.info(f"No docs to update for {file_uuid}")
                    return False

                # Build upsert batch: only keep those where origin.filename changes
                batch = []
                for row in rows:
                    doc_id = row["id"]
                    meta_val = row.get("metadata", "{}")
                    if isinstance(meta_val, (str, bytes, bytearray)):
                        try:
                            meta = json.loads(meta_val)
                        except json.JSONDecodeError:
                            logger.warning(f"Skipping {doc_id}: invalid metadata JSON")
                            continue
                    else:
                        meta = meta_val

                    origin = meta.get("origin", {})
                    if origin.get("filename") == new_file_name:
                        continue

                    origin["filename"] = new_file_name
                    meta["origin"] = origin
                    batch.append(
                        {
                            "id": doc_id,
                            "document_id": row["document_id"],
                            "content": row["content"],
                            "metadata": meta,
                            "sparse_vector": row["sparse_vector"],
                            "dense_vector": row["dense_vector"],
                            "timestamp": row["timestamp"],
                            "record_type": row["record_type"],
                        }
                    )

                if not batch:
                    logger.info(f"No filename changes needed for {file_uuid}")
                    return False

                self.client.upsert(collection_name=collection_name, data=batch)

            logger.info(f"Updated filename in {len(batch)} docs for {file_uuid}")
            return True

        except Exception:
            logger.exception(f"Could not update filename for {file_uuid}")
            raise


# Example usage
if __name__ == "__main__":
    import sys

    # Hardcoded values
    COLLECTION_NAME = "test_collection"
    QUERY_FILTER = 'record_type == "document_chunk"'

    # Create Milvus store instance
    milvus_store = MilvusStore()

    # Simple argument handling - just use the first argument
    if len(sys.argv) < 2:
        print(
            "Usage: python -m backend.knowledge.milvus_store [--query|--delete|--clear]"
        )
        sys.exit(1)

    action = sys.argv[1].lower()

    if action == "--delete":
        print(f"Deleting collection: {COLLECTION_NAME}")
        result = milvus_store.delete_collection(COLLECTION_NAME)
        if result:
            print(f"\nCollection '{COLLECTION_NAME}' successfully deleted\n")
        else:
            print(
                f"\nFailed to delete collection '{COLLECTION_NAME}' or it doesn't exist\n"
            )

    elif action == "--query":
        print(f"\nQuerying collection: {COLLECTION_NAME} with filter: {QUERY_FILTER}\n")
        documents = milvus_store.fetch_documents_with_filter(
            collection_name=COLLECTION_NAME, filter_expr=QUERY_FILTER, result_limit=10
        )
        print(f"\nNumber of documents found: {len(documents)}\n")
        for i, doc in enumerate(documents, 1):
            print(f"\n===== Document {i} =====")
            print(f"ID: {doc.metadata.get('id', 'N/A')}")
            print(f"Document ID: {doc.metadata.get('document_id', 'N/A')}")
            print(f"Record Type: {doc.metadata.get('record_type', 'N/A')}")
            print(f"Content: {doc.page_content[:200]}...")
            print("=" * 40)

    elif action == "--clear":
        print(f"\nClearing all documents from collection: {COLLECTION_NAME}")
        if not milvus_store.client.has_collection(COLLECTION_NAME):
            print(f"Collection '{COLLECTION_NAME}' does not exist")
            sys.exit(1)

        # Use delete_documents_with_filter to clear all documents
        result = milvus_store.delete_documents_with_filter(
            collection_name=COLLECTION_NAME,
            filter_expr="id != ''",  # Match all documents
        )

        if result:
            print(
                f"Successfully cleared all documents from collection '{COLLECTION_NAME}'"
            )
        else:
            print(
                f"No documents found or failed to clear collection '{COLLECTION_NAME}'"
            )

    else:
        print(f"Unknown action: {action}")
        print(
            "Usage: python -m backend.knowledge.milvus_store [--query|--delete|--clear]"
        )
        sys.exit(1)
