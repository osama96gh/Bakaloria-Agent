#!/bin/bash

# Docker Build and Push Script for Bakaloria Agent
# This script builds multi-architecture Docker images and pushes them to Docker Hub

# Configuration - Update these values
DOCKER_USERNAME="osama96gh"  # Your Docker Hub username
IMAGE_NAME="bakaloria-agent"
TAG="latest"

# Full image name
FULL_IMAGE_NAME="$DOCKER_USERNAME/$IMAGE_NAME:$TAG"

echo "========================================="
echo "Building and Pushing Bakaloria Agent"
echo "Multi-Architecture Build (AMD64 + ARM64)"
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

# Step 2: Create or use buildx builder
echo ""
echo "Step 2: Setting up buildx for multi-architecture..."
if ! docker buildx ls | grep -q "multiarch-builder"; then
    echo "Creating multiarch-builder..."
    docker buildx create --name multiarch-builder --use
else
    echo "Using existing multiarch-builder..."
    docker buildx use multiarch-builder
fi

# Step 3: Build and push multi-architecture image
echo ""
echo "Step 3: Building multi-architecture image..."
echo "Platforms: linux/amd64, linux/arm64"
echo "Image: $FULL_IMAGE_NAME"
echo ""

docker buildx build --platform linux/amd64,linux/arm64 -t $FULL_IMAGE_NAME --push .

if [ $? -ne 0 ]; then
    echo "Error: Docker build failed!"
    exit 1
fi

echo ""
echo "========================================="
echo "✓ Success! Multi-arch image pushed to Docker Hub"
echo "========================================="
echo ""
echo "Image available at: $FULL_IMAGE_NAME"
echo "Supported platforms:"
echo "  - linux/amd64 (for Hostinger, AWS, etc.)"
echo "  - linux/arm64 (for Mac M1/M2, ARM servers)"
echo ""
echo "Next steps:"
echo "1. Deploy to Hostinger using docker-compose.yml"
echo "2. Set ANTHROPIC_API_KEY in Hostinger's environment variables"
echo ""
