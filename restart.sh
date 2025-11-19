#!/bin/bash

CONTAINER_NAME="filebrowser"

echo "Stopping and removing existing container..."
docker stop $CONTAINER_NAME 2>/dev/null || echo "No container running"
docker rm $CONTAINER_NAME 2>/dev/null || echo "No container to remove"

echo "Building new image..."
docker build -t hello:latest .

if [ $? -eq 0 ]; then
    echo "Starting container..."
    docker run -d \
        --name $CONTAINER_NAME \
        --restart unless-stopped \
        -p 666:666 \
        -v "/Volumes/VERBATIM HD/David/Movies:/app/data:ro" \
        -v filebrowser-db:/app/db \
        hello:latest

    echo "Container started successfully!"
    echo "View logs with: docker logs -f $CONTAINER_NAME"
else
    echo "Build failed!"
    exit 1
fi
