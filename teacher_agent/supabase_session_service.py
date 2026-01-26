"""
Custom Supabase Session Service for Google ADK.

Uses Supabase REST API instead of direct PostgreSQL connections,
which works better with Supabase's connection pooling and IPv4/IPv6 setup.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from google.adk.sessions.base_session_service import (
    BaseSessionService,
    GetSessionConfig,
    ListSessionsResponse,
)
from google.adk.sessions.session import Session
from google.adk.events import Event
from google.genai import types

logger = logging.getLogger(__name__)

# Try to import supabase client
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("supabase-py not installed")


class SupabaseSessionService(BaseSessionService):
    """
    A Supabase-based session service using REST API.

    This implementation uses the Supabase client (REST API) instead of
    direct PostgreSQL connections, providing better compatibility with
    Supabase's infrastructure.

    Tables required:
        - adk_sessions: Stores session metadata and state
        - adk_events: Stores conversation events/history
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ):
        """
        Initialize the Supabase session service.

        Args:
            supabase_url: Supabase project URL (defaults to SUPABASE_URL env var)
            supabase_key: Supabase service key (defaults to SUPABASE_SERVICE_KEY env var)
        """
        if not SUPABASE_AVAILABLE:
            raise ImportError("supabase-py is required for SupabaseSessionService")

        url = supabase_url or os.getenv("SUPABASE_URL")
        key = supabase_key or os.getenv("SUPABASE_SERVICE_KEY")

        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required")

        self._client: Client = create_client(url, key)
        self._ensure_tables_exist()
        logger.info("SupabaseSessionService initialized with REST API")

    # SQL Schema for required tables (run in Supabase SQL Editor if tables don't exist)
    TABLES_SQL = """
    -- ADK Sessions table: stores session metadata and state
    CREATE TABLE IF NOT EXISTS adk_sessions (
        id BIGSERIAL PRIMARY KEY,
        session_id TEXT NOT NULL UNIQUE,
        app_name TEXT NOT NULL,
        user_id TEXT NOT NULL,
        state JSONB DEFAULT '{}',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- Index for faster lookups
    CREATE INDEX IF NOT EXISTS idx_adk_sessions_lookup
        ON adk_sessions(app_name, user_id, session_id);

    -- ADK Events table: stores conversation history
    CREATE TABLE IF NOT EXISTS adk_events (
        id BIGSERIAL PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        session_id TEXT NOT NULL,
        event_data JSONB NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- Index for faster event retrieval
    CREATE INDEX IF NOT EXISTS idx_adk_events_session
        ON adk_events(session_id, created_at);

    -- Enable Row Level Security
    ALTER TABLE adk_sessions ENABLE ROW LEVEL SECURITY;
    ALTER TABLE adk_events ENABLE ROW LEVEL SECURITY;

    -- Policy for service role (full access)
    CREATE POLICY "Service role has full access to adk_sessions"
        ON adk_sessions FOR ALL
        USING (true)
        WITH CHECK (true);

    CREATE POLICY "Service role has full access to adk_events"
        ON adk_events FOR ALL
        USING (true)
        WITH CHECK (true);
    """

    def _ensure_tables_exist(self) -> None:
        """Verify required tables exist, raise error with schema if not."""
        try:
            # Check if tables exist by trying to query them
            self._client.table("adk_sessions").select("session_id").limit(1).execute()
            self._client.table("adk_events").select("event_id").limit(1).execute()
            logger.debug("ADK session tables verified")
        except Exception as e:
            error_msg = str(e).lower()
            if "does not exist" in error_msg or "relation" in error_msg:
                logger.error(
                    f"ADK session tables don't exist. "
                    f"Please create them in Supabase SQL Editor:\n{self.TABLES_SQL}"
                )
                raise RuntimeError(
                    "ADK session tables (adk_sessions, adk_events) don't exist. "
                    "See logs for the SQL schema to create them."
                )
            # Other errors (e.g., empty table) are fine
            logger.debug(f"Table check passed: {e}")

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        """Creates a new session in Supabase."""
        session_id = session_id or str(uuid.uuid4())
        state = state or {}
        now = datetime.now(timezone.utc).isoformat()

        try:
            # Insert session record
            self._client.table("adk_sessions").insert({
                "session_id": session_id,
                "app_name": app_name,
                "user_id": user_id,
                "state": json.dumps(state),
                "created_at": now,
                "updated_at": now,
            }).execute()

            logger.debug(f"Created session {session_id} for user {user_id}")

            return Session(
                id=session_id,
                app_name=app_name,
                user_id=user_id,
                state=state,
                events=[],
            )
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        """Gets a session from Supabase."""
        try:
            # Get session record
            result = (
                self._client.table("adk_sessions")
                .select("*")
                .eq("session_id", session_id)
                .eq("app_name", app_name)
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            if not result or not result.data:
                logger.debug(f"Session {session_id} not found")
                return None

            session_data = result.data
            state = json.loads(session_data.get("state", "{}"))

            # Get events for this session
            events = []
            events_result = (
                self._client.table("adk_events")
                .select("*")
                .eq("session_id", session_id)
                .order("created_at", desc=False)
                .execute()
            )

            if events_result.data:
                for event_data in events_result.data:
                    event = self._deserialize_event(event_data)
                    if event:
                        events.append(event)

            # Apply config filters if provided
            if config:
                if config.num_recent_events is not None:
                    events = events[-config.num_recent_events:]

            logger.debug(f"Retrieved session {session_id} with {len(events)} events")

            return Session(
                id=session_id,
                app_name=app_name,
                user_id=user_id,
                state=state,
                events=events,
            )
        except Exception as e:
            logger.error(f"Failed to get session: {e}")
            return None

    async def list_sessions(
        self, *, app_name: str, user_id: Optional[str] = None
    ) -> ListSessionsResponse:
        """Lists sessions from Supabase."""
        try:
            query = (
                self._client.table("adk_sessions")
                .select("session_id, app_name, user_id, state, created_at, updated_at")
                .eq("app_name", app_name)
            )

            if user_id:
                query = query.eq("user_id", user_id)

            result = query.execute()

            sessions = []
            for session_data in result.data or []:
                sessions.append(Session(
                    id=session_data["session_id"],
                    app_name=session_data["app_name"],
                    user_id=session_data["user_id"],
                    state=json.loads(session_data.get("state", "{}")),
                    events=[],  # Don't load events for list operation
                ))

            logger.debug(f"Listed {len(sessions)} sessions for app {app_name}")
            return ListSessionsResponse(sessions=sessions)
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return ListSessionsResponse(sessions=[])

    async def delete_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        """Deletes a session and its events from Supabase."""
        try:
            # Delete events first (foreign key constraint)
            self._client.table("adk_events").delete().eq(
                "session_id", session_id
            ).execute()

            # Delete session
            self._client.table("adk_sessions").delete().eq(
                "session_id", session_id
            ).eq("app_name", app_name).eq("user_id", user_id).execute()

            logger.debug(f"Deleted session {session_id}")
        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            raise

    async def append_event(self, session: Session, event: Event) -> Event:
        """Appends an event to the session and persists it to Supabase."""
        # Call parent implementation to update in-memory session
        event = await super().append_event(session, event)

        if event.partial:
            return event

        try:
            # Persist event to database
            now = datetime.now(timezone.utc).isoformat()

            self._client.table("adk_events").insert({
                "event_id": str(uuid.uuid4()),
                "session_id": session.id,
                "event_data": self._serialize_event(event),
                "created_at": now,
            }).execute()

            # Update session state and timestamp
            self._client.table("adk_sessions").update({
                "state": json.dumps(session.state),
                "updated_at": now,
            }).eq("session_id", session.id).execute()

            logger.debug(f"Appended event to session {session.id}")
        except Exception as e:
            logger.error(f"Failed to append event: {e}")
            # Don't raise - event is already in memory, just log the error

        return event

    def _serialize_event(self, event: Event) -> str:
        """Serialize an Event to JSON string."""
        try:
            # Handle timestamp - could be datetime, float, or None
            timestamp_value = None
            if event.timestamp:
                if hasattr(event.timestamp, 'isoformat'):
                    timestamp_value = event.timestamp.isoformat()
                elif isinstance(event.timestamp, (int, float)):
                    # Unix timestamp - convert to ISO format
                    timestamp_value = datetime.fromtimestamp(event.timestamp, timezone.utc).isoformat()
                else:
                    timestamp_value = str(event.timestamp)

            # Convert event to a serializable dict
            event_dict = {
                "id": event.id,
                "invocation_id": event.invocation_id,
                "author": event.author,
                "branch": event.branch,
                "timestamp": timestamp_value,
                "partial": event.partial,
                "turn_complete": event.turn_complete,
                "error_code": event.error_code,
                "error_message": event.error_message,
            }

            # Serialize content if present
            if event.content:
                content_parts = []
                for part in event.content.parts or []:
                    if hasattr(part, 'text') and part.text:
                        content_parts.append({"text": part.text})
                    # Skip non-text parts for now (images, etc.)
                event_dict["content"] = {
                    "role": event.content.role,
                    "parts": content_parts,
                }

            # Serialize actions if present
            if event.actions:
                event_dict["actions"] = {
                    "state_delta": event.actions.state_delta if event.actions.state_delta else None,
                }

            return json.dumps(event_dict)
        except Exception as e:
            logger.error(f"Failed to serialize event: {e}")
            return "{}"

    def _deserialize_event(self, event_data: dict) -> Optional[Event]:
        """Deserialize an Event from database record."""
        try:
            data = json.loads(event_data.get("event_data", "{}"))

            # Skip events with missing required data (corrupted/incomplete records)
            if not data.get("id") or not data.get("author"):
                logger.debug(f"Skipping event with missing required fields: {data.get('id')}")
                return None

            # Reconstruct content
            content = None
            if data.get("content"):
                parts = []
                for part_data in data["content"].get("parts", []):
                    if "text" in part_data:
                        parts.append(types.Part(text=part_data["text"]))
                content = types.Content(
                    role=data["content"].get("role", "model"),
                    parts=parts,
                )

            # Reconstruct actions - required field, provide default
            from google.adk.events import EventActions
            actions = EventActions(state_delta={})
            if data.get("actions") and data["actions"].get("state_delta"):
                actions = EventActions(state_delta=data["actions"]["state_delta"])

            return Event(
                id=data["id"],
                invocation_id=data.get("invocation_id") or str(uuid.uuid4()),
                author=data["author"],
                branch=data.get("branch"),
                content=content,
                actions=actions,
                partial=data.get("partial", False),
                turn_complete=data.get("turn_complete", False),
                error_code=data.get("error_code"),
                error_message=data.get("error_message"),
            )
        except Exception as e:
            logger.error(f"Failed to deserialize event: {e}")
            return None
