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


def make_context():
    return SimpleNamespace(
        bot=SimpleNamespace(
            send_chat_action=AsyncMock(),
            send_message=AsyncMock(),
            get_file=AsyncMock(),
        )
    )


class TelegramHandlerTests(unittest.IsolatedAsyncioTestCase):
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
            await handlers.new_command(update, context)
            await handlers.reset_persona_command(update, context)
            await handlers.handle_message(update, context)
            await handlers.handle_photo_message(update, context)
            await handlers.handle_voice_message(update, context)

        self.assertEqual(outreach.update_interaction.call_count, 7)
        outreach.update_interaction.assert_called_with("telegram", "123", 456)


class OutreachJobTests(unittest.IsolatedAsyncioTestCase):
    async def test_outreach_job_skips_when_agent_returns_skip(self):
        outreach = Mock()
        outreach.get_outreach_candidates.return_value = [self._candidate()]
        context = make_context()

        with (
            patch.object(telegram_main, "outreach_service", outreach),
            patch.object(telegram_main, "get_or_create_goa_task", AsyncMock(return_value="task-1")),
            patch.object(
                telegram_main,
                "ask_agent_via_goa",
                AsyncMock(return_value={"status": "success", "response": "SKIP"}),
            ),
        ):
            await telegram_main.outreach_job(context)

        context.bot.send_message.assert_not_awaited()
        outreach.record_outreach.assert_not_called()

    async def test_outreach_job_sends_response_and_records_outreach(self):
        outreach = Mock()
        outreach.get_outreach_candidates.return_value = [self._candidate()]
        context = make_context()

        with (
            patch.object(telegram_main, "outreach_service", outreach),
            patch.object(telegram_main, "get_or_create_goa_task", AsyncMock(return_value="task-1")),
            patch.object(
                telegram_main,
                "ask_agent_via_goa",
                AsyncMock(return_value={"status": "success", "response": "<b>مرحبا</b>"}),
            ),
        ):
            await telegram_main.outreach_job(context)

        context.bot.send_message.assert_awaited_once_with(
            chat_id=456,
            text="<b>مرحبا</b>",
            parse_mode="HTML",
        )
        outreach.record_outreach.assert_called_once_with("telegram", "123")

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

        with (
            patch.object(telegram_main, "outreach_service", outreach),
            patch.object(telegram_main, "get_or_create_goa_task", AsyncMock(return_value="task-1")),
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
