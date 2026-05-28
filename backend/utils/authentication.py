# Custom libraries
from logger import configure_logging
from utils.schema_utils import set_schema

# Database modules
from repository.authentication_repository import AuthenticationRepository
from repository.permission_repository import PermissionRepository
from repository.user_access_repository import UserAccessRepository

# Default libraries
import os
import time
from uuid import UUID

# Installed libraries
import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import HTTPException, status
from datetime import datetime


load_dotenv()
logger = configure_logging(logger_name=__name__)


class Authentication:
    def __init__(self):
        # Load JWT secret key from environment variable
        self.jwt_secret = os.getenv("JWT_SECRET")

    def hash_password(self, password: str):
        # Generate a unique salt for each password
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), salt)
        return {"hashed_password": hashed_password.decode("utf-8"), "salt": salt}

    def generate_token(
        self, user_uuid: str, token_type: str, db, organization_schema: str
    ):
        try:
            issued_at = int(time.time())

            if token_type == "access_token":
                expiration_time = (
                    issued_at + int(os.getenv("TOKEN_VALIDITY", 12)) * 3600
                )
            elif token_type == "refresh_token":
                expiration_time = issued_at + 1209600  # 14 days
            else:
                # Handle invalid token types or raise an exception
                raise ValueError("Invalid token type requested")

            # Create the JWT payload
            payload = {
                "iat": issued_at,
                "exp": expiration_time,
                "sub": str(user_uuid),
                "org_id": str(organization_schema),
            }

            if token_type == "access_token":
                # Get user role and web routes from db
                user_access_repository = UserAccessRepository(db)
                user_role = user_access_repository.get_role_by_user_id(user_uuid)
                user_access = user_access_repository.get_user_access_by_user_id(
                    user_uuid
                )
                permission_repository = PermissionRepository(db)
                access_control = permission_repository.get_web_app_permissions(
                    user_role.role_permissions
                )

                payload["user_role"] = user_role.name
                payload["access_control"] = access_control
                payload["permissions"] = user_role.role_permissions
                # payload["app_access"] = (
                #     user_access.app_access
                #     if user_access and user_access.app_access
                #     else {}
                # )

            # Generate the JWT auth token using the secret key
            token = jwt.encode(payload, self.jwt_secret, algorithm="HS256")

            return token

        except Exception as e:
            logger.error(f"An error occurred in token generation: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token generation failed.",
            )

    def create_user_session(self, user, db, organization_schema: str):
        """Generate tokens, store auth record, update last_login. Returns (access_token, refresh_token)."""
        access_token = self.generate_token(str(user.id), "access_token", db, organization_schema)
        refresh_token = self.generate_token(str(user.id), "refresh_token", db, organization_schema)

        AuthenticationRepository(db).create_authentication(user.id, {
            "access_token": access_token,
            "refresh_token": refresh_token,
        })
        from repository.user_repository import UserRepository
        UserRepository(db).update_user({"user_uuid": user.id, "last_login": str(datetime.now())})

        return access_token, refresh_token

    def verify_password(self, password: str, salt: str, hashed_password: str) -> bool:
        """
        Verify a password using the provided salt and hashed_password.
        """
        try:
            # Convert the salt to bytes
            salt_bytes = bytes.fromhex(salt.replace("\\x", ""))

            # Convert the hashed_password to bytes (no need to encode again)
            hashed_password_bytes = hashed_password.encode("utf-8")

            # Hash the input password using the provided salt
            hashed_input_password = bcrypt.hashpw(password.encode("utf-8"), salt_bytes)

            # Compare the hashed input password with the stored hashed password
            result = hashed_input_password == hashed_password_bytes
            return result

        except Exception as e:
            logger.error(f"An error occurred: {e}")
            return False

    def verify_token(self, token: str, request_token_type: str, decoded_token: dict = None):
        """
        Verify JWT token validity and check if it exists in database.

        Args:
            token: JWT token string
            request_token_type: Expected token type ('access_token' or 'refresh_token')
            decoded_token: Pre-decoded token payload (optional, to avoid re-decoding)

        OPTIMIZED: Accepts pre-decoded token to avoid redundant decode operations.
        
        Handles three scenarios with separate HTTP status codes:
        1. Expired token - 401 Unauthorized (token expired)
        2. Logged out token - 401 Unauthorized (token invalid/revoked)
        3. Corrupted token - 400 Bad Request (malformed token)
        """
        try:
            # Decode token only if not already provided
            if decoded_token is None:
                decoded_token = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])

            # Determine token type based on the time difference
            if (
                decoded_token["exp"] - decoded_token["iat"]
                == int(os.getenv("TOKEN_VALIDITY", 12)) * 3600
            ):
                token_type = "access_token"
            elif decoded_token["exp"] - decoded_token["iat"] == 1209600:
                token_type = "refresh_token"
            else:
                raise ValueError("Invalid token type based on time difference")

            user_uuid = decoded_token["sub"]
            organization_schema = decoded_token.get("org_id")
            user_role = decoded_token.get("user_role")

            # Verify token type matches request
            if token_type != request_token_type:
                logger.error(f"Token type mismatch: expected {request_token_type}, got {token_type}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # For ROOT users, always look up tokens in public schema
            # For other users, use schema from JWT token
            lookup_schema = "public" if user_role == "ROOT" else organization_schema

            with set_schema(lookup_schema) as org_db:
                authentication_repository = AuthenticationRepository(org_db)
                user_authentication = authentication_repository.get_user_by_uuid(
                    user_uuid
                )

                # Check if token exists in database (handles logged out scenario)
                if any(
                    getattr(record, token_type) == token
                    for record in user_authentication
                ):
                    pass  # Token is valid
                else:
                    # Scenario 2: Logged out token (token not found in database)
                    logger.warning(
                        f"Logged out user tried to use application: {user_uuid}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token has been revoked or is invalid",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                    
        except jwt.ExpiredSignatureError:
            # Scenario 1: Expired token
            logger.warning("Expired JWT token attempted to be used")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except (jwt.InvalidSignatureError, jwt.DecodeError, jwt.InvalidTokenError) as e:
            # Scenario 3: Corrupted token (invalid signature, malformed, etc.)
            logger.error(f"Corrupted JWT token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed or invalid token format",
            )
        except HTTPException:
            # Re-raise HTTPExceptions
            raise
        except Exception as e:
            # Handle any other unexpected errors
            logger.error(f"JWT token verification failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token verification failed",
                headers={"WWW-Authenticate": "Bearer"},
            )
