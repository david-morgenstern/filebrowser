#!/bin/bash

# Publish filebrowser Docker image to daveyo89/filebrowser
# Usage: ./publish.sh [version]
# Examples:
#   ./publish.sh          # builds and pushes as 'latest'
#   ./publish.sh v1.05    # builds and pushes as 'v1.05' and 'latest'

IMAGE_NAME="daveyo89/filebrowser"
VERSION="${1:-latest}"

echo "Building Docker image: ${IMAGE_NAME}:${VERSION}"

# Build the image
docker build -t "${IMAGE_NAME}:${VERSION}" .

if [ $? -ne 0 ]; then
    echo "Build failed!"
    exit 1
fi

# If a version was specified, also tag as latest
if [ "$VERSION" != "latest" ]; then
    docker tag "${IMAGE_NAME}:${VERSION}" "${IMAGE_NAME}:latest"
    echo "Tagged as ${IMAGE_NAME}:latest"
fi

# Push the image(s)
echo "Pushing ${IMAGE_NAME}:${VERSION}"
docker push "${IMAGE_NAME}:${VERSION}"

if [ "$VERSION" != "latest" ]; then
    echo "Pushing ${IMAGE_NAME}:latest"
    docker push "${IMAGE_NAME}:latest"
fi

echo "Done! Published ${IMAGE_NAME}:${VERSION}"
