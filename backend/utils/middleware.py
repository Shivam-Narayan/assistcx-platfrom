import os
import jwt
from fastapi import Request, status, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from configs.user_roles import OPEN_ROUTES, ROOT_ONLY_ROUTES
from configs.module_registry import ENABLED_MODULES
from logger import configure_logging
from utils.api_key_authentication import APIKeyAuthentication
from utils.authentication import Authentication
from utils.permissions import Permissions
from utils.rbac_utils import check_access, find_matching_modules, parse_filters_query_params

logger = configure_logging(__name__)

# Initialize utilities
api_key_authentication = APIKeyAuthentication()
authentication = Authentication()
permissions = Permissions()


def handle_validation_error(exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic validation errors with user-friendly messages."""
    error = exc.errors()[0] if exc.errors() else {}
    field = " -> ".join(str(loc) for loc in error.get("loc", []))
    msg = error.get("msg", "Validation error")

    if "uuid" in str(msg).lower():
        detail = f"Invalid UUID format for '{field}'. Expected format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    else:
        detail = f"{field}: {msg}" if field else msg

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": detail},
    )


async def call_next_with_validation(request: Request, call_next) -> JSONResponse:
    """Call the next handler with validation error handling.

    Note: BaseHTTPMiddleware doesn't propagate exceptions to FastAPI exception handlers,
    so we handle RequestValidationError here explicitly.
    """
    try:
        response = await call_next(request)
        return add_security_headers(response)
    except RequestValidationError as exc:
        return handle_validation_error(exc)


class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication and Authorization Middleware.

    Responsibilities:
    1. Skip auth for open routes and OPTIONS requests
    2. Verify JWT tokens
    3. Extract and attach user/org info to request.state
    4. Verify user + data access permissions
    5. Add security headers to responses
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next_with_validation(request, call_next)

        # Skip authentication for open routes
        if any(path == route or path.startswith(route + "/") for route in OPEN_ROUTES):
            return await call_next_with_validation(request, call_next)

        # Safety net: return 404 for routes whose modules are all disabled
        matching_modules = find_matching_modules(path)
        if matching_modules and not any(
            m in ENABLED_MODULES for m in matching_modules
        ):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"detail": "Not Found"},
            )

        auth_header = request.headers.get("Authorization")

        # API key path: /task-api accepts ApiKey or X-API-Key only
        if path.startswith("/task-api"):
            raw_api_key = (
                auth_header[7:].strip()
                if auth_header and auth_header.startswith("ApiKey ")
                else request.headers.get("X-API-Key") or ""
            )
            raw_api_key = raw_api_key.strip() if raw_api_key else ""
            if not raw_api_key:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "API key required"},
                )
            try:
                validated_api_key = api_key_authentication.validate_api_key(raw_api_key)

                # Store in request.state
                request.state.org_id = validated_api_key.get("org_id")
                request.state.user_id = validated_api_key.get("api_key_id")
                request.state.auth_type = "api_key"

                request.state.filters = parse_filters_query_params(request) or None

                return await call_next_with_validation(request, call_next)

            except HTTPException as e:
                return JSONResponse(
                    status_code=e.status_code,
                    content={"detail": e.detail},
                )

        # JWT path: Bearer token required
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning(f"No authentication token provided for {path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required"},
            )

        token = auth_header[7:]  # strip "Bearer "

        try:
            # Decode token ONCE (validates signature automatically)
            jwt_secret = os.getenv("JWT_SECRET")
            decoded_token = jwt.decode(token, jwt_secret, algorithms=["HS256"])

            # Verify the token (checks DB for logout/deactivation)
            # verify_token handles expired, logged out, and corrupted token scenarios
            authentication.verify_token(token, "access_token", decoded_token)

            # Store in request.state
            request.state.user_id = decoded_token.get("sub")
            request.state.org_id = decoded_token.get("org_id")
            request.state.token = token
            request.state.decoded_token = decoded_token

            # ROOT users bypass all permission checks
            user_role_name = decoded_token.get("user_role")
            is_root_only = any(
                path == route or path.startswith(route + "/")
                for route in ROOT_ONLY_ROUTES
            )

            if user_role_name == "ROOT":
                request.state.filters = parse_filters_query_params(request) or None
            elif is_root_only:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Root access required."},
                )
            else:
                role_permissions = decoded_token.get("permissions", {})

                # Route-level permission check (in-memory, no DB query)
                if not check_access(role_permissions, request.method, path):
                    logger.error(f"User not permitted to access: {request.method} {path}")
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Access denied."},
                    )

                # Data-level permissions (uses decoded_token)
                data_filters = await permissions.verify_user_data_access(
                    decoded_token, request
                )
                request.state.filters = data_filters

        except jwt.ExpiredSignatureError:
            # Scenario 1: Expired token (caught before verify_token if decode fails)
            logger.warning(f"Expired JWT token")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Token has expired"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        except (jwt.InvalidSignatureError, jwt.DecodeError, jwt.InvalidTokenError) as e:
            # Scenario 3: Corrupted token (caught before verify_token if decode fails)
            logger.error(f"Corrupted JWT token in middleware: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Malformed or invalid token format"},
            )
        except HTTPException as http_error:
            # HTTPException from verify_token or permissions - preserve status code and detail
            # verify_token handles expired, logged out, and corrupted token scenarios
            logger.error(f"Authentication error: {http_error.detail}")
            return JSONResponse(
                status_code=http_error.status_code,
                content={"detail": http_error.detail},
                headers=getattr(http_error, "headers", {}),
            )
        except Exception as e:
            # Unexpected error
            logger.error(f"Unexpected authentication error: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication failed"},
            )

        # Proceed to route handler
        return await call_next_with_validation(request, call_next)


def add_security_headers(response):
    """Add security headers to the response.

    Args:
        response: The FastAPI response

    Returns:
        The response with security headers
    """
    # Set security headers
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )

    # For streaming responses (SSE), add specific headers
    if response.headers.get("content-type") == "text/event-stream":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["Connection"] = "keep-alive"
        response.headers["Keep-Alive"] = "timeout=120"
        # Disable buffering for proxies and intermediaries
        response.headers["X-Accel-Buffering"] = "no"
        response.headers["X-Proxy-Buffering"] = "no"
        # Prevent response compression for streaming
        response.headers["Content-Encoding"] = "identity"

    return response
