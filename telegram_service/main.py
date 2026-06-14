"""
Telegram Bot for Educational Assistant Agent.

Main entry point for the Telegram bot application. This acts purely as an
interface to Goa, sending all messages and commands to the bulbul agent.
"""

import asyncio
import logging
from datetime import datetime, timezone

from telegram import BotCommand
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    Application,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PollAnswerHandler,
    filters,
)

from .telegram_bot.handlers import (
    ask_agent_via_goa,
    close_goa_task,
    error_handler,
    get_or_create_goa_task,
    callback_query_handler,
    handle_message,
    handle_photo_message,
    help_command,
    goals_command,
    new_command,
    poll_answer_handler,
    reset_persona_command,
    settings_command,
    start_command,
    handle_voice_message,
)
from .telegram_bot.config import (
    APP_NAME,
    OUTREACH_CHECK_INTERVAL_SECONDS,
    OUTREACH_COOLDOWN_HOURS,
    OUTREACH_INACTIVITY_HOURS,
    TELEGRAM_BOT_TOKEN,
)
from .telegram_bot.ui import build_outreach_markup
from .telegram_bot.utils import sanitize_html_for_telegram, split_message
from bulbul_agent.core.outreach_service import outreach_service

logger = logging.getLogger(__name__)


BOT_COMMANDS = [
    BotCommand("start", "Start Bulbul"),
    BotCommand("help", "Show help"),
    BotCommand("goals", "Show goals and progress"),
    BotCommand("settings", "Change response preferences"),
    BotCommand("new", "Start a fresh conversation"),
    BotCommand("reset_persona", "Reset Bulbul persona"),
]
ALLOWED_UPDATES = ["message", "edited_message", "callback_query", "poll_answer"]


async def setup_bot_commands(application: Application) -> None:
    await application.bot.set_my_commands(BOT_COMMANDS)


async def get_or_create_outreach_task(user_id: int) -> str:
    """Create an outreach task linked to the active chat task when Goa allows it."""
    main_task_id = await get_or_create_goa_task(user_id)
    try:
        return await get_or_create_goa_task(
            user_id,
            purpose="outreach",
            parent_task_id=main_task_id,
        )
    except Exception as e:
        logger.warning(
            "Failed to create parented outreach task for user %s; falling back: %s",
            user_id,
            e,
        )
        return await get_or_create_goa_task(user_id, purpose="outreach")


def _build_outreach_prompt(hours_inactive: float) -> str:
    """Build the internal prompt that asks the agent to decide on outreach."""
    hours_display = f"{hours_inactive:.0f}"
    return (
        "[رسالة نظام داخلية - لا تظهر هذا النص للمستخدم]\n"
        f"لم يتواصل معك المستخدم منذ {hours_display} ساعات.\n"
        "بناءً على أهداف المستخدم الحالية وذاكرته وشخصيتك، قرر هل يجب أن تبادر بالتواصل معه؟\n"
        "إذا لديه هدف نشط مناسب: اختر هدفاً واحداً فقط، وابعث دفعة صغيرة ومفيدة مرتبطة بالخطوة التالية. "
        "ذكّره بالهدف بلطف، واقترح خطوة سهلة يمكنه فعلها الآن، بدون ضغط أو تأنيب. "
        "استخدم ما تعرفه عنه من الأهداف والذاكرة لتجعل الرسالة شخصية. "
        "لا تذكر أنك نظام آلي أو أنك تتابع نشاطه.\n"
        "لا توقف أو تؤرشف أي هدف بسبب هذه الرسالة الداخلية.\n"
        "إذا لا يوجد هدف أو سياق كافٍ لرسالة مفيدة: أجب بكلمة واحدة فقط: SKIP"
    )


async def outreach_job(context: CallbackContext) -> None:
    """Periodic job that checks inactive users and sends proactive messages."""
    if not outreach_service:
        return

    logger.info("Running proactive outreach check...")
    candidates = outreach_service.get_outreach_candidates(
        platform="telegram",
        inactivity_hours=OUTREACH_INACTIVITY_HOURS,
        cooldown_hours=OUTREACH_COOLDOWN_HOURS,
    )

    if not candidates:
        logger.info("No outreach candidates found")
        return

    for user in candidates:
        user_id = user["platform_user_id"]
        chat_id = user["chat_id"]

        last_interaction = datetime.fromisoformat(
            user["last_interaction_at"].replace("Z", "+00:00")
        )
        hours_inactive = (
            datetime.now(timezone.utc) - last_interaction
        ).total_seconds() / 3600

        try:
            task_id = await get_or_create_outreach_task(int(user_id))
            try:
                result = await ask_agent_via_goa(
                    task_id,
                    _build_outreach_prompt(hours_inactive),
                )
            finally:
                await close_goa_task(task_id)

            if result["status"] != "success":
                logger.warning(
                    f"Outreach agent error for user {user_id}: {result.get('error')}"
                )
                continue

            response = result["response"].strip()
            if response == "SKIP" or not response:
                logger.info(f"Agent decided to skip outreach for user {user_id}")
                continue

            chunks = split_message(sanitize_html_for_telegram(response))
            for i, chunk in enumerate(chunks):
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode="HTML",
                        reply_markup=build_outreach_markup() if i == len(chunks) - 1 else None,
                    )
                except BadRequest:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        reply_markup=build_outreach_markup() if i == len(chunks) - 1 else None,
                    )

                if i < len(chunks) - 1:
                    await asyncio.sleep(0.5)

            outreach_service.record_outreach("telegram", user_id)
            logger.info(f"Sent proactive outreach to user {user_id}")

        except Forbidden:
            logger.warning(f"User {user_id} blocked the bot, disabling outreach")
            try:
                outreach_service._client.table("user_engagement").update(
                    {"outreach_enabled": False}
                ).eq("platform", "telegram").eq(
                    "platform_user_id", user_id
                ).execute()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Failed to send outreach to user {user_id}: {e}")


def main() -> None:
    """
    Main function to set up and run the Telegram bot.
    """
    logger.info("Starting Educational Assistant Telegram Bot (Decoupled)")
    logger.info(f"App name: {APP_NAME}")

    # Create the Application
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(setup_bot_commands).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("new", new_command))
    application.add_handler(CommandHandler("goals", goals_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("reset_persona", reset_persona_command))
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    application.add_handler(PollAnswerHandler(poll_answer_handler))

    # Register message handler for text messages (not commands)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # Register handler for photo messages
    application.add_handler(
        MessageHandler(filters.PHOTO, handle_photo_message)
    )
    
    # Register handler for voice messages
    application.add_handler(
        MessageHandler(filters.VOICE, handle_voice_message)
    )

    # Register error handler
    application.add_error_handler(error_handler) # type: ignore

    # Register proactive outreach scheduled job
    if outreach_service and application.job_queue:
        application.job_queue.run_repeating(
            outreach_job,
            interval=OUTREACH_CHECK_INTERVAL_SECONDS,
            first=60,
            name="outreach_job",
        )
        logger.info(
            f"Proactive outreach job scheduled "
            f"(interval={OUTREACH_CHECK_INTERVAL_SECONDS}s, "
            f"inactivity={OUTREACH_INACTIVITY_HOURS}h, "
            f"cooldown={OUTREACH_COOLDOWN_HOURS}h)"
        )
    else:
        logger.warning("Proactive outreach disabled (missing outreach_service or job_queue)")

    logger.info("Bot handlers registered successfully")
    logger.info("Starting polling...")

    # Start the Bot
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=ALLOWED_UPDATES,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        raise
