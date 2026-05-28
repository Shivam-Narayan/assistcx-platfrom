# Custom libraries
from schemas.data_file_schema import DataFileResponse

# Default libraries
from typing import Optional, Dict, List

# Installed libraries
from pydantic import BaseModel


class SharepointFile(BaseModel):
    file_id: str
    site_id: str
    collection_id: str


class SharepointFolder(BaseModel):
    folder_id: str
    site_id: str
    collection_id: str


class SharepointSite(BaseModel):
    site_id: str
    collection_id: str


class SharepointBulkDownload(BaseModel):
    sharepoint_files: Optional[List[SharepointFile]] = []
    sharepoint_folders: Optional[List[SharepointFolder]] = []
    sharepoint_sites: Optional[List[SharepointSite]] = []


class SharepointBulkDownloadResponse(BaseModel):
    successful_downloads: DataFileResponse
    unsuccessful_downloads: Optional[List[Dict]] = []
