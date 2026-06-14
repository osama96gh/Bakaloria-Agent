import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("GOA_API_KEY", "test-goa-key")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telegram_service.telegram_bot.ui import (
    build_goal_card_markup,
    build_outreach_markup,
    build_settings_markup,
    goal_card_text,
)


class TelegramUITests(unittest.TestCase):
    def test_goal_card_markup_contains_goal_actions(self):
        markup = build_goal_card_markup("goal-01")
        data = [button.callback_data for row in markup.inline_keyboard for button in row]
        labels = [button.text for row in markup.inline_keyboard for button in row]

        self.assertIn("goal:continue:goal-01", data)
        self.assertIn("goal:quiz:goal-01", data)
        self.assertIn("goal:done:goal-01", data)
        self.assertIn("goal:pause:goal-01", data)
        self.assertIn("goal:details:goal-01", data)
        self.assertIn("🚀 نكمل", labels)
        self.assertIn("🎯 اختبرني", labels)
        self.assertNotIn("Continue", labels)

    def test_outreach_markup_contains_core_actions(self):
        markup = build_outreach_markup("goal-01")
        data = [button.callback_data for row in markup.inline_keyboard for button in row]
        labels = [button.text for row in markup.inline_keyboard for button in row]

        self.assertEqual(data, [
            "outreach:continue:goal-01",
            "outreach:later",
            "outreach:goals",
        ])
        self.assertEqual(labels, ["🚀 نكمل", "لاحقاً", "🎯 أهدافي"])

    def test_settings_markup_contains_disabled_voice_option(self):
        markup = build_settings_markup()
        data = [button.callback_data for row in markup.inline_keyboard for button in row]
        labels = [button.text for row in markup.inline_keyboard for button in row]

        self.assertIn("settings:length:short", data)
        self.assertIn("settings:output:voice_disabled", data)
        self.assertIn("مختصر", labels)
        self.assertIn("الصوت قريباً", labels)

    def test_goal_card_text_includes_progress(self):
        text = goal_card_text({
            "goal_id": "goal-01",
            "title": "Learn Python",
            "status": "active",
            "progress_summary": "Finished loops",
            "current_step": "functions",
            "next_action": "solve exercises",
        })

        self.assertIn("Learn Python", text)
        self.assertIn("Finished loops", text)
        self.assertIn("solve exercises", text)
        self.assertIn("نشط", text)
        self.assertIn("▰", text)
        self.assertIn("📌", text)
        self.assertNotIn("Status:", text)


if __name__ == "__main__":
    unittest.main()
