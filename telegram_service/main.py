"""
Telegram Bot for Educational Assistant Agent.

Main entry point for the Telegram bot application. This acts purely as an
interface to Goa, sending all messages and commands to the bulbul agent.
"""

import asyncio
import logging
from datetime import datetime, timezone

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from .telegram_bot.handlers import (
    error_handler,
    handle_message,
    handle_photo_message,
    help_command,
    new_command,
    reset_persona_command,
    start_command,
    handle_voice_message,
)
from .telegram_bot.config import (
    APP_NAME,
    TELEGRAM_BOT_TOKEN,
)

logger = logging.getLogger(__name__)


def main() -> None:
    """
    Main function to set up and run the Telegram bot.
    """
    logger.info("Starting Educational Assistant Telegram Bot (Decoupled)")
    logger.info(f"App name: {APP_NAME}")

    # Create the Application
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
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

    logger.info("Bot handlers registered successfully")
    logger.info("Starting polling...")

    # Start the Bot
    application.run_polling(
        drop_pending_updates=True,
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
