#!/bin/bash

echo "Stopping existing container..."
docker stop $(docker ps -q --filter ancestor=hello:latest) 2>/dev/null || echo "No container running"

echo "Building new image..."
docker build --no-cache -t hello:latest .

if [ $? -eq 0 ]; then
    echo "Starting container..."
    docker run -p 666:666 -v "/Volumes/VERBATIM HD/David/Movies:/app/data:ro" hello:latest
else
    echo "Build failed!"
    exit 1
fi
