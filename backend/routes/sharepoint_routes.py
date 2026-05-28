# Custom libraries
from logger import configure_logging
from integrations.office_365.sharepoint import Sharepoint
from schemas.sharepoint_schema import (
    DataFileResponse,
    SharepointBulkDownload,
    SharepointBulkDownloadResponse,
)
from utils.schema_utils import get_schema_db

# Database modules
from sqlalchemy.orm import Session

# Default libraries
from typing import List, Union
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, HTTPException, Depends
import requests


logger = configure_logging(__name__)

sharepoint_router = APIRouter(prefix="/sharepoint", tags=["SharePoint"])


@sharepoint_router.get("/sites", response_model=List[dict], deprecated=True)
def list_sites(db: Session = Depends(get_schema_db)):
    """List all SharePoint sites for the organization."""
    try:
        sharepoint = Sharepoint(db)
        return sharepoint.list_all_sites()
    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error listing SharePoint sites: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@sharepoint_router.get("/sites/{site_id}/objects", response_model=List[dict])
def list_objects_in_site(
    site_id: Union[UUID, str], db: Session = Depends(get_schema_db)
):
    """List all objects in a specific SharePoint site."""
    try:
        sharepoint = Sharepoint(db)
        return sharepoint.list_objects_in_site(site_id)
    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except requests.exceptions.HTTPError as http_error:
        logger.error(f"Error listing files for site {site_id}: {http_error}")
        raise HTTPException(
            status_code=http_error.response.status_code, detail=str(http_error)
        )
    except Exception as e:
        logger.error(f"Error listing files for site {site_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@sharepoint_router.get(
    "/sites/{site_uuid}/{folder_id}/objects", response_model=List[dict]
)
def list_objects_in_folder(
    site_uuid: Union[UUID, str],
    folder_id: str,
    db: Session = Depends(get_schema_db),
):
    """List all objects in a folder in a specific SharePoint site."""
    try:
        sharepoint = Sharepoint(db)
        return sharepoint.list_objects_in_folder(site_uuid, folder_id)
    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except requests.exceptions.HTTPError as http_error:
        logger.error(f"Error listing files for site {site_uuid}: {http_error}")
        raise HTTPException(
            status_code=http_error.response.status_code, detail=str(http_error)
        )
    except Exception as e:
        logger.error(f"Error listing files for site {site_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@sharepoint_router.post("/files/import", response_model=SharepointBulkDownloadResponse)
def bulk_download_files(
    sharepoint_downloads: SharepointBulkDownload = Body(...),
    db: Session = Depends(get_schema_db),
):
    """Initiate bulk download of files from SharePoint sites."""
    try:
        sharepoint = Sharepoint(db)

        sharepoint_downloads = (sharepoint_downloads.sharepoint_files or []) + (
            sharepoint_downloads.sharepoint_folders
            or [] + (sharepoint_downloads.sharepoint_sites or [])
        )

        downloaded_data_files = sharepoint.process_downloads(sharepoint_downloads)

        if downloaded_data_files:
            return SharepointBulkDownloadResponse(
                successful_downloads=DataFileResponse(
                    data_files=downloaded_data_files["download_successes"],
                    total=len(downloaded_data_files["download_successes"]),
                ),
                unsuccessful_downloads=downloaded_data_files["download_failures"],
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to download files from Sharepoint.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error initiating bulk download: {e}")
        raise HTTPException(status_code=500, detail=str(e))
