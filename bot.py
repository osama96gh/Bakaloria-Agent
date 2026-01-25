"""
Telegram Bot for Educational Assistant Agent.

Main entry point for the Telegram bot application that provides educational
assistance to high school students in Arabic.
"""

import asyncio
import logging

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from telegram_bot import (
    error_handler,
    handle_message,
    handle_photo_message,
    handle_voice_message,
    help_command,
    new_command,
    session_manager,
    start_command,
)
from telegram_bot.config import APP_NAME, TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)


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
