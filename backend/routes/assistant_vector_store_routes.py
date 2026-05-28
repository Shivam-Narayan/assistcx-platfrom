"""
Vector Store and Knowledge Config routes.

Sections:
  1. Vector Store Management (from milvus_routes.py)
  2. Knowledge Config (from embedding_routes.py)
"""

from configs.embedding_models import EMBEDDING_MODELS
from knowledge.milvus_search import MilvusSearch
from knowledge.milvus_store import MilvusStore
from knowledge.utils import get_embedding_model_for_collection
from logger import configure_logging
from schemas.embedding_schema import EmbeddingModelsResponse
from schemas.milvus_schema import (
    DocumentResult,
    KnowledgeSearchResponse,
    KnowledgeSearchRequest,
    HybridSearchRequest,
    HybridSearchResponse,
    MilvusCollectionResponse,
    MilvusCollectionsDeleteResponse,
    DocumentQueryRequest,
    DocumentQueryResponse,
)

from typing import List
import os

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jwt import decode


logger = configure_logging(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")


def get_org_schema_from_token(token: str) -> str:
    """Extract org_schema from JWT token."""
    try:
        decoded = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        return decoded.get("org_id", "public")
    except Exception:
        return "public"


async def get_milvus_store() -> MilvusStore:
    """Get MilvusStore instance."""
    try:
        return MilvusStore()
    except Exception as e:
        logger.error(f"Failed to initialize MilvusStore: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize vector store",
        )


# =============================================================================
# SECTION 1: VECTOR STORE MANAGEMENT  (tag: "Vector Store")
# =============================================================================

vector_store_router = APIRouter(tags=["Vector Store"])


@vector_store_router.get("/assistant/vector-store/collections")
@vector_store_router.get("/milvus-collections", deprecated=True, include_in_schema=False)
async def list_collections(
    milvus_store: MilvusStore = Depends(get_milvus_store), response_model=List[str]
):
    """Get list of all collection names in Milvus."""
    try:
        return milvus_store.list_collections()
    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve collections: {str(e)}",
        )


@vector_store_router.get(
    "/assistant/vector-store/collections/{collection_name}/stats",
    response_model=MilvusCollectionResponse,
)
@vector_store_router.get(
    "/milvus-collections/{collection_name}/stats",
    response_model=MilvusCollectionResponse,
    deprecated=True,
    include_in_schema=False,
)
async def get_collection_stats(
    collection_name: str,
    milvus_store: MilvusStore = Depends(get_milvus_store),
) -> MilvusCollectionResponse:
    """Get statistics for a specific collection."""
    try:
        if not milvus_store.client.has_collection(collection_name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Collection '{collection_name}' not found",
            )

        with milvus_store.collection_loader(collection_name):
            all_records = milvus_store.client.query(
                collection_name=collection_name,
                filter="",
                output_fields=["id", "record_type", "document_id"],
                limit=16384,
            )

        document_contexts = 0
        document_chunks = 0
        document_knowledge = 0
        unique_files = set()

        for record in all_records:
            document_id = record.get("document_id", "")
            record_type = record.get("record_type", "")

            if document_id:
                unique_files.add(document_id)

            if record_type == "document_context":
                document_contexts += 1
            elif record_type == "document_chunk":
                document_chunks += 1
            elif record_type == "document_knowledge":
                document_knowledge += 1

        return MilvusCollectionResponse(
            collection_name=collection_name,
            total_documents=len(unique_files),
            total_records=len(all_records),
            document_contexts=document_contexts,
            document_chunks=document_chunks,
            document_knowledge=document_knowledge,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get collection stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve collection statistics: {str(e)}",
        )


@vector_store_router.delete(
    "/assistant/vector-store/collections", response_model=MilvusCollectionsDeleteResponse
)
@vector_store_router.delete(
    "/milvus-collections", response_model=MilvusCollectionsDeleteResponse,
    deprecated=True, include_in_schema=False,
)
async def delete_collections(
    collection_names: List[str] = Body(...),
    action: str = Query("delete", description="Action: 'delete' or 'clear'"),
    milvus_store: MilvusStore = Depends(get_milvus_store),
) -> MilvusCollectionsDeleteResponse:
    """Delete or clear multiple collections from Milvus.

    Args:
        collection_names: List of collection names.
        action: 'delete' removes collections entirely, 'clear' removes all records but keeps collections.
    """
    if action not in ("delete", "clear"):
        raise HTTPException(status_code=400, detail="action must be 'delete' or 'clear'")

    successful = []
    failed = []

    for collection_name in collection_names:
        try:
            if action == "delete":
                if milvus_store.delete_collection(collection_name):
                    successful.append(collection_name)
                else:
                    failed.append(collection_name)
            else:  # clear
                success = milvus_store.delete_documents_with_filter(
                    collection_name=collection_name,
                    additional_filter="id != ''",
                )
                if success:
                    successful.append(collection_name)
                else:
                    failed.append(collection_name)
        except Exception as e:
            failed.append(collection_name)
            logger.error(f"Failed to {action} collection {collection_name}: {e}")

    return MilvusCollectionsDeleteResponse(
        successful=successful, failed=failed, total_successful=len(successful)
    )


# Deprecated alias for clear endpoint — routes to the merged handler with action=clear
@vector_store_router.delete(
    "/milvus-collections/clear",
    response_model=MilvusCollectionsDeleteResponse,
    deprecated=True,
    include_in_schema=False,
)
async def clear_collections_deprecated(
    collection_names: List[str] = Body(...),
    milvus_store: MilvusStore = Depends(get_milvus_store),
) -> MilvusCollectionsDeleteResponse:
    """Deprecated: Use DELETE /assistant/vector-store/collections?action=clear instead."""
    successful = []
    failed = []

    for collection_name in collection_names:
        try:
            success = milvus_store.delete_documents_with_filter(
                collection_name=collection_name,
                additional_filter="id != ''",
            )
            if success:
                successful.append(collection_name)
            else:
                failed.append(collection_name)
        except Exception as e:
            failed.append(collection_name)
            logger.error(f"Failed to clear collection {collection_name}: {e}")

    return MilvusCollectionsDeleteResponse(
        successful=successful, failed=failed, total_successful=len(successful)
    )


@vector_store_router.post("/assistant/vector-store/search", response_model=KnowledgeSearchResponse)
async def knowledge_search(
    request: KnowledgeSearchRequest,
    token: str = Depends(oauth2_scheme),
) -> KnowledgeSearchResponse:
    """Perform knowledge search using dense and sparse embeddings."""
    try:
        org_schema = get_org_schema_from_token(token)
        embedding_model = get_embedding_model_for_collection(org_schema, request.collection_name)
        logger.info(f"Using embedding model {embedding_model} for collection {request.collection_name}")
        milvus_search = MilvusSearch()

        collections = milvus_search.client.list_collections()
        if request.collection_name not in collections:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Collection '{request.collection_name}' not found. "
                f"Available collections: {collections}",
            )

        documents = await milvus_search.knowledge_search(
            collection_name=request.collection_name,
            queries=request.query,
            dense_model=embedding_model,
            organization_schema=org_schema,
            result_limit=request.result_limit,
            search_scope=request.search_scope,
            document_limit=request.document_limit,
            score_cutoff=request.score_cutoff,
        )

        results = [
            DocumentResult(
                id=doc.metadata.get("id", ""),
                content=doc.page_content,
                distance=doc.metadata.get("distance", 0.0),
                file_uuid=doc.metadata.get("file_uuid"),
                created_at=doc.metadata.get("created_at"),
                metadata={
                    k: v
                    for k, v in doc.metadata.items()
                    if k not in ["id", "distance", "document_id", "created_at"]
                },
            )
            for doc in documents
        ]

        return KnowledgeSearchResponse(
            query=request.query,
            collection_name=request.collection_name,
            total_results=len(results),
            results=results,
            search_scope=request.search_scope,
            document_limit=request.document_limit,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Knowledge search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Knowledge search operation failed: {str(e)}",
        )


@vector_store_router.post("/assistant/vector-store/hybrid-search", response_model=HybridSearchResponse, deprecated=True)
async def hybrid_search(
    request: HybridSearchRequest,
    token: str = Depends(oauth2_scheme),
) -> HybridSearchResponse:
    """Deprecated: Use /assistant/vector-store/search instead.

    Perform hybrid search using dense and sparse embeddings.
    """
    try:
        org_schema = get_org_schema_from_token(token)
        embedding_model = get_embedding_model_for_collection(org_schema, request.collection_name)
        logger.info(f"Using embedding model {embedding_model} for collection {request.collection_name}")
        milvus_search = MilvusSearch()

        collections = milvus_search.client.list_collections()
        if request.collection_name not in collections:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Collection '{request.collection_name}' not found. "
                f"Available collections: {collections}",
            )

        documents = milvus_search.hybrid_search(
            collection_name=request.collection_name,
            queries=request.query,
            dense_model=embedding_model,
            organization_schema=org_schema,
            result_limit=request.result_limit,
            filter_expr=request.filter_expr,
            score_cutoff=request.score_cutoff,
        )

        results = [
            DocumentResult(
                id=doc.metadata.get("id", ""),
                content=doc.page_content,
                distance=doc.metadata.get("distance", 0.0),
                file_uuid=doc.metadata.get("file_uuid"),
                created_at=doc.metadata.get("created_at"),
                metadata=doc.metadata,
            )
            for doc in documents
        ]

        return HybridSearchResponse(
            query=request.query,
            collection_name=request.collection_name,
            total_results=len(results),
            results=results,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Hybrid search operation failed: {str(e)}",
        )


@vector_store_router.post("/assistant/vector-store/documents/query", response_model=DocumentQueryResponse)
async def document_query(
    request: DocumentQueryRequest,
    milvus_store: MilvusStore = Depends(get_milvus_store),
) -> DocumentQueryResponse:
    """Query documents by flexible criteria (file_uuid, record_type, or custom filter)."""
    try:
        collections = milvus_store.list_collections()
        if request.collection_name not in collections:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Collection '{request.collection_name}' not found. "
                f"Available collections: {collections}",
            )

        documents = milvus_store.fetch_documents_with_filter(
            collection_name=request.collection_name,
            file_uuid=request.file_uuid,
            record_type=request.record_type,
            filter_expr=request.filter_expr,
            result_limit=request.result_limit,
        )

        results = [
            DocumentResult(
                id=doc.metadata.get("id", ""),
                content=doc.page_content,
                record_type=doc.metadata.get("record_type", ""),
                file_uuid=doc.metadata.get("file_uuid"),
                created_at=doc.metadata.get("created_at"),
                metadata={
                    k: v
                    for k, v in doc.metadata.items()
                    if k not in ["id", "record_type", "document_id", "created_at"]
                },
            )
            for doc in documents
        ]

        return DocumentQueryResponse(
            collection_name=request.collection_name,
            total_results=len(results),
            results=results,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document query operation failed: {str(e)}",
        )


# =============================================================================
# SECTION 2: KNOWLEDGE CONFIG  (tag: "Knowledge")
# =============================================================================

knowledge_router = APIRouter(tags=["Knowledge"])


@knowledge_router.get("/embedding-models", response_model=EmbeddingModelsResponse)
def get_embedding_models():
    """Retrieves available embedding models from EMBEDDING_MODELS config."""
    try:
        return EmbeddingModelsResponse(
            embedding_models=EMBEDDING_MODELS,
            total=len(EMBEDDING_MODELS),
        )
    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
