"""
Telegram bot package for the Educational Assistant Agent.

This package provides a Telegram bot interface for interacting with
the educational assistant agent.
"""

from .handlers import (
    error_handler,
    handle_message,
    handle_photo_message,
    handle_voice_message,
    help_command,
    new_command,
    reset_persona_command,
    start_command,
)

__all__ = [
    "start_command",
    "help_command",
    "new_command",
    "reset_persona_command",
    "handle_message",
    "handle_photo_message",
    "handle_voice_message",
    "error_handler",
]
