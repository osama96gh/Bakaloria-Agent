"""
Utility functions for the Telegram bot.

Provides helper functions for message handling, error formatting, and logging.
"""

import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)


def split_message(text: str, max_length: int = 4096) -> List[str]:
    """
    Split long messages to fit within Telegram's character limit.

    Splits on paragraph boundaries first, then sentences, then words,
    while preserving Arabic text integrity.

    Args:
        text: The message text to split
        max_length: Maximum length per chunk (default 4096 for Telegram)

    Returns:
        List of message chunks, each under max_length characters

    Example:
        >>> long_text = "..." * 5000
        >>> chunks = split_message(long_text)
        >>> all(len(chunk) <= 4096 for chunk in chunks)
        True
    """
    if len(text) <= max_length:
        return [text]

    chunks: List[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Try to split on paragraph boundary
        split_pos = remaining.rfind("\n\n", 0, max_length)

        # If no paragraph break, try sentence boundary (Arabic or English)
        if split_pos == -1:
            # Look for sentence endings: ., ?, !, ؟ (Arabic question mark), . (Arabic period)
            split_pos = max(
                remaining.rfind(". ", 0, max_length),
                remaining.rfind("? ", 0, max_length),
                remaining.rfind("! ", 0, max_length),
                remaining.rfind("؟ ", 0, max_length),
                remaining.rfind("。 ", 0, max_length),
            )

        # If no sentence break, try word boundary
        if split_pos == -1:
            split_pos = remaining.rfind(" ", 0, max_length)

        # If no word boundary, force split at max_length (rare edge case)
        if split_pos == -1:
            split_pos = max_length

        # Extract chunk and update remaining
        chunk = remaining[:split_pos].strip()
        if chunk:
            chunks.append(chunk)

        remaining = remaining[split_pos:].strip()

    return chunks


def format_error_message(error: Optional[Exception] = None) -> str:
    """
    Create user-friendly error messages in Arabic.

    Maps exception types to localized Arabic error messages.

    Args:
        error: The exception that occurred (if any)

    Returns:
        Localized error message string in Arabic

    Example:
        >>> from telegram.error import NetworkError
        >>> msg = format_error_message(NetworkError())
        >>> "تليجرام" in msg
        True
    """
    if error is None:
        return "حدث خطأ غير متوقع، يرجى المحاولة مرة أخرى."

    error_type = type(error).__name__
    error_msg = str(error).lower()

    # Telegram API errors
    if "network" in error_type.lower() or "connection" in error_msg:
        return "عذراً، حدث خطأ في الاتصال بتليجرام. يرجى المحاولة مرة أخرى."

    # Timeout errors
    if "timeout" in error_type.lower() or "timeout" in error_msg:
        return "عذراً، استغرق الأمر وقتاً طويلاً. يرجى المحاولة مرة أخرى."

    # Rate limiting
    if "rate" in error_msg or "limit" in error_msg:
        return "عذراً، تم إرسال عدد كبير من الرسائل. يرجى الانتظار قليلاً ثم المحاولة مرة أخرى."

    # API errors
    if "api" in error_msg or "unauthorized" in error_msg:
        return "حدث خطأ في الاتصال بالخدمة، يرجى المحاولة لاحقاً."

    # Generic error
    return "حدث خطأ غير متوقع، يرجى المحاولة مرة أخرى."


def log_user_interaction(
    user_id: int,
    username: Optional[str],
    query: str,
    status: str,
    duration: Optional[float] = None,
) -> None:
    """
    Log user interactions for monitoring and analytics.

    Args:
        user_id: Telegram user ID
        username: Telegram username (may be None)
        query: User's query text
        status: Response status ("success" or "error")
        duration: Response time in seconds (optional)

    Example:
        >>> log_user_interaction(123456, "user1", "What is math?", "success", 2.5)
    """
    # Truncate long queries for logging
    query_preview = query[:50] + "..." if len(query) > 50 else query

    username_str = f"@{username}" if username else "unknown"

    if duration is not None:
        logger.info(
            f"Query from user_id={user_id} ({username_str}): "
            f'"{query_preview}" | status={status} | duration={duration:.2f}s'
        )
    else:
        logger.info(
            f"Query from user_id={user_id} ({username_str}): "
            f'"{query_preview}" | status={status}'
        )


def sanitize_markdown(text: str) -> str:
    """
    Sanitize text for safe use in Telegram markdown.

    Currently returns plain text. Can be enhanced to support
    HTML or MarkdownV2 formatting if needed.

    Args:
        text: Text to sanitize

    Returns:
        Sanitized text safe for Telegram

    Example:
        >>> sanitize_markdown("Hello *world*")
        'Hello *world*'
    """
    # For now, return plain text (Telegram handles Arabic RTL automatically)
    # Future: could add HTML formatting support
    return text
