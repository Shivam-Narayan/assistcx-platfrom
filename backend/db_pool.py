# Standard library imports
import os
import asyncio
from contextlib import contextmanager, asynccontextmanager
from typing import Dict, Generator, AsyncGenerator

# Third-party imports
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import QueuePool, NullPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from logger import configure_logging

logger = configure_logging(__name__)

# Base class for declarative models (shared across all schemas)
Base = declarative_base()


class DatabasePoolManager:
    _instance = None
    _engines: Dict[str, any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabasePoolManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL")
        # Set reasonable pool size limits
        self.pool_size = int(os.getenv("DB_POOL_SIZE", "2"))
        self.max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "50"))
        self.pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
        self.pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "3600"))
        self._session_factories = {}

    def get_engine(self, schema_name: str):
        """Get or create an engine for a specific schema"""
        if schema_name not in self._engines:
            engine = create_engine(
                self.database_url,
                poolclass=QueuePool,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_timeout=self.pool_timeout,  # Wait timeout for connection
                pool_pre_ping=True,  # Ensures connections are valid
                pool_recycle=self.pool_recycle,  # Recycle connections periodically
            )

            # Set schema for all connections from this engine
            @event.listens_for(engine, "connect")
            def set_search_path(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute(f"SET search_path TO '{schema_name}'")
                finally:
                    cursor.close()

            # Set schema for every session checkout to ensure correct schema context
            @event.listens_for(engine, "checkout")
            def set_search_path_on_checkout(
                dbapi_connection, connection_record, connection_proxy
            ):
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute(f"SET search_path TO '{schema_name}'")
                finally:
                    cursor.close()

            self._engines[schema_name] = engine

        return self._engines[schema_name]

    def get_session_factory(self, schema_name: str) -> sessionmaker:
        """Get or create a session factory for a specific schema"""
        if schema_name not in self._session_factories:
            engine = self.get_engine(schema_name)
            self._session_factories[schema_name] = sessionmaker(
                bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
            )
        return self._session_factories[schema_name]

    def create_session(self, schema: str) -> Session:
        """
        Get a raw session object for a specific schema.
        This should be used only for short-lived operations and local testing.
        """
        session_factory = self.get_session_factory(schema)
        return session_factory()

    @contextmanager
    def get_session(
        self, schema_name: str = "public"
    ) -> Generator[Session, None, None]:
        """Get a database session for a specific schema"""
        session_factory = self.get_session_factory(schema_name)
        session = session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose_all(self):
        """Clean up all synchronous database connections"""
        for engine in self._engines.values():
            engine.dispose()


# --- Async Database Pool Manager (SQLAlchemy ORM) ---
class AsyncDatabasePoolManager:
    _instance = None
    _engines: Dict[str, any] = {}
    _session_factories: Dict[str, async_sessionmaker] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AsyncDatabasePoolManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self.database_url = os.getenv("ASYNC_DATABASE_URL")

        self.pool_size = int(os.getenv("ASYNC_DB_POOL_SIZE", "5"))
        self.max_overflow = int(os.getenv("ASYNC_DB_MAX_OVERFLOW", "10"))
        self.pool_timeout = int(os.getenv("ASYNC_DB_POOL_TIMEOUT", "30"))
        self.pool_recycle = int(os.getenv("ASYNC_DB_POOL_RECYCLE", "3600"))

        self._initialized = True

    def get_async_engine(self, schema_name: str):
        """Get or create an async engine for a specific schema"""
        if schema_name not in self._engines:
            engine = create_async_engine(
                self.database_url,
                # Connection pooling for better performance and resource management
                pool_size=self.pool_size,  # Number of connections to maintain in pool
                max_overflow=self.max_overflow,  # Maximum overflow connections allowed
                pool_timeout=self.pool_timeout,  # Seconds to wait before giving up on getting connection
                pool_recycle=self.pool_recycle,  # Recycle connections after this many seconds
                pool_pre_ping=True,
                echo=False,
                future=True,
                connect_args={"server_settings": {"search_path": schema_name}},
            )

            self._engines[schema_name] = engine

        return self._engines[schema_name]

    def get_session_factory(self, schema_name: str) -> async_sessionmaker:
        """Get or create an async session factory for a specific schema"""
        if schema_name not in self._session_factories:
            engine = self.get_async_engine(schema_name)
            self._session_factories[schema_name] = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
        return self._session_factories[schema_name]

    @asynccontextmanager
    async def get_session(
        self, schema_name: str = "public"
    ) -> AsyncGenerator[AsyncSession, None]:
        """Get an async database session for a specific schema"""
        session_factory = self.get_session_factory(schema_name)
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def dispose_all(self):
        """Clean up all async engines"""
        for engine in self._engines.values():
            await engine.dispose()
