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

"""Service module for exposing the customizable Bulbul agent."""

import logging
import os
from pathlib import Path

from google.adk.agents.llm_agent import Agent
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.models import Gemini
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.google_search_tool import GoogleSearchTool

from .persona_service import PersonaService
from .memory_service import MemoryService
from .goal_service import GoalService
from .tools.persona_tool import update_persona
from .tools.memory_tool import manage_memory
from .tools.goal_tool import manage_goal

logger = logging.getLogger(__name__)

# Module-level services - persist across the app lifecycle
_goa_url = os.getenv("GOA_URL")
_goa_api_key = os.getenv("GOA_AGENT_API_KEY") or os.getenv("GOA_API_KEY")

# Initialize persona service
_persona_service = PersonaService(
    goa_url=_goa_url,
    goa_api_key=_goa_api_key,
)

# Initialize memory service
_memory_service = MemoryService(
    goa_url=_goa_url,
    goa_api_key=_goa_api_key,
)

_goal_service = GoalService(
    goa_url=_goa_url,
    goa_api_key=_goa_api_key,
)

# Sub-agents for built-in tools (isolated to avoid function calling conflicts)
_search_agent = Agent(
    model=Gemini(model='gemini-3.1-pro-preview'),
    name="google_search",

    description=(
        "Search the web for current information, news, facts, or any up-to-date data. "
        "Use when the user asks about recent events, needs fact-checking, "
        "or wants information you're not sure about."
    ),
    instruction=(
        "You are a search assistant. Use Google Search to find the requested information. "
        "Return the results clearly and concisely in Arabic. Include source context when relevant."
    ),
    tools=[GoogleSearchTool()],
)

_code_agent = Agent(
    model=Gemini(model='gemini-3.1-pro-preview'),
    name="code_executor",

    description=(
        "Execute Python code for math calculations, data analysis, programming tasks, "
        "or any computation that needs verification. "
        "Use when accuracy matters or when showing step-by-step calculations."
    ),
    instruction=(
        "You are a code execution assistant. Write and execute Python code to solve the given task. "
        "Show the code and explain the output. Respond in Arabic."
    ),
    code_executor=BuiltInCodeExecutor(),
)

# Create agent once at module level
_prompt_file = Path(__file__).parent / "instruction.md"
_agent = Agent(
    model=Gemini(model='gemini-3.1-pro-preview'),
    name="bulbul",

    instruction=_prompt_file.read_text(encoding="utf-8") if _prompt_file.exists() else "أنت مساعد ذكي.",
    description="assistant",
    tools=[
        update_persona,
        manage_memory,
        manage_goal,
        AgentTool(agent=_search_agent),
        AgentTool(agent=_code_agent),
    ],
)

async def reset_user_persona(user_id: str) -> bool:
    """Reset a user's persona to defaults."""
    try:
        await _persona_service.reset_persona(user_id)
        logger.info(f"Reset persona for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to reset persona for user {user_id}: {e}")
        return False

# Export main interfaces
__all__ = [
    '_agent',
    '_persona_service',
    '_memory_service',
    '_goal_service',
    'reset_user_persona',
]
