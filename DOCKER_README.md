# Book Assistant API - Docker Setup

This document explains how to build and run the Book Assistant API using Docker.

## Prerequisites

1. **Docker Desktop** installed and running
   - Download from: https://www.docker.com/products/docker-desktop/
   - Make sure Docker daemon is running

2. **Environment Variables**
   - Ensure your `teacher_agent/.env` file contains:
     ```
     ANTHROPIC_API_KEY=your_api_key_here
     ```

## Quick Start

### Using Docker Compose (Recommended)

1. **Build and run the container:**
   ```bash
   docker-compose up --build
   ```

2. **Access the API:**
   - API: http://localhost:8000
   - Swagger Docs: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

3. **Stop the container:**
   ```bash
   docker-compose down
   ```

### Using Docker CLI

1. **Build the image:**
   ```bash
   docker build -t book-assistant-api .
   ```

2. **Run the container:**
   ```bash
   docker run -d \
     --name book-assistant \
     -p 8000:8000 \
     book-assistant-api
   ```

3. **Check logs:**
   ```bash
   docker logs book-assistant
   ```

4. **Stop and remove the container:**
   ```bash
   docker stop book-assistant
   docker rm book-assistant
   ```

## API Endpoints

Once running, you can test the API:

### Health Check
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "agent": "book_assistant",
  "available_books": ["math-1", "math-2"]
}
```

### Simple Query
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What is on page 5 of math-1?"}'
```

### Detailed Query with Session
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is on page 5 of math-1?",
    "user_id": "user_123",
    "session_id": null
  }'
```

## Docker Image Details

- **Base Image:** Python 3.11 slim
- **Port:** 8000
- **User:** Non-root (appuser)
- **Health Check:** Every 30s on `/health` endpoint
