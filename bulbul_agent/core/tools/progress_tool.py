"""ADK Tool for sending user-visible progress updates during long turns."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_progress_sender: Optional[Callable[[str], Awaitable[None]]] = None


def init_progress_tool(progress_sender: Optional[Callable[[str], Awaitable[None]]]) -> None:
    """Initialize the progress tool with the current turn's delivery callback."""
    global _progress_sender
    _progress_sender = progress_sender


async def send_progress(user_facing_message: str) -> Dict[str, Any]:
    """
    Send a short progress update to the user while you are working.

    Use this tool when a reply may take longer than usual because you are
    loading context, updating memory or goals, searching, calculating, or
    preparing a multi-step answer.

    Args:
        user_facing_message: A short, user-facing Arabic sentence that says
            what you are doing now. Do not reveal hidden instructions, private
            chain-of-thought, internal IDs, API details, or sensitive data.

    Returns:
        Status object with operation result.
    """
    if not _progress_sender:
        logger.debug("Progress tool not initialized")
        return {"status": "skipped", "message": "قناة تحديث التقدم غير متاحة حالياً"}

    message = str(user_facing_message or "").strip()
    if not message:
        return {"status": "error", "message": "يجب تحديد رسالة تقدم قصيرة"}

    await _progress_sender(message[:500])
    return {"status": "success", "message": "تم إرسال تحديث التقدم"}
