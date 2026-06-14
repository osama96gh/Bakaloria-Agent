import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("GOA_API_KEY", "test-goa-key")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telegram.error import Forbidden

from telegram_service import main as telegram_main
from telegram_service.telegram_bot import handlers


def make_update(text="hello"):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=123, username="tester"),
        effective_chat=SimpleNamespace(id=456),
        message=SimpleNamespace(
            text=text,
            caption=None,
            photo=["photo"],
            voice=SimpleNamespace(file_id="voice-id", mime_type="audio/ogg", duration=1),
            reply_text=AsyncMock(),
        ),
    )


def make_callback_update(data="goal:continue:goal-01"):
    return SimpleNamespace(
        callback_query=SimpleNamespace(
            data=data,
            from_user=SimpleNamespace(id=123),
            message=SimpleNamespace(
                chat_id=456,
                reply_text=AsyncMock(),
            ),
            answer=AsyncMock(),
        ),
        poll_answer=None,
    )


def make_poll_answer_update(poll_id="poll-1", option_ids=None):
    return SimpleNamespace(
        callback_query=None,
        poll_answer=SimpleNamespace(
            poll_id=poll_id,
            option_ids=[0] if option_ids is None else option_ids,
        ),
    )


def make_context():
    return SimpleNamespace(
        bot=SimpleNamespace(
            send_chat_action=AsyncMock(),
            send_message=AsyncMock(),
            send_poll=AsyncMock(return_value=SimpleNamespace(poll=SimpleNamespace(id="poll-1"))),
            get_file=AsyncMock(),
        )
    )


class TelegramHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_or_create_goa_task_uses_purpose_in_external_ref(self):
        response = Mock()
        response.json.return_value = {"task": {"id": "task-1"}}
        goa_request = AsyncMock(return_value=response)

        with patch.object(handlers, "_goa_request", goa_request):
            task_id = await handlers.get_or_create_goa_task(
                123,
                purpose="outreach",
                parent_task_id="main-task",
            )

        self.assertEqual(task_id, "task-1")
        response.raise_for_status.assert_called_once_with()
        goa_request.assert_awaited_once_with("POST", "/tasks/upsert", json={
            "external_ref": "telegram_123_outreach",
            "on_create": {
                "parent_task_id": "main-task",
                "subject": "outreach for telegram_123",
            },
        })

    async def test_reset_goa_task_raises_for_close_response(self):
        response = Mock()

        goa_request = AsyncMock(return_value=response)
        with (
            patch.object(handlers, "get_or_create_goa_task", AsyncMock(return_value="task-1")),
            patch.object(handlers, "_goa_request", goa_request),
        ):
            result = await handlers.reset_goa_task(123)

        self.assertTrue(result)
        response.raise_for_status.assert_called_once_with()
        goa_request.assert_awaited_once_with("POST", "/tasks/task-1/close")

    async def test_new_command_sends_success_only_when_reset_succeeds(self):
        update = make_update("/new")

        with (
            patch.object(handlers, "reset_goa_task", AsyncMock(return_value=True)),
            patch.object(handlers, "outreach_service", None),
        ):
            await handlers.new_command(update, make_context())

        update.message.reply_text.assert_awaited_once()
        args, kwargs = update.message.reply_text.await_args
        self.assertIn("تم بدء محادثة جديدة", args[0])
        self.assertIsNone(kwargs["parse_mode"])

    async def test_new_command_reports_failed_reset(self):
        update = make_update("/new")

        with (
            patch.object(handlers, "reset_goa_task", AsyncMock(return_value=False)),
            patch.object(handlers, "outreach_service", None),
        ):
            await handlers.new_command(update, make_context())

        update.message.reply_text.assert_awaited_once()
        args, kwargs = update.message.reply_text.await_args
        self.assertIn("لم أتمكن من بدء محادثة جديدة", args[0])
        self.assertIsNone(kwargs["parse_mode"])

    async def test_reset_persona_warns_when_session_reset_fails(self):
        update = make_update("/reset_persona")

        with (
            patch.object(handlers, "forward_to_agent", AsyncMock()),
            patch.object(handlers, "reset_goa_task", AsyncMock(return_value=False)),
            patch.object(handlers, "outreach_service", None),
        ):
            await handlers.reset_persona_command(update, make_context())

        update.message.reply_text.assert_awaited_once()
        args, kwargs = update.message.reply_text.await_args
        self.assertIn("لم أتمكن من مسح سجل المحادثة", args[0])
        self.assertIsNone(kwargs["parse_mode"])

    async def test_inbound_handlers_record_engagement(self):
        update = make_update("hello")
        context = make_context()
        outreach = Mock()

        with (
            patch.object(handlers, "outreach_service", outreach),
            patch.object(handlers, "forward_to_agent", AsyncMock()),
            patch.object(handlers, "reset_goa_task", AsyncMock(return_value=True)),
            patch.object(handlers, "download_photo", AsyncMock(return_value=(b"img", "image/jpeg"))),
            patch.object(handlers, "download_voice", AsyncMock(return_value=(None, "", 0))),
        ):
            await handlers.start_command(update, context)
            await handlers.help_command(update, context)
            await handlers.goals_command(update, context)
            await handlers.new_command(update, context)
            await handlers.reset_persona_command(update, context)
            await handlers.handle_message(update, context)
            await handlers.handle_photo_message(update, context)
            await handlers.handle_voice_message(update, context)

        self.assertEqual(outreach.update_interaction.call_count, 8)
        outreach.update_interaction.assert_called_with("telegram", "123", 456)

    async def test_goals_command_forwards_to_agent(self):
        update = make_update("/goals")

        with (
            patch.object(handlers, "forward_to_agent", AsyncMock()) as forward,
            patch.object(handlers, "outreach_service", None),
        ):
            await handlers.goals_command(update, make_context())

        forward.assert_awaited_once()
        self.assertEqual(forward.await_args.args[2], "/goals")

    async def test_settings_command_sends_buttons(self):
        update = make_update("/settings")

        with patch.object(handlers, "outreach_service", None):
            await handlers.settings_command(update, make_context())

        update.message.reply_text.assert_awaited_once()
        args, kwargs = update.message.reply_text.await_args
        self.assertIn("الإعدادات", args[0])
        self.assertIsNotNone(kwargs["reply_markup"])

    async def test_render_goal_cards_uses_inline_markup(self):
        update = make_update("/goals")
        result = {
            "status": "success",
            "response": "fallback",
            "ui": {
                "type": "goal_cards",
                "goals": [{
                    "goal_id": "goal-01",
                    "title": "Learn Python",
                    "status": "active",
                    "progress_summary": "Started",
                }],
            },
        }

        await handlers.render_agent_result(update, make_context(), result)

        update.message.reply_text.assert_awaited_once()
        args, kwargs = update.message.reply_text.await_args
        self.assertIn("Learn Python", args[0])
        self.assertIsNotNone(kwargs["reply_markup"])

    async def test_ask_agent_reads_ui_from_answer_metadata(self):
        post_response = Mock()
        post_response.json.return_value = {"event": {"id": "q1"}}
        post_response.raise_for_status.return_value = None
        task_response = Mock()
        task_response.status_code = 200
        task_response.json.return_value = {
            "events": [{
                "event_type": "answer",
                "in_reply_to": "q1",
                "content": {
                    "text": "goals",
                },
                "metadata": {"ui": {"type": "goal_cards", "goals": []}},
            }]
        }

        with patch.object(
            handlers,
            "_goa_request",
            AsyncMock(side_effect=[post_response, task_response]),
        ):
            result = await handlers.ask_agent_via_goa("task-1", "/goals")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["ui"], {"type": "goal_cards", "goals": []})

    async def test_ask_agent_does_not_send_fixed_progress_while_polling(self):
        post_response = Mock()
        post_response.json.return_value = {"event": {"id": "q1"}}
        post_response.raise_for_status.return_value = None
        pending_response = Mock()
        pending_response.status_code = 200
        pending_response.json.return_value = {"events": []}
        answer_response = Mock()
        answer_response.status_code = 200
        answer_response.json.return_value = {
            "events": [{
                "event_type": "answer",
                "in_reply_to": "q1",
                "content": {"text": "done"},
            }]
        }
        progress = AsyncMock()

        with (
            patch.object(handlers.asyncio, "sleep", AsyncMock()),
            patch.object(
                handlers,
                "_goa_request",
                AsyncMock(side_effect=[post_response, pending_response, answer_response]),
            ),
        ):
            result = await handlers.ask_agent_via_goa(
                "task-1",
                "slow question",
                progress_callback=progress,
            )

        self.assertEqual(result["status"], "success")
        progress.assert_not_awaited()

    async def test_ask_agent_forwards_agent_progress_events(self):
        post_response = Mock()
        post_response.json.return_value = {"event": {"id": "q1"}}
        post_response.raise_for_status.return_value = None
        progress_response = Mock()
        progress_response.status_code = 200
        progress_response.json.return_value = {
            "events": [{
                "id": "p1",
                "event_type": "progress",
                "in_reply_to": "q1",
                "content": {"text": "أراجع أهدافك الآن."},
            }]
        }
        answer_response = Mock()
        answer_response.status_code = 200
        answer_response.json.return_value = {
            "events": [
                {
                    "id": "p1",
                    "event_type": "progress",
                    "in_reply_to": "q1",
                    "content": {"text": "أراجع أهدافك الآن."},
                },
                {
                    "event_type": "answer",
                    "in_reply_to": "q1",
                    "content": {"text": "done"},
                },
            ]
        }
        progress = AsyncMock()

        with (
            patch.object(handlers.asyncio, "sleep", AsyncMock()),
            patch.object(
                handlers,
                "_goa_request",
                AsyncMock(side_effect=[post_response, progress_response, answer_response]),
            ),
        ):
            result = await handlers.ask_agent_via_goa(
                "task-1",
                "slow question",
                progress_callback=progress,
            )

        self.assertEqual(result["status"], "success")
        progress.assert_awaited_once_with("أراجع أهدافك الآن.")

    async def test_keep_typing_refreshes_until_stopped(self):
        bot = SimpleNamespace(send_chat_action=AsyncMock())
        stop_event = asyncio.Event()

        with patch.object(handlers, "TYPING_REFRESH_SECONDS", 0.01):
            typing_task = asyncio.create_task(
                handlers.keep_typing(bot, 456, stop_event)
            )
            await asyncio.sleep(0.025)
            stop_event.set()
            await asyncio.wait_for(typing_task, timeout=1)

        self.assertGreaterEqual(bot.send_chat_action.await_count, 2)
        bot.send_chat_action.assert_awaited_with(
            chat_id=456,
            action=handlers.ChatAction.TYPING,
        )

    async def test_send_agent_text_renders_progress_before_final_response(self):
        context = make_context()
        reply_message = SimpleNamespace(reply_text=AsyncMock())

        async def fake_ask_agent(*args, progress_callback=None, **kwargs):
            await progress_callback("أراجع التفاصيل الآن.")
            return {"status": "success", "response": "الجواب النهائي"}

        with (
            patch.object(handlers, "get_or_create_goa_task", AsyncMock(return_value="task-1")),
            patch.object(handlers, "ask_agent_via_goa", fake_ask_agent),
        ):
            await handlers.send_agent_text(
                user_id=123,
                chat_id=456,
                context=context,
                query_text="hello",
                reply_message=reply_message,
            )

        self.assertEqual(reply_message.reply_text.await_count, 2)
        first_args, first_kwargs = reply_message.reply_text.await_args_list[0]
        second_args, _ = reply_message.reply_text.await_args_list[1]
        self.assertIn("أراجع التفاصيل", first_args[0])
        self.assertIsNone(first_kwargs["parse_mode"])
        self.assertEqual(second_args[0], "الجواب النهائي")

    async def test_callback_goal_continue_forwards_synthetic_prompt(self):
        update = make_callback_update("goal:continue:goal-01")

        with patch.object(handlers, "send_agent_text", AsyncMock()) as send_agent:
            await handlers.callback_query_handler(update, make_context())

        update.callback_query.answer.assert_awaited_once()
        send_agent.assert_awaited_once()
        self.assertIn("goal-01", send_agent.await_args.kwargs["query_text"])

    async def test_callback_pause_asks_for_confirmation(self):
        update = make_callback_update("goal:pause:goal-01")

        await handlers.callback_query_handler(update, make_context())

        update.callback_query.message.reply_text.assert_awaited_once()
        _, kwargs = update.callback_query.message.reply_text.await_args
        self.assertIsNotNone(kwargs["reply_markup"])

    async def test_quiz_callback_sends_poll_and_stores_context(self):
        update = make_callback_update("goal:quiz:goal-01")
        context = make_context()
        quiz_json = (
            '{"question":"What repeats code?","options":["Variable","Loop"],'
            '"correct_index":1,"explanation":"Loops repeat code."}'
        )

        handlers.POLL_CONTEXTS.clear()
        with patch.object(
            handlers,
            "send_agent_text",
            AsyncMock(return_value={"status": "success", "response": quiz_json}),
        ):
            await handlers.callback_query_handler(update, context)

        context.bot.send_poll.assert_awaited_once()
        self.assertEqual(handlers.POLL_CONTEXTS["poll-1"]["goal_id"], "goal-01")

    async def test_quiz_callback_falls_back_on_invalid_json(self):
        update = make_callback_update("goal:quiz:goal-01")
        context = make_context()

        with patch.object(
            handlers,
            "send_agent_text",
            AsyncMock(return_value={"status": "success", "response": "not json"}),
        ):
            await handlers.callback_query_handler(update, context)

        context.bot.send_poll.assert_not_awaited()
        update.callback_query.message.reply_text.assert_awaited_once()

    async def test_poll_answer_forwards_progress_context(self):
        handlers.POLL_CONTEXTS.clear()
        handlers.POLL_CONTEXTS["poll-1"] = {
            "goal_id": "goal-01",
            "user_id": 123,
            "chat_id": 456,
            "correct_index": 0,
        }

        with patch.object(handlers, "send_agent_text", AsyncMock()) as send_agent:
            await handlers.poll_answer_handler(make_poll_answer_update(), make_context())

        send_agent.assert_awaited_once()
        self.assertIn("صحيحة", send_agent.await_args.kwargs["query_text"])


class OutreachJobTests(unittest.IsolatedAsyncioTestCase):
    def test_allowed_updates_include_interactive_types(self):
        self.assertIn("callback_query", telegram_main.ALLOWED_UPDATES)
        self.assertIn("poll_answer", telegram_main.ALLOWED_UPDATES)

    def test_outreach_prompt_is_goal_aware_and_preserves_skip(self):
        prompt = telegram_main._build_outreach_prompt(6)

        self.assertIn("أهداف المستخدم", prompt)
        self.assertIn("هدف نشط", prompt)
        self.assertIn("SKIP", prompt)
        self.assertIn("لا توقف أو تؤرشف", prompt)

    async def test_get_or_create_outreach_task_links_to_main_task(self):
        get_task = AsyncMock(side_effect=["main-task", "outreach-task"])

        with patch.object(telegram_main, "get_or_create_goa_task", get_task):
            task_id = await telegram_main.get_or_create_outreach_task(123)

        self.assertEqual(task_id, "outreach-task")
        self.assertEqual(get_task.await_args_list[0].args, (123,))
        self.assertEqual(get_task.await_args_list[1].args, (123,))
        self.assertEqual(get_task.await_args_list[1].kwargs, {
            "purpose": "outreach",
            "parent_task_id": "main-task",
        })

    async def test_get_or_create_outreach_task_falls_back_when_parent_rejected(self):
        get_task = AsyncMock(side_effect=["main-task", RuntimeError("bad parent"), "fallback-task"])

        with patch.object(telegram_main, "get_or_create_goa_task", get_task):
            task_id = await telegram_main.get_or_create_outreach_task(123)

        self.assertEqual(task_id, "fallback-task")
        self.assertEqual(get_task.await_args_list[2].args, (123,))
        self.assertEqual(get_task.await_args_list[2].kwargs, {"purpose": "outreach"})

    async def test_outreach_job_skips_when_agent_returns_skip(self):
        outreach = Mock()
        outreach.get_outreach_candidates.return_value = [self._candidate()]
        context = make_context()
        get_task = AsyncMock(return_value="task-1")
        close_task = AsyncMock(return_value=True)

        with (
            patch.object(telegram_main, "outreach_service", outreach),
            patch.object(telegram_main, "get_or_create_outreach_task", get_task),
            patch.object(telegram_main, "close_goa_task", close_task),
            patch.object(
                telegram_main,
                "ask_agent_via_goa",
                AsyncMock(return_value={"status": "success", "response": "SKIP"}),
            ),
        ):
            await telegram_main.outreach_job(context)

        context.bot.send_message.assert_not_awaited()
        outreach.record_outreach.assert_not_called()
        get_task.assert_awaited_once_with(123)
        close_task.assert_awaited_once_with("task-1")

    async def test_outreach_job_sends_response_and_records_outreach(self):
        outreach = Mock()
        outreach.get_outreach_candidates.return_value = [self._candidate()]
        context = make_context()
        get_task = AsyncMock(return_value="task-1")
        close_task = AsyncMock(return_value=True)

        with (
            patch.object(telegram_main, "outreach_service", outreach),
            patch.object(telegram_main, "get_or_create_outreach_task", get_task),
            patch.object(telegram_main, "close_goa_task", close_task),
            patch.object(
                telegram_main,
                "ask_agent_via_goa",
                AsyncMock(return_value={"status": "success", "response": "<b>مرحبا</b>"}),
            ),
        ):
            await telegram_main.outreach_job(context)

        context.bot.send_message.assert_awaited_once()
        _, kwargs = context.bot.send_message.await_args
        self.assertEqual(kwargs["chat_id"], 456)
        self.assertEqual(kwargs["text"], "<b>مرحبا</b>")
        self.assertEqual(kwargs["parse_mode"], "HTML")
        self.assertIsNotNone(kwargs["reply_markup"])
        context.bot.send_message.assert_awaited_with(
            chat_id=456,
            text="<b>مرحبا</b>",
            parse_mode="HTML",
            reply_markup=kwargs["reply_markup"],
        )
        outreach.record_outreach.assert_called_once_with("telegram", "123")
        get_task.assert_awaited_once_with(123)
        close_task.assert_awaited_once_with("task-1")

    async def test_outreach_job_disables_outreach_when_user_blocks_bot(self):
        table = Mock()
        table.update.return_value = table
        table.eq.return_value = table
        client = Mock()
        client.table.return_value = table
        outreach = Mock()
        outreach._client = client
        outreach.get_outreach_candidates.return_value = [self._candidate()]
        context = make_context()
        context.bot.send_message.side_effect = Forbidden("blocked")
        get_task = AsyncMock(return_value="task-1")
        close_task = AsyncMock(return_value=True)

        with (
            patch.object(telegram_main, "outreach_service", outreach),
            patch.object(telegram_main, "get_or_create_outreach_task", get_task),
            patch.object(telegram_main, "close_goa_task", close_task),
            patch.object(
                telegram_main,
                "ask_agent_via_goa",
                AsyncMock(return_value={"status": "success", "response": "مرحبا"}),
            ),
        ):
            await telegram_main.outreach_job(context)

        client.table.assert_called_once_with("user_engagement")
        table.update.assert_called_once_with({"outreach_enabled": False})
        table.execute.assert_called_once_with()
        outreach.record_outreach.assert_not_called()
        get_task.assert_awaited_once_with(123)
        close_task.assert_awaited_once_with("task-1")

    def _candidate(self):
        return {
            "platform_user_id": "123",
            "chat_id": 456,
            "last_interaction_at": (
                datetime.now(timezone.utc) - timedelta(hours=6)
            ).isoformat(),
        }


if __name__ == "__main__":
    unittest.main()
