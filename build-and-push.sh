#!/bin/bash

# Docker Build and Push Script for Bakaloria Agent
# This script builds the Docker image locally and pushes it to Docker Hub

# Configuration - Update these values
DOCKER_USERNAME="your-dockerhub-username"  # Replace with your Docker Hub username
IMAGE_NAME="bakaloria-agent"
TAG="latest"

# Full image name
FULL_IMAGE_NAME="$DOCKER_USERNAME/$IMAGE_NAME:$TAG"

echo "========================================="
echo "Building and Pushing Bakaloria Agent"
echo "========================================="
echo ""

# Step 1: Check if user is logged in to Docker Hub
echo "Step 1: Checking Docker Hub login status..."
if ! docker info 2>/dev/null | grep -q "Username"; then
    echo "You are not logged in to Docker Hub."
    echo "Please run: docker login"
    echo "Then run this script again."
    exit 1
fi

# Step 2: Build the Docker image
echo ""
echo "Step 2: Building Docker image..."
echo "Image: $FULL_IMAGE_NAME"
echo ""

docker build -t $FULL_IMAGE_NAME .

if [ $? -ne 0 ]; then
    echo "Error: Docker build failed!"
    exit 1
fi

echo "✓ Docker image built successfully!"

# Step 3: Push the image to Docker Hub
echo ""
echo "Step 3: Pushing image to Docker Hub..."
echo ""

docker push $FULL_IMAGE_NAME

if [ $? -ne 0 ]; then
    echo "Error: Docker push failed!"
    echo "Make sure you have:"
    echo "1. Logged in to Docker Hub (docker login)"
    echo "2. Created the repository on Docker Hub if it doesn't exist"
    echo "3. Have push permissions to the repository"
    exit 1
fi

echo ""
echo "========================================="
echo "✓ Success! Image pushed to Docker Hub"
echo "========================================="
echo ""
echo "Image available at: $FULL_IMAGE_NAME"
echo ""
echo "Next steps:"
echo "1. Update docker-compose.hostinger.yml with your image name"
echo "2. Deploy to Hostinger using the docker-compose.hostinger.yml file"
echo ""
