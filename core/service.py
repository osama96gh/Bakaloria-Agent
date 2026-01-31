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

"""Service module for exposing the customizable Bulbul agent as a Python function.

This module provides a programmatic interface to the ADK agent with dynamic
persona configuration, following the ADK Runtime's Event Loop pattern.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any, List

from google.adk.agents.llm_agent import Agent
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.genai import types

from .persona_service import PersonaService
from .memory_service import MemoryService
from .tools.persona_tool import init_persona_tool, update_persona
from .tools.memory_tool import init_memory_tool, manage_memory

logger = logging.getLogger(__name__)

# Module-level services - persist across the app lifecycle
_supabase_url = os.getenv("SUPABASE_URL")
_supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

# Validate Supabase configuration - required, no fallback
if not _supabase_url or not _supabase_key:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables are required. "
        "Please configure them in your .env file."
    )

# Initialize session service with Supabase
from .supabase_session_service import SupabaseSessionService
_session_service = SupabaseSessionService(
    supabase_url=_supabase_url,
    supabase_key=_supabase_key,
)
logger.info("Using SupabaseSessionService with REST API")

# Initialize persona service
_persona_service = PersonaService(
    supabase_url=_supabase_url,
    supabase_key=_supabase_key,
)

# Initialize memory service
_memory_service = MemoryService(
    supabase_url=_supabase_url,
    supabase_key=_supabase_key,
)

# Create agent once at module level (uses ADK state injection for persona)
_prompt_file = Path(__file__).parent / "instruction.md"
_agent = Agent(
    model=Gemini(model='gemini-3-pro-preview'),
    name="bulbul",
    instruction=_prompt_file.read_text(encoding="utf-8"),
    description="assistant",
    tools=[update_persona, manage_memory],
)


async def process_agent_query(
    query: str,
    user_id: str = "default_user",
    session_id: Optional[str] = None,
    app_name: str = "bulbul",
    image_data: Optional[bytes] = None,
    image_mime_type: str = "image/jpeg"
) -> Dict[str, Any]:
    """Process a user query through the customizable Bulbul agent.

    This function uses a shared agent instance with ADK state injection
    for persona, following the ADK Runtime's Event Loop pattern.

    Args:
        query: The user's message/question
        user_id: User identifier for session and persona management
        session_id: Optional session ID for conversation continuity
        app_name: Application name for session management
        image_data: Optional image data bytes
        image_mime_type: MIME type for image data

    Returns:
        Dictionary containing:
            - response: The agent's text response
            - session_id: Session ID for future queries
            - status: "success" or "error"
            - error: Error message if status is "error"
    """
    try:
        # Load user's persona from database
        persona = await _persona_service.get_persona(user_id)
        logger.debug(f"Loaded persona for user {user_id}: {list(persona.keys())}")

        # Load user's memories from database
        memories = await _memory_service.get_memories(user_id)
        logger.debug(f"Loaded {len(memories)} memories for user {user_id}")

        # Initialize tools with current context
        init_persona_tool(_persona_service, user_id)
        init_memory_tool(_memory_service, user_id)

        # Build initial state with persona data
        initial_state = dict(persona)

        # Format and add memories to state
        if memories:
            formatted_memories = "\n".join(
                f"- [{m['fact_id']}] {m['fact']}" for m in memories
            )
            initial_state["user_memories"] = formatted_memories
        else:
            initial_state["user_memories"] = "لا توجد ذكريات محفوظة بعد"

        # Create or retrieve session
        if session_id:
            # Try to get existing session
            session = await _session_service.get_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id
            )
            if session:
                # Update session state with current persona
                session.state.update(initial_state)
            else:
                # Session not found, create new one with persona state
                session = await _session_service.create_session(
                    app_name=app_name,
                    user_id=user_id,
                    state=initial_state
                )
        else:
            # Create new session with persona state
            session = await _session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                state=initial_state
            )

        # Initialize Runner with the shared agent
        runner = Runner(
            agent=_agent,
            app_name=app_name,
            session_service=_session_service
        )

        # Build parts list for multimodal content
        parts: List[types.Part] = []

        # Add image part if provided (image first for better context)
        if image_data is not None:
            blob = types.Blob(data=image_data, mime_type=image_mime_type)
            parts.append(types.Part(inline_data=blob))

        # Add text part
        if query:
            parts.append(types.Part(text=query))
        elif image_data is not None:
            # Default prompt for image-only messages
            parts.append(types.Part(text="ما هذا؟"))

        # Create user message content
        content = types.Content(role='user', parts=parts)

        # Collect response parts
        response_parts = []

        # Execute the agent through the Runner's event loop
        events = runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=content
        )

        # Process events from the agent
        async for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    # Skip thinking/reasoning parts - only include actual response
                    if part.text and not getattr(part, 'thought', False):
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
        logger.exception(f"Error processing query for user {user_id}")
        return {
            "response": "",
            "session_id": session_id,
            "status": "error",
            "error": str(e)
        }


async def ask_agent(
    query: str,
    user_id: str = "default_user",
    session_id: Optional[str] = None
) -> str:
    """Simple interface to ask the Bulbul agent a question.

    This is a convenience wrapper around process_agent_query that
    returns just the text response.

    Args:
        query: The question/message
        user_id: User identifier for persona
        session_id: Optional session ID for conversation continuity

    Returns:
        The agent's response as a string
    """
    result = await process_agent_query(query, user_id=user_id, session_id=session_id)

    if result["status"] == "success":
        return result["response"]
    else:
        return f"Error: {result['error']}"


async def reset_user_persona(user_id: str) -> bool:
    """Reset a user's persona to defaults.

    Args:
        user_id: The user's unique identifier

    Returns:
        True if successful, False otherwise
    """
    try:
        await _persona_service.reset_persona(user_id)
        logger.info(f"Reset persona for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to reset persona for user {user_id}: {e}")
        return False


# Export main interfaces
__all__ = [
    'process_agent_query',
    'ask_agent',
    'reset_user_persona',
]
