# Custom libraries
from integrations.office_365.outlook import Outlook
from logger import configure_logging
from schemas.user_profile_schema import (
    UserProfileEdit,
    UserPasswordUpdate,
    Office365UserProfileDetail,
)
from schemas.user_schema import Message, UserDetail
from utils.authentication import Authentication
from utils.schema_utils import get_schema_db, get_session_for_role

# Database modules
from repository.user_repository import UserRepository
from sqlalchemy.orm import Session

# Default libraries
from uuid import UUID
import os

# Installed libraries
from dotenv import load_dotenv
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt import decode


load_dotenv()

logger = configure_logging(logger_name=__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")

user_profile_router = APIRouter(tags=["User Profile"])


@user_profile_router.get(
    "/profile/office365", response_model=Office365UserProfileDetail
)
def get_office365_user_profile(
    db: Session = Depends(get_schema_db), token: str = Depends(oauth2_scheme)
):
    """
    Retrieve Office365 user profile data based on token.
    """
    try:
        # Decode JWT token and extract information from decoded payload
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_uuid = decoded_token["sub"]
        user_role = decoded_token["user_role"]

        # Get appropriate session based on user role
        with get_session_for_role(user_role, db) as session:
            user_repository = UserRepository(session)
            user = user_repository.get_user_by_id(UUID(user_uuid))

            if not user:
                raise HTTPException(
                    status_code=404, detail="User not found. Please check and retry."
                )

            outlook = Outlook(session)
            office365_profile = outlook.get_user_profile(user.email)

            if not office365_profile:
                raise HTTPException(
                    status_code=404,
                    detail="Office365 User not found. Please check and retry.",
                )

            # Map Office365 profile fields to schema
            office365_user_profile = {
                "id": office365_profile.get("id"),
                "business_phones": office365_profile.get("businessPhones"),
                "display_name": office365_profile.get("displayName"),
                "given_name": office365_profile.get("givenName"),
                "surname": office365_profile.get("surname"),
                "user_principal_name": office365_profile.get("userPrincipalName"),
                "job_title": office365_profile.get("jobTitle"),
                "mail": office365_profile.get("mail"),
                "mobile_phone": office365_profile.get("mobilePhone"),
                "office_location": office365_profile.get("officeLocation"),
                "preferred_language": office365_profile.get("preferredLanguage"),
                "company_name": office365_profile.get("companyName"),
                "department": office365_profile.get("department"),
                "usage_location": office365_profile.get("usageLocation"),
                "street_address": office365_profile.get("streetAddress"),
                "city": office365_profile.get("city"),
                "state": office365_profile.get("state"),
                "country": office365_profile.get("country"),
                "postal_code": office365_profile.get("postalCode"),
            }

            return Office365UserProfileDetail(**office365_user_profile)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_profile_router.get("/profile", response_model=UserDetail)
def get_user_profile(
    db: Session = Depends(get_schema_db), token: str = Depends(oauth2_scheme)
):
    """
    Gets user profile data based on token.
    """
    try:
        # Decode JWT token and extract information from decoded payload
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_uuid = decoded_token["sub"]
        user_role = decoded_token["user_role"]

        # Get appropriate session based on user role
        with get_session_for_role(user_role, db) as session:
            user_repository = UserRepository(session)
            user = user_repository.get_user_by_id(UUID(user_uuid), user_details=True)

            if user is not None:
                return UserDetail.model_validate(user)
            else:
                raise HTTPException(
                    status_code=404,
                    detail="User not found. Please check and retry.",
                )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_profile_router.patch("/profile", response_model=UserDetail)
def edit_user_profile(
    db: Session = Depends(get_schema_db),
    user_profile_data: UserProfileEdit = Body(...),
    token: str = Depends(oauth2_scheme),
):
    """
    Edits user profile data based on token.
    """
    try:
        # Decode JWT token and extract information from decoded payload
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_uuid = decoded_token["sub"]
        user_role = decoded_token["user_role"]

        # Get appropriate session based on user role
        with get_session_for_role(user_role, db) as session:
            user_repository = UserRepository(session)

            update_data = {
                k: v for k, v in user_profile_data.model_dump().items() if v is not None
            }
            update_data["user_uuid"] = UUID(user_uuid)

            result_user = user_repository.update_user(update_data)

            if result_user:
                logger.info(f"Profile edited successfully for user: {user_uuid}")
                return UserDetail.model_validate(result_user)
            else:
                raise HTTPException(
                    status_code=404,
                    detail="Failed to edit Profile. Please check and retry.",
                )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_profile_router.put("/profile/password", response_model=Message)
def update_user_password(
    db: Session = Depends(get_schema_db),
    password_data: UserPasswordUpdate = Body(...),
    token: str = Depends(oauth2_scheme),
):
    """
    Updates user password based on token.
    """
    try:
        # Decode JWT token and extract information from decoded payload
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_uuid = decoded_token["sub"]
        user_role = decoded_token["user_role"]

        # Get appropriate session based on user role
        with get_session_for_role(user_role, db) as session:
            user_repository = UserRepository(session)
            user = user_repository.get_user_by_id(UUID(user_uuid))

            if user:
                if Authentication().verify_password(
                    password_data.current_password, user.salt, user.hashed_password
                ):
                    update_data = {
                        "user_uuid": UUID(user_uuid),
                        "password": password_data.new_password,
                    }
                    user_repository.update_user(update_data)

                    logger.info(f"Password updated successfully for user: {user_uuid}")
                    return {"message": "Password updated successfully."}
                else:
                    logger.error(f"Incorrect current password : {user.id}")
                    raise HTTPException(
                        status_code=422,
                        detail="Incorrect current password.",
                    )
            else:
                logger.error(f"User not found : {user_uuid}")
                raise HTTPException(
                    status_code=404,
                    detail="User not found.",
                )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
