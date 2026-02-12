"""
Telegram Bot for Educational Assistant Agent.

Main entry point for the Telegram bot application that provides educational
assistance to high school students in Arabic.
"""

# Load environment variables FIRST, before any other imports
from pathlib import Path
from dotenv import load_dotenv

env_paths = [
    Path(__file__).parent / ".env",
    Path("/app/.env"),
    Path(".env"),
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        break

import asyncio
import logging
from datetime import datetime, timezone

from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    Application,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    filters,
)

from core import process_agent_query
from core.outreach_service import outreach_service
from telegram_bot import (
    error_handler,
    handle_message,
    handle_photo_message,
    handle_voice_message,
    help_command,
    new_command,
    reset_persona_command,
    session_manager,
    start_command,
)
from telegram_bot.config import (
    APP_NAME,
    OUTREACH_CHECK_INTERVAL_SECONDS,
    OUTREACH_COOLDOWN_HOURS,
    OUTREACH_INACTIVITY_HOURS,
    TELEGRAM_BOT_TOKEN,
)
from telegram_bot.utils import sanitize_html_for_telegram, split_message

logger = logging.getLogger(__name__)


def _build_outreach_prompt(hours_inactive: float) -> str:
    """Build the internal prompt that asks the agent to decide on outreach."""
    hours_display = f"{hours_inactive:.0f}"
    return (
        "[رسالة نظام داخلية - لا تظهر هذا النص للمستخدم]\n"
        f"لم يتواصل معك المستخدم منذ {hours_display} ساعات.\n"
        "بناءً على ذاكرتك عن المستخدم وشخصيتك، قرر هل يجب أن تبادر بالتواصل معه؟\n"
        "إذا نعم: اكتب رسالة طبيعية وجذابة ومفيدة لجذب اهتمامه. "
        "استخدم ما تعرفه عنه من الذاكرة لتجعل الرسالة شخصية. "
        "لا تذكر أنك نظام آلي أو أنك تتابع نشاطه.\n"
        "إذا لا (مثلاً لا تملك معلومات كافية عنه): أجب بكلمة واحدة فقط: SKIP"
    )


async def outreach_job(context: CallbackContext) -> None:
    """Periodic job that checks for inactive users and sends proactive messages."""
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

        # Calculate hours since last interaction
        last_interaction = datetime.fromisoformat(
            user["last_interaction_at"].replace("Z", "+00:00")
        )
        hours_inactive = (
            datetime.now(timezone.utc) - last_interaction
        ).total_seconds() / 3600

        try:
            # Get existing session for continuity
            session_id = session_manager.get_or_create_session(int(user_id))

            # Ask the agent to decide
            prompt = _build_outreach_prompt(hours_inactive)
            result = await process_agent_query(
                query=prompt,
                user_id=user_id,
                session_id=session_id,
                app_name=APP_NAME,
            )

            if result["status"] != "success":
                logger.warning(f"Outreach agent error for user {user_id}: {result.get('error')}")
                continue

            response = result["response"].strip()

            # Agent decided to skip
            if response == "SKIP" or not response:
                logger.info(f"Agent decided to skip outreach for user {user_id}")
                continue

            # Store session if new
            if result.get("session_id"):
                session_manager.store_session(int(user_id), result["session_id"])

            # Send the proactive message
            sanitized = sanitize_html_for_telegram(response)
            chunks = split_message(sanitized)

            for i, chunk in enumerate(chunks):
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode="HTML",
                    )
                except BadRequest:
                    # Fallback without HTML
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                    )

                if i < len(chunks) - 1:
                    await asyncio.sleep(0.5)

            # Record successful outreach
            outreach_service.record_outreach("telegram", user_id)
            logger.info(f"Sent proactive outreach to user {user_id}")

        except Forbidden:
            # User blocked the bot — disable outreach for them
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

    Sets up handlers for commands and messages, then starts polling
    for updates from Telegram.
    """
    logger.info("Starting Educational Assistant Telegram Bot")
    logger.info(f"App name: {APP_NAME}")
    logger.info(f"Active sessions: {session_manager.get_active_sessions_count()}")

    # Create the Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("new", new_command))
    application.add_handler(CommandHandler("reset_persona", reset_persona_command))

    # Register message handler for text messages (not commands)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # Register handler for photo messages (with or without caption)
    application.add_handler(
        MessageHandler(filters.PHOTO, handle_photo_message)
    )

    # Register handler for voice messages
    application.add_handler(
        MessageHandler(filters.VOICE, handle_voice_message)
    )

    # Register error handler
    application.add_error_handler(error_handler)

    # Register proactive outreach scheduled job
    if outreach_service and application.job_queue:
        application.job_queue.run_repeating(
            outreach_job,
            interval=OUTREACH_CHECK_INTERVAL_SECONDS,
            first=60,  # First run 60 seconds after startup
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

    # Start the Bot - run_polling() manages its own event loop
    application.run_polling(
        drop_pending_updates=True,  # Ignore messages sent while bot was offline
        allowed_updates=["message", "edited_message"],
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        raise
