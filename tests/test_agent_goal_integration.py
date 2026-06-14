import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


os.environ.setdefault("GOA_API_KEY", "test-goa-key")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bulbul_agent import main as agent_main
from bulbul_agent.core.tools import goal_tool, progress_tool


class JsonResponse:
    def __init__(self, data=None, status_code=200, content=b""):
        self._data = data or {}
        self.status_code = status_code
        self.content = content
        self.text = ""

    def json(self):
        return self._data

    def raise_for_status(self):
        return None


class FakeRunner:
    def __init__(self, *args, **kwargs):
        self.session_service = kwargs["session_service"]

    async def run_async(self, **kwargs):
        event = SimpleNamespace(
            content=SimpleNamespace(
                parts=[SimpleNamespace(text="جواب", thought=False)]
            ),
            is_final_response=lambda: True,
        )
        yield event


class AgentGoalIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_goals_command_posts_goal_cards_ui_payload(self):
        question = {
            "id": "q1",
            "event_type": "question",
            "content": {"text": "/goals"},
        }
        agent_main._goal_service.get_goals = AsyncMock(return_value=[
            {
                "goal_id": "goal-01",
                "title": "Learn Python",
                "status": "active",
                "progress_summary": "Started",
            }
        ])
        posted_payloads = []

        async def fake_goa_request(method, path, **kwargs):
            if method == "GET" and path == "/tasks/task-1":
                return JsonResponse({"task": {"external_ref": "telegram_123"}})
            if method == "POST" and path == "/tasks/task-1/events":
                posted_payloads.append(kwargs["json"])
                return JsonResponse(status_code=201)
            raise AssertionError(f"Unexpected Goa request: {method} {path}")

        with patch.object(agent_main, "_goa_request", AsyncMock(side_effect=fake_goa_request)):
            await agent_main.process_question("task-1", "q1", [question])

        self.assertEqual(posted_payloads[0]["metadata"]["ui"]["type"], "goal_cards")
        self.assertEqual(posted_payloads[0]["metadata"]["ui"]["goals"][0]["goal_id"], "goal-01")

    async def test_post_answer_uses_top_level_metadata_for_ui(self):
        calls = []

        async def fake_goa_request(method, path, **kwargs):
            calls.append(kwargs["json"])
            return JsonResponse(status_code=201)

        with patch.object(agent_main, "_goa_request", AsyncMock(side_effect=fake_goa_request)):
            await agent_main.post_answer(
                "task-1",
                "q1",
                "hello",
                ui={"type": "goal_cards", "goals": []},
            )

        self.assertEqual(calls[0]["content"], {"text": "hello"})
        self.assertEqual(calls[0]["metadata"], {"ui": {"type": "goal_cards", "goals": []}})

    async def test_post_progress_uses_progress_event_type(self):
        calls = []

        async def fake_goa_request(method, path, **kwargs):
            calls.append(kwargs["json"])
            return JsonResponse(status_code=201)

        with patch.object(agent_main, "_goa_request", AsyncMock(side_effect=fake_goa_request)):
            await agent_main.post_progress("task-1", "q1", "أراجع أهدافك الآن.")

        self.assertEqual(calls[0]["event_type"], "progress")
        self.assertEqual(calls[0]["content"], {"text": "أراجع أهدافك الآن."})
        self.assertEqual(calls[0]["in_reply_to"], "q1")
        self.assertEqual(calls[0]["payload"], {"answering": ["q1"]})

    async def test_progress_tool_sends_current_turn_message(self):
        sender = AsyncMock()
        progress_tool.init_progress_tool(sender)

        result = await progress_tool.send_progress("أبحث عن المعلومة الآن.")

        self.assertEqual(result["status"], "success")
        sender.assert_awaited_once_with("أبحث عن المعلومة الآن.")

    async def test_process_question_loads_goals_into_state_and_initializes_tool(self):
        question = {
            "id": "q1",
            "event_type": "question",
            "content": {"text": "اشرح loops"},
        }
        agent_main._persona_service.get_persona = AsyncMock(return_value={})
        agent_main._memory_service.get_memories = AsyncMock(return_value=[])
        agent_main._goal_service.get_goals = AsyncMock(return_value=[
            {
                "goal_id": "goal-01",
                "title": "Learn Python",
                "description": "From zero",
                "status": "active",
                "progress_summary": "Finished variables",
                "completed_steps": ["variables"],
                "current_step": "loops",
                "next_action": "practice loops",
                "interest_signals": [],
            }
        ])

        async def fake_goa_request(method, path, **kwargs):
            if method == "GET" and path == "/tasks/task-1":
                return JsonResponse({"task": {"external_ref": "telegram_123"}})
            if method == "POST" and path == "/tasks/task-1/events":
                return JsonResponse(status_code=201)
            raise AssertionError(f"Unexpected Goa request: {method} {path}")

        with (
            patch.object(agent_main, "_goa_request", AsyncMock(side_effect=fake_goa_request)),
            patch.object(agent_main, "Runner", FakeRunner),
        ):
            await agent_main.process_question("task-1", "q1", [question])

        agent_main._goal_service.get_goals.assert_awaited_once_with(
            "123",
            statuses=("proposed", "active", "paused"),
        )
        self.assertIs(goal_tool._goal_service, agent_main._goal_service)
        self.assertEqual(goal_tool._current_user_id, "123")
        self.assertIsNotNone(progress_tool._progress_sender)

    def test_format_goals_for_state_includes_progress_fields(self):
        formatted = agent_main._format_goals_for_state([
            {
                "goal_id": "goal-01",
                "title": "Learn Python",
                "description": "From zero",
                "status": "active",
                "progress_summary": "Finished variables",
                "completed_steps": ["variables"],
                "current_step": "loops",
                "next_action": "practice loops",
            }
        ])

        self.assertIn("[goal-01] Learn Python (active)", formatted)
        self.assertIn("Finished variables", formatted)
        self.assertIn("practice loops", formatted)


if __name__ == "__main__":
    unittest.main()
