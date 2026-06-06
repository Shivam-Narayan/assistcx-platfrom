#!/bin/bash
 
# Function to display usage information
show_help() {
    echo "Usage: $0 [OPTION]"
    echo "Manage Docker services for the platform."
    echo
    echo "Options:"
    echo "  --update         Update AssistCX images to latest and start services"
    echo "  --update-all     Update all images to latest and start services"
    echo "  --latest         Use latest image tags and start services"
    echo "  --X.Y.Z         Use specific version X.Y.Z of images and start services"
    echo "  --down           Stop and remove all services"
    echo "  --staged        Enable staged startup sequence (recommended for production)"
    echo "  --fast          Disable staged startup sequence (recommended for development)"
    echo "  -h, --help      Display this help message"
    echo
    echo "Examples:"
    echo "  $0 --fast               # Quick start without staged startup"
    echo "  $0 --down               # Stop and remove all services"
    echo "  $0 --update             # Update with staged startup"
    echo "  $0 --latest             # Latest version with staged startup"
    echo "  $0 --1.2.3              # Specific version with staged startup"
    echo
    echo "If no option is provided, the script will start or restart services with current images."
}
 
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

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
 
# Function to perform Docker login
docker_login() {
    # Check if we have the environment variables
    if [[ -z "$DOCKER_USER" || -z "$DOCKER_ACCESS_TOKEN" ]]; then
        echo "Docker credentials not found in .env file at ${PROJECT_ROOT}/.env"
        echo "Please set DOCKER_USER and DOCKER_ACCESS_TOKEN."
        exit 1
    fi
 
    echo "Logging in to Docker Hub as $DOCKER_USER..."
    if ! echo "$DOCKER_ACCESS_TOKEN" | docker login --username "$DOCKER_USER" --password-stdin; then
        echo "Docker login failed. Please check your credentials in ${PROJECT_ROOT}/.env"
        exit 1
    fi
    echo "Docker login successful"
}

# Function to configure storage mount volume
configure_storage_mount() {
    # Set up the storage mount volume configuration
    if [ -n "$STORAGE_MOUNT_POINT" ]; then
        # Check for the operating system
        if [[ "$(uname)" == "Darwin" ]]; then
            # macOS uses :delegated for mount propagation
            MOUNT_OPTION=":delegated"
        else
            # Linux uses :rshared for mount propagation
            MOUNT_OPTION=":rshared"
        fi
 
        export STORAGE_MOUNT_VOLUME="$STORAGE_MOUNT_POINT:/mnt/data-bucket$MOUNT_OPTION"
        echo "Storage mount enabled: $STORAGE_MOUNT_POINT"
    else
        export STORAGE_MOUNT_VOLUME="/dev/null:/mnt/data-bucket"
        echo "Storage mount disabled (using /dev/null)"
    fi
}
 
# Multiple storage mounts with docker-compose.override.yml
configure_storage_mount_v2() {
    local mounts_file="${PROJECT_ROOT}/mounts.json"
    local override_file="${PROJECT_ROOT}/docker-compose.override.yml"
    
    # Services that need storage mounts
    local services_with_storage=(
        "backend-core" "attachment-worker" "knowledge-worker"
        "agent-worker" "backend-worker" "celery-beat"
    )
    
    if [ ! -f "$mounts_file" ]; then
        echo "No mounts.json found, using single mount configuration..."
        rm -f "$override_file"
        export STORAGE_MOUNT_VOLUME="${STORAGE_MOUNT_VOLUME:-/dev/null:/mnt/data-bucket}"
        echo "Using storage mount: $STORAGE_MOUNT_VOLUME"
        return
    fi
    
    echo "Found mounts.json, configuring multiple storage mounts..."
    
    # Validate dependencies and JSON
    if ! command -v jq &> /dev/null; then
        echo "Error: jq is required but not installed. Please install jq first."
        exit 1
    fi
    
    if ! jq empty "$mounts_file" 2>/dev/null; then
        echo "Error: Invalid JSON format in mounts.json"
        exit 1
    fi
    
    # Extract mount information
    local mount_count=$(jq '. | length' "$mounts_file")
    local json_content=$(jq -c '.' "$mounts_file")
    local mount_option=$([ "$(uname)" = "Darwin" ] && echo ":delegated" || echo ":rshared")
    
    # Validate that at least one mount is provided
    if [ "$mount_count" -eq 0 ]; then
        echo "Error: No mount entries found in mounts JSON file. At least one storage mount must be provided."
        exit 1
    fi
    
    # Validate all host paths
    echo "Validating host paths..."
    while IFS= read -r host_path; do
        if [ ! -d "$host_path" ]; then
            echo "Error: Host path does not exist or is not accessible: $host_path"
            echo "Please ensure all host paths in mounts.json exist before starting the services."
            exit 1
        fi
        echo "✓ Host path validated: $host_path"
    done < <(jq -r '.[].host' "$mounts_file")
    
    echo "Generating override for $mount_count storage mounts..."
    
    # Generate services YAML content
    local services_yaml=""
    for service in "${services_with_storage[@]}"; do
        local has_backend_volume=$(grep -A 10 "container_name: $service" "${PROJECT_ROOT}/docker-compose.yml" | grep -c "./backend:/app" || true)
        
        services_yaml+="  $service:"$'\n'
        services_yaml+="    volumes:"$'\n'
        
        # Add backend volume if present in original
        if [ "$has_backend_volume" -gt 0 ]; then
            services_yaml+="      - ./backend:/app"$'\n'
        fi
        
        # Add all storage mounts
        while IFS= read -r mount_line; do
            services_yaml+="      - $mount_line"$'\n'
        done < <(jq -r '.[] | "\(.host):\(.container)'"$mount_option"'"' "$mounts_file")
        
        # Add environment variables
        services_yaml+="    environment:"$'\n'
        services_yaml+="      - STORAGE_MOUNT_POINTS=$json_content"$'\n'
        
        echo "Configured storage mounts for: $service"
    done
    
    # Generate the complete YAML file
    cat > "$override_file" << EOF
# Auto-generated override for multiple storage mounts
services:
$services_yaml
EOF
    
    # Validate generated YAML
    if ! $DOCKER_COMPOSE_CMD -f "${PROJECT_ROOT}/docker-compose.yml" -f "$override_file" config > /dev/null 2>&1; then
        echo "Error: Generated invalid YAML"
        echo "Docker compose validation output:"
        $DOCKER_COMPOSE_CMD -f "${PROJECT_ROOT}/docker-compose.yml" -f "$override_file" config 2>&1 || true
        echo "Removing override file"
        rm -f "$override_file"
        exit 1
    fi
    
    # Set backward compatibility variable
    local first_mount=$(jq -r '.[0] | "\(.host):\(.container)"' "$mounts_file")
    export STORAGE_MOUNT_VOLUME="${first_mount}${mount_option}"
    
    echo "Generated docker-compose.override.yml with $mount_count storage mounts"
}
 
# Function to remove all project-related Docker images
remove_project_images() {
    echo "Removing all local Docker images for current project..."
    $DOCKER_COMPOSE_CMD config | grep 'image:' | awk '{ print $2 }' | sort | uniq | xargs -r docker rmi
}

# Function to remove only AssistCX Docker images
remove_assistcx_images() {
    echo "Removing AssistCX Docker images..."
    docker rmi sshivam6495/assistcx-backend:${IMAGE_VERSION:-latest} 2>/dev/null || true
    docker rmi sshivam6495/assistcx-web:${IMAGE_VERSION:-latest} 2>/dev/null || true
}

# Function to start services quickly (development mode)
start_services_quick() {
    echo "Starting Docker Compose services (quick mode)..."
    $DOCKER_COMPOSE_CMD up --force-recreate -d
    if [ $? -ne 0 ]; then
        echo "Failed to start services. Check if the specified image version exists."
        exit 1
    fi
}
 
# Function to start services gracefully (production mode)
start_services_staged() {
    echo "Starting services in staged sequence..."
    
    # Stage 1: Core Infrastructure
    echo "Stage 1: Starting databases and message broker..."
    $DOCKER_COMPOSE_CMD up --force-recreate -d postgres redis
    echo "Waiting for databases to initialize..."
    sleep 10
    
    # Stage 2: Starting data infrastructure services
    echo "Stage 2: Starting additional infrastructure services (etcd, milvus, minio)..."
    $DOCKER_COMPOSE_CMD up --force-recreate -d etcd milvus minio
    sleep 10  
    
    # Stage 3: Core services
    echo "Stage 3: Starting core services..."
    for service in backend-core attachment-worker agent-worker backend-worker knowledge-worker; do
        echo "Starting $service..."
        $DOCKER_COMPOSE_CMD up --force-recreate -d $service
        sleep 5
    done
    
    # Stage 4: Beat scheduler
    echo "Stage 4: Starting celery beat..."
    $DOCKER_COMPOSE_CMD up --force-recreate -d celery-beat
    sleep 5
    
    # Stage 5: Frontend
    echo "Stage 5: Starting web application..."
    $DOCKER_COMPOSE_CMD up --force-recreate -d web-app
    sleep 5

    # Stage 6: Auxiliary Services
    echo "Stage 6: Starting auxiliary services..."
    $DOCKER_COMPOSE_CMD up --force-recreate -d flower redis-commander pgadmin

    # Stage 7: Monitoring
    echo "Stage 7: Starting monitoring stack..."
    $DOCKER_COMPOSE_CMD up --force-recreate -d loki promtail grafana prometheus cadvisor
    sleep 10
    
    echo "All services started successfully."
}
 
# Function to check if image exists
check_image_exists() {
    local image_name=$1
    local version=$2
    if ! docker pull "$image_name:$version" &>/dev/null; then
        echo "Error: Image $image_name:$version does not exist."
        return 1
    fi
    return 0
}
 
# Function to load env
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
 
# Function to stop services
stop_services() {
    echo "Stopping Docker Compose services..."
    $DOCKER_COMPOSE_CMD stop
    echo "Removing stopped containers..."
    $DOCKER_COMPOSE_CMD rm -f
}
 
# Set the Docker Compose command
DOCKER_COMPOSE_CMD=$(determine_docker_compose_command)
 
# Parse command line arguments
STAGED_MODE=true  # Default to true
COMMAND=""
VERSION=""
 
while [[ $# -gt 0 ]]; do
    case "$1" in
        --staged)
            STAGED_MODE=true
            ;;
        --fast)
            STAGED_MODE=false
            ;;
        --update|--update-all|--latest|--down)
            COMMAND="$1"
            ;;
        --[0-9]*)
            COMMAND="--version"
            VERSION="${1#--}"
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
    shift
done
 

# Initialize environment (decrypt, load, determine dev mode, encrypt if needed)
initialize_env

# Handle --down command early (before other setup)
if [ "$COMMAND" = "--down" ]; then
    echo "Stopping and removing all platform containers..."
    $DOCKER_COMPOSE_CMD down
    exit 0
fi

# Configure storage mount
configure_storage_mount_v2
# Login to docker
docker_login
 
# Main logic
case "$COMMAND" in
    --update)
        stop_services
        remove_assistcx_images
        export IMAGE_VERSION=latest
        if [ "$STAGED_MODE" = true ]; then
            start_services_staged
        else
            start_services_quick
        fi
        ;;
    --update-all)
        stop_services
        remove_project_images
        export IMAGE_VERSION=latest
        if [ "$STAGED_MODE" = true ]; then
            start_services_staged
        else
            start_services_quick
        fi
        ;;
    --latest)
        stop_services
        export IMAGE_VERSION=latest
        if [ "$STAGED_MODE" = true ]; then
            start_services_staged
        else
            start_services_quick
        fi
        ;;
    --version)
        stop_services
        if check_image_exists "sshivam6495/assistcx-backend" "$VERSION" &&
           check_image_exists "sshivam6495/assistcx-web" "$VERSION"; then
            export IMAGE_VERSION=$VERSION
            if [ "$STAGED_MODE" = true ]; then
                start_services_staged
            else
                start_services_quick
            fi
        else
            echo "One or more required images for version $VERSION do not exist."
            exit 1
        fi
        ;;
    "")
        # Default behavior when no command is provided
        if $DOCKER_COMPOSE_CMD ps | grep -q "Up"; then
            echo "Restarting Docker Compose services..."
            $DOCKER_COMPOSE_CMD restart
        else
            if [ "$STAGED_MODE" = true ]; then
                start_services_staged
            else
                start_services_quick
            fi
        fi
        ;;
esac

# Handle domain configuration
if [ -n "$DOMAIN_NAME" ]; then
    echo "Domain name detected in environment. Running domain setup script..."
    "${PROJECT_ROOT}/scripts/domain.sh"
else
    echo "Domain setup not needed. Stopping and removing Nginx container..."
    $DOCKER_COMPOSE_CMD stop nginx
    $DOCKER_COMPOSE_CMD rm -f nginx
fi

# Encrypt and remove the .env file only if not in dev mode
if [ "$DEV_MODE" = false ]; then
    encrypt_env
    echo "Cleaning up: removing .env file..."
    rm -f "${PROJECT_ROOT}/.env"
else
    echo "Keeping .env file (ENVIRONMENT is local)"
fi
