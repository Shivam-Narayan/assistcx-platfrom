import json
from typing import Dict, List, Optional, Union
from collections import defaultdict

from langchain_core.documents import Document
from pymilvus import (
    AnnSearchRequest,
    WeightedRanker,
    RRFRanker,
)
from logger import configure_logging
from .milvus_base import MilvusBase

logger = configure_logging(__name__)


class MilvusSearch(MilvusBase):
    """
    Milvus hybrid search with dense embeddings and BM25 text search.

    Supports three search strategies: collection-wide (content chunks),
    knowledge topic (pre-extracted summaries), and document metadata (overviews).
    """

    def __init__(
        self,
        result_limit: int = 50,
        score_cutoff: float = 0.1,
    ):
        super().__init__()
        self.result_limit = result_limit
        self.score_cutoff = score_cutoff

    def _filter_document_ids(
        self, collection_name: str, filter_expr: str
    ) -> List[str]:
        """Pure filter query — no vector scoring, returns ALL matching doc IDs.

        Used for metadata-to-docid resolution: metadata fields only exist on
        document_context records, so searches on document_chunk or document_knowledge
        must first resolve metadata filters to document IDs via this method.
        """
        with self.collection_loader(collection_name):
            results = self.client.query(
                collection_name=collection_name,
                filter=filter_expr,
                output_fields=["document_id"],
            )
        return list({r["document_id"] for r in results if r.get("document_id")})

    def _process_search_results(
        self,
        raw_results: List[List[Dict]],
        result_limit: Optional[int] = None,
        score_cutoff: Optional[float] = None,
        max_chunks_per_doc: Optional[int] = None,
    ) -> List[Document]:
        """
        Process and deduplicate search results from Milvus.

        Args:
            raw_results: Raw results from Milvus search/hybrid_search
            result_limit: Optional limit on number of results to return
            score_cutoff: Score threshold for filtering. Defaults to self.score_cutoff.
            max_chunks_per_doc: Optional cap on chunks per document for broader coverage.

        Returns:
            List of deduplicated Document objects grouped by document_id (file UUID),
            sorted by relevance within each file group
        """
        if score_cutoff is None:
            score_cutoff = self.score_cutoff
        seen_records = {}  # record_id -> Document (keep best score)

        for hits_for_query in raw_results:
            for hit in hits_for_query:
                record_id = hit.get("id")
                if not record_id:
                    continue

                current_score = hit.get("distance", 0)

                # Skip if we already have a better scoring version
                existing_score = (
                    seen_records[record_id].metadata.get("distance", 0)
                    if record_id in seen_records
                    else -1
                )

                if record_id in seen_records and current_score <= existing_score:
                    continue

                entity = hit.get("entity", {})

                # Parse metadata safely
                base_meta = {}
                if meta_str := entity.get("metadata"):
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
                        "id": record_id,
                        "distance": current_score,
                        "file_uuid": entity.get("document_id"),
                        "record_type": entity.get("record_type"),
                        "created_at": entity.get("timestamp"),
                    }
                )

                seen_records[record_id] = Document(
                    page_content=entity.get("content", ""), metadata=base_meta
                )

        # Convert to list
        unique_docs = list(seen_records.values())

        # STEP 1: Filter by score cutoff
        if score_cutoff > 0:
            unique_docs = [
                doc
                for doc in unique_docs
                if doc.metadata.get("distance", 0) >= score_cutoff
            ]
            logger.info(
                f"Filtered to {len(unique_docs)} results above score cutoff {score_cutoff}"
            )

        # STEP 2: Group by document, sort by max score per group
        # This ensures highest-scoring document-chunk combos appear first
        doc_groups = defaultdict(list)
        for doc in unique_docs:
            doc_groups[doc.metadata.get("file_uuid", "")].append(doc)

        # Sort groups by max score, sort chunks within each group
        unique_docs = []
        for doc_id, chunks in sorted(
            doc_groups.items(),
            key=lambda x: max(c.metadata.get("distance", 0) for c in x[1]),
            reverse=True,
        ):
            # Sort chunks within this document by score (descending)
            chunks.sort(key=lambda x: -x.metadata.get("distance", 0))
            if max_chunks_per_doc:
                chunks = chunks[:max_chunks_per_doc]
            unique_docs.extend(chunks)

        # STEP 3: Apply limit AFTER filtering and sorting
        if result_limit is not None:
            unique_docs = unique_docs[:result_limit]

        logger.info(
            f"Processed {len(unique_docs)} unique documents from search results"
        )

        return unique_docs

    def hybrid_search(
        self,
        collection_name: str,
        queries: Union[str, List[str]],
        dense_model: str,
        organization_schema: Optional[str] = None,
        result_limit: Optional[int] = None,
        filter_expr: Optional[str] = None,
        score_cutoff: Optional[float] = None,
        max_chunks_per_doc: Optional[int] = None,
    ) -> List[Document]:
        """
        Perform hybrid search with flexible filtering capabilities.

        Args:
            collection_name: Name of the collection
            queries: Single query or list of queries
            dense_model: Model name for dense embeddings (e.g., "Alibaba-NLP/gte-multilingual-base" or "openai/text-embedding-3-small").
            organization_schema: Organization schema for API-based models (required for OpenAI).
            result_limit: Number of results to return per query
            filter_expr: Optional filter expression for flexible filtering.
                        If None, defaults to 'record_type == "document_chunk"'
            score_cutoff: Optional score threshold for filtering results.
                         If None, uses the default score_cutoff from constructor
            max_chunks_per_doc: Optional cap on chunks per document for broader coverage.

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

            # Combined filters (AND/OR)
            filter_expr='record_type == "document_chunk" AND document_id in ["doc1", "doc2"]'
            filter_expr='record_type == "document_chunk" AND metadata["knowledge_topic"] == "finance"'

        Returns:
            List of Document objects
        """
        # Input validation
        if not collection_name or not isinstance(collection_name, str):
            raise ValueError("collection_name must be a non-empty string")

        if not queries:
            raise ValueError("queries cannot be empty")

        if result_limit is not None and result_limit <= 0:
            raise ValueError(f"result_limit must be positive, got {result_limit}")

        # Normalize to list
        if isinstance(queries, str):
            query_list = [queries]
        else:
            query_list = queries

        if not query_list:
            raise ValueError("queries list cannot be empty")

        try:
            # Get dense embedding function (ModelProvider handles caching)
            dense_ef, _ = self._get_dense_embedder(dense_model, organization_schema)
            
            # Generate dense embeddings for queries
            query_dense_batch = dense_ef.encode_documents(query_list)

            # Use provided filter or default to document chunks if no filter specified
            if not filter_expr:
                filter_expr = 'record_type == "document_chunk"'

            # Build hybrid search requests
            # Dense vector search (semantic similarity)
            dense_req = AnnSearchRequest(
                data=query_dense_batch,
                anns_field="dense_vector",
                param={"metric_type": "IP", "params": {"nprobe": 256}},
                limit=result_limit,
                expr=filter_expr,
            )

            # BM25 text search (keyword matching)
            # Milvus BM25 function automatically converts text queries to sparse vectors
            bm25_req = AnnSearchRequest(
                data=query_list,  # Raw text queries - BM25 function handles conversion
                anns_field="sparse_vector",
                param={"metric_type": "BM25"},
                limit=result_limit,
                expr=filter_expr,
            )

            # Choose ranker
            ranker = (
                RRFRanker(self.rrf_k)
                if self.use_rrf
                else WeightedRanker(self.dense_weight, self.sparse_weight)
            )

            # Perform hybrid search (dense + BM25)
            with self.collection_loader(collection_name):
                raw_results = self.client.hybrid_search(
                    collection_name=collection_name,
                    reqs=[dense_req, bm25_req],
                    ranker=ranker,
                    limit=result_limit,
                    output_fields=[
                        "content",
                        "document_id",
                        "record_type",
                        "metadata",
                        "timestamp",
                    ],
                )

            # Process results using helper function with limit and optional cutoff override
            unique_docs = self._process_search_results(
                raw_results, result_limit, score_cutoff, max_chunks_per_doc
            )

            logger.info(f"Found {len(unique_docs)} chunks")
            return unique_docs

        except Exception as e:
            logger.error(f"Error in hybrid search: {e}")
            return []

    async def knowledge_search(
        self,
        collection_name: str,
        queries: Union[str, List[str]],
        dense_model: str,
        organization_schema: Optional[str] = None,
        search_scope: Optional[str] = None,
        result_limit: Optional[int] = None,
        knowledge_topic: Optional[str] = None,
        filter_expr: Optional[str] = None,
        score_cutoff: Optional[float] = None,
    ) -> List[Document]:
        """
        Main search method with support for different strategies.

        Args:
            collection_name: Name of the collection to search
            queries: Single query string or list of query strings
            dense_model: Model name for dense embeddings (e.g., "Alibaba-NLP/gte-multilingual-base" or "openai/text-embedding-3-small").
            organization_schema: Organization schema for API-based models (required for OpenAI).
            search_scope: Search strategy - document_content, document_metadata, knowledge_topic
            result_limit: Number of results to return
            knowledge_topic: Knowledge topic filter for knowledge_topic search
            filter_expr: Optional filter expression for more specific search
            score_cutoff: Optional score threshold for filtering results.
                         If None, uses the default score_cutoff from constructor

        Returns:
            List of Document objects
        """
        # Input validation
        if not collection_name or not isinstance(collection_name, str):
            raise ValueError("collection_name must be a non-empty string")

        if not queries:
            raise ValueError("queries cannot be empty")

        try:
            # Validate search scope
            valid_scopes = {
                "document_content",
                "document_metadata",
                "knowledge_topic",
            }
            if search_scope is not None and search_scope not in valid_scopes:
                raise ValueError(
                    f"search_scope must be one of {valid_scopes}, got '{search_scope}'"
                )

            # Auto-select result count based on scope
            if result_limit is None:
                result_limit = self.result_limit

            if search_scope == "document_content":
                # Hybrid search on document_chunk records
                document_content_filter = 'record_type == "document_chunk"'

                # Metadata fields only exist on document_context records.
                # Resolve metadata filters to document IDs via pure filter query.
                if filter_expr:
                    context_filter = f'record_type == "document_context" AND {filter_expr}'
                    doc_ids = self._filter_document_ids(
                        collection_name, context_filter
                    )
                    if doc_ids:
                        doc_id_list = ", ".join(f'"{did}"' for did in doc_ids)
                        document_content_filter += (
                            f" AND document_id IN [{doc_id_list}]"
                        )
                    else:
                        logger.info(
                            "No documents matched metadata filter, returning empty"
                        )
                        return []

                return self.hybrid_search(
                    collection_name=collection_name,
                    queries=queries,
                    dense_model=dense_model,
                    organization_schema=organization_schema,
                    result_limit=result_limit,
                    filter_expr=document_content_filter,
                    score_cutoff=score_cutoff,
                    max_chunks_per_doc=5,
                )

            elif search_scope == "document_metadata":
                # Hybrid search on document_context records
                document_metadata_filter = 'record_type == "document_context"'
                if filter_expr:
                    document_metadata_filter = (
                        f"{document_metadata_filter} AND {filter_expr}"
                    )

                return self.hybrid_search(
                    collection_name=collection_name,
                    queries=queries,
                    dense_model=dense_model,
                    organization_schema=organization_schema,
                    result_limit=result_limit,
                    filter_expr=document_metadata_filter,
                    score_cutoff=score_cutoff,
                )

            elif search_scope == "knowledge_topic":
                # Hybrid search on document_knowledge with knowledge_topic filter
                if not knowledge_topic:
                    raise ValueError(
                        "knowledge_topic is required for knowledge_topic search scope"
                    )

                # Escape quotes in knowledge_topic to prevent injection
                escaped_topic = knowledge_topic.replace('"', '\\"')

                # Default knowledge_topic filter
                knowledge_topic_filter = f'record_type == "document_knowledge" AND metadata["knowledge_topic"] == "{escaped_topic}"'

                # Metadata fields only exist on document_context records.
                # Resolve metadata filters to document IDs via pure filter query.
                relevant_doc_ids = None
                if filter_expr:
                    context_filter = f'record_type == "document_context" AND {filter_expr}'
                    relevant_doc_ids = self._filter_document_ids(
                        collection_name, context_filter
                    ) or None

                # Add document ID filter if we found relevant documents
                if relevant_doc_ids:
                    doc_id_list = ", ".join(
                        [f'"{doc_id}"' for doc_id in relevant_doc_ids]
                    )
                    knowledge_topic_filter = (
                        f"{knowledge_topic_filter} AND document_id IN [{doc_id_list}]"
                    )

                return self.hybrid_search(
                    collection_name=collection_name,
                    queries=queries,
                    dense_model=dense_model,
                    organization_schema=organization_schema,
                    result_limit=result_limit,
                    filter_expr=knowledge_topic_filter,
                    score_cutoff=score_cutoff,
                )

            else:
                raise ValueError(
                    f"search_scope must be one of {valid_scopes}, got '{search_scope}'"
                )

        except Exception as e:
            logger.error(f"Error in knowledge_search: {e}")
            raise


# Example usage
if __name__ == "__main__":
    import asyncio

    # Hardcoded values
    collection_name = "annual_reports_jb29"
    search_queries = ["Segment wise revenue of Apple", "Apple's total revenue in 2024"]
    search_scope = "document_content"

    # Create Milvus search instance
    milvus_search = MilvusSearch()

    # Get embedding model for the collection (example - in real usage, get from collection config)
    dense_model = "Alibaba-NLP/gte-multilingual-base"  # Example model
    organization_schema = "public"  # Example schema

    print(f"\nSearching collection: {collection_name} with queries: {search_queries}\n")
    documents = asyncio.run(
        milvus_search.knowledge_search(
            collection_name=collection_name,
            queries=search_queries,
            dense_model=dense_model,
            organization_schema=organization_schema,
            search_scope=search_scope,
        )
    )
    print(f"\nNumber of documents in final results: {len(documents)}\n")
    for i, doc in enumerate(documents):
        print(
            f"(\n\n===== Document {i+1} ===== \n"
            f"Score: {doc.metadata.get('distance'):.4f}\n"
            f"Content: \n{doc.page_content}\n"
            f"Metadata: \n{doc.metadata}\n"
        )
