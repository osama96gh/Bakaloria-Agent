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

"""Persona Service - Manages agent persona configurations using Goa memory."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class PersonaService:
    """
    Service for managing agent persona configurations.

    Uses Goa's participant-owned memory API. Per-user persona values are stored
    under namespaced keys: user:{user_id}:persona:{key}.
    """

    def __init__(
        self,
        goa_url: Optional[str] = None,
        goa_api_key: Optional[str] = None,
        **_: Any,
    ):
        """
        Initialize the PersonaService.

        Args:
            goa_url: Goa base URL (defaults to GOA_URL or http://195.35.0.64)
            goa_api_key: Goa participant API key. Defaults to GOA_AGENT_API_KEY
                if set, otherwise GOA_API_KEY.

        Raises:
            RuntimeError: If Goa is not configured
        """
        self._goa_url = (goa_url or os.getenv("GOA_URL") or "http://195.35.0.64").rstrip("/")
        self._goa_api_key = (
            goa_api_key
            or os.getenv("GOA_AGENT_API_KEY")
            or os.getenv("GOA_API_KEY")
        )

        if not self._goa_api_key:
            raise RuntimeError(
                "PersonaService requires GOA_AGENT_API_KEY or GOA_API_KEY environment variable"
            )

        logger.info("PersonaService initialized with Goa memory")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._goa_api_key}",
            "Content-Type": "application/json",
        }

    def _persona_key(self, user_id: str, key: str) -> str:
        return f"user:{user_id}:persona:{key}"

    def _persona_prefix(self, user_id: str) -> str:
        return f"user:{user_id}:persona:"

    def _persona_tags(self, user_id: str, key: str) -> list[str]:
        tags = ["bulbul", "persona"]
        key_tag = f"persona:{key}"
        if len(key_tag) <= 64:
            tags.append(key_tag)
        user_tag = f"user:{user_id}"
        if len(user_tag) <= 64:
            tags.append(user_tag)
        return tags

    def _persona_value(self, user_id: str, key: str, value: Any) -> dict[str, Any]:
        return {
            "type": "agent_persona_value",
            "source": "goa.memory",
            "user_id": str(user_id),
            "key": key,
            "value": value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _parse_entry(self, entry: dict[str, Any]) -> tuple[Optional[str], Any]:
        full_key = entry.get("key", "")
        persona_key = full_key.rsplit(":", 1)[-1] if ":" in full_key else None
        raw_value = entry.get("value")

        if isinstance(raw_value, dict) and raw_value.get("type") == "agent_persona_value":
            persona_key = raw_value.get("key") or persona_key
            value = raw_value.get("value")
        else:
            value = raw_value

        if not persona_key:
            logger.warning("Skipping malformed Goa persona entry: %s", full_key)
            return None, None

        return str(persona_key), value

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30.0, headers=self._headers()) as client:
            response = await client.request(method, f"{self._goa_url}{path}", **kwargs)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = response.text.strip()
            raise RuntimeError(
                f"Goa persona request failed: {method} {path} -> "
                f"HTTP {response.status_code} {response.reason_phrase}: {body or '<empty>'}"
            ) from exc

        return response

    async def get_persona(self, user_id: str) -> Dict[str, Any]:
        """
        Load all persona key-value pairs for a user.

        Args:
            user_id: The user's unique identifier

        Returns:
            Dictionary of all persona attributes, empty dict if none exist
        """
        response = await self._request(
            "GET",
            "/memory",
            params={"prefix": self._persona_prefix(user_id)},
        )
        persona: Dict[str, Any] = {}
        for entry in response.json().get("entries", []):
            key, value = self._parse_entry(entry)
            if key is not None:
                persona[key] = value
        return persona

    async def get_value(self, user_id: str, key: str) -> Optional[Any]:
        """
        Get a single persona value.

        Args:
            user_id: The user's unique identifier
            key: The persona attribute key

        Returns:
            The value if found, None otherwise
        """
        response = await self._request(
            "GET",
            "/memory",
            params={"key": self._persona_key(user_id, key)},
        )
        entries = response.json().get("entries", [])
        if not entries:
            return None
        _, value = self._parse_entry(entries[0])
        return value

    async def set_value(self, user_id: str, key: str, value: Any) -> None:
        """
        Set/update a single persona value (upsert).

        Args:
            user_id: The user's unique identifier
            key: The persona attribute key
            value: The value to store
        """
        await self._request(
            "POST",
            "/memory",
            json={
                "key": self._persona_key(user_id, key),
                "value": self._persona_value(user_id, key, value),
                "tags": self._persona_tags(user_id, key),
            },
        )
        logger.debug("Set Goa persona value: %s/%s", user_id, key)

    async def set_values(self, user_id: str, updates: Dict[str, Any]) -> None:
        """
        Set multiple persona values.

        Args:
            user_id: The user's unique identifier
            updates: Dictionary of key-value pairs to set
        """
        for key, value in updates.items():
            await self.set_value(user_id, key, value)
        logger.debug("Set %d Goa persona values for user %s", len(updates), user_id)

    async def delete_value(self, user_id: str, key: str) -> None:
        """
        Remove a persona key.

        Args:
            user_id: The user's unique identifier
            key: The persona attribute key to delete
        """
        await self._request(
            "DELETE",
            "/memory",
            params={"key": self._persona_key(user_id, key)},
        )
        logger.debug("Deleted Goa persona key: %s/%s", user_id, key)

    async def reset_persona(self, user_id: str) -> None:
        """
        Delete all persona data for a user.

        Args:
            user_id: The user's unique identifier
        """
        await self._request(
            "DELETE",
            "/memory",
            params={"prefix": self._persona_prefix(user_id)},
        )
        logger.info("Reset Goa persona for user %s", user_id)
