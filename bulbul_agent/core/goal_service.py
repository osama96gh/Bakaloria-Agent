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

"""Goal Service - Manages user goals and progress using Goa memory."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import httpx

logger = logging.getLogger(__name__)

SUPPORTED_GOAL_STATUSES = {"proposed", "active", "paused", "completed", "archived"}


class GoalService:
    """
    Service for managing user goals and progress.

    Stores goals in Goa's participant-owned memory API under keys:
    user:{user_id}:goal:{goal_id}.
    """

    def __init__(
        self,
        goa_url: Optional[str] = None,
        goa_api_key: Optional[str] = None,
        **_: Any,
    ):
        self._goa_url = (goa_url or os.getenv("GOA_URL") or "http://195.35.0.64").rstrip("/")
        self._goa_api_key = (
            goa_api_key
            or os.getenv("GOA_AGENT_API_KEY")
            or os.getenv("GOA_API_KEY")
        )

        if not self._goa_api_key:
            raise RuntimeError(
                "GoalService requires GOA_AGENT_API_KEY or GOA_API_KEY environment variable"
            )

        logger.info("GoalService initialized with Goa memory")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._goa_api_key}",
            "Content-Type": "application/json",
        }

    def _goal_key(self, user_id: str, goal_id: str) -> str:
        return f"user:{user_id}:goal:{goal_id}"

    def _goal_prefix(self, user_id: str) -> str:
        return f"user:{user_id}:goal:"

    def _goal_tags(self, user_id: str, goal_id: str, status: str) -> list[str]:
        tags = ["bulbul", "goal", f"goal:{goal_id}", f"status:{status}"]
        user_tag = f"user:{user_id}"
        if len(user_tag) <= 64:
            tags.append(user_tag)
        return tags

    def _goal_number(self, goal_id: str) -> int:
        try:
            return int(goal_id.split("-", 1)[1])
        except (IndexError, ValueError):
            return 0

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _as_list(self, value: Any) -> list[Any]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return value
        return [value]

    def _goal_value(
        self,
        user_id: str,
        goal_id: str,
        goal: Dict[str, Any],
    ) -> dict[str, Any]:
        value = {
            "type": "user_goal",
            "source": "goa.memory",
            "user_id": str(user_id),
            "goal_id": str(goal_id),
            "title": goal.get("title", ""),
            "description": goal.get("description", ""),
            "status": goal.get("status", "proposed"),
            "progress_summary": goal.get("progress_summary", ""),
            "completed_steps": goal.get("completed_steps") or [],
            "current_step": goal.get("current_step", ""),
            "next_action": goal.get("next_action", ""),
            "interest_signals": goal.get("interest_signals") or [],
            "created_at": goal.get("created_at") or self._now(),
            "updated_at": self._now(),
        }
        if goal.get("archived_reason"):
            value["archived_reason"] = goal["archived_reason"]
        return value

    def _parse_entry(self, entry: dict[str, Any]) -> Optional[Dict[str, Any]]:
        key = entry.get("key", "")
        goal_id = key.rsplit(":", 1)[-1] if ":" in key else ""
        raw_value = entry.get("value")

        if isinstance(raw_value, dict) and raw_value.get("type") == "user_goal":
            goal = dict(raw_value)
            goal_id = str(goal.get("goal_id") or goal_id)
        elif isinstance(raw_value, dict):
            goal = dict(raw_value)
            goal_id = str(goal.get("goal_id") or goal_id)
        else:
            logger.warning("Skipping malformed Goa goal entry: %s", key)
            return None

        if not goal_id or not goal.get("title"):
            logger.warning("Skipping malformed Goa goal entry: %s", key)
            return None

        status = str(goal.get("status") or "proposed")
        if status not in SUPPORTED_GOAL_STATUSES:
            status = "proposed"

        return {
            "goal_id": goal_id,
            "title": str(goal.get("title") or ""),
            "description": str(goal.get("description") or ""),
            "status": status,
            "progress_summary": str(goal.get("progress_summary") or ""),
            "completed_steps": self._as_list(goal.get("completed_steps")),
            "current_step": str(goal.get("current_step") or ""),
            "next_action": str(goal.get("next_action") or ""),
            "interest_signals": self._as_list(goal.get("interest_signals")),
            "created_at": str(goal.get("created_at") or ""),
            "updated_at": str(goal.get("updated_at") or ""),
            **(
                {"archived_reason": str(goal.get("archived_reason"))}
                if goal.get("archived_reason")
                else {}
            ),
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30.0, headers=self._headers()) as client:
            response = await client.request(method, f"{self._goa_url}{path}", **kwargs)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = response.text.strip()
            raise RuntimeError(
                f"Goa goal request failed: {method} {path} -> "
                f"HTTP {response.status_code} {response.reason_phrase}: {body or '<empty>'}"
            ) from exc

        return response

    async def _get_next_goal_id(self, user_id: str) -> str:
        goals = await self.get_goals(user_id)
        max_num = max((self._goal_number(goal["goal_id"]) for goal in goals), default=0)
        return f"goal-{max_num + 1:02d}"

    async def get_goals(
        self,
        user_id: str,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        response = await self._request(
            "GET",
            "/memory",
            params={"prefix": self._goal_prefix(user_id)},
        )
        entries = response.json().get("entries", [])
        goals = [parsed for entry in entries if (parsed := self._parse_entry(entry))]
        if statuses is not None:
            status_set = set(statuses)
            goals = [goal for goal in goals if goal["status"] in status_set]
        return sorted(goals, key=lambda goal: self._goal_number(goal["goal_id"]))

    async def get_goal(self, user_id: str, goal_id: str) -> Optional[Dict[str, Any]]:
        response = await self._request(
            "GET",
            "/memory",
            params={"key": self._goal_key(user_id, goal_id)},
        )
        entries = response.json().get("entries", [])
        if not entries:
            return None
        return self._parse_entry(entries[0])

    async def create_goal(
        self,
        user_id: str,
        title: str,
        description: str = "",
        status: str = "proposed",
    ) -> str:
        if status not in SUPPORTED_GOAL_STATUSES:
            raise ValueError(f"Unsupported goal status: {status}")

        goal_id = await self._get_next_goal_id(user_id)
        goal = self._goal_value(
            user_id,
            goal_id,
            {
                "title": title,
                "description": description,
                "status": status,
                "created_at": self._now(),
            },
        )
        await self._request(
            "POST",
            "/memory",
            json={
                "key": self._goal_key(user_id, goal_id),
                "value": goal,
                "tags": self._goal_tags(user_id, goal_id, status),
            },
        )
        logger.debug("Created Goa goal %s for user %s", goal_id, user_id)
        return goal_id

    async def update_goal(self, user_id: str, goal_id: str, updates: Dict[str, Any]) -> bool:
        existing = await self.get_goal(user_id, goal_id)
        if not existing:
            return False

        clean_updates = {k: v for k, v in updates.items() if v is not None}
        if clean_updates.get("interest_signals"):
            clean_updates["interest_signals"] = [
                *(existing.get("interest_signals") or []),
                *list(clean_updates["interest_signals"]),
            ]
        updated = {**existing, **clean_updates}
        status = updated.get("status", "proposed")
        if status not in SUPPORTED_GOAL_STATUSES:
            raise ValueError(f"Unsupported goal status: {status}")

        value = self._goal_value(user_id, goal_id, updated)
        await self._request(
            "POST",
            "/memory",
            json={
                "key": self._goal_key(user_id, goal_id),
                "value": value,
                "tags": self._goal_tags(user_id, goal_id, status),
            },
        )
        logger.debug("Updated Goa goal %s for user %s", goal_id, user_id)
        return True

    async def delete_goal(self, user_id: str, goal_id: str) -> bool:
        response = await self._request(
            "DELETE",
            "/memory",
            params={"key": self._goal_key(user_id, goal_id)},
        )
        deleted = response.json().get("deleted", 0)
        if deleted:
            logger.debug("Deleted Goa goal %s for user %s", goal_id, user_id)
            return True
        return False

    async def clear_goals(self, user_id: str) -> None:
        await self._request(
            "DELETE",
            "/memory",
            params={"prefix": self._goal_prefix(user_id)},
        )
        logger.info("Cleared all Goa goals for user %s", user_id)
