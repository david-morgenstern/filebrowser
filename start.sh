#!/bin/bash

CONTAINER_NAME="filebrowser"
IMAGE="daveyo89/filebrowser:latest"
DATA_PATH="/Volumes/VERBATIM HD/David/Movies"

echo "Stopping and removing existing container..."
docker stop $CONTAINER_NAME 2>/dev/null || echo "No container running"
docker rm $CONTAINER_NAME 2>/dev/null || echo "No container to remove"

echo "Starting filebrowser container..."
docker run -d \
  --name $CONTAINER_NAME \
  --restart unless-stopped \
  -p 666:666 \
  -v "$DATA_PATH:/app/data:ro" \
  -v filebrowser-db:/app/db \
  $IMAGE

if [ $? -eq 0 ]; then
    echo "✓ Filebrowser started successfully!"
    echo ""
    echo "Access it at: http://localhost:666"
    echo "View logs: docker logs -f $CONTAINER_NAME"
else
    echo "✗ Failed to start container"
    exit 1
fi
