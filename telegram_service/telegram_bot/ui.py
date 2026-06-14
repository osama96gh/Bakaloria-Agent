"""Telegram-native UI helpers for Bulbul."""

from __future__ import annotations

from typing import Any, Dict, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_goal_card_markup(goal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Continue", callback_data=f"goal:continue:{goal_id}"),
            InlineKeyboardButton("Quiz Me", callback_data=f"goal:quiz:{goal_id}"),
        ],
        [
            InlineKeyboardButton("Mark Done", callback_data=f"goal:done:{goal_id}"),
            InlineKeyboardButton("Pause", callback_data=f"goal:pause:{goal_id}"),
            InlineKeyboardButton("Details", callback_data=f"goal:details:{goal_id}"),
        ],
    ])


def build_pause_confirm_markup(goal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Pause Goal", callback_data=f"goal:pause_confirm:{goal_id}"),
        InlineKeyboardButton("Cancel", callback_data="goal:cancel"),
    ]])


def build_outreach_markup(goal_id: str = "") -> InlineKeyboardMarkup:
    continue_data = f"outreach:continue:{goal_id}" if goal_id else "outreach:continue"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Continue", callback_data=continue_data),
        InlineKeyboardButton("Later", callback_data="outreach:later"),
        InlineKeyboardButton("Show Goals", callback_data="outreach:goals"),
    ]])


def build_settings_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Short", callback_data="settings:length:short"),
            InlineKeyboardButton("Balanced", callback_data="settings:length:balanced"),
            InlineKeyboardButton("Detailed", callback_data="settings:length:detailed"),
        ],
        [
            InlineKeyboardButton("Text Only", callback_data="settings:output:text"),
            InlineKeyboardButton("Voice Planned", callback_data="settings:output:voice_disabled"),
        ],
    ])


def goal_card_text(goal: Dict[str, Any]) -> str:
    status = goal.get("status") or "unknown"
    title = goal.get("title") or "Goal"
    progress = goal.get("progress_summary") or "No progress summary yet"
    current_step = goal.get("current_step") or "Not set"
    next_action = goal.get("next_action") or "Not set"
    goal_id = goal.get("goal_id") or ""
    return (
        f"<b>{title}</b> <code>{goal_id}</code>\n"
        f"Status: {status}\n"
        f"Progress: {progress}\n"
        f"Current: {current_step}\n"
        f"Next: {next_action}"
    )


def goal_cards_ui(goals: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "type": "goal_cards",
        "goals": goals,
    }
