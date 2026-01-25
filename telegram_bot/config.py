"""
Configuration and environment validation for the Telegram bot.

This module handles environment variable loading, validation, and provides
constants used throughout the bot application.
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
# Try parent directory first, then /app (Docker), then default
env_paths = [
    Path(__file__).parent.parent / ".env",
    Path("/app/.env"),
    Path(".env"),
]

for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        break

# Environment variables validation
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Validate required environment variables
missing_vars = []
if not TELEGRAM_BOT_TOKEN:
    missing_vars.append(
        "TELEGRAM_BOT_TOKEN: Get from @BotFather on Telegram (/mybots command)"
    )
if not ANTHROPIC_API_KEY:
    missing_vars.append("ANTHROPIC_API_KEY: Get from Anthropic Console")

if missing_vars:
    error_msg = "Missing required environment variables:\n" + "\n".join(
        f"  - {var}" for var in missing_vars
    )
    logging.error(error_msg)
    print(error_msg, file=sys.stderr)
    sys.exit(1)

# Constants
APP_NAME = "educational_assistant"
MAX_MESSAGE_LENGTH = 4096  # Telegram message length limit

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure logging with UTF-8 encoding for Arabic text
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

# Set UTF-8 encoding for output (Docker compatibility)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
