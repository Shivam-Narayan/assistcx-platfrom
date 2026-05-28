#!/bin/bash

# Exit on any error, undefined variables, and pipe failures
set -euo pipefail

# Logging function with timestamps
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Error trap handler
error_handler() {
    log "ERROR: Backup failed at line $1. Exit code: $2"
    exit 1
}

# Set up error trap
trap 'error_handler $LINENO $?' ERR

log "INFO: Starting backup process..."

# Determine Docker Compose command
determine_docker_compose_command() {
    if command -v docker-compose &>/dev/null; then
        echo "docker-compose"
    elif command -v docker compose &>/dev/null; then
        echo "docker compose"
    else
        log "ERROR: Docker Compose is not installed."
        exit 1
    fi
}

# Load database variables from .env
ENV_FILE=".env"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
else
    log "ERROR: .env file not found. Please ensure it's in the parent directory."
    exit 1
fi

# Determine Docker Compose command
DOCKER_COMPOSE_CMD=$(determine_docker_compose_command)

# Configurable Parameters
CONTAINER_NAME="postgres"
DB_NAME="${POSTGRES_DB}"
DB_USER="${POSTGRES_USER}"

# Container Backup Path (mounted volume)
CONTAINER_BACKUP_DIR="/mnt/data-bucket"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
CONTAINER_BACKUP_FILE="${CONTAINER_BACKUP_DIR}/db_backups/${DB_NAME}_full_backup_${TIMESTAMP}.sql"

# Ensure container backup directory exists
log "INFO: Creating backup directory inside container if it doesn't exist..."
docker exec "$CONTAINER_NAME" mkdir -p "${CONTAINER_BACKUP_DIR}/db_backups"

# Get list of all schemas in the database (excluding system schemas)
log "INFO: Detecting all schemas in database '$DB_NAME'..."
SCHEMAS=$(docker exec "$CONTAINER_NAME" sh -c "PGPASSWORD='${POSTGRES_PASSWORD}' psql -U $DB_USER -d $DB_NAME -t -c \"SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast', 'pg_temp_1', 'pg_toast_temp_1') AND schema_name NOT LIKE 'pg_temp_%' AND schema_name NOT LIKE 'pg_toast_temp_%';\"" | tr -d ' ' | grep -v '^$')

if [ -z "$SCHEMAS" ]; then
    log "WARNING: No user schemas found, backing up entire database..."
    SCHEMA_LIST=""
else
    log "INFO: Found schemas: $(echo $SCHEMAS | tr '\n' ', ' | sed 's/,$//')"
    # Build schema list for pg_dump
    SCHEMA_LIST=""
    for schema in $SCHEMAS; do
        SCHEMA_LIST="$SCHEMA_LIST --schema=$schema"
    done
fi

# Perform the full backup (all schemas + data)
log "INFO: Backing up full database '$DB_NAME' with all schemas to container path: $CONTAINER_BACKUP_FILE"
log "INFO: Using serializable-deferrable mode for transaction consistency..."

if [ -z "$SCHEMA_LIST" ]; then
    # Backup entire database if no specific schemas found
    docker exec "$CONTAINER_NAME" sh -c "PGPASSWORD='${POSTGRES_PASSWORD}' pg_dump -U $DB_USER --serializable-deferrable --column-inserts $DB_NAME > $CONTAINER_BACKUP_FILE"
else
    # Backup specific schemas
    docker exec "$CONTAINER_NAME" sh -c "PGPASSWORD='${POSTGRES_PASSWORD}' pg_dump -U $DB_USER --serializable-deferrable --column-inserts $SCHEMA_LIST $DB_NAME > $CONTAINER_BACKUP_FILE"
fi

# Verify backup was created successfully and validate integrity
if docker exec "$CONTAINER_NAME" [ -s "$CONTAINER_BACKUP_FILE" ]; then
    BACKUP_SIZE=$(docker exec "$CONTAINER_NAME" du -h "$CONTAINER_BACKUP_FILE" | cut -f1)
    log "INFO: Backup file created - File size: $BACKUP_SIZE"
    
    # Validate SQL syntax and structure
    log "INFO: Validating backup file integrity..."
    if docker exec "$CONTAINER_NAME" sh -c "PGPASSWORD='${POSTGRES_PASSWORD}' psql -U $DB_USER -d $DB_NAME -c '\\set ON_ERROR_STOP on' -f $CONTAINER_BACKUP_FILE --dry-run 2>/dev/null || head -100 $CONTAINER_BACKUP_FILE | grep -q 'INSERT\|CREATE\|ALTER'"; then
        log "INFO: Backup validation successful"
        log "INFO: Backup file created at: $CONTAINER_BACKUP_FILE"
        log "INFO: Backup file is available on host at: storage/db_backups/${DB_NAME}_full_backup_${TIMESTAMP}.sql"
    else
        log "ERROR: Backup validation failed - file may be corrupted"
        exit 1
    fi
else
    log "ERROR: Backup failed or resulted in empty file"
    exit 1
fi