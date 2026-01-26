"""
Session management for platform users with Supabase persistence.

Maps platform user IDs (Telegram, web, etc.) to ADK agent session IDs
for conversation continuity across application restarts.
"""

import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Try to import supabase client
try:
    from supabase import create_client, Client

    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("supabase-py not installed, falling back to in-memory sessions")


class SessionManager:
    """
    Manages mapping between platform users and ADK sessions.

    Provides persistent storage via Supabase with in-memory fallback.
    Supports multiple platforms (Telegram, web, mobile, etc.).

    Attributes:
        _supabase: Supabase client for database operations
        _fallback_sessions: In-memory store as fallback
        _platform: Platform identifier (e.g., 'telegram', 'web')

    Example:
        >>> manager = SessionManager(platform="telegram")
        >>> session_id = manager.get_or_create_session(123456789)
        >>> session_id is None  # First call returns None (no session yet)
        True
        >>> manager.store_session(123456789, "uuid-session-id")
        >>> manager.get_or_create_session(123456789)
        'uuid-session-id'
    """

    def __init__(self, platform: str = "telegram") -> None:
        """
        Initialize the session manager.

        Args:
            platform: Platform identifier (default: "telegram")
        """
        self._platform = platform
        self._supabase: Optional[Client] = None
        self._fallback_sessions: Dict[str, str] = {}

        if SUPABASE_AVAILABLE:
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_SERVICE_KEY")
            if url and key:
                try:
                    self._supabase = create_client(url, key)
                    logger.info(
                        f"SessionManager initialized with Supabase persistence "
                        f"(platform: {platform})"
                    )
                except Exception as e:
                    logger.error(f"Failed to initialize Supabase client: {e}")
            else:
                logger.warning(
                    "SUPABASE_URL or SUPABASE_SERVICE_KEY not configured"
                )

        if not self._supabase:
            logger.info(
                f"SessionManager using in-memory storage (platform: {platform})"
            )

    def get_or_create_session(self, platform_user_id: int) -> Optional[str]:
        """
        Get the stored session ID for a platform user.

        Args:
            platform_user_id: The platform user's unique ID (e.g., Telegram user ID)

        Returns:
            The stored session_id if exists, None otherwise.
            Returning None allows the agent service to create a new session.
        """
        user_id_str = str(platform_user_id)

        if self._supabase:
            try:
                result = (
                    self._supabase.table("platform_user_sessions")
                    .select("session_id")
                    .eq("platform", self._platform)
                    .eq("platform_user_id", user_id_str)
                    .eq("is_active", True)
                    .maybe_single()
                    .execute()
                )
                if result.data:
                    session_id = result.data.get("session_id")
                    logger.debug(
                        f"Retrieved session for {self._platform} user "
                        f"{platform_user_id}: {session_id}"
                    )
                    return session_id
                else:
                    logger.debug(
                        f"No active session found for {self._platform} user "
                        f"{platform_user_id}"
                    )
                    return None
            except Exception as e:
                logger.error(f"Failed to get session from Supabase: {e}")
                # Fallback to in-memory
                return self._fallback_sessions.get(user_id_str)

        return self._fallback_sessions.get(user_id_str)

    def store_session(self, platform_user_id: int, session_id: str) -> None:
        """
        Store a session ID for a platform user.

        This should be called after each call to process_agent_query()
        to update the session ID (which may be newly created).

        Args:
            platform_user_id: The platform user's unique ID
            session_id: The ADK session ID to store
        """
        user_id_str = str(platform_user_id)

        if self._supabase:
            try:
                # Try to update existing active session first
                update_result = (
                    self._supabase.table("platform_user_sessions")
                    .update({"session_id": session_id, "updated_at": "now()"})
                    .eq("platform", self._platform)
                    .eq("platform_user_id", user_id_str)
                    .eq("is_active", True)
                    .execute()
                )

                # If no row was updated, insert new one
                if not update_result.data:
                    self._supabase.table("platform_user_sessions").insert(
                        {
                            "platform": self._platform,
                            "platform_user_id": user_id_str,
                            "session_id": session_id,
                            "is_active": True,
                        }
                    ).execute()

                logger.debug(
                    f"Stored session for {self._platform} user "
                    f"{platform_user_id}: {session_id}"
                )
            except Exception as e:
                logger.error(f"Failed to store session in Supabase: {e}")
                # Fallback to in-memory
                self._fallback_sessions[user_id_str] = session_id
        else:
            self._fallback_sessions[user_id_str] = session_id

    def reset_session(self, platform_user_id: int) -> None:
        """
        Reset a user's session (for /new command).

        Marks the current session as inactive so the next message
        will create a fresh session with no conversation history.

        Args:
            platform_user_id: The platform user's unique ID
        """
        user_id_str = str(platform_user_id)

        if self._supabase:
            try:
                # Mark current active session as inactive
                self._supabase.table("platform_user_sessions").update(
                    {"is_active": False, "updated_at": "now()"}
                ).eq("platform", self._platform).eq(
                    "platform_user_id", user_id_str
                ).eq(
                    "is_active", True
                ).execute()
                logger.info(
                    f"Reset session for {self._platform} user {platform_user_id}"
                )
            except Exception as e:
                logger.error(f"Failed to reset session in Supabase: {e}")

        # Also clear from fallback
        self._fallback_sessions.pop(user_id_str, None)

    def get_active_sessions_count(self) -> int:
        """
        Get the number of active sessions for this platform.

        Returns:
            Number of users with active sessions
        """
        if self._supabase:
            try:
                result = (
                    self._supabase.table("platform_user_sessions")
                    .select("id", count="exact")
                    .eq("platform", self._platform)
                    .eq("is_active", True)
                    .execute()
                )
                return result.count or 0
            except Exception as e:
                logger.error(f"Failed to count sessions from Supabase: {e}")
                return len(self._fallback_sessions)

        return len(self._fallback_sessions)
