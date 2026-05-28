# Custom libraries
from schemas.data_file_schema import DataFileDetail

# Default libraries
from datetime import datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, field_validator

AvailabilityStatus = Literal["PUBLISHED", "UNLISTED"]


class CollectionConfig(BaseModel):
    """Configuration for creating a new collection. embedding_model is immutable after creation.
    data_store is injected server-side (same as private_data_collection) and not accepted from client."""

    advanced_knowledge_extraction: bool = False
    connected_sharepoint_sites: Optional[List[Dict]] = []
    embedding_model: Optional[str] = "Alibaba-NLP/gte-multilingual-base"


class CollectionConfigUpdate(BaseModel):
    """Configuration for updating a collection. embedding_model cannot be changed.
    data_store is not updatable via API."""

    advanced_knowledge_extraction: Optional[bool] = None
    connected_sharepoint_sites: Optional[List[Dict]] = None
    # embedding_model is intentionally excluded - it cannot be changed after creation


class DataCollectionBase(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = "folder"
    is_root: Optional[bool] = False
    parent_id: Optional[UUID] = None
    status: Optional[str] = "ACTIVE"
    collection_config: Optional[CollectionConfig] = None
    availability: Optional[AvailabilityStatus] = "UNLISTED"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        # Handle None case for optional fields in child classes
        if v is None:
            return v

        if not v:
            raise ValueError("Name cannot be empty")

        # Check max length
        if len(v) > 128:
            raise ValueError("Name cannot exceed 128 characters")

        # Check if starts with a letter
        if not v[0].isalpha():
            raise ValueError("Name must start with a letter")

        # Check if contains only letters, numbers, and underscores
        if not all(c.isalnum() or c in ("_", " ") for c in v):
            raise ValueError("Name can only contain letters, numbers, and underscores")

        return v


class DataCollectionCreate(DataCollectionBase):
    collection_config: CollectionConfig


class DataCollectionUpdate(BaseModel):
    """Schema for updating a collection. Uses CollectionConfigUpdate which excludes embedding_model."""

    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    status: Optional[str] = None
    owner_id: Optional[UUID] = None
    collection_config: Optional[CollectionConfigUpdate] = None
    availability: Optional[AvailabilityStatus] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if v is None:
            return v
        if not v:
            raise ValueError("Name cannot be empty")
        if len(v) > 128:
            raise ValueError("Name cannot exceed 128 characters")
        if not v[0].isalpha():
            raise ValueError("Name must start with a letter")
        if not all(c.isalnum() or c in ("_", " ") for c in v):
            raise ValueError("Name can only contain letters, numbers, and underscores")
        return v


class DataCollectionDetail(DataCollectionBase):
    id: UUID
    owner_id: Optional[UUID] = None
    index_name: str
    file_count: Optional[int] = None
    total_size: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class DataCollectionResponse(BaseModel):
    data_collections: List[DataCollectionDetail]
    total: int


class DataCollectionDataFileResponse(BaseModel):
    data_collections: List[DataCollectionDetail]
    data_files: List[DataFileDetail]
    total: int

    @classmethod
    def from_data_collections_and_data_files(
        cls,
        data_collections: List[DataCollectionDetail],
        data_files: List[DataFileDetail],
        total: int,
    ):
        # Filter out ROOT data folder
        filtered_data_collections = [
            data_collection
            for data_collection in data_collections
            if data_collection.name != "ROOT" and not data_collection.is_root
        ]
        # Adjust total if ROOT collection exists
        total -= any(
            data_collection.name == "ROOT" or data_collection.is_root
            for data_collection in data_collections
        )
        return cls(
            data_collections=filtered_data_collections,
            data_files=data_files,
            total=total,
        )


class DataCollectionSiteUpdate(BaseModel):
    site_url: str
    action: Literal["connect", "disconnect"]
