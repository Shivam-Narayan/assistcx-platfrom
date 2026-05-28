# Custom libraries
from logger import configure_logging
from schemas.user_schema import (
    EmailDiscoverRequest,
    EmailDiscoverResponse,
    SSOExchangeRequest,
    SSOSettingsResponse,
    SSOSettingsUpdate,
    TeamsAuthRequest,
    UserAuthentication,
    UserLogin,
)
from utils.authentication import Authentication
from utils.schema_utils import (
    get_organization_schemas,
    get_session_for_role,
    get_schema_db,
    get_user_schema,
    set_schema,
)
from utils.auth_sso import sso_service

# Database modules
from db_pool import DatabasePoolManager
from repository.authentication_repository import AuthenticationRepository
from repository.configuration_repository import ConfigurationRepository
from repository.user_repository import UserRepository
from sqlalchemy.orm import Session

# Default libraries
from datetime import datetime
from typing import Optional
from uuid import UUID
import os

# Installed libraries
from dotenv import load_dotenv
from jwt import decode
from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt


load_dotenv()

db_pool = DatabasePoolManager()

logger = configure_logging(logger_name=__name__)

authentication = Authentication()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")

authentication_router = APIRouter(tags=["Authentication"])


@authentication_router.post("/authorize")
def authorize(form_data: OAuth2PasswordRequestForm = Depends()):
    """Used for authorization on docs page. Uses OpenAPI security standards."""
    result = login(UserLogin(email=form_data.username, password=form_data.password))
    return {
        "access_token": result.access_token,
        "token_type": "bearer",
        "refresh_token": result.refresh_token,
    }


@authentication_router.post("/login", response_model=UserAuthentication, deprecated=True)
@authentication_router.post("/auth/login", response_model=UserAuthentication)
def login(user_data: UserLogin = Body(...)):
    """Handles user login by checking credentials against stored user data."""
    organization_schema = get_user_schema(user_data.email)
    if not organization_schema:
        raise HTTPException(status_code=404, detail="User does not exist. Please check and retry.")

    with db_pool.get_session(organization_schema) as org_db:
        # SSO-only check (ROOT user bypasses — always allowed password login)
        is_root_user = user_data.email == os.getenv("PLATFORM_ROOT_USER")
        if not is_root_user:
            org_config = ConfigurationRepository(org_db).get_configuration()
            if org_config and org_config.auth_config:
                if org_config.auth_config.get("auth_method") == "sso":
                    raise HTTPException(status_code=403, detail="This organization requires SSO authentication.")

        user = UserRepository(org_db).get_user_by_id(user_data.email)
        if not user:
            raise HTTPException(status_code=404, detail="User does not exist. Please check and retry.")
        if user.account_status != "active" or not authentication.verify_password(
            user_data.password, user.salt, user.hashed_password
        ):
            raise HTTPException(status_code=401, detail="Invalid credentials.")

        # ROOT users can switch to a different org schema
        target_schema = organization_schema
        if user_data.db_schema and user.email == os.getenv("PLATFORM_ROOT_USER"):
            if user_data.db_schema not in get_organization_schemas():
                raise HTTPException(status_code=400, detail="Organization does not exist. Please check and retry.")
            target_schema = user_data.db_schema

        access_token, refresh_token = authentication.create_user_session(user, org_db, target_schema)

        logger.info(f"Successful login by user: {user.id}")
        return UserAuthentication(
            user_uuid=user.id,
            access_token=access_token,
            refresh_token=refresh_token,
        )


@authentication_router.post("/logout", deprecated=True)
@authentication_router.post("/auth/logout")
def logout(
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
    request: Request = None,
):
    """
    Handles user log out.
    """
    try:
        # Use decoded token from request.state if present, otherwise decode the token
        decoded_token = getattr(request.state, "decoded_token", None)
        if not decoded_token:
            decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_uuid = decoded_token["sub"]
        user_role = decoded_token["user_role"]

        # Get appropriate session based on user role
        with get_session_for_role(user_role, db) as session:
            authentication_repository = AuthenticationRepository(session)
            logout_success = authentication_repository.delete_authentication(user_uuid)

            if logout_success:
                logger.info(f"Successful logout by user: {user_uuid}")
                return {"message": "User logged out successfully."}
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked or is invalid",
                    headers={"WWW-Authenticate": "Bearer"},
                )

    except jwt.ExpiredSignatureError:
        logger.warning(f"Expired JWT token attempted to be used for logout")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.InvalidSignatureError, jwt.DecodeError, jwt.InvalidTokenError) as e:
        logger.error(f"Corrupted JWT token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed or invalid token format",
        )
    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


@authentication_router.post("/token", response_model=UserAuthentication, deprecated=True)
@authentication_router.post("/auth/token", response_model=UserAuthentication)
def refresh_token(token: str = Depends(oauth2_scheme)):
    """
    Refreshes authentication and refresh tokens by validating refresh token in bearer token field.
    """
    try:
        # Decode JWT token and extract information from decoded payload
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_uuid = decoded_token["sub"]
        organization_id = decoded_token["org_id"]

        # verify_token handles expired, logged out, and corrupted token scenarios
        authentication.verify_token(token, "refresh_token", decoded_token)

        # Set schema public if user_role is ROOT, else based on organization_id
        organization_schema = get_user_schema(UUID(user_uuid))
        
        with set_schema(organization_schema) as org_db:
            # Generate new auth and refresh tokens
            new_access_token = authentication.generate_token(
                str(user_uuid), "access_token", org_db, organization_id
            )
            new_refresh_token = authentication.generate_token(
                str(user_uuid), "refresh_token", org_db, organization_id
            )

            # Create or update authentication record
            authentication_repository = AuthenticationRepository(org_db)
            authentication_data = {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
            }
            authentication_repository.update_authentication(
                token, authentication_data
            )

            logger.info(f"Tokens refreshed successfully for user: {user_uuid}")

            return UserAuthentication(
                user_uuid=user_uuid,
                access_token=new_access_token,
                refresh_token=new_refresh_token,
            )

    except jwt.ExpiredSignatureError:
        # Scenario 1: Expired token (caught before verify_token if decode fails)
        logger.warning("Expired JWT token attempted to be used for refresh")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.InvalidSignatureError, jwt.DecodeError, jwt.InvalidTokenError) as e:
        # Scenario 3: Corrupted token (caught before verify_token if decode fails)
        logger.error(f"Corrupted JWT token in refresh: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed or invalid token format",
        )
    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions (including those from verify_token)
        # verify_token already handles expired, logged out, and corrupted scenarios
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Handle other errors
        logger.error(f"An error occurred: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: {e}",
        )


# ── SSO Endpoints ──────────────────────────────────────────────────────


@authentication_router.post("/auth/discover", response_model=EmailDiscoverResponse)
def discover_auth_method(request_data: EmailDiscoverRequest = Body(...)):
    """
    Given a user's email, returns the org's configured auth method.
    Always returns a safe default for unknown users (does not reveal org existence).
    """
    try:
        result = sso_service.discover_email(request_data.email)
        return EmailDiscoverResponse(**result)
    except Exception as e:
        logger.error(f"Error in auth discover: {e}")
        return EmailDiscoverResponse()


@authentication_router.get("/auth/sso/authorize")
def sso_authorize(
    provider: str = Query(..., description="SSO provider: microsoft, google, oidc"),
    email: str = Query(..., description="User email from discovery step"),
):
    """
    Initiates the OAuth flow by redirecting the browser to the IdP.
    Generates state, stores in Redis, and returns HTTP 302 redirect to IdP.
    """
    try:
        authorize_url = sso_service.build_authorize_url(email.strip().lower(), provider)
        return RedirectResponse(url=authorize_url, status_code=302)
    except ValueError as e:
        logger.error(f"SSO authorize error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"SSO authorize unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate SSO")


@authentication_router.get("/auth/sso/callback")
def sso_callback(
    code: str = Query(..., description="Authorization code from IdP"),
    state: str = Query(..., description="State parameter for CSRF validation"),
):
    """
    Receives the IdP callback after user authentication.
    Validates state, exchanges code for tokens, generates one-time sso_code,
    and redirects to the frontend /sso-complete page.
    """
    try:
        result = sso_service.handle_callback(code, state)
        return RedirectResponse(url=result["redirect_url"], status_code=302)
    except Exception as e:
        logger.error(f"SSO callback unexpected error: {e}")
        frontend_url = sso_service.frontend_url
        return RedirectResponse(
            url=f"{frontend_url}/sso-complete?error=unexpected_error",
            status_code=302,
        )


@authentication_router.post("/auth/sso/exchange", response_model=UserAuthentication)
def sso_exchange(request_data: SSOExchangeRequest = Body(...)):
    """
    Exchanges a one-time sso_code for platform app tokens.
    Called by the frontend's NextAuth authorize() function.
    """
    try:
        token_data = sso_service.exchange_code(request_data.code)
        if not token_data:
            raise HTTPException(status_code=400, detail="Invalid or expired code")
        return UserAuthentication(
            user_uuid=token_data["user_uuid"],
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SSO exchange error: {e}")
        raise HTTPException(status_code=500, detail="Failed to exchange SSO code")


@authentication_router.post("/auth/teams", response_model=UserAuthentication)
def teams_auth(request_data: TeamsAuthRequest = Body(...)):
    """
    Authenticates a user via Microsoft Teams SSO token.
    Validates the Teams token, extracts email, and returns platform app tokens.
    Enabled by default for all orgs — no admin configuration needed.
    """
    try:
        token_data = sso_service.authenticate_teams_token(request_data.teams_token)
        return UserAuthentication(
            user_uuid=token_data["user_uuid"],
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
        )
    except ValueError as e:
        logger.error(f"Teams auth error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Teams auth unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Teams authentication failed")


@authentication_router.get("/auth/settings", response_model=SSOSettingsResponse)
def get_auth_settings(db: Session = Depends(get_schema_db)):
    """
    Returns the org's current authentication/SSO configuration.
    Never exposes the actual client secret. Requires admin access (organizations: edit).
    """
    try:
        result = sso_service.get_settings(db)
        return SSOSettingsResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting auth settings: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@authentication_router.put("/auth/settings", response_model=SSOSettingsResponse)
def update_auth_settings(
    settings: SSOSettingsUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Updates the org's authentication/SSO configuration.
    Encrypts client_secret before storage. Requires admin access (organizations: edit).
    """
    try:
        update_data = settings.model_dump(exclude_unset=True)
        result = sso_service.update_settings(db, update_data)
        return SSOSettingsResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating auth settings: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
