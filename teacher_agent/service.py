# Copyright 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Service module for exposing the Book Assistant Agent as a Python function.

This module provides a programmatic interface to the ADK agent, following the
ADK Runtime's Event Loop pattern for proper state management and event processing.
"""

from typing import Optional, Dict, Any
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from .agent import root_agent


async def process_agent_query(
    query: str,
    user_id: str = "default_user",
    session_id: Optional[str] = None,
    app_name: str = "book_assistant"
) -> Dict[str, Any]:
    """Process a user query through the Book Assistant Agent.
    
    This function exposes the ADK agent as a Python function, following the
    ADK Runtime's Event Loop pattern. It handles:
    - Session creation/management via SessionService
    - Event processing through the Runner
    - State commitment through the event loop
    - Response collection from yielded events
    
    Args:
        query: The user's question about book content
        user_id: User identifier for session management
        session_id: Optional session ID for conversation continuity
        app_name: Application name for session management
        
    Returns:
        Dictionary containing:
            - response: The agent's text response
            - session_id: Session ID for future queries
            - status: "success" or "error"
            - error: Error message if status is "error"
            
    Example:
        >>> import asyncio
        >>> from teacher_agent.service import process_agent_query
        >>> 
        >>> async def main():
        ...     result = await process_agent_query("What is on page 5 of math-1?")
        ...     print(result["response"])
        ...     # Use session_id for follow-up questions
        ...     follow_up = await process_agent_query(
        ...         "Can you explain more?", 
        ...         session_id=result["session_id"]
        ...     )
        ...     print(follow_up["response"])
        ...
        >>> asyncio.run(main())
    """
    try:
        # Initialize session service
        session_service = InMemorySessionService()
        
        # Create or retrieve session
        if session_id:
            # Try to get existing session
            session = await session_service.get_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id
            )
            if not session:
                # Session not found, create new one
                session = await session_service.create_session(
                    app_name=app_name,
                    user_id=user_id
                )
        else:
            # Create new session
            session = await session_service.create_session(
                app_name=app_name,
                user_id=user_id
            )
        
        # Initialize Runner with the agent and session service
        runner = Runner(
            agent=root_agent,
            app_name=app_name,
            session_service=session_service
        )
        
        # Create user message content
        content = types.Content(
            role='user',
            parts=[types.Part(text=query)]
        )
        
        # Collect response parts
        response_parts = []
        
        # Execute the agent through the Runner's event loop
        # The Runner will:
        # 1. Append the user query to session history
        # 2. Call agent.run_async(context)
        # 3. Process events yielded by the agent
        # 4. Commit state changes via SessionService
        # 5. Forward events to us
        events = runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=content
        )
        
        # Process events from the agent
        async for event in events:
            # Each event has been processed by the Runner before we receive it
            # State changes in event.actions have been committed
            
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_parts.append(part.text)
            
            # The final response is marked by is_final_response()
            if event.is_final_response():
                break
        
        # Combine all response parts
        final_response = "".join(response_parts)
        
        return {
            "response": final_response,
            "session_id": session.id,
            "status": "success",
            "error": None
        }
        
    except Exception as e:
        return {
            "response": "",
            "session_id": session_id,
            "status": "error",
            "error": str(e)
        }


async def ask_agent(
    query: str,
    session_id: Optional[str] = None
) -> str:
    """Simple interface to ask the Book Assistant Agent a question.
    
    This is a convenience wrapper around process_agent_query that
    returns just the text response.
    
    Args:
        query: The question about book content
        session_id: Optional session ID for conversation continuity
        
    Returns:
        The agent's response as a string
        
    Example:
        >>> import asyncio
        >>> from teacher_agent.service import ask_agent
        >>> 
        >>> response = await ask_agent("What is on page 10 of math-2?")
        >>> print(response)
    """
    result = await process_agent_query(query, session_id=session_id)
    
    if result["status"] == "success":
        return result["response"]
    else:
        return f"Error: {result['error']}"


# Export main interfaces
__all__ = [
    'process_agent_query',
    'ask_agent'
]
