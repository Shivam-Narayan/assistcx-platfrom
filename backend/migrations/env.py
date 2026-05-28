import os
import re
from sqlalchemy import engine_from_config, pool, text
from alembic import context
from dotenv import load_dotenv

# Import models
from models import Base

# Load environment variables from .env file
load_dotenv("../../.env")
target_metadata = [Base.metadata]

# Overwrite the sqlalchemy.url from the alembic.ini file with DATABASE_URL from the environment
config = context.config
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.execute("CREATE EXTENSION IF NOT EXISTS citext;")
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    schema = context.get_x_argument(as_dictionary=True).get("tenant", "public")
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', schema):
        raise ValueError(f"Invalid schema name: {schema}")

    with connectable.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.commit()

        connection.dialect.default_schema_name = schema
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            # Ensure citext extension is available
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS citext;"))

            # Set the search path to include the schema and public
            connection.execute(text(f'SET search_path TO "{schema}", public'))

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS alembic_version (
                        version_num VARCHAR(32) NOT NULL,
                        CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                    )
                    """
                )
            )
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
