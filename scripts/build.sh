#!/bin/bash

# Get the absolute path of the root directory
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

# Function to display usage information
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  --latest             Use 'latest' as the version tag"
    echo "  --bump TYPE          Bump version (TYPE: major, minor, patch)"
    echo "  --amd                Build for AMD64 platform (default is ARM64)"
    echo "  --push               Push the images to the registry"
    echo "  -h, --help           Display this help message"
}

# Initialize variables
VERSION=""
PLATFORM="--platform=linux/arm64" # Default to ARM64
BUMP_TYPE=""
CREATE_LATEST=false
PUSH_IMAGES=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --latest)
            CREATE_LATEST=true
            shift
            ;;
        --bump)
            BUMP_TYPE="$2"
            CREATE_LATEST=true
            shift 2
            ;;
        --amd)
            PLATFORM="--platform=linux/amd64"
            shift
            ;;
        --push)
            PUSH_IMAGES=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Handle version bumping if requested
if [ -n "$BUMP_TYPE" ]; then
    NEW_VERSION=$(python "$ROOT_DIR/backend/version.py" "$BUMP_TYPE")
    echo "Bumped version to: $NEW_VERSION"
    git add "$ROOT_DIR/backend/__init__.py"
    git commit -m "Bump version to $NEW_VERSION"
    VERSION=$NEW_VERSION
else
    # Extract version from version.py
    VERSION=$(python "$ROOT_DIR/backend/version.py")
    echo "Using current version from __init__.py: $VERSION"
fi

echo "Building platform version: $VERSION with $(echo $PLATFORM | cut -d'=' -f2)"

# Define your image name with version tag
BACKEND_BASE_IMAGE="vikasr111/assistcx-backend:$VERSION"

# Define latest tag name
BACKEND_BASE_LATEST="vikasr111/assistcx-backend:latest"

# Ensure Docker CLI is set to use Buildx
export DOCKER_CLI_EXPERIMENTAL=enabled

# Build and tag the backend base image
echo "Building backend core image..."
docker buildx build $PLATFORM -t $BACKEND_BASE_IMAGE -f "$ROOT_DIR/backend/Dockerfile" --target backend-core "$ROOT_DIR/backend" --load

# Always create 'latest' tag
echo "Creating 'latest' tag..."
docker tag $BACKEND_BASE_IMAGE $BACKEND_BASE_LATEST

# If PUSH_IMAGES is true, push the images
if [ "$PUSH_IMAGES" = true ]; then
    echo "Pushing versioned and 'latest' tags..."
    docker push $BACKEND_BASE_IMAGE
    docker push $BACKEND_BASE_LATEST
fi

echo "Build process completed."

# If we bumped the version, create and push a git tag
if [ -n "$BUMP_TYPE" ]; then
    git tag -a "v$NEW_VERSION" -m "Release version $NEW_VERSION"
    git push origin "v$NEW_VERSION"
    echo "Created and pushed tag v$NEW_VERSION"
fi