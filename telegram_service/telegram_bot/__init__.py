"""
Telegram bot package for the Educational Assistant Agent.

This package provides a Telegram bot interface for interacting with
the educational assistant agent.
"""

from .handlers import (
    error_handler,
    callback_query_handler,
    handle_message,
    handle_photo_message,
    handle_voice_message,
    help_command,
    goals_command,
    new_command,
    poll_answer_handler,
    reset_persona_command,
    settings_command,
    start_command,
)

__all__ = [
    "start_command",
    "help_command",
    "goals_command",
    "settings_command",
    "new_command",
    "reset_persona_command",
    "handle_message",
    "handle_photo_message",
    "handle_voice_message",
    "callback_query_handler",
    "poll_answer_handler",
    "error_handler",
]
