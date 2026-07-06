"""Memory Service - manages user memories/facts in Supabase."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

logger = logging.getLogger(__name__)


class MemoryService:
    """Service for managing remembered facts about users."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        client: Optional[Client] = None,
        **_: Any,
    ) -> None:
        self._client = client or create_client(
            supabase_url or self._required_env("SUPABASE_URL"),
            supabase_key or self._required_env("SUPABASE_SERVICE_KEY"),
        )
        logger.info("MemoryService initialized with Supabase")

    def _required_env(self, name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise RuntimeError(f"MemoryService requires {name} environment variable")
        return value

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _fact_number(self, fact_id: str) -> int:
        try:
            return int(fact_id.split("-", 1)[1])
        except (IndexError, ValueError):
            return 0

    async def _get_next_fact_id(self, user_id: str) -> str:
        memories = await self.get_memories(user_id)
        max_num = max((self._fact_number(memory["fact_id"]) for memory in memories), default=0)
        return f"fact-{max_num + 1:02d}"

    async def get_memories(self, user_id: str) -> List[Dict[str, str]]:
        result = (
            self._client.table("user_memory")
            .select("fact_id,fact")
            .eq("user_id", str(user_id))
            .execute()
        )
        memories = [
            {"fact_id": str(row.get("fact_id")), "fact": str(row.get("fact") or "")}
            for row in (result.data or [])
            if row.get("fact_id")
        ]
        return sorted(memories, key=lambda memory: self._fact_number(memory["fact_id"]))

    async def add_memory(self, user_id: str, fact: str) -> str:
        fact_id = await self._get_next_fact_id(user_id)
        self._client.table("user_memory").insert(
            {
                "user_id": str(user_id),
                "fact_id": fact_id,
                "fact": fact,
                "updated_at": self._now(),
            },
        ).execute()
        logger.debug("Added memory %s for user %s", fact_id, user_id)
        return fact_id

    async def update_memory(self, user_id: str, fact_id: str, fact: str) -> bool:
        existing = (
            self._client.table("user_memory")
            .select("id")
            .eq("user_id", str(user_id))
            .eq("fact_id", fact_id)
            .limit(1)
            .execute()
        )
        if not existing.data:
            return False

        (
            self._client.table("user_memory")
            .update({
                "fact": fact,
                "updated_at": self._now(),
            })
            .eq("id", existing.data[0]["id"])
            .execute()
        )
        logger.debug("Updated memory %s for user %s", fact_id, user_id)
        return True

    async def remove_memory(self, user_id: str, fact_id: str) -> bool:
        existing = (
            self._client.table("user_memory")
            .select("id")
            .eq("user_id", str(user_id))
            .eq("fact_id", fact_id)
            .limit(1)
            .execute()
        )
        if not existing.data:
            return False

        (
            self._client.table("user_memory")
            .delete()
            .eq("id", existing.data[0]["id"])
            .execute()
        )
        logger.debug("Removed memory %s for user %s", fact_id, user_id)
        return True

    async def clear_memories(self, user_id: str) -> None:
        (
            self._client.table("user_memory")
            .delete()
            .eq("user_id", str(user_id))
            .execute()
        )
        logger.info("Cleared all memories for user %s", user_id)
