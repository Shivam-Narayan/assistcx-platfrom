# checkpointer.py - Simplified implementation following LangGraph reference pattern

import os
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from logger import configure_logging

logger = configure_logging(__name__)


def get_db_connection_string(schema: str) -> str:
    """Build connection string with schema support using your existing DATABASE_URL."""

    # Use your existing DATABASE_URL
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    # URL-encode the search_path option (= becomes %3D)
    options_param = f"options=-csearch_path%3D{schema}"

    # Build connection string with proper URL encoding
    connection_string = (
        f"{database_url}&{options_param}"
        if "?" in database_url
        else f"{database_url}?{options_param}"
    )

    return connection_string


@asynccontextmanager
async def get_checkpointer_context(schema: str):
    """
    Context manager that follows LangGraph's reference pattern with proper URL encoding.

    Note: LangGraph's from_conn_string() doesn't accept connection kwargs like
    autocommit and prepare_threshold. These are handled internally by LangGraph.
    """
    connection_string = get_db_connection_string(schema)

    # LangGraph handles connection settings internally
    # No need to pass connection_kwargs to from_conn_string()
    async with AsyncPostgresSaver.from_conn_string(connection_string) as checkpointer:
        logger.debug(f"Checkpointer context opened for schema: {schema}")
        try:
            yield checkpointer
        finally:
            logger.debug(f"Checkpointer context closed for schema: {schema}")


# Alternative: Simple non-context manager version if you prefer
async def get_checkpointer(schema: str) -> AsyncPostgresSaver:
    """
    Simple checkpointer creation - LangGraph handles connection settings internally.

    Note: Your original connection_kwargs (autocommit, prepare_threshold) are not
    supported by LangGraph's from_conn_string() method. LangGraph handles these internally.
    """
    connection_string = get_db_connection_string(schema)

    # LangGraph handles connection management internally
    checkpointer = AsyncPostgresSaver.from_conn_string(connection_string)
    logger.debug(f"Created checkpointer for schema: {schema}")
    return checkpointer


async def run_checkpointer_migrations(schema: str) -> bool:
    """Run checkpointer migrations for a schema."""
    try:
        logger.info(f"Running checkpointer migrations for schema: {schema}")

        # Use context manager for migrations
        async with get_checkpointer_context(schema) as checkpointer:
            await checkpointer.setup()

        logger.info(f"Completed checkpointer migrations for schema: {schema}")
        return True

    except Exception as e:
        logger.error(
            f"Checkpointer migrations failed for schema {schema}: {e}", exc_info=True
        )
        return False


async def get_pool_stats(schema: str) -> Dict[str, Any]:
    """Simple pool stats - LangGraph manages pools internally."""
    return {
        "schema": schema,
        "message": "Pool management handled by LangGraph internally",
        "approach": "using AsyncPostgresSaver.from_conn_string() context manager",
    }


# --- Main block for running migrations ---
if __name__ == "__main__":
    import argparse
    import asyncio
    import sys

    parser = argparse.ArgumentParser(
        description="Run checkpointer migrations for a specified schema."
    )
    parser.add_argument(
        "--schema", default="public", help="Database schema to run migrations for"
    )
    args = parser.parse_args()

    schema_to_migrate = args.schema

    async def main():
        try:
            logger.info(
                f"Starting checkpointer migrations for schema: {schema_to_migrate}"
            )
            success = await run_checkpointer_migrations(schema_to_migrate)

            if success:
                logger.info(
                    f"Migrations completed successfully for schema '{schema_to_migrate}'"
                )
                return 0
            else:
                logger.error(f"Migrations failed for schema '{schema_to_migrate}'")
                return 1

        except KeyboardInterrupt:
            logger.info("Migration script interrupted by user")
            return 1
        except Exception as e:
            logger.error(f"Unexpected error during migration: {e}", exc_info=True)
            return 1

    # Run migrations
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Failed to run migration script: {e}")
        sys.exit(1)
