#!/bin/bash

# Exit on any error, undefined variables, and pipe failures
set -euo pipefail

# Logging function with timestamps
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Error trap handler
error_handler() {
    log "ERROR: Restore failed at line $1. Exit code: $2"
    exit 1
}

# Set up error trap
trap 'error_handler $LINENO $?' ERR

log "INFO: Starting restore process..."

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

# Configuration from env or default
CONTAINER_NAME="postgres"
DB_NAME="${POSTGRES_DB}"
DB_USER="${POSTGRES_USER}"

BACKUP_DIR="./storage/db_backups"

# Interactive menu for backup selection
log "INFO: Choose restore option:"
echo "1) Restore from latest backup"
echo "2) Select specific backup file"
read -p "Enter your choice (1 or 2): " choice

case $choice in
    1)
        log "INFO: Looking for latest backup..."
        BACKUP_FILE=$(ls -t "$BACKUP_DIR/${DB_NAME}_full_backup_"*.sql 2>/dev/null | head -n 1)
        if [ -z "$BACKUP_FILE" ]; then
            log "ERROR: No backup file found in $BACKUP_DIR for database '$DB_NAME'"
            exit 1
        fi
        log "INFO: Using latest backup file: $(basename "$BACKUP_FILE")"
        ;;
    2)
        log "INFO: Available backup files:"
        backup_files=($(ls -t "$BACKUP_DIR/${DB_NAME}_full_backup_"*.sql 2>/dev/null))
        if [ ${#backup_files[@]} -eq 0 ]; then
            log "ERROR: No backup files found in $BACKUP_DIR for database '$DB_NAME'"
            exit 1
        fi
        
        for i in "${!backup_files[@]}"; do
            file_size=$(du -h "${backup_files[$i]}" | cut -f1)
            file_date=$(date -r "${backup_files[$i]}" '+%Y-%m-%d %H:%M:%S')
            echo "$((i+1))) $(basename "${backup_files[$i]}") - Size: $file_size - Date: $file_date"
        done
        
        read -p "Enter the number of the backup file to restore: " file_choice
        if [[ ! "$file_choice" =~ ^[0-9]+$ ]] || [ "$file_choice" -lt 1 ] || [ "$file_choice" -gt ${#backup_files[@]} ]; then
            log "ERROR: Invalid selection. Please enter a number between 1 and ${#backup_files[@]}"
            exit 1
        fi
        
        BACKUP_FILE="${backup_files[$((file_choice-1))]}"
        log "INFO: Using selected backup file: $(basename "$BACKUP_FILE")"
        ;;
    *)
        log "ERROR: Invalid choice. Please select 1 or 2."
        exit 1
        ;;
esac

# Validate backup file before restore
log "INFO: Validating backup file before restore..."
if [ ! -f "$BACKUP_FILE" ]; then
    log "ERROR: Backup file does not exist: $BACKUP_FILE"
    exit 1
fi

# Check if backup file contains valid SQL
if ! head -100 "$BACKUP_FILE" | grep -q 'INSERT\|CREATE\|ALTER'; then
    log "ERROR: Backup file appears to be invalid or corrupted"
    exit 1
fi

# Create a safety backup of current database before restore in the same location as normal backups
docker exec "$CONTAINER_NAME" mkdir -p "/mnt/data-bucket/db_backups"
SAFETY_BACKUP_FILE="/mnt/data-bucket/db_backups/safety_backup_${DB_NAME}_$(date +%Y%m%d_%H%M%S).sql"
log "INFO: Creating safety backup of current database..."
docker exec "$CONTAINER_NAME" sh -c "PGPASSWORD='${POSTGRES_PASSWORD}' pg_dump -U $DB_USER --serializable-deferrable $DB_NAME > $SAFETY_BACKUP_FILE"

if [ $? -ne 0 ]; then
    log "ERROR: Failed to create safety backup"
    exit 1
fi

log "INFO: Safety backup created at: $SAFETY_BACKUP_FILE"

# Setup required PostgreSQL extensions before restore
log "INFO: Setting up required PostgreSQL extensions..."

# Create citext extension (database-wide, available to all schemas)
log "INFO: Creating citext extension for database (available to all schemas)..."

# First ensure public schema exists, then create extension in it
docker exec -i "$CONTAINER_NAME" sh -c "PGPASSWORD='${POSTGRES_PASSWORD}' psql -U $DB_USER -d $DB_NAME -c 'CREATE SCHEMA IF NOT EXISTS public;'"
docker exec -i "$CONTAINER_NAME" sh -c "PGPASSWORD='${POSTGRES_PASSWORD}' psql -U $DB_USER -d $DB_NAME -c 'CREATE EXTENSION IF NOT EXISTS citext SCHEMA public;'"

if [ $? -eq 0 ]; then
    log "INFO: citext extension setup completed successfully (available to all schemas)"
else
    log "WARNING: citext extension setup failed, continuing with restore..."
fi

# Clean the backup file (remove pg_dump headers if any)
CLEANED_FILE="/tmp/cleaned_${DB_NAME}_restore.sql"
log "INFO: Cleaning backup file..."
grep -v "^pg_dump:" "$BACKUP_FILE" > "$CLEANED_FILE"

# Restore process using safer method
log "INFO: Starting database restore..."
log "INFO: Restoring data from: $(basename "$BACKUP_FILE")"

# Use transaction-safe restore
docker exec -i "$CONTAINER_NAME" sh -c "PGPASSWORD='${POSTGRES_PASSWORD}' psql -U $DB_USER -d $DB_NAME -c 'BEGIN;'" && \
cat "$CLEANED_FILE" | docker exec -i "$CONTAINER_NAME" sh -c "PGPASSWORD='${POSTGRES_PASSWORD}' psql -U $DB_USER -d $DB_NAME" && \
docker exec -i "$CONTAINER_NAME" sh -c "PGPASSWORD='${POSTGRES_PASSWORD}' psql -U $DB_USER -d $DB_NAME -c 'COMMIT;'"

if [ $? -ne 0 ]; then
    log "ERROR: Restore failed, rolling back..."
    docker exec -i "$CONTAINER_NAME" sh -c "PGPASSWORD='${POSTGRES_PASSWORD}' psql -U $DB_USER -d $DB_NAME -c 'ROLLBACK;'"
    log "INFO: Safety backup is available at: $SAFETY_BACKUP_FILE"
    exit 1
fi

log "INFO: Restore complete! Database '$DB_NAME' has been restored from $(basename "$BACKUP_FILE")"
log "INFO: Safety backup is available at: $SAFETY_BACKUP_FILE"
log "INFO: Host path: storage/db_backups/$(basename $SAFETY_BACKUP_FILE) (you can remove it manually if restore was successful)"

# Cleanup temporary file
rm -f "$CLEANED_FILE"
