"""
Configuration and environment validation for the Telegram bot service.
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

env_paths = [
    Path(__file__).parent.parent.parent / ".env",
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

# Validate required environment variables
missing_vars = []
if not TELEGRAM_BOT_TOKEN:
    missing_vars.append("TELEGRAM_BOT_TOKEN: Get from @BotFather on Telegram")

if missing_vars:
    error_msg = "Missing required environment variables:\n" + "\n".join(
        f"  - {var}" for var in missing_vars
    )
    logging.error(error_msg)
    print(error_msg, file=sys.stderr)
    sys.exit(1)

# Constants
APP_NAME = "educational_assistant"
MAX_MESSAGE_LENGTH = 4096

# Proactive outreach settings
OUTREACH_CHECK_INTERVAL_SECONDS = int(os.getenv("OUTREACH_CHECK_INTERVAL_SECONDS", "3133"))
OUTREACH_INACTIVITY_HOURS = int(os.getenv("OUTREACH_INACTIVITY_HOURS", "5"))
OUTREACH_COOLDOWN_HOURS = int(os.getenv("OUTREACH_COOLDOWN_HOURS", "21"))

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
