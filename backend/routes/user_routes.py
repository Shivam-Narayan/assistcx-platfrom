# Custom libraries
from logger import configure_logging
from schemas.user_schema import (
    Message,
    UserAuthentication,
    UserCreate,
    UserDetail,
    UserLogin,
    UserResponse,
    UserUpdate,
)
from utils.authentication import Authentication
from utils.common_utils import parse_identifier
from utils.schema_utils import (
    get_schema_db,
    get_current_schema,
    set_schema,
)

# Database modules
from repository.authentication_repository import AuthenticationRepository
from repository.user_repository import UserRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional, Union
from uuid import UUID

# Installed libraries
from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Path,
    Query,
    Request,
)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm


load_dotenv()

logger = configure_logging(logger_name=__name__)

authentication = Authentication()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")

user_router = APIRouter(tags=["Users"])


@user_router.get("/users", response_model=UserResponse)
def get_users(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves user information based on specified criteria.
    """
    try:
        user_repository = UserRepository(db)

        filters = request.state.filters

        # Fetch all users
        users, total = user_repository.get_all_users(
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return UserResponse(users=users, total=total)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_router.get("/users/search", response_model=UserResponse)
def search_users(
    keyword: str = Query(None, description="Search keyword"),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Searches and retrieves user information based on specified keyword.
    """
    try:
        user_repository = UserRepository(db)

        filters = request.state.filters

        # Search users
        if keyword:
            users, total = user_repository.search_users(
                keyword=keyword,
                filters=filters,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            if users:
                return UserResponse(users=users, total=total)
            else:
                return UserResponse(users=[], total=0)
        else:
            raise HTTPException(
                status_code=400,
                detail="No keyword provided.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_router.get("/users/{user_identifier}", response_model=UserResponse)
def get_user(
    user_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves user information based on its user_identifier.
    """
    try:
        identifier = parse_identifier(user_identifier)
        user = UserRepository(db).get_user_by_id(identifier, user_details=True)

        # ROOT-only + self-only fallback:
        # When ROOT switches org, its UUID won't exist in tenant schema; fetch ROOT from public.
        decoded = getattr(request.state, "decoded_token", None) if request else None
        is_root = bool(decoded and decoded.get("user_role") == "ROOT")
        is_self = bool(decoded and str(decoded.get("sub")) == str(identifier))
        if user is None and is_root and is_self:
            with set_schema("public") as public_db:
                user = UserRepository(public_db).get_user_by_id(
                    identifier, user_details=True
                )

        if user is None:
            raise HTTPException(
                status_code=404,
                detail="User not found. Please check and retry.",
            )

        return UserResponse(users=[user], total=1)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_router.post("/users", response_model=UserDetail)
def create_user(
    user_data: UserCreate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Creates a new user.
    """
    try:
        user_repository = UserRepository(db)

        result_user = user_repository.create_user(user_data.model_dump())

        if result_user:
            logger.info(f"User created successfully: {result_user.id}")
            return UserDetail.model_validate(result_user)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create User.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_router.patch("/users/{user_uuid}", response_model=UserDetail)
def update_user(
    user_uuid: UUID,
    user_data: UserUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Updates an existing user based on its user_uuid.
    """
    try:
        user_repository = UserRepository(db)

        update_data = {k: v for k, v in user_data.model_dump().items() if v is not None}

        # Append user_uuid to update_data
        update_data["user_uuid"] = user_uuid

        result_user = user_repository.update_user(update_data)

        if result_user:
            logger.info(f"User updated successfully: {result_user.id}")
            return UserDetail.model_validate(result_user)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update User. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_router.post("/users/{user_uuid}/{action}", response_model=Message)
def activate_or_deactivate_user(
    user_uuid: UUID,
    action: str = Path(
        ..., description="Action to perform: 'activate' or 'deactivate'"
    ),
    db: Session = Depends(get_schema_db),
):
    """
    Enables or disables a user account by setting the account_status to 'active' or 'inactive'
    """
    try:
        if action not in ["activate", "deactivate"]:
            raise HTTPException(status_code=400, detail="Not found.")

        status = "active" if action == "activate" else "inactive"

        user_repository = UserRepository(db)

        # Validate if the user exists
        existing_user = user_repository.get_user_by_id(user_uuid)

        if not existing_user:
            raise HTTPException(
                status_code=404,
                detail="User not found. Please check and retry.",
            )

        # Update user account_status to 'active'
        result_user = user_repository.update_user(
            {"user_uuid": user_uuid, "account_status": status}
        )

        if result_user:
            # Delete the authentication record for the user
            authentication_repository = AuthenticationRepository(db)

            authentication_repository.delete_authentication(user_uuid)

            return {"message": f"User is now {status}."}
        else:
            raise HTTPException(
                status_code=422,
                detail="Failed to enable User.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_router.delete("/users/{user_uuid}", response_model=Message)
def delete_user(
    user_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Deletes an existing user based on its UUID. Only allowed for root user.
    """
    try:
        user_repository = UserRepository(db)

        deleted_user = user_repository.delete_user_by_id(user_uuid)

        if deleted_user:
            logger.info(f"User deleted successfully: {user_uuid}")
            return {"message": "User deleted successfully."}
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete user. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_user: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# Deprecated
# @user_router.get("/v1/users", response_model=UserResponse)
# def get_paginated_users(
#     page: int = Query(1, description="Page number", gt=0),
#     page_size: int = Query(10, description="Number of items per page", gt=0),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     sort_by: str = Query("created_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Retrieves paginated user information based on specified criteria.
#     """
#     try:
#         user_repository = UserRepository(db)

#         filters = request.state.filters

#         # Fetch all users
#         users, total = user_repository.paginated_get_all_users(
#             page=page,
#             page_size=page_size,
#             filters=filters,
#             sort_by=sort_by,
#             sort_order=sort_order,
#         )

#         return UserResponse(users=users, total=total)

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @user_router.get("/v1/users-search", response_model=UserResponse)
# def search_paginated_users(
#     keyword: str = Query(None, description="Search keyword"),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     page: int = Query(1, description="Page number", gt=0),
#     page_size: int = Query(10, description="Number of items per page", gt=0),
#     sort_by: str = Query("created_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves paginated user information based on specified keyword.
#     """
#     try:
#         user_repository = UserRepository(db)

#         filters = request.state.filters

#         # Search users
#         if keyword:
#             users, total = user_repository.paginated_search_user(
#                 keyword=keyword,
#                 page=page,
#                 page_size=page_size,
#                 filters=filters,
#                 sort_by=sort_by,
#                 sort_order=sort_order,
#             )

#             if users:
#                 return UserResponse(users=users, total=total)
#             else:
#                 return UserResponse(users=[], total=0)
#         else:
#             raise HTTPException(
#                 status_code=400,
#                 detail="No keyword provided.",
#             )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @user_router.get("/users/search", response_model=UserResponse)
# def search_users(
#     keyword: str = Query(None, description="Search keyword"),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     sort_by: str = Query("created_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (desc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves user information based on specified keyword.
#     """
#     try:
#         user_repository = UserRepository(db)

#         filters = request.state.filters

#         # Search users
#         if keyword:
#             users = user_repository.search_user(
#                 keyword=keyword,
#                 filters=filters,
#                 sort_by=sort_by,
#                 sort_order=sort_order,
#             )

#             if users:
#                 return UserResponse(users=users, total=len(users))
#             else:
#                 return UserResponse(users=[], total=0)
#         else:
#             raise HTTPException(
#                 status_code=400,
#                 detail="No keyword provided.",
#             )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @user_router.get("/v1/users/search", response_model=UserResponse)
# def search_paginated_users(
#     keyword: str = Query(None, description="Search keyword"),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     page: int = Query(1, description="Page number", gt=0),
#     page_size: int = Query(10, description="Number of items per page", gt=0),
#     sort_by: str = Query("created_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves paginated user information based on specified keyword.
#     """
#     try:
#         user_repository = UserRepository(db)

#         filters = request.state.filters

#         # Search users
#         if keyword:
#             users, total = user_repository.paginated_search_user(
#                 keyword=keyword,
#                 page=page,
#                 page_size=page_size,
#                 filters=filters,
#                 sort_by=sort_by,
#                 sort_order=sort_order,
#             )

#             if users:
#                 return UserResponse(users=users, total=total)
#             else:
#                 return UserResponse(users=[], total=0)
#         else:
#             raise HTTPException(
#                 status_code=400,
#                 detail="No keyword provided.",
#             )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
