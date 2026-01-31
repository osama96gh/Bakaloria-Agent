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

"""Persona Service - Manages agent persona configurations with flexible key-value storage."""

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Try to import supabase client
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = type(None)  # Use type(None) instead of None for type annotation compatibility


class PersonaService:
    """
    Service for managing agent persona configurations.

    Uses a flexible key-value store where the agent can save any attributes
    it finds useful. Values are stored as TEXT - complex values (objects/arrays)
    are JSON-stringified.

    Example usage:
        >>> service = PersonaService()
        >>> await service.set_value("user123", "name", "سارة")
        >>> await service.set_values("user123", {"role": "مدرسة", "dialect": "syrian"})
        >>> persona = await service.get_persona("user123")
        >>> # Returns: {"name": "سارة", "role": "مدرسة", "dialect": "syrian"}
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ):
        """
        Initialize the PersonaService.

        Args:
            supabase_url: Supabase project URL (defaults to SUPABASE_URL env var)
            supabase_key: Supabase service key (defaults to SUPABASE_SERVICE_KEY env var)

        Raises:
            RuntimeError: If Supabase is not available or not configured
        """
        if not SUPABASE_AVAILABLE:
            raise RuntimeError(
                "PersonaService requires supabase package. Install with: pip install supabase"
            )

        url = supabase_url or os.getenv("SUPABASE_URL")
        key = supabase_key or os.getenv("SUPABASE_SERVICE_KEY")

        if not url or not key:
            raise RuntimeError(
                "PersonaService requires SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables"
            )

        try:
            self._supabase: Client = create_client(url, key)
            logger.info("PersonaService initialized with Supabase")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Supabase for PersonaService: {e}") from e

    def _serialize_value(self, value: Any) -> str:
        """Serialize a value to string for storage."""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    def _deserialize_value(self, value_str: str) -> Any:
        """Deserialize a stored string value back to its original type."""
        if value_str is None:
            return None
        # Try to parse as JSON, fall back to string
        try:
            return json.loads(value_str)
        except (json.JSONDecodeError, TypeError):
            return value_str

    async def get_persona(self, user_id: str) -> Dict[str, Any]:
        """
        Load all persona key-value pairs for a user.

        Args:
            user_id: The user's unique identifier

        Returns:
            Dictionary of all persona attributes, empty dict if none exist
        """
        result = (
            self._supabase.table("agent_persona")
            .select("key, value")
            .eq("user_id", user_id)
            .execute()
        )
        if result.data:
            return {
                row["key"]: self._deserialize_value(row["value"])
                for row in result.data
            }
        return {}

    async def get_value(self, user_id: str, key: str) -> Optional[Any]:
        """
        Get a single persona value.

        Args:
            user_id: The user's unique identifier
            key: The persona attribute key

        Returns:
            The value if found, None otherwise
        """
        result = (
            self._supabase.table("agent_persona")
            .select("value")
            .eq("user_id", user_id)
            .eq("key", key)
            .maybe_single()
            .execute()
        )
        if result.data:
            return self._deserialize_value(result.data["value"])
        return None

    async def set_value(self, user_id: str, key: str, value: Any) -> None:
        """
        Set/update a single persona value (upsert).

        Args:
            user_id: The user's unique identifier
            key: The persona attribute key
            value: The value to store (will be JSON-stringified if complex)
        """
        serialized = self._serialize_value(value)

        self._supabase.table("agent_persona").upsert(
            {
                "user_id": user_id,
                "key": key,
                "value": serialized,
                "updated_at": "now()"
            },
            on_conflict="user_id,key"
        ).execute()
        logger.debug(f"Set persona value: {user_id}/{key}")

    async def set_values(self, user_id: str, updates: Dict[str, Any]) -> None:
        """
        Set multiple persona values at once.

        Args:
            user_id: The user's unique identifier
            updates: Dictionary of key-value pairs to set
        """
        if not updates:
            return

        rows = [
            {
                "user_id": user_id,
                "key": key,
                "value": self._serialize_value(value),
                "updated_at": "now()"
            }
            for key, value in updates.items()
        ]
        self._supabase.table("agent_persona").upsert(
            rows,
            on_conflict="user_id,key"
        ).execute()
        logger.debug(f"Set {len(updates)} persona values for user {user_id}")

    async def delete_value(self, user_id: str, key: str) -> None:
        """
        Remove a persona key.

        Args:
            user_id: The user's unique identifier
            key: The persona attribute key to delete
        """
        self._supabase.table("agent_persona").delete().eq(
            "user_id", user_id
        ).eq("key", key).execute()
        logger.debug(f"Deleted persona key: {user_id}/{key}")

    async def reset_persona(self, user_id: str) -> None:
        """
        Delete all persona data for a user.

        Args:
            user_id: The user's unique identifier
        """
        self._supabase.table("agent_persona").delete().eq(
            "user_id", user_id
        ).execute()
        logger.info(f"Reset persona for user {user_id}")
