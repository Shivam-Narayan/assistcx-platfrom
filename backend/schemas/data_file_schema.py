# Default libraries
from datetime import datetime
from typing import Any, Dict, List, Optional
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints


class DataFileStatus(BaseModel):
    status: str
    timestamp: str


class DataFileBase(BaseModel):
    name: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore
    size: Optional[int] = None
    mime_type: Optional[str] = None
    md5_hash: Optional[str] = None
    source_type: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] = None  # type: ignore
    source_metadata: Optional[Dict] = None
    file_metadata: Optional[Dict] = None
    acl_metadata: Optional[Dict] = None
    status: Optional[List[DataFileStatus]] = None
    last_synced: Optional[datetime] = None


class DataFileDetail(DataFileBase):
    id: UUID
    collection_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class DataFileResponse(BaseModel):
    data_files: List[DataFileDetail]
    total: int


class DataFileUpload(BaseModel):
    successful_uploads: DataFileResponse
    unsuccessful_uploads: Optional[List[Dict]] = []


class DataFileMove(BaseModel):
    collection_id: UUID


class DataFileRename(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]


class DataFileDownload(BaseModel):
    mime_type: str
    file_name: str
    content: str


class DataFileBulkAction(BaseModel):
    data_file_ids: List[UUID]


class KnowledgeItem(BaseModel):
    id: str
    document_id: str
    record_type: str
    knowledge_topic: Optional[str] = None
    content: str
    created_at: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeResponse(BaseModel):
    knowledge: List[KnowledgeItem]
    total: int


class ChunksAndContentResponse(BaseModel):
    chunks: Optional[List[Dict[str, Any]]] = None
    extracted_content: Optional[str] = None
