import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock


os.environ.setdefault("GOA_API_KEY", "test-goa-key")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bulbul_agent.core.goal_service import GoalService


class JsonResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class GoalServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = GoalService(goa_url="http://goa.test", goa_api_key="key")

    async def test_get_goals_reads_rich_values_sorted_and_filtered(self):
        self.service._request = AsyncMock(return_value=JsonResponse({
            "entries": [
                {
                    "key": "user:123:goal:goal-02",
                    "value": {
                        "type": "user_goal",
                        "goal_id": "goal-02",
                        "title": "Fitness",
                        "status": "archived",
                    },
                },
                {
                    "key": "user:123:goal:goal-01",
                    "value": {
                        "type": "user_goal",
                        "goal_id": "goal-01",
                        "title": "Python",
                        "status": "active",
                        "completed_steps": ["variables"],
                    },
                },
            ]
        }))

        goals = await self.service.get_goals("123", statuses=("active",))

        self.assertEqual(len(goals), 1)
        self.assertEqual(goals[0]["goal_id"], "goal-01")
        self.assertEqual(goals[0]["completed_steps"], ["variables"])
        self.service._request.assert_awaited_once_with(
            "GET",
            "/memory",
            params={"prefix": "user:123:goal:"},
        )

    async def test_create_goal_uses_next_goal_id_and_goa_key(self):
        self.service._request = AsyncMock(side_effect=[
            JsonResponse({
                "entries": [
                    {
                        "key": "user:123:goal:goal-02",
                        "value": {"goal_id": "goal-02", "title": "Old"},
                    }
                ]
            }),
            JsonResponse({"key": "user:123:goal:goal-03"}),
        ])

        goal_id = await self.service.create_goal("123", "Learn Python", "From zero")

        self.assertEqual(goal_id, "goal-03")
        _, post_call = self.service._request.await_args_list
        self.assertEqual(post_call.args[:2], ("POST", "/memory"))
        payload = post_call.kwargs["json"]
        self.assertEqual(payload["key"], "user:123:goal:goal-03")
        self.assertEqual(payload["value"]["title"], "Learn Python")
        self.assertEqual(payload["value"]["description"], "From zero")
        self.assertEqual(payload["value"]["status"], "proposed")

    async def test_update_goal_returns_false_when_missing(self):
        self.service._request = AsyncMock(return_value=JsonResponse({"entries": []}))

        updated = await self.service.update_goal("123", "goal-01", {"status": "active"})

        self.assertFalse(updated)
        self.service._request.assert_awaited_once_with(
            "GET",
            "/memory",
            params={"key": "user:123:goal:goal-01"},
        )

    async def test_update_goal_preserves_created_at_and_appends_interest_signal(self):
        self.service._request = AsyncMock(side_effect=[
            JsonResponse({
                "entries": [
                    {
                        "key": "user:123:goal:goal-01",
                        "value": {
                            "type": "user_goal",
                            "goal_id": "goal-01",
                            "title": "Python",
                            "status": "active",
                            "created_at": "created",
                            "interest_signals": ["started lesson"],
                        },
                    }
                ]
            }),
            JsonResponse({"key": "user:123:goal:goal-01"}),
        ])

        updated = await self.service.update_goal(
            "123",
            "goal-01",
            {"progress_summary": "Finished loops", "interest_signals": ["asked for quiz"]},
        )

        self.assertTrue(updated)
        _, post_call = self.service._request.await_args_list
        value = post_call.kwargs["json"]["value"]
        self.assertEqual(value["created_at"], "created")
        self.assertEqual(value["progress_summary"], "Finished loops")
        self.assertEqual(value["interest_signals"], ["started lesson", "asked for quiz"])

    async def test_archive_goal_sets_status_and_reason(self):
        self.service._request = AsyncMock(side_effect=[
            JsonResponse({
                "entries": [
                    {
                        "key": "user:123:goal:goal-01",
                        "value": {
                            "type": "user_goal",
                            "goal_id": "goal-01",
                            "title": "Python",
                            "status": "active",
                        },
                    }
                ]
            }),
            JsonResponse({"key": "user:123:goal:goal-01"}),
        ])

        updated = await self.service.update_goal(
            "123",
            "goal-01",
            {"status": "archived", "archived_reason": "User lost interest"},
        )

        self.assertTrue(updated)
        _, post_call = self.service._request.await_args_list
        value = post_call.kwargs["json"]["value"]
        self.assertEqual(value["status"], "archived")
        self.assertEqual(value["archived_reason"], "User lost interest")

    async def test_delete_goal_deletes_by_key(self):
        self.service._request = AsyncMock(return_value=JsonResponse({"deleted": 1}))

        deleted = await self.service.delete_goal("123", "goal-01")

        self.assertTrue(deleted)
        self.service._request.assert_awaited_once_with(
            "DELETE",
            "/memory",
            params={"key": "user:123:goal:goal-01"},
        )


if __name__ == "__main__":
    unittest.main()
