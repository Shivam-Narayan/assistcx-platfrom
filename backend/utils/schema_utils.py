# Custom libraries
from logger import configure_logging
from models.user import User
from db_pool import DatabasePoolManager, AsyncDatabasePoolManager

# Database modules
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

# Default libraries
from contextlib import contextmanager
from typing import Generator, AsyncGenerator, List, Optional, Union
from uuid import UUID
import os
import subprocess

# Installed libraries
from dotenv import load_dotenv
from fastapi import HTTPException, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.security import OAuth2PasswordBearer
from jwt import decode


load_dotenv()

db_pool = DatabasePoolManager()
async_db_pool = AsyncDatabasePoolManager()

logger = configure_logging(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize", auto_error=False)

# Reserved system schemas that should not be used
RESERVED_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast", "pg_temp"}


def run_alembic_migration(schema: str):
    try:
        # Define the command to run Alembic migration with the given schema
        command = ["alembic", "-x", f"tenant={schema}", "upgrade", "head"]

        # Run the command using subprocess
        result = subprocess.run(command, capture_output=True, text=True, check=True)

        # Check for errors
        if result.returncode != 0:
            logger.error(
                f"Alembic command returned non-zero exit code {result.returncode}, {result.stderr}"
            )
            raise HTTPException(
                status_code=500, detail="Failed to apply Alembic migration."
            )
        else:
            logger.info(
                f"Alembic migration for organization {schema} applied successfully"
            )
    except Exception as e:
        logger.error(
            f"Failed to apply Alembic migration for organization {schema}: {e}"
        )
        raise HTTPException(
            status_code=500, detail="Failed to apply Alembic migration."
        )


def check_schema_exists(schema_name: str) -> bool:
    """
    Check if schema exists in database.

    Args:
        schema_name (str): Schema name to check.

    Returns:
        bool: True if schema exists, False otherwise.
    """
    try:
        with db_pool.get_session("public") as db:
            result = db.execute(
                text(
                    "SELECT 1 FROM information_schema.schemata WHERE schema_name = :name"
                ),
                {"name": schema_name},
            )
            return result.fetchone() is not None
    except Exception as e:
        logger.error(f"Error in check_schema_exists: {e}")
        return False


async def check_schema_exists_async(schema_name: str) -> bool:
    """
    Check if schema exists in database (async version - non-blocking).

    Args:
        schema_name (str): Schema name to check.

    Returns:
        bool: True if schema exists, False otherwise.
    """
    try:
        async with async_db_pool.get_session("public") as db:
            result = await db.execute(
                text(
                    "SELECT 1 FROM information_schema.schemata WHERE schema_name = :name"
                ),
                {"name": schema_name},
            )
            row = result.fetchone()
            return row is not None  # True if row exists, False otherwise
    except Exception as e:
        logger.error(f"Error in check_schema_exists_async: {e}")
        return False


def get_organization_schemas() -> Optional[List]:
    """Get all organization schemas"""
    try:
        # Use public schema to query information_schema
        with db_pool.get_session("public") as db:
            result = db.execute(
                text("SELECT schema_name FROM information_schema.schemata")
            )
            schemas = [row[0] for row in result if row[0] not in RESERVED_SCHEMAS]
            return schemas
    except Exception as e:
        logger.error(f"Error getting organization schemas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Function to retrieve the current schema
def get_current_schema(db: Session) -> Optional[str]:
    """
    Retrieves the current schema from the database session.
    """
    try:
        current_schema = db.scalar(text("SELECT current_schema();"))
        return current_schema

    except Exception as e:
        logger.error(f"Error occurred in get_current_schema: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


async def get_current_schema_async(db: AsyncSession) -> Optional[str]:
    """
    Retrieves the current schema from an async database session.
    """
    try:
        current_schema = await db.scalar(text("SELECT current_schema();"))
        return current_schema
    except Exception as e:
        logger.error(f"Error occurred in get_current_schema_async: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# Function to get schema by finding the user based on user_id
def get_user_schema(user_id: Union[UUID, str] = None) -> Optional[str]:
    """
    Retrieves schema for a specific user using optimized cross-schema query.

    Args:
        user_id: User ID (UUID), email, or user_id string

    Returns:
        Schema name where the user was found, or None if not found
    """
    try:
        # Get all organization schemas
        with db_pool.get_session("public") as db:
            schemas = get_organization_schemas()

            # Determine the WHERE clause based on user_id type
            if isinstance(user_id, UUID):
                where_clause = "id = :id"
            elif "@" in str(user_id):
                where_clause = "email = :id"
            else:
                where_clause = "user_id = :id"

            # Query each schema for the user
            for schema in schemas:
                try:
                    quoted_schema = f'"{schema}"'
                    query = text(
                        f"""
                        SELECT 1 FROM {quoted_schema}.users 
                        WHERE {where_clause}
                        LIMIT 1
                    """
                    )
                    result = db.execute(query, {"id": str(user_id)})
                    if result.fetchone():
                        return schema
                except Exception as schema_error:
                    logger.debug(f"Error querying schema {schema}: {schema_error}")
                    continue

        return None
    except Exception as e:
        logger.error(f"Error occurred in get_user_schema: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@contextmanager
def set_schema(
    organization_schema: Optional[str] = None,
) -> Generator[Session, None, None]:
    """
    Context manager to set up a database session for a specific schema, automatically closed when exiting the context.

    Args:
        organization_schema (Optional[str]): Schema name to use, defaults to 'public' schema

    Yields:
        Session: Database session with the specified schema
    """
    try:
        # Default to 'public' schema if no schema is provided
        schema_name = (
            organization_schema if organization_schema is not None else "public"
        )

        with db_pool.get_session(schema_name) as session:
            yield session

    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        # Log the error and raise an HTTPException
        logger.error(f"An error occurred in set_schema: {e}")
        raise HTTPException(status_code=500, detail=f"Database session error: {e}")


def get_schema_db(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
) -> Generator[Session, None, None]:
    """
    FastAPI dependency for DB session scoped to request org schema based on API key or JWT token.

    Args:
        request(Request): FastAPI request object
        token(Optional[str]): JWT token to decode

    Returns:
        Generator[Session, None, None]: Database session with the specified schema
    """
    try:
        schema_name = "public"

        # API key auth: middleware sets request.state.org_id (db_schema)
        if getattr(request.state, "auth_type", None) == "api_key":
            schema_name = getattr(request.state, "org_id", None) or "public"
        # JWT path: use middleware-decoded token when present (avoids re-decode and re-validation)
        elif getattr(request.state, "decoded_token", None):
            schema_name = request.state.decoded_token.get("org_id", "public")
        elif token:
            jwt_secret = os.getenv("JWT_SECRET")
            try:
                decoded_token = decode(token, jwt_secret, algorithms=["HS256"])
                schema_name = decoded_token.get("org_id", "public")
            except Exception as e:
                logger.error(f"JWT decode error: {e}")
                raise HTTPException(
                    status_code=401, detail="Invalid authentication token"
                )

        with db_pool.get_session(schema_name) as session:
            yield session

    except HTTPException:
        raise
    except RequestValidationError:
        # Re-raise validation errors to be handled by middleware
        raise
    except Exception as e:
        logger.error(f"Error in get_schema_db: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@contextmanager
def get_session_for_role(
    user_role: str,
    injected_db: Session,
    root_schema: str = "public",
) -> Generator[Session, None, None]:
    """
    Context manager to get the appropriate database session based on user role.
    ROOT users get a new session for the specified schema (default: public).
    Other users use the injected session from FastAPI dependency.

    Args:
        user_role: The user's role from JWT token.
        injected_db: The session injected by FastAPI Depends(get_schema_db).
        root_schema: Schema to use for ROOT users (default: "public").

    Yields:
        Session: The appropriate database session.
    """
    if user_role == "ROOT":
        with set_schema(root_schema) as root_db:
            yield root_db
    else:
        yield injected_db


async def get_async_schema_db(
    token: str = Depends(oauth2_scheme),
) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for async SQLAlchemy database sessions with schema validation.

    Args:
        token (str): JWT token to decode.

    Returns:
        AsyncGenerator[AsyncSession, None]: Async database session with the specified schema.
    """
    try:
        jwt_secret = os.getenv("JWT_SECRET")
        decoded_token = decode(token, jwt_secret, algorithms=["HS256"])
        schema_name = decoded_token.get("org_id", "public")

        # Verify schema exists (use async version to avoid blocking event loop)
        if not await check_schema_exists_async(schema_name):
            logger.warning(f"Schema does not exist: {schema_name}")
            raise HTTPException(status_code=404, detail="Schema not found")

        async with async_db_pool.get_session(schema_name) as session:
            yield session

    except HTTPException:
        raise
    except RequestValidationError:
        raise
    except Exception as e:
        logger.error(f"Error in get_async_schema_db: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
