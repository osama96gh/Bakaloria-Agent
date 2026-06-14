"""Telegram-native UI helpers for Bulbul."""

from __future__ import annotations

from html import escape
from typing import Any, Dict, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_goal_card_markup(goal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚀 نكمل", callback_data=f"goal:continue:{goal_id}"),
            InlineKeyboardButton("🎯 اختبرني", callback_data=f"goal:quiz:{goal_id}"),
        ],
        [
            InlineKeyboardButton("✅ تمت", callback_data=f"goal:done:{goal_id}"),
            InlineKeyboardButton("⏸️ إيقاف", callback_data=f"goal:pause:{goal_id}"),
            InlineKeyboardButton("📋 تفاصيل", callback_data=f"goal:details:{goal_id}"),
        ],
    ])


def build_pause_confirm_markup(goal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⏸️ أوقف الهدف", callback_data=f"goal:pause_confirm:{goal_id}"),
        InlineKeyboardButton("إلغاء", callback_data="goal:cancel"),
    ]])


def build_outreach_markup(goal_id: str = "") -> InlineKeyboardMarkup:
    continue_data = f"outreach:continue:{goal_id}" if goal_id else "outreach:continue"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 نكمل", callback_data=continue_data),
        InlineKeyboardButton("لاحقاً", callback_data="outreach:later"),
        InlineKeyboardButton("🎯 أهدافي", callback_data="outreach:goals"),
    ]])


def build_settings_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("مختصر", callback_data="settings:length:short"),
            InlineKeyboardButton("متوازن", callback_data="settings:length:balanced"),
            InlineKeyboardButton("مفصل", callback_data="settings:length:detailed"),
        ],
        [
            InlineKeyboardButton("نص فقط", callback_data="settings:output:text"),
            InlineKeyboardButton("الصوت قريباً", callback_data="settings:output:voice_disabled"),
        ],
    ])


def _display(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return escape(text or fallback)


def _status_display(status: str) -> tuple[str, str]:
    status_map = {
        "proposed": ("🟡", "مقترح"),
        "active": ("🟢", "نشط"),
        "paused": ("⏸️", "متوقف مؤقتاً"),
        "completed": ("🏁", "مكتمل"),
        "archived": ("⚪", "مؤرشف"),
    }
    return status_map.get(status, ("⚪", "غير محدد"))


def _progress_percent(goal: Dict[str, Any]) -> int:
    status = goal.get("status")
    if status == "completed":
        return 100
    if status in {"proposed", "archived"}:
        return 0
    completed_steps = goal.get("completed_steps") or []
    if completed_steps:
        return min(90, max(15, len(completed_steps) * 20))
    if status == "active":
        return 10
    return 0


def _progress_bar(percent: int) -> str:
    filled = max(0, min(10, round(percent / 10)))
    return "▰" * filled + "▱" * (10 - filled)


def goal_card_text(goal: Dict[str, Any]) -> str:
    status_emoji, status = _status_display(str(goal.get("status") or ""))
    title = _display(goal.get("title"), "هدف بدون عنوان")
    progress = _display(goal.get("progress_summary"), "لسه ما في تقدم محفوظ")
    current_step = _display(goal.get("current_step"), "غير محددة")
    next_action = _display(goal.get("next_action"), "غير محددة")
    goal_id = _display(goal.get("goal_id"), "")
    percent = _progress_percent(goal)
    bar = _progress_bar(percent)
    return (
        f"🎯 <b>{title}</b>\n"
        f"{status_emoji} <b>{status}</b>  |  <code>{goal_id}</code>\n\n"
        f"<code>{bar}</code> {percent}%\n"
        f"📌 <b>التقدم:</b> {progress}\n"
        f"🧭 <b>الآن:</b> {current_step}\n"
        f"✨ <b>التالي:</b> {next_action}"
    )


def goal_cards_ui(goals: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "type": "goal_cards",
        "goals": goals,
    }
