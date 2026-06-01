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

"""Memory Service - Manages user memories/facts with flexible storage."""

import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Try to import supabase client
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = type(None)


class MemoryService:
    """
    Service for managing user memories/facts.

    Stores facts about the user that the agent learns during conversations.
    Each fact has a unique fact_id (format: fact-XX) for easy reference.

    Example usage:
        >>> service = MemoryService()
        >>> fact_id = await service.add_memory("user123", "يحب القهوة السوداء")
        >>> # Returns: "fact-01"
        >>> await service.update_memory("user123", "fact-01", "يحب القهوة بالحليب")
        >>> memories = await service.get_memories("user123")
        >>> # Returns: [{"fact_id": "fact-01", "fact": "يحب القهوة بالحليب"}]
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ):
        """
        Initialize the MemoryService.

        Args:
            supabase_url: Supabase project URL (defaults to SUPABASE_URL env var)
            supabase_key: Supabase service key (defaults to SUPABASE_SERVICE_KEY env var)

        Raises:
            RuntimeError: If Supabase is not available or not configured
        """
        if not SUPABASE_AVAILABLE:
            raise RuntimeError(
                "MemoryService requires supabase package. Install with: pip install supabase"
            )

        url = supabase_url or os.getenv("SUPABASE_URL")
        key = supabase_key or os.getenv("SUPABASE_SERVICE_KEY")

        if not url or not key:
            raise RuntimeError(
                "MemoryService requires SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables"
            )

        try:
            self._supabase: Client = create_client(url, key)
            logger.info("MemoryService initialized with Supabase")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Supabase for MemoryService: {e}") from e

    async def _get_next_fact_id(self, user_id: str) -> str:
        """Generate the next fact_id for a user (fact-01, fact-02, etc.)."""
        result = (
            self._supabase.table("user_memory")
            .select("fact_id")
            .eq("user_id", user_id)
            .order("fact_id", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            last_id = result.data[0]["fact_id"]
            num = int(last_id.split("-")[1]) + 1
            return f"fact-{num:02d}"
        return "fact-01"

    async def get_memories(self, user_id: str) -> List[Dict[str, str]]:
        """
        Load all memories for a user, sorted by fact_id.

        Args:
            user_id: The user's unique identifier

        Returns:
            List of dictionaries with fact_id and fact keys
        """
        result = (
            self._supabase.table("user_memory")
            .select("fact_id, fact")
            .eq("user_id", user_id)
            .order("fact_id")
            .execute()
        )
        return result.data if result.data else []

    async def add_memory(self, user_id: str, fact: str) -> str:
        """
        Add a new memory for a user.

        Args:
            user_id: The user's unique identifier
            fact: The fact text to store

        Returns:
            The generated fact_id (e.g., "fact-01")
        """
        fact_id = await self._get_next_fact_id(user_id)

        self._supabase.table("user_memory").insert({
            "user_id": user_id,
            "fact_id": fact_id,
            "fact": fact,
        }).execute()
        logger.debug(f"Added memory {fact_id} for user {user_id}")

        return fact_id

    async def update_memory(self, user_id: str, fact_id: str, fact: str) -> bool:
        """
        Update an existing memory.

        Args:
            user_id: The user's unique identifier
            fact_id: The fact identifier to update
            fact: The new fact text

        Returns:
            True if found and updated, False otherwise
        """
        result = (
            self._supabase.table("user_memory")
            .update({"fact": fact, "updated_at": "now()"})
            .eq("user_id", user_id)
            .eq("fact_id", fact_id)
            .execute()
        )
        if result.data:
            logger.debug(f"Updated memory {fact_id} for user {user_id}")
            return True
        return False

    async def remove_memory(self, user_id: str, fact_id: str) -> bool:
        """
        Remove a memory.

        Args:
            user_id: The user's unique identifier
            fact_id: The fact identifier to remove

        Returns:
            True if found and removed, False otherwise
        """
        result = (
            self._supabase.table("user_memory")
            .delete()
            .eq("user_id", user_id)
            .eq("fact_id", fact_id)
            .execute()
        )
        if result.data:
            logger.debug(f"Removed memory {fact_id} for user {user_id}")
            return True
        return False

    async def clear_memories(self, user_id: str) -> None:
        """
        Delete all memories for a user.

        Args:
            user_id: The user's unique identifier
        """
        self._supabase.table("user_memory").delete().eq(
            "user_id", user_id
        ).execute()
        logger.info(f"Cleared all memories for user {user_id}")
