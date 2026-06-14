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

"""ADK Tool for managing user goals and progress."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..goal_service import GoalService

logger = logging.getLogger(__name__)

_goal_service: "GoalService" = None
_current_user_id: str = None


def init_goal_tool(goal_service: "GoalService", user_id: str) -> None:
    """Initialize the goal tool with service and user context."""
    global _goal_service, _current_user_id
    _goal_service = goal_service
    _current_user_id = user_id


def _parse_list(value: Any) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
        return [line.strip("- •\t ") for line in stripped.splitlines() if line.strip("- •\t ")]
    return [str(value)]


def _clean_updates(
    *,
    title: str = "",
    description: str = "",
    status: str = "",
    progress_summary: str = "",
    completed_steps: Any = "",
    current_step: str = "",
    next_action: str = "",
    interest_signal: str = "",
    archived_reason: str = "",
) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}
    if title:
        updates["title"] = title
    if description:
        updates["description"] = description
    if status:
        updates["status"] = status
    if progress_summary:
        updates["progress_summary"] = progress_summary
    parsed_steps = _parse_list(completed_steps)
    if parsed_steps:
        updates["completed_steps"] = parsed_steps
    if current_step:
        updates["current_step"] = current_step
    if next_action:
        updates["next_action"] = next_action
    if interest_signal:
        updates["interest_signals"] = [interest_signal]
    if archived_reason:
        updates["archived_reason"] = archived_reason
    return updates


async def manage_goal(
    action: str,
    goal_id: str = "",
    title: str = "",
    description: str = "",
    progress_summary: str = "",
    completed_steps: str = "",
    current_step: str = "",
    next_action: str = "",
    interest_signal: str = "",
    archived_reason: str = "",
) -> Dict[str, Any]:
    """
    Manage user goals and progress.

    Use this tool for long-running learning or practical personal goals. Do not
    use it for casual one-off questions. Ask the user before creating a goal or
    before pausing/archiving because they seem uninterested.

    Actions:
    - "create_proposed": Create a proposed goal after asking the user or when
      preparing a goal suggestion. Requires title.
    - "activate": Mark a goal active after user confirmation. Requires goal_id.
    - "update_progress": Update milestone progress for a relevant active goal.
      Requires goal_id and at least one progress field.
    - "pause": Pause a goal after user confirmation. Requires goal_id.
    - "complete": Mark a goal completed. Requires goal_id.
    - "archive": Archive a goal after user confirmation. Requires goal_id.
    - "list": List all goals.
    - "delete": Permanently delete a goal. Requires goal_id.

    completed_steps can be a JSON list string or newline-separated text.
    """
    global _goal_service, _current_user_id

    if not _goal_service or not _current_user_id:
        logger.error("Goal tool not initialized - missing service or user_id")
        return {"status": "error", "message": "خدمة الأهداف غير متاحة حالياً"}

    try:
        if action == "list":
            goals = await _goal_service.get_goals(_current_user_id)
            return {"status": "success", "goals": goals}

        if action == "create_proposed":
            if not title:
                return {"status": "error", "message": "يجب تحديد عنوان الهدف"}
            new_goal_id = await _goal_service.create_goal(
                _current_user_id,
                title=title,
                description=description,
                status="proposed",
            )
            return {
                "status": "success",
                "message": f"تم اقتراح الهدف: {new_goal_id}",
                "goal_id": new_goal_id,
            }

        if action in {"activate", "pause", "complete", "archive", "delete", "update_progress"}:
            if not goal_id:
                return {"status": "error", "message": "يجب تحديد goal_id"}

        if action == "delete":
            deleted = await _goal_service.delete_goal(_current_user_id, goal_id)
            if deleted:
                return {"status": "success", "message": f"تم حذف الهدف: {goal_id}"}
            return {"status": "error", "message": f"لم يتم العثور على الهدف: {goal_id}"}

        status_by_action = {
            "activate": "active",
            "pause": "paused",
            "complete": "completed",
            "archive": "archived",
        }

        if action in status_by_action:
            updates = _clean_updates(
                title=title,
                description=description,
                progress_summary=progress_summary,
                completed_steps=completed_steps,
                current_step=current_step,
                next_action=next_action,
                interest_signal=interest_signal,
                archived_reason=archived_reason,
            )
            updates["status"] = status_by_action[action]
            updated = await _goal_service.update_goal(_current_user_id, goal_id, updates)
            if updated:
                return {"status": "success", "message": f"تم تحديث الهدف: {goal_id}"}
            return {"status": "error", "message": f"لم يتم العثور على الهدف: {goal_id}"}

        if action == "update_progress":
            updates = _clean_updates(
                title=title,
                description=description,
                progress_summary=progress_summary,
                completed_steps=completed_steps,
                current_step=current_step,
                next_action=next_action,
                interest_signal=interest_signal,
            )
            if not updates:
                return {"status": "error", "message": "يجب تحديد تحديث واحد على الأقل"}
            updated = await _goal_service.update_goal(_current_user_id, goal_id, updates)
            if updated:
                return {"status": "success", "message": f"تم تحديث تقدم الهدف: {goal_id}"}
            return {"status": "error", "message": f"لم يتم العثور على الهدف: {goal_id}"}

        return {
            "status": "error",
            "message": (
                "إجراء غير معروف. استخدم create_proposed أو activate أو "
                "update_progress أو pause أو complete أو archive أو list أو delete"
            ),
        }

    except Exception as e:
        logger.error("Error in manage_goal: %s", e)
        return {"status": "error", "message": f"خطأ في إدارة الأهداف: {str(e)}"}
