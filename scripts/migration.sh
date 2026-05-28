#!/bin/bash

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Function to initialize environment
initialize_env() {
    # Decrypt .env.enc if .env doesn't exist
    if [ ! -f "$PROJECT_ROOT/.env" ] && [ -f "$PROJECT_ROOT/.env.enc" ]; then
        echo "Decrypting .env.enc..."
        age --decrypt -o "$PROJECT_ROOT/.env" "$PROJECT_ROOT/.env.enc" || exit 1
    fi

    # Load environment variables from .env file (strip inline comments)
    if [ -f "${PROJECT_ROOT}/.env" ]; then
        echo "Loading environment variables from ${PROJECT_ROOT}/.env"
        export $(grep -v '^#' "${PROJECT_ROOT}/.env" | sed 's/#.*$//' | xargs)
    else
        echo "Error: .env file not found in the project root directory (${PROJECT_ROOT})"
        exit 1
    fi

    # Determine if we're in dev mode
    if [ -n "$ENVIRONMENT" ] && [ "$ENVIRONMENT" = "local" ]; then
        export DEV_MODE=true
        echo "Running in development mode (local environment)"
    else
        export DEV_MODE=false
    fi
}

# Function to encrypt env file
encrypt_env() {
    if [ -f "$PROJECT_ROOT/.env" ]; then
        echo "Encrypting .env for security..."
        age --passphrase -o "$PROJECT_ROOT/.env.enc" "$PROJECT_ROOT/.env" || exit 1
    fi
}

# Function to determine Docker Compose command
determine_docker_compose_command() {
    if command -v docker-compose &>/dev/null; then
        echo "docker-compose"
    elif command -v docker compose &>/dev/null; then
        echo "docker compose"
    else
        echo "Docker Compose is not installed." >&2
        exit 1
    fi
}

# Determine the Docker Compose command
DOCKER_COMPOSE_CMD=$(determine_docker_compose_command)

# Initialize environment (decrypt, load, determine dev mode, encrypt if needed)
initialize_env

# Container name
container_name="backend-core"

# Check if schema names are provided as arguments
if [ "$#" -lt 1 ]; then
    echo "No schema names provided. Auto-discovering all schemas from Postgres..."
    # Mirror the exclusion list used in backend/migrations/db_patch.sql
    discovered=$($DOCKER_COMPOSE_CMD exec -T postgres psql -tAq \
        -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast', 'pg_temp_1', 'pg_toast_temp_1') ORDER BY schema_name;")
    if [ $? -ne 0 ] || [ -z "$discovered" ]; then
        echo "Failed to auto-discover schemas (or none found). Falling back to 'public'."
        schemas=("public")
    else
        schemas=()
        while IFS= read -r s; do
            [ -n "$s" ] && schemas+=("$s")
        done <<< "$discovered"
        echo "Discovered schemas: ${schemas[*]}"
    fi
else
    schemas=("$@")
fi

# Run migrations for each schema
failed_schemas=()
for schema in "${schemas[@]}"; do
    echo "Running database migrations for schema: $schema..."

    # Run Alembic migrations
    echo "Running Alembic migrations..."
    $DOCKER_COMPOSE_CMD exec -T $container_name alembic -x tenant=$schema upgrade head
    if [ $? -ne 0 ]; then
        echo "Alembic migration for schema $schema failed." >&2
        failed_schemas+=("$schema")
        continue
    else
        echo "Alembic migration for schema $schema completed successfully."
    fi

    # Run checkpointer migrations with schema argument
    echo "Running checkpointer migrations..."
    $DOCKER_COMPOSE_CMD exec -T $container_name python /app/agents/shared_utils/checkpointer.py --schema $schema
    if [ $? -ne 0 ]; then
        echo "Checkpointer migration for schema $schema failed." >&2
        failed_schemas+=("$schema")
        continue
    else
        echo "Checkpointer migration for schema $schema completed successfully."
    fi
done

if [ ${#failed_schemas[@]} -gt 0 ]; then
    echo "Migration FAILED for schemas: ${failed_schemas[*]}" >&2
    echo "Migration succeeded for remaining schemas. Re-run with failed schemas to retry."
    exit 1
fi

echo "All database migrations completed successfully."

# Apply post-migration SQL patch (runs once across all schemas — patch handles its own schema loop)
PATCH_FILE="$PROJECT_ROOT/backend/migrations/db_patch.sql"
if [ -f "$PATCH_FILE" ]; then
    echo "Applying db_patch.sql..."
    $DOCKER_COMPOSE_CMD exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$PATCH_FILE"
    if [ $? -ne 0 ]; then
        echo "db_patch.sql failed." >&2
        exit 1
    fi
    echo "db_patch.sql applied successfully."
else
    echo "Warning: $PATCH_FILE not found, skipping patch."
fi

# Encrypt and remove the .env file only if not in dev mode
if [ "$DEV_MODE" = false ]; then
    encrypt_env
    echo "Cleaning up: removing .env file..."
    rm -f "${PROJECT_ROOT}/.env"
else
    echo "Keeping .env file (ENVIRONMENT is local)"
fi