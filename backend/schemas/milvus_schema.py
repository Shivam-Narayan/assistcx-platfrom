# Default libraries
from typing import Any, Dict, List, Optional, Union

# Installed libraries
from pydantic import BaseModel, Field, field_validator


class DocumentResult(BaseModel):
    """Single document result from search and query operations."""

    id: str = Field(description="Document ID")
    content: str = Field(description="Document content/text")
    distance: Optional[float] = Field(None, description="Similarity distance score")
    file_uuid: Optional[str] = Field(None, description="Source file UUID")
    record_type: Optional[str] = Field(
        None, description="Type of record (e.g., document_chunk)"
    )
    created_at: Optional[int] = Field(None, description="Document creation timestamp")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class SearchRequestBase(BaseModel):
    """Base class for all search requests with common validation."""

    query: Union[str, List[str]] = Field(
        ...,
        description="Single query string or list of query strings",
    )
    collection_name: str = Field(
        ...,
        description="Name of the collection to search in",
    )
    result_limit: Optional[int] = Field(
        default=50, ge=1, le=100, description="Number of results to return (1-100)"
    )
    score_cutoff: Optional[float] = Field(
        default=0.1, ge=0.0, le=1.0, description="Score cutoff for results (0.0-1.0)"
    )

    @field_validator("query")
    def validate_query(cls, v):
        if isinstance(v, str):
            if not v.strip():
                raise ValueError("Query string cannot be empty")
            if len(v) > 1000:
                raise ValueError("Query string too long (max 1000 characters)")
        elif isinstance(v, list):
            if not v:
                raise ValueError("Query list cannot be empty")
            if len(v) > 10:
                raise ValueError("Too many queries (max 10)")
            for query in v:
                if not isinstance(query, str) or not query.strip():
                    raise ValueError("All queries must be non-empty strings")
        return v

    @field_validator("collection_name")
    def validate_collection_name(cls, v):
        if not v.strip():
            raise ValueError("Collection name cannot be empty")
        return v.strip()


class SearchResponseBase(BaseModel):
    """Base class for all search responses."""

    query: Union[str, List[str]] = Field(description="Original query/queries")
    collection_name: str = Field(description="Collection searched")
    total_results: int = Field(description="Total number of results returned")
    results: List[DocumentResult] = Field(description="Search results")


class KnowledgeSearchRequest(SearchRequestBase):
    """Request model for knowledge search."""

    search_scope: Optional[str] = Field(
        default="contextual",
        description="Search strategy: 'global', 'exhaustive', or 'contextual' (default)",
        examples=["global", "exhaustive", "contextual"],
    )
    document_limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Number of documents to retrieve in the first stage of contextual search",
    )


class KnowledgeSearchResponse(SearchResponseBase):
    """Response model for knowledge search."""

    search_scope: Optional[str] = Field(
        default=None,
        description="Search strategy used: 'global', 'exhaustive', or 'contextual'",
    )
    document_limit: Optional[int] = Field(
        default=None,
        description="Number of documents retrieved in the first stage (contextual search only)",
    )


class HybridSearchRequest(SearchRequestBase):
    """Request model for hybrid search with dense + sparse vectors."""

    filter_expr: Optional[str] = Field(
        None,
        description="Optional Milvus filter expression",
        example='record_type == "document_chunk"',
    )


class HybridSearchResponse(SearchResponseBase):
    """Response model for hybrid search."""

    pass


class DocumentQueryRequest(BaseModel):
    """Request model for document query."""

    collection_name: str = Field(
        ...,
        description="Name of the collection to query in",
    )
    file_uuid: Optional[str] = Field(None, description="File UUID to filter by")
    record_type: Optional[str] = Field(
        None, description="Record type to filter by", example="document_chunk"
    )
    filter_expr: Optional[str] = Field(
        None,
        description="Filter expression to filter by",
        example='document_id == "doc123"',
    )
    result_limit: Optional[int] = Field(
        default=50, ge=1, le=100, description="Number of results to return (1-100)"
    )

    @field_validator("collection_name")
    def validate_collection_name(cls, v):
        if not v.strip():
            raise ValueError("Collection name cannot be empty")
        return v.strip()


class DocumentQueryResponse(BaseModel):
    """Response model for document query response."""

    collection_name: str = Field(description="Collection queired")
    total_results: int = Field(description="Total number of results returned")
    results: List[DocumentResult] = Field(description="Query results")


class MilvusCollectionResponse(BaseModel):
    """Response model for collection statistics."""

    collection_name: str
    total_documents: int
    total_records: int
    document_contexts: int
    document_chunks: int
    document_knowledge: int


class MilvusCollectionsDeleteResponse(BaseModel):
    """Response model for delete collections operation."""

    successful: List[str]
    failed: List[str]
    total_successful: int
