"""Persona Service - manages agent persona values in Supabase."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from supabase import Client, create_client

logger = logging.getLogger(__name__)


class PersonaService:
    """Service for managing per-user agent persona configuration."""

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
        logger.info("PersonaService initialized with Supabase")

    def _required_env(self, name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise RuntimeError(f"PersonaService requires {name} environment variable")
        return value

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, (dict, list, bool, int, float)) or value is None:
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _deserialize_value(self, value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def get_persona(self, user_id: str) -> Dict[str, Any]:
        result = (
            self._client.table("agent_persona")
            .select("key,value")
            .eq("user_id", str(user_id))
            .execute()
        )
        return {
            str(row["key"]): self._deserialize_value(row.get("value"))
            for row in (result.data or [])
            if row.get("key")
        }

    async def get_value(self, user_id: str, key: str) -> Optional[Any]:
        result = (
            self._client.table("agent_persona")
            .select("value")
            .eq("user_id", str(user_id))
            .eq("key", key)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        return self._deserialize_value(rows[0].get("value"))

    async def set_value(self, user_id: str, key: str, value: Any) -> None:
        row = {
            "user_id": str(user_id),
            "key": key,
            "value": self._serialize_value(value),
            "updated_at": self._now(),
        }
        existing = (
            self._client.table("agent_persona")
            .select("id")
            .eq("user_id", str(user_id))
            .eq("key", key)
            .limit(1)
            .execute()
        )
        if existing.data:
            (
                self._client.table("agent_persona")
                .update(row)
                .eq("id", existing.data[0]["id"])
                .execute()
            )
        else:
            self._client.table("agent_persona").insert(row).execute()
        logger.debug("Set persona value: %s/%s", user_id, key)

    async def set_values(self, user_id: str, updates: Dict[str, Any]) -> None:
        if not updates:
            return
        for key, value in updates.items():
            await self.set_value(user_id, key, value)
        logger.debug("Set %d persona values for user %s", len(updates), user_id)

    async def delete_value(self, user_id: str, key: str) -> None:
        (
            self._client.table("agent_persona")
            .delete()
            .eq("user_id", str(user_id))
            .eq("key", key)
            .execute()
        )
        logger.debug("Deleted persona key: %s/%s", user_id, key)

    async def reset_persona(self, user_id: str) -> None:
        (
            self._client.table("agent_persona")
            .delete()
            .eq("user_id", str(user_id))
            .execute()
        )
        logger.info("Reset persona for user %s", user_id)
