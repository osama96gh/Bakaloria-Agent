import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


os.environ.setdefault("GOA_API_KEY", "test-goa-key")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bulbul_agent.core.tools import goal_tool


class GoalToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = SimpleNamespace(
            get_goals=AsyncMock(return_value=[]),
            create_goal=AsyncMock(return_value="goal-01"),
            update_goal=AsyncMock(return_value=True),
            delete_goal=AsyncMock(return_value=True),
        )
        goal_tool.init_goal_tool(self.service, "123")

    async def test_create_proposed_requires_title(self):
        result = await goal_tool.manage_goal("create_proposed")

        self.assertEqual(result["status"], "error")
        self.service.create_goal.assert_not_awaited()

    async def test_create_proposed_creates_proposed_goal(self):
        result = await goal_tool.manage_goal(
            "create_proposed",
            title="Learn Python",
            description="From zero",
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["goal_id"], "goal-01")
        self.service.create_goal.assert_awaited_once_with(
            "123",
            title="Learn Python",
            description="From zero",
            status="proposed",
        )

    async def test_update_progress_requires_goal_id(self):
        result = await goal_tool.manage_goal("update_progress", progress_summary="Done")

        self.assertEqual(result["status"], "error")
        self.service.update_goal.assert_not_awaited()

    async def test_update_progress_parses_completed_steps(self):
        result = await goal_tool.manage_goal(
            "update_progress",
            goal_id="goal-01",
            progress_summary="Finished basics",
            completed_steps='["variables", "loops"]',
            current_step="functions",
            next_action="Solve 3 exercises",
            interest_signal="asked for practice",
        )

        self.assertEqual(result["status"], "success")
        self.service.update_goal.assert_awaited_once_with(
            "123",
            "goal-01",
            {
                "progress_summary": "Finished basics",
                "completed_steps": ["variables", "loops"],
                "current_step": "functions",
                "next_action": "Solve 3 exercises",
                "interest_signals": ["asked for practice"],
            },
        )

    async def test_archive_sets_archived_status_and_reason(self):
        result = await goal_tool.manage_goal(
            "archive",
            goal_id="goal-01",
            archived_reason="User confirmed no longer interested",
        )

        self.assertEqual(result["status"], "success")
        self.service.update_goal.assert_awaited_once_with(
            "123",
            "goal-01",
            {
                "status": "archived",
                "archived_reason": "User confirmed no longer interested",
            },
        )

    async def test_list_returns_goals(self):
        self.service.get_goals.return_value = [{"goal_id": "goal-01", "title": "Python"}]

        result = await goal_tool.manage_goal("list")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["goals"], [{"goal_id": "goal-01", "title": "Python"}])
        self.service.get_goals.assert_awaited_once_with("123")


if __name__ == "__main__":
    unittest.main()
