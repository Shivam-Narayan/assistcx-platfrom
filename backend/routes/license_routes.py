# Custom libraries
from logger import configure_logging
from utils.license_utils import License
from utils.schema_utils import get_schema_db

# Database modules
from schemas.user_schema import Message

# Default libraries
import os

# Installed libraries
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Depends, Request
from requests.exceptions import RequestException
from sqlalchemy.orm import Session
import requests

# Load environment variables
load_dotenv()

# Configure logging
logger = configure_logging(logger_name=__name__)

# Initialize the router
lisence_router = APIRouter(tags=["License"])


@lisence_router.get("/license/{tenant_code}", response_model=Message)
def get_license_token(tenant_code: str = None, db: Session = Depends(get_schema_db)):
    """
    Calls an external API endpoint to get usage data and stores the returned string in Redis.
    """
    try:
        license_instance = License(db=db)
        if license_instance.get_license_token(tenant_code=tenant_code):
            logger.info("License stored in Redis successfully")
            return {"message": "License created successfully."}
        else:
            logger.error("Unknown error at license creation")

    except requests.exceptions.RequestException as e:
        # Log the error and raise HTTPException
        logger.error(f"Error in fetching usage data: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch usage data")

    except Exception as e:
        # Log any other exceptions and raise HTTPException
        logger.error(f"An error occurred: {e}")
        raise HTTPException(
            status_code=500, detail="An error occurred while storing usage token"
        )
