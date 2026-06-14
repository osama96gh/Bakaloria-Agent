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

"""Memory Service - Manages user memories/facts using Goa memory."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class MemoryService:
    """
    Service for managing user memories/facts.

    Stores facts about users in Goa's participant-owned memory API. Goa memory
    is owned by the authenticated participant, so user facts are namespaced by
    key: user:{user_id}:memory:{fact_id}.
    """

    def __init__(
        self,
        goa_url: Optional[str] = None,
        goa_api_key: Optional[str] = None,
        **_: Any,
    ):
        """
        Initialize the MemoryService.

        Args:
            goa_url: Goa base URL (defaults to GOA_URL or http://195.35.0.64)
            goa_api_key: Goa participant API key. Defaults to GOA_AGENT_API_KEY
                if set, otherwise GOA_API_KEY.

        Raises:
            RuntimeError: If Goa is not configured or /memory is unavailable
        """
        self._goa_url = (goa_url or os.getenv("GOA_URL") or "http://195.35.0.64").rstrip("/")
        self._goa_api_key = (
            goa_api_key
            or os.getenv("GOA_AGENT_API_KEY")
            or os.getenv("GOA_API_KEY")
        )

        if not self._goa_api_key:
            raise RuntimeError(
                "MemoryService requires GOA_AGENT_API_KEY or GOA_API_KEY environment variable"
            )

        logger.info("MemoryService initialized with Goa memory")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._goa_api_key}",
            "Content-Type": "application/json",
        }

    def _memory_key(self, user_id: str, fact_id: str) -> str:
        return f"user:{user_id}:memory:{fact_id}"

    def _memory_prefix(self, user_id: str) -> str:
        return f"user:{user_id}:memory:"

    def _memory_tags(self, user_id: str, fact_id: str) -> list[str]:
        tags = ["bulbul", "user_memory", f"fact:{fact_id}"]
        user_tag = f"user:{user_id}"
        if len(user_tag) <= 64:
            tags.append(user_tag)
        return tags

    def _memory_value(self, user_id: str, fact_id: str, fact: str) -> dict[str, Any]:
        return {
            "type": "user_memory_fact",
            "source": "goa.memory",
            "user_id": str(user_id),
            "fact_id": str(fact_id),
            "fact": fact,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _parse_entry(self, entry: dict[str, Any]) -> Optional[Dict[str, str]]:
        key = entry.get("key", "")
        fact_id = key.rsplit(":", 1)[-1] if ":" in key else ""
        value = entry.get("value")

        if isinstance(value, dict):
            fact_id = str(value.get("fact_id") or fact_id)
            fact = value.get("fact")
        elif isinstance(value, str):
            fact = value
        else:
            fact = None

        if not fact_id or fact is None:
            logger.warning("Skipping malformed Goa memory entry: %s", key)
            return None

        return {"fact_id": fact_id, "fact": str(fact)}

    def _fact_number(self, fact_id: str) -> int:
        try:
            return int(fact_id.split("-", 1)[1])
        except (IndexError, ValueError):
            return 0

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30.0, headers=self._headers()) as client:
            response = await client.request(method, f"{self._goa_url}{path}", **kwargs)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = response.text.strip()
            raise RuntimeError(
                f"Goa memory request failed: {method} {path} -> "
                f"HTTP {response.status_code} {response.reason_phrase}: {body or '<empty>'}"
            ) from exc

        return response

    async def _get_next_fact_id(self, user_id: str) -> str:
        """Generate the next fact_id for a user (fact-01, fact-02, etc.)."""
        memories = await self.get_memories(user_id)
        max_num = max((self._fact_number(memory["fact_id"]) for memory in memories), default=0)
        return f"fact-{max_num + 1:02d}"

    async def get_memories(self, user_id: str) -> List[Dict[str, str]]:
        """
        Load all memories for a user, sorted by fact_id.

        Args:
            user_id: The user's unique identifier

        Returns:
            List of dictionaries with fact_id and fact keys
        """
        response = await self._request(
            "GET",
            "/memory",
            params={"prefix": self._memory_prefix(user_id)},
        )
        entries = response.json().get("entries", [])
        memories = [parsed for entry in entries if (parsed := self._parse_entry(entry))]
        return sorted(memories, key=lambda memory: self._fact_number(memory["fact_id"]))

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
        await self._request(
            "POST",
            "/memory",
            json={
                "key": self._memory_key(user_id, fact_id),
                "value": self._memory_value(user_id, fact_id, fact),
                "tags": self._memory_tags(user_id, fact_id),
            },
        )
        logger.debug("Added Goa memory %s for user %s", fact_id, user_id)
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
        key = self._memory_key(user_id, fact_id)
        existing = await self._request("GET", "/memory", params={"key": key})
        if not existing.json().get("entries"):
            return False

        await self._request(
            "POST",
            "/memory",
            json={
                "key": key,
                "value": self._memory_value(user_id, fact_id, fact),
                "tags": self._memory_tags(user_id, fact_id),
            },
        )
        logger.debug("Updated Goa memory %s for user %s", fact_id, user_id)
        return True

    async def remove_memory(self, user_id: str, fact_id: str) -> bool:
        """
        Remove a memory.

        Args:
            user_id: The user's unique identifier
            fact_id: The fact identifier to remove

        Returns:
            True if found and removed, False otherwise
        """
        response = await self._request(
            "DELETE",
            "/memory",
            params={"key": self._memory_key(user_id, fact_id)},
        )
        deleted = response.json().get("deleted", 0)
        if deleted:
            logger.debug("Removed Goa memory %s for user %s", fact_id, user_id)
            return True
        return False

    async def clear_memories(self, user_id: str) -> None:
        """
        Delete all memories for a user.

        Args:
            user_id: The user's unique identifier
        """
        await self._request(
            "DELETE",
            "/memory",
            params={"prefix": self._memory_prefix(user_id)},
        )
        logger.info("Cleared all Goa memories for user %s", user_id)
