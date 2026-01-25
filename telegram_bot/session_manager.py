"""
Session management for Telegram users.

Maps Telegram user IDs to ADK agent session IDs for conversation continuity.
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages mapping between Telegram users and agent sessions.

    Provides in-memory storage of session IDs per Telegram user to maintain
    conversation context across multiple messages.

    Attributes:
        _sessions: In-memory store of telegram_user_id -> session_id mappings

    Example:
        >>> manager = SessionManager()
        >>> session_id = manager.get_or_create_session(123456789)
        >>> session_id is None  # First call returns None (no session yet)
        True
        >>> manager.store_session(123456789, "uuid-session-id")
        >>> manager.get_or_create_session(123456789)
        'uuid-session-id'
    """

    def __init__(self) -> None:
        """Initialize the session manager with empty session storage."""
        self._sessions: Dict[int, str] = {}
        logger.info("SessionManager initialized (in-memory only)")

    def get_or_create_session(self, telegram_user_id: int) -> Optional[str]:
        """
        Get the stored session ID for a Telegram user.

        Args:
            telegram_user_id: The Telegram user's unique ID

        Returns:
            The stored session_id if exists, None otherwise.
            Returning None allows the agent service to create a new session.

        Example:
            >>> manager = SessionManager()
            >>> session_id = manager.get_or_create_session(12345)
            >>> session_id is None
            True
        """
        session_id = self._sessions.get(telegram_user_id)

        if session_id:
            logger.debug(
                f"Retrieved session for user {telegram_user_id}: {session_id}"
            )
        else:
            logger.debug(
                f"No session found for user {telegram_user_id}, will create new"
            )

        return session_id

    def store_session(self, telegram_user_id: int, session_id: str) -> None:
        """
        Store a session ID for a Telegram user.

        This should be called after each call to process_agent_query()
        to update the session ID (which may be newly created).

        Args:
            telegram_user_id: The Telegram user's unique ID
            session_id: The agent session ID to store

        Example:
            >>> manager = SessionManager()
            >>> manager.store_session(12345, "new-session-uuid")
            >>> manager.get_or_create_session(12345)
            'new-session-uuid'
        """
        is_new = telegram_user_id not in self._sessions

        self._sessions[telegram_user_id] = session_id

        if is_new:
            logger.info(
                f"New session created for user {telegram_user_id}: {session_id}"
            )
        else:
            logger.debug(
                f"Updated session for user {telegram_user_id}: {session_id}"
            )

    def reset_session(self, telegram_user_id: int) -> None:
        """
        Reset a user's session (for /new command).

        Removes the stored session ID, so the next message will create
        a fresh session with no conversation history.

        Args:
            telegram_user_id: The Telegram user's unique ID

        Example:
            >>> manager = SessionManager()
            >>> manager.store_session(12345, "old-session")
            >>> manager.reset_session(12345)
            >>> manager.get_or_create_session(12345) is None
            True
        """
        if telegram_user_id in self._sessions:
            old_session_id = self._sessions[telegram_user_id]
            del self._sessions[telegram_user_id]
            logger.info(
                f"Reset session for user {telegram_user_id} "
                f"(removed session {old_session_id})"
            )
        else:
            logger.debug(
                f"No session to reset for user {telegram_user_id}"
            )

    def get_active_sessions_count(self) -> int:
        """
        Get the number of active sessions.

        Returns:
            Number of users with active sessions

        Example:
            >>> manager = SessionManager()
            >>> manager.get_active_sessions_count()
            0
            >>> manager.store_session(123, "session-1")
            >>> manager.get_active_sessions_count()
            1
        """
        return len(self._sessions)
