"""Goal Service - manages user goals in Supabase ADK session state."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from supabase import Client, create_client

logger = logging.getLogger(__name__)

SUPPORTED_GOAL_STATUSES = {"proposed", "active", "paused", "completed", "archived"}


class GoalService:
    """Service for managing user goals and progress."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        client: Optional[Client] = None,
        app_name: str = "educational_assistant",
        **_: Any,
    ) -> None:
        self._client = client or create_client(
            supabase_url or self._required_env("SUPABASE_URL"),
            supabase_key or self._required_env("SUPABASE_SERVICE_KEY"),
        )
        self._app_name = app_name
        logger.info("GoalService initialized with Supabase adk_sessions")

    def _required_env(self, name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise RuntimeError(f"GoalService requires {name} environment variable")
        return value

    def _session_id(self, user_id: str) -> str:
        return f"bulbul:user:{user_id}:goals"

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

    def _normalize_goal(self, goal: dict[str, Any]) -> Optional[Dict[str, Any]]:
        goal_id = str(goal.get("goal_id") or "")
        title = str(goal.get("title") or "")
        if not goal_id or not title:
            logger.warning("Skipping malformed Supabase goal state entry: %s", goal)
            return None

        status = str(goal.get("status") or "proposed")
        if status not in SUPPORTED_GOAL_STATUSES:
            status = "proposed"

        normalized = {
            "goal_id": goal_id,
            "title": title,
            "description": str(goal.get("description") or ""),
            "status": status,
            "progress_summary": str(goal.get("progress_summary") or ""),
            "completed_steps": self._as_list(goal.get("completed_steps")),
            "current_step": str(goal.get("current_step") or ""),
            "next_action": str(goal.get("next_action") or ""),
            "interest_signals": self._as_list(goal.get("interest_signals")),
            "created_at": str(goal.get("created_at") or ""),
            "updated_at": str(goal.get("updated_at") or ""),
        }
        if goal.get("archived_reason"):
            normalized["archived_reason"] = str(goal.get("archived_reason"))
        return normalized

    def _goal_value(self, goal_id: str, goal: Dict[str, Any]) -> dict[str, Any]:
        now = self._now()
        value = {
            "goal_id": str(goal_id),
            "title": goal.get("title", ""),
            "description": goal.get("description", ""),
            "status": goal.get("status", "proposed"),
            "progress_summary": goal.get("progress_summary", ""),
            "completed_steps": goal.get("completed_steps") or [],
            "current_step": goal.get("current_step", ""),
            "next_action": goal.get("next_action", ""),
            "interest_signals": goal.get("interest_signals") or [],
            "created_at": goal.get("created_at") or now,
            "updated_at": now,
        }
        if goal.get("archived_reason"):
            value["archived_reason"] = goal["archived_reason"]
        return value

    async def _load_state(self, user_id: str) -> tuple[Optional[int], dict[str, Any]]:
        result = (
            self._client.table("adk_sessions")
            .select("id,state")
            .eq("session_id", self._session_id(user_id))
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None, {"goals": []}
        state = rows[0].get("state") or {}
        if not isinstance(state, dict):
            state = {"goals": []}
        state.setdefault("goals", [])
        return rows[0]["id"], state

    async def _save_state(self, user_id: str, row_id: Optional[int], state: dict[str, Any]) -> None:
        payload = {
            "session_id": self._session_id(user_id),
            "app_name": self._app_name,
            "user_id": str(user_id),
            "state": state,
            "updated_at": self._now(),
        }
        if row_id is None:
            self._client.table("adk_sessions").insert(payload).execute()
        else:
            (
                self._client.table("adk_sessions")
                .update(payload)
                .eq("id", row_id)
                .execute()
            )

    async def _get_next_goal_id(self, user_id: str) -> str:
        goals = await self.get_goals(user_id)
        max_num = max((self._goal_number(goal["goal_id"]) for goal in goals), default=0)
        return f"goal-{max_num + 1:02d}"

    async def get_goals(
        self,
        user_id: str,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        _, state = await self._load_state(user_id)
        goals = [
            parsed
            for goal in (state.get("goals") or [])
            if isinstance(goal, dict) and (parsed := self._normalize_goal(goal))
        ]
        if statuses is not None:
            status_set = set(statuses)
            goals = [goal for goal in goals if goal["status"] in status_set]
        return sorted(goals, key=lambda goal: self._goal_number(goal["goal_id"]))

    async def get_goal(self, user_id: str, goal_id: str) -> Optional[Dict[str, Any]]:
        goals = await self.get_goals(user_id)
        return next((goal for goal in goals if goal["goal_id"] == goal_id), None)

    async def create_goal(
        self,
        user_id: str,
        title: str,
        description: str = "",
        status: str = "proposed",
    ) -> str:
        if status not in SUPPORTED_GOAL_STATUSES:
            raise ValueError(f"Unsupported goal status: {status}")

        row_id, state = await self._load_state(user_id)
        goals = [
            parsed
            for goal in (state.get("goals") or [])
            if isinstance(goal, dict) and (parsed := self._normalize_goal(goal))
        ]
        max_num = max((self._goal_number(goal["goal_id"]) for goal in goals), default=0)
        goal_id = f"goal-{max_num + 1:02d}"
        goals.append(
            self._goal_value(
                goal_id,
                {
                    "title": title,
                    "description": description,
                    "status": status,
                    "created_at": self._now(),
                },
            )
        )
        state["goals"] = goals
        await self._save_state(user_id, row_id, state)
        logger.debug("Created goal %s for user %s", goal_id, user_id)
        return goal_id

    async def update_goal(self, user_id: str, goal_id: str, updates: Dict[str, Any]) -> bool:
        row_id, state = await self._load_state(user_id)
        goals = [
            parsed
            for goal in (state.get("goals") or [])
            if isinstance(goal, dict) and (parsed := self._normalize_goal(goal))
        ]
        for index, existing in enumerate(goals):
            if existing["goal_id"] != goal_id:
                continue

            clean_updates = {key: value for key, value in updates.items() if value is not None}
            if clean_updates.get("interest_signals"):
                clean_updates["interest_signals"] = [
                    *(existing.get("interest_signals") or []),
                    *list(clean_updates["interest_signals"]),
                ]
            updated = {**existing, **clean_updates}
            status = updated.get("status", "proposed")
            if status not in SUPPORTED_GOAL_STATUSES:
                raise ValueError(f"Unsupported goal status: {status}")

            goals[index] = self._goal_value(goal_id, updated)
            state["goals"] = goals
            await self._save_state(user_id, row_id, state)
            logger.debug("Updated goal %s for user %s", goal_id, user_id)
            return True
        return False

    async def delete_goal(self, user_id: str, goal_id: str) -> bool:
        row_id, state = await self._load_state(user_id)
        goals = [
            parsed
            for goal in (state.get("goals") or [])
            if isinstance(goal, dict) and (parsed := self._normalize_goal(goal))
        ]
        remaining = [goal for goal in goals if goal["goal_id"] != goal_id]
        if len(remaining) == len(goals):
            return False
        state["goals"] = remaining
        await self._save_state(user_id, row_id, state)
        logger.debug("Deleted goal %s for user %s", goal_id, user_id)
        return True

    async def clear_goals(self, user_id: str) -> None:
        row_id, state = await self._load_state(user_id)
        state["goals"] = []
        await self._save_state(user_id, row_id, state)
        logger.info("Cleared all goals for user %s", user_id)
