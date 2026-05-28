# Custom libraries
from __init__ import __version__
from logger import configure_logging
from schemas.asset_schema import Changelog, Version

# Default libraries
import os

# Installed libraries
from fastapi import APIRouter, HTTPException


logger = configure_logging(__name__)

asset_router = APIRouter(tags=["Assets"])


@asset_router.get("/changelog", response_model=Changelog)
def get_changelog():
    """
    Retrieves the application changelog from the changelog.md file.
    """
    try:
        asset_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "assets", "changelog.md"
        )
        with open(asset_path, "r", encoding="utf-8") as md_file:
            content = md_file.read()

        return {"content": content}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@asset_router.get("/version", response_model=Version)
def get_version():
    """
    Retrieves the current application version.
    """
    try:
        return {"version": __version__}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
