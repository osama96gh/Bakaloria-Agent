#!/usr/bin/env python3
"""FastAPI application for exposing the Book Assistant Agent as a REST API.

This module creates a FastAPI server that provides HTTP endpoints for interacting
with the ADK Book Assistant Agent.
"""

from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from teacher_agent import process_agent_query, ask_agent
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Book Assistant Agent API",
    description="REST API for interacting with the ADK Book Assistant Agent that helps users understand textbook content",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware for browser-based clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models for request/response
class QueryRequest(BaseModel):
    """Request model for agent queries."""
    query: str = Field(..., description="The question to ask the agent about book content")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")
    user_id: str = Field("default_user", description="User identifier for session management")
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "What is on page 5 of math-1?",
                "session_id": None,
                "user_id": "user_123"
            }
        }


class QueryResponse(BaseModel):
    """Response model for agent queries."""
    response: str = Field(..., description="The agent's response in Arabic")
    session_id: str = Field(..., description="Session ID for future queries")
    status: str = Field(..., description="Status of the query (success/error)")
    error: Optional[str] = Field(None, description="Error message if status is error")
    
    class Config:
        json_schema_extra = {
            "example": {
                "response": "محتوى الصفحة 5 من كتاب الرياضيات...",
                "session_id": "fc7b9048-cc0d-4096-9293-758f8889258f",
                "status": "success",
                "error": None
            }
        }


class SimpleQueryRequest(BaseModel):
    """Simplified request model for quick queries."""
    query: str = Field(..., description="The question to ask the agent")
    session_id: Optional[str] = Field(None, description="Optional session ID for conversation continuity")
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "Explain page 10 of math-2",
                "session_id": None
            }
        }


class SimpleQueryResponse(BaseModel):
    """Simplified response model."""
    response: str = Field(..., description="The agent's response")
    
    class Config:
        json_schema_extra = {
            "example": {
                "response": "الصفحة 10 من كتاب math-2 تحتوي على..."
            }
        }


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str = Field(..., description="Health status")
    agent: str = Field(..., description="Agent name")
    available_books: list[str] = Field(..., description="List of available books")


@app.get("/", tags=["General"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Book Assistant Agent API",
        "version": "1.0.0",
        "description": "REST API for the ADK Book Assistant Agent",
        "endpoints": {
            "docs": "/docs",
            "redoc": "/redoc",
            "health": "/health",
            "query": "/query",
            "simple_query": "/ask"
        }
    }


@app.get("/health", response_model=HealthResponse, tags=["General"])
async def health_check():
    """Health check endpoint to verify the API is running."""
    return HealthResponse(
        status="healthy",
        agent="book_assistant",
        available_books=["math-1", "math-2"]
    )


@app.post("/query", response_model=QueryResponse, tags=["Agent"])
async def query_agent(request: QueryRequest):
    """
    Send a query to the Book Assistant Agent.
    
    This endpoint processes queries through the ADK agent and returns
    detailed responses including session management for conversation continuity.
    
    The agent:
    - Analyzes book page images using vision capabilities
    - Responds in Arabic language
    - Maintains conversation context through sessions
    - Can retrieve pages from math-1 and math-2 books
    """
    try:
        logger.info(f"Processing query: {request.query[:50]}... (session: {request.session_id})")
        
        # Call the agent service
        result = await process_agent_query(
            query=request.query,
            user_id=request.user_id,
            session_id=request.session_id
        )
        
        # Return the response
        return QueryResponse(
            response=result["response"],
            session_id=result["session_id"],
            status=result["status"],
            error=result.get("error")
        )
        
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ask", response_model=SimpleQueryResponse, tags=["Agent"])
async def ask_agent_simple(request: SimpleQueryRequest):
    """
    Simplified endpoint for quick queries to the agent.
    
    This endpoint provides a simpler interface that returns just the response text.
    Useful for quick questions without needing full session management details.
    """
    try:
        logger.info(f"Processing simple query: {request.query[:50]}...")
        
        # Call the simple agent interface
        response = await ask_agent(
            query=request.query,
            session_id=request.session_id
        )
        
        return SimpleQueryResponse(response=response)
        
    except Exception as e:
        logger.error(f"Error in simple query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query/batch", tags=["Agent"])
async def batch_query(queries: list[QueryRequest]):
    """
    Process multiple queries in batch.
    
    Useful for processing multiple questions at once.
    Each query can have its own session_id for different conversations.
    """
    results = []
    
    for query_request in queries:
        try:
            result = await process_agent_query(
                query=query_request.query,
                user_id=query_request.user_id,
                session_id=query_request.session_id
            )
            
            results.append(QueryResponse(
                response=result["response"],
                session_id=result["session_id"],
                status=result["status"],
                error=result.get("error")
            ))
        except Exception as e:
            results.append(QueryResponse(
                response="",
                session_id=query_request.session_id or "",
                status="error",
                error=str(e)
            ))
    
    return results


# Optional: Streaming endpoint using Server-Sent Events
from fastapi.responses import StreamingResponse
import json


@app.post("/query/stream", tags=["Agent"])
async def stream_query(request: QueryRequest):
    """
    Stream the agent's response as it's generated.
    
    This endpoint uses Server-Sent Events (SSE) to stream partial responses
    as they're generated by the agent. Useful for real-time UI updates.
    
    Note: This is a placeholder for future implementation when the service
    supports streaming responses.
    """
    async def generate():
        try:
            # For now, we'll just return the full response as a single event
            # In the future, this could be enhanced to stream partial responses
            result = await process_agent_query(
                query=request.query,
                user_id=request.user_id,
                session_id=request.session_id
            )
            
            # Send the response as SSE
            yield f"data: {json.dumps(result)}\n\n"
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            error_data = {"error": str(e), "status": "error"}
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    # Run the server
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
