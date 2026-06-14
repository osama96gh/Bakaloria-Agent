import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telegram_service.telegram_bot.transcription.gemini_stt import (  # noqa: E402
    DEFAULT_GEMINI_STT_MODEL,
    GEMINI_STT_MODEL_ENV,
    GeminiSTTProvider,
)


class GeminiSTTProviderTests(unittest.TestCase):
    def test_uses_latest_flash_alias_by_default(self):
        with patch.dict(os.environ, {GEMINI_STT_MODEL_ENV: ""}, clear=False):
            os.environ.pop(GEMINI_STT_MODEL_ENV, None)

            provider = GeminiSTTProvider(api_key="test-key")

        self.assertEqual(provider.name, f"Gemini Audio ({DEFAULT_GEMINI_STT_MODEL})")

    def test_model_can_be_overridden_by_environment(self):
        with patch.dict(os.environ, {GEMINI_STT_MODEL_ENV: "gemini-3.5-flash"}):
            provider = GeminiSTTProvider(api_key="test-key")

        self.assertEqual(provider.name, "Gemini Audio (gemini-3.5-flash)")

    def test_explicit_model_takes_precedence(self):
        with patch.dict(os.environ, {GEMINI_STT_MODEL_ENV: "gemini-flash-latest"}):
            provider = GeminiSTTProvider(api_key="test-key", model="gemini-3.5-flash")

        self.assertEqual(provider.name, "Gemini Audio (gemini-3.5-flash)")
