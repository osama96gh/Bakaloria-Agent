

"""Teacher Agent Package - Exposes the book assistant agent for helping users understand textbook content."""

from .agent import root_agent
from .service import process_agent_query, ask_agent

# Expose book_assistant_agent as root_agent
book_assistant_agent = root_agent

# Define what should be available when using "from teacher_agent import *"
__all__ = [
    'root_agent',
    'book_assistant_agent',
    'process_agent_query',
    'ask_agent'
]
