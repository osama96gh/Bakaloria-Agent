"""Telegram bot handlers for messages and commands."""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest, TimedOut
from telegram.ext import ContextTypes

from .utils import (
    format_error_message,
    log_user_interaction,
    sanitize_html_for_telegram,
    split_message,
)
from .ui import (
    build_goal_card_markup,
    build_outreach_markup,
    build_pause_confirm_markup,
    build_settings_markup,
    goal_card_text,
)
from bulbul_agent.core.outreach_service import outreach_service
from bulbul_agent.core.local_runtime import ask_local_agent, reset_local_session as reset_bulbul_session

logger = logging.getLogger(__name__)

MAX_SEND_RETRIES = 3
RETRY_DELAY_SECONDS = 1.0
TYPING_REFRESH_SECONDS = 4.0
POLL_CONTEXTS: Dict[str, Dict[str, Any]] = {}
DYNAMIC_UI_ACTION_TTL_SECONDS = 15 * 60
DYNAMIC_UI_ACTIONS: Dict[str, Dict[str, Any]] = {}


async def get_or_create_local_session(
    user_id: int,
    purpose: str = "chat",
    parent_task_id: Optional[str] = None,
) -> str:
    """Return the local session key for a Telegram user."""
    return str(user_id)


async def close_local_session(session_id: str) -> bool:
    """No-op close hook for local outreach turns."""
    return True


async def reset_local_session_history(user_id: int) -> bool:
    """Reset the in-process conversation history for a user."""
    reset_bulbul_session(user_id)
    return True


def record_user_engagement(update: Update) -> None:
    """Record a Telegram user interaction for proactive outreach."""
    if not outreach_service or not update.effective_user or not update.effective_chat:
        return

    outreach_service.update_interaction(
        "telegram",
        str(update.effective_user.id),
        update.effective_chat.id,
    )


async def ask_agent(
    session_id: str,
    text: str,
    image_bytes: Optional[bytes] = None,
    image_mime: str = "",
    progress_callback: Optional[Callable[[str], Awaitable[None]]] = None,
) -> dict:
    """Ask the local Bulbul runtime directly."""
    try:
        return await ask_local_agent(
            user_id=session_id,
            text=text,
            image_bytes=image_bytes,
            image_mime=image_mime,
            progress_callback=progress_callback,
        )
    except Exception as e:
        logger.error(f"Error running local Bulbul agent: {e}")
        return {"status": "error", "error": str(e)}


async def send_reply_with_retry(
    message,
    text: str,
    parse_mode: Optional[str] = "HTML",
    max_retries: int = MAX_SEND_RETRIES,
    reply_markup=None,
) -> bool:
    """Send a reply message with retry logic for timeouts and formatting issues."""
    for attempt in range(max_retries):
        try:
            await message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
            return True
        except BadRequest as e:
            if "Can't parse entities" in str(e) and parse_mode == "HTML":
                try:
                    await message.reply_text(text, parse_mode=None, reply_markup=reply_markup)
                    return True
                except TimedOut:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                        continue
                    return False
            else:
                raise
        except TimedOut:
            if attempt < max_retries - 1:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            else:
                return False
    return False


async def send_text_with_retry(
    bot,
    chat_id: int,
    text: str,
    parse_mode: Optional[str] = "HTML",
    max_retries: int = MAX_SEND_RETRIES,
    reply_markup=None,
) -> bool:
    for attempt in range(max_retries):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            return True
        except BadRequest as e:
            if "Can't parse entities" in str(e) and parse_mode == "HTML":
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=None,
                    reply_markup=reply_markup,
                )
                return True
            raise
        except TimedOut:
            if attempt < max_retries - 1:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            else:
                return False
    return False


def _cleanup_dynamic_ui_actions() -> None:
    now = time.monotonic()
    expired = [
        token for token, context in DYNAMIC_UI_ACTIONS.items()
        if context.get("expires_at", 0) <= now
    ]
    for token in expired:
        DYNAMIC_UI_ACTIONS.pop(token, None)


def _build_dynamic_actions_markup(ui: dict, chat_id: int, user_id: Optional[int]) -> Optional[InlineKeyboardMarkup]:
    if not isinstance(ui, dict) or ui.get("version") != 1:
        return None

    buttons = []
    action_context: Dict[str, Dict[str, str]] = {}
    token = uuid.uuid4().hex[:12]

    for element in (ui.get("elements") or []):
        if not isinstance(element, dict) or element.get("type") != "actions":
            continue
        for button in (element.get("buttons") or []):
            if not isinstance(button, dict):
                continue
            label = str(button.get("label") or "").strip()[:64]
            if not label:
                continue
            url = str(button.get("url") or "").strip()
            if url.startswith(("http://", "https://")):
                buttons.append(InlineKeyboardButton(label, url=url))
                continue
            prompt = str(button.get("prompt") or "").strip()
            if not prompt:
                continue
            button_id = str(button.get("id") or f"action_{len(action_context) + 1}").strip()[:32]
            action_context[button_id] = {"label": label, "prompt": prompt[:1000]}
            buttons.append(InlineKeyboardButton(label, callback_data=f"ui:{token}:{button_id}"))

    if action_context:
        _cleanup_dynamic_ui_actions()
        DYNAMIC_UI_ACTIONS[token] = {
            "chat_id": chat_id,
            "user_id": user_id,
            "expires_at": time.monotonic() + DYNAMIC_UI_ACTION_TTL_SECONDS,
            "actions": action_context,
        }

    if not buttons:
        return None

    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


def _dynamic_ui_elements(ui: dict, element_type: str) -> list[dict]:
    if not isinstance(ui, dict) or ui.get("version") != 1:
        return []
    return [
        element for element in (ui.get("elements") or [])
        if isinstance(element, dict) and element.get("type") == element_type
    ]


async def render_dynamic_ui_response(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    response: str,
    ui: Optional[dict],
    reply_message=None,
    user_id: Optional[int] = None,
) -> None:
    response = sanitize_html_for_telegram(response or "")
    chunks = split_message(response) if response else []
    actions_markup = _build_dynamic_actions_markup(ui or {}, chat_id, user_id)

    if chunks:
        for index, chunk in enumerate(chunks):
            reply_markup = actions_markup if index == len(chunks) - 1 else None
            if reply_message:
                await send_reply_with_retry(reply_message, chunk, reply_markup=reply_markup)
            else:
                await send_text_with_retry(context.bot, chat_id, chunk, reply_markup=reply_markup)
    elif actions_markup:
        if reply_message:
            await send_reply_with_retry(reply_message, "اختر من الأزرار:", reply_markup=actions_markup)
        else:
            await send_text_with_retry(context.bot, chat_id, "اختر من الأزرار:", reply_markup=actions_markup)

    for quiz in _dynamic_ui_elements(ui or {}, "quiz"):
        sent = await context.bot.send_poll(
            chat_id=chat_id,
            question=quiz["question"],
            options=quiz["options"],
            type="quiz",
            correct_option_id=quiz["correct_index"],
            explanation=quiz.get("explanation") or None,
            is_anonymous=False,
        )
        POLL_CONTEXTS[sent.poll.id] = {
            "goal_id": quiz.get("goal_id", "dynamic-ui"),
            "user_id": user_id,
            "chat_id": chat_id,
            "correct_index": quiz["correct_index"],
        }

    for poll in _dynamic_ui_elements(ui or {}, "poll"):
        await context.bot.send_poll(
            chat_id=chat_id,
            question=poll["question"],
            options=poll["options"],
            type="regular",
            allows_multiple_answers=bool(poll.get("multiple_answers")),
            is_anonymous=False,
        )


async def answer_callback_safely(query, *args, **kwargs) -> bool:
    try:
        await query.answer(*args, **kwargs)
        return True
    except BadRequest as e:
        message = str(e)
        if "Query is too old" in message or "query id is invalid" in message:
            logger.info("Ignoring stale callback query: %s", message)
            return False
        raise


async def clear_callback_markup_safely(query) -> None:
    message = getattr(query, "message", None)
    edit_reply_markup = getattr(message, "edit_reply_markup", None)
    if not edit_reply_markup:
        return
    try:
        await edit_reply_markup(reply_markup=None)
    except BadRequest as e:
        message = str(e)
        if "Message is not modified" in message or "message to edit not found" in message:
            logger.debug("Ignoring callback markup clear failure: %s", message)
            return
        logger.info("Could not clear callback markup: %s", message)


async def keep_typing(bot, chat_id: int, stop_event: asyncio.Event) -> None:
    """Refresh Telegram's typing indicator until stop_event is set."""
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e:
            logger.debug("Failed to refresh typing indicator: %s", e)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TYPING_REFRESH_SECONDS)
        except asyncio.TimeoutError:
            continue


async def send_progress_update(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    reply_message=None,
) -> None:
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception as e:
        logger.debug("Failed to send progress chat action: %s", e)

    progress_text = f"⏳ {text}"
    if reply_message:
        await send_reply_with_retry(reply_message, progress_text, parse_mode=None)
    else:
        await send_text_with_retry(context.bot, chat_id, progress_text, parse_mode=None)


async def render_agent_result(update: Update, context: ContextTypes.DEFAULT_TYPE, result: dict) -> None:
    if result["status"] != "success":
        if update.message:
            await send_reply_with_retry(update.message, "عذراً، واجهت مشكلة في الاتصال بالوكيل الذكي.", parse_mode=None)
        return

    ui = result.get("ui") or {}
    if ui.get("type") == "goal_cards":
        goals = ui.get("goals") or []
        if goals and update.message:
            for goal in goals:
                await send_reply_with_retry(
                    update.message,
                    sanitize_html_for_telegram(goal_card_text(goal)),
                    reply_markup=build_goal_card_markup(goal.get("goal_id", "")),
                )
            return

    if update.message:
        await render_dynamic_ui_response(
            context=context,
            chat_id=update.effective_chat.id if update.effective_chat else update.message.chat_id,
            response=result.get("response", ""),
            ui=ui,
            reply_message=update.message,
            user_id=update.effective_user.id if update.effective_user else None,
        )


async def send_agent_text(
    *,
    user_id: int,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    query_text: str,
    reply_message=None,
    render_response: bool = True,
) -> dict:
    typing_stop = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(context.bot, chat_id, typing_stop))
    try:
        session_id = await get_or_create_local_session(user_id)
        result = await ask_agent(
            session_id,
            query_text,
            progress_callback=lambda message: send_progress_update(
                context=context,
                chat_id=chat_id,
                text=message,
                reply_message=reply_message,
            ),
        )
    finally:
        typing_stop.set()
        await typing_task

    if render_response:
        ui = result.get("ui") or {}
        if ui.get("type") == "goal_cards":
            goals = ui.get("goals") or []
            if goals:
                for goal in goals:
                    text = sanitize_html_for_telegram(goal_card_text(goal))
                    if reply_message:
                        await send_reply_with_retry(
                            reply_message,
                            text,
                            reply_markup=build_goal_card_markup(goal.get("goal_id", "")),
                        )
                    else:
                        await send_text_with_retry(
                            context.bot,
                            chat_id,
                            text,
                            reply_markup=build_goal_card_markup(goal.get("goal_id", "")),
                        )
                return result

        await render_dynamic_ui_response(
            context=context,
            chat_id=chat_id,
            response=result.get("response", ""),
            ui=ui,
            reply_message=reply_message,
            user_id=user_id,
        )

    return result


async def download_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[Optional[bytes], str]:
    if not update.message or not update.message.photo:
        return None, ""
    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()
        return bytes(photo_bytes), "image/jpeg"
    except Exception as e:
        logger.error(f"Failed to download photo: {e}")
        return None, ""


async def forward_to_agent(update: Update, context: ContextTypes.DEFAULT_TYPE, query_text: str, photo_bytes: Optional[bytes] = None, mime_type: str = "") -> None:
    """Core logic to forward any message/command to the local agent."""
    if not update.effective_user or not update.effective_chat or not update.message:
        return
        
    user_id = update.effective_user.id
    
    try:
        typing_stop = asyncio.Event()
        typing_task = asyncio.create_task(
            keep_typing(context.bot, update.effective_chat.id, typing_stop)
        )
        try:
            session_id = await get_or_create_local_session(user_id)
            result = await ask_agent(
                session_id,
                query_text,
                photo_bytes,
                mime_type,
                progress_callback=lambda message: send_progress_update(
                    context=context,
                    chat_id=update.effective_chat.id,
                    text=message,
                    reply_message=update.message,
                ),
            )
        finally:
            typing_stop.set()
            await typing_task

        await render_agent_result(update, context, result)
    except Exception as e:
        logger.exception(f"Error handling message: {e}")
        await send_reply_with_retry(update.message, format_error_message(e), parse_mode=None)


def _synthetic_goal_prompt(action: str, goal_id: str) -> str:
    prompts = {
        "continue": (
            f"تابع معي الهدف {goal_id}. رد كمدرب شخصي بالعربية: "
            "ابدأ بجملة حماسية قصيرة، ثم أعطني خطوة واحدة عملية الآن، ثم سؤال متابعة واحد. "
            "استخدم HTML وإيموجي مناسب، ولا تطل."
        ),
        "done": (
            f"اعتبر أنني أنجزت الخطوة الحالية في الهدف {goal_id}. "
            "حدّث التقدم، واحتفل بالإنجاز بجملة محددة، ثم اقترح الخطوة التالية. "
            "استخدم HTML وإيموجي مناسب."
        ),
        "pause_confirm": (
            f"أريد إيقاف الهدف {goal_id} مؤقتاً. حدّث حالة الهدف بعد موافقتي، "
            "ورد بلطف واذكر أنه يمكنني الرجوع له لاحقاً."
        ),
        "details": (
            f"اعرض تفاصيل الهدف {goal_id} كبطاقة جميلة بالعربية، وليس كبيانات خام. "
            "استخدم هذا الشكل تقريباً: عنوان قوي، حالة مترجمة، شريط تقدم نصي من 10 خانات، "
            "ملخص التقدم، الخطوة الحالية، الخطوة التالية، واقتراح واحد ذكي. "
            "استخدم HTML وإيموجيز قليلة. لا تستخدم كلمات إنجليزية مثل Proposed أو Status."
        ),
    }
    return prompts.get(action, f"تابع الهدف {goal_id} برد عربي مختصر وجذاب.")


def _parse_quiz_response(text: str) -> Optional[dict]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    question = str(data.get("question") or "").strip()
    options = data.get("options") or []
    correct_index = data.get("correct_index")
    explanation = str(data.get("explanation") or "").strip()

    if not question or not isinstance(options, list) or len(options) < 2:
        return None
    if not isinstance(correct_index, int) or correct_index < 0 or correct_index >= len(options):
        return None

    return {
        "question": question[:300],
        "options": [str(option)[:100] for option in options[:10]],
        "correct_index": correct_index,
        "explanation": explanation[:200],
    }


async def _send_goal_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE, goal_id: str) -> None:
    query = update.callback_query
    if not query or not query.message or not query.from_user:
        return

    prompt = (
        f"أنشئ سؤال اختبار قصير للهدف {goal_id}. "
        "أجب JSON فقط بدون أي شرح خارج JSON وبالشكل التالي: "
        '{"question":"...","options":["...","...","..."],"correct_index":0,"explanation":"..."}'
    )
    result = await send_agent_text(
        user_id=query.from_user.id,
        chat_id=query.message.chat_id,
        context=context,
        query_text=prompt,
        render_response=False,
    )
    quiz = _parse_quiz_response(result.get("response", "")) if result.get("status") == "success" else None
    if not quiz:
        await query.message.reply_text(
            "لم أتمكن من تجهيز اختبار مناسب الآن. جرّب مرة ثانية بعد قليل.",
        )
        return

    sent = await context.bot.send_poll(
        chat_id=query.message.chat_id,
        question=quiz["question"],
        options=quiz["options"],
        type="quiz",
        correct_option_id=quiz["correct_index"],
        explanation=quiz["explanation"] or None,
        is_anonymous=False,
    )
    POLL_CONTEXTS[sent.poll.id] = {
        "goal_id": goal_id,
        "user_id": query.from_user.id,
        "chat_id": query.message.chat_id,
        "correct_index": quiz["correct_index"],
    }


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    if data.startswith("ui:"):
        parts = data.split(":", 2)
        if len(parts) != 3 or not query.message or not query.from_user:
            return
        _cleanup_dynamic_ui_actions()
        token, button_id = parts[1], parts[2]
        action_set = DYNAMIC_UI_ACTIONS.get(token)
        action = (action_set or {}).get("actions", {}).get(button_id)
        if not action:
            await answer_callback_safely(query, "هذا الزر انتهت صلاحيته.")
            await query.message.reply_text("انتهت صلاحية هذا الزر. اطلب مني الخيار مرة ثانية.")
            return
        stored_user_id = action_set.get("user_id")
        if stored_user_id and stored_user_id != query.from_user.id:
            await answer_callback_safely(query, "هذا الزر مخصص لمحادثة أخرى.", show_alert=True)
            return
        consumed = action_set.setdefault("consumed", set())
        if button_id in consumed:
            await answer_callback_safely(query, "تم استلامه بالفعل، بلبل يعمل عليه الآن.")
            return
        consumed.add(button_id)
        await answer_callback_safely(query, "تم استلام طلبك، بلبل يعمل عليه الآن.")
        await clear_callback_markup_safely(query)
        await send_agent_text(
            user_id=query.from_user.id,
            chat_id=query.message.chat_id,
            context=context,
            query_text=action["prompt"],
            reply_message=query.message,
        )
        return

    if data == "goal:cancel":
        await answer_callback_safely(query, "تمام.")
        if query.message:
            await query.message.reply_text("تمام، ما غيرت شيئاً.")
        return

    if data.startswith("settings:"):
        if data == "settings:output:voice_disabled":
            await answer_callback_safely(query, "الردود الصوتية قادمة لاحقاً، لكنها غير مفعلة حالياً.", show_alert=True)
            return
        if query.message and query.from_user:
            await answer_callback_safely(query, "تم، أعمل على التحديث.")
            await send_agent_text(
                user_id=query.from_user.id,
                chat_id=query.message.chat_id,
                context=context,
                query_text=f"حدّث تفضيلاتي بناءً على هذا الاختيار: {data}",
                reply_message=query.message,
            )
        return

    if data.startswith("outreach:"):
        if data == "outreach:later":
            await answer_callback_safely(query, "تمام، نكمل لاحقاً.")
            return
        if data == "outreach:goals" and query.message and query.from_user:
            await answer_callback_safely(query, "تمام، أجهز أهدافك.")
            await send_agent_text(
                user_id=query.from_user.id,
                chat_id=query.message.chat_id,
                context=context,
                query_text="/goals",
                reply_message=query.message,
            )
            return
        if data.startswith("outreach:continue") and query.message and query.from_user:
            parts = data.split(":")
            goal_id = parts[2] if len(parts) > 2 else ""
            prompt = _synthetic_goal_prompt("continue", goal_id) if goal_id else "تابع معي آخر هدف نشط واقترح خطوة صغيرة الآن."
            await answer_callback_safely(query, "تم استلام طلبك، بلبل يعمل عليه الآن.")
            await send_agent_text(
                user_id=query.from_user.id,
                chat_id=query.message.chat_id,
                context=context,
                query_text=prompt,
                reply_message=query.message,
            )
            return

    if not data.startswith("goal:") or not query.message or not query.from_user:
        return

    parts = data.split(":", 2)
    if len(parts) != 3:
        return
    action, goal_id = parts[1], parts[2]

    if action == "pause":
        await answer_callback_safely(query, "تمام.")
        await query.message.reply_text(
            "هل تريد إيقاف هذا الهدف مؤقتاً؟",
            reply_markup=build_pause_confirm_markup(goal_id),
        )
        return
    if action == "quiz":
        await answer_callback_safely(query, "وصلني، أجهز الاختبار الآن.")
        await _send_goal_quiz(update, context, goal_id)
        return

    await answer_callback_safely(query, "تم استلام طلبك، بلبل يعمل عليه الآن.")
    await send_agent_text(
        user_id=query.from_user.id,
        chat_id=query.message.chat_id,
        context=context,
        query_text=_synthetic_goal_prompt(action, goal_id),
        reply_message=query.message,
    )


# Command Handlers - they just forward the command text to the agent!
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user and update.message:
        record_user_engagement(update)
        await send_reply_with_retry(
            update.message,
            "مرحباً! أنا مساعدك الذكي القابل للتخصيص ✨\n\n"
            "الأوامر المتاحة:\n"
            "/help - عرض المساعدة\n"
            "/new - بدء محادثة جديدة\n"
            "/goals - عرض أهدافك وتقدمك\n"
            "/reset_persona - إعادة تعيين شخصيتي والبدء من جديد\n\n"
            "أرسل أي رسالة وسأتعرف عليك! 🎓",
            parse_mode=None,
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user and update.message:
        record_user_engagement(update)
        await send_reply_with_retry(
            update.message,
            "📖 كيفية استخدام المساعد الذكي\n\n"
            "أنا مساعد قابل للتخصيص - يمكنك تحديد شخصيتي ودوري وأسلوبي!\n\n"
            "الأوامر المتاحة:\n"
            "/start - رسالة الترحيب\n"
            "/help - عرض هذه المساعدة\n"
            "/new - بدء محادثة جديدة (نسيان المحادثة السابقة)\n"
            "/goals - عرض أهدافك وتقدمك\n"
            "/reset_persona - إعادة تعيين شخصيتي والبدء من جديد\n\n"
            "كيفية تخصيصي:\n"
            "• أخبرني باسمك المفضل لي\n"
            "• حدد دوري (مدرس، صديق، مستشار، إلخ)\n"
            "• اختر أسلوب التواصل (رسمي، ودود، مرح)\n"
            "• حدد المجالات التي تريد مساعدة فيها\n\n"
            "فقط أرسل رسالتك وسأساعدك! 💡",
            parse_mode=None,
        )

async def goals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user and update.message:
        record_user_engagement(update)
        await forward_to_agent(update, context, "/goals")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user and update.message:
        record_user_engagement(update)
        await send_reply_with_retry(
            update.message,
            "<b>الإعدادات</b>\nاختر كيف تحب تكون ردود بلبل.\n\nالردود الصوتية قادمة لاحقاً، لكنها غير مفعلة حتى نربط مزود تحويل النص إلى صوت.",
            reply_markup=build_settings_markup(),
        )


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user and update.message:
        record_user_engagement(update)
        # Reset local conversation history so we get a fresh session.
        reset_succeeded = await reset_local_session_history(update.effective_user.id)
        if not reset_succeeded:
            await send_reply_with_retry(
                update.message,
                "عذراً، لم أتمكن من بدء محادثة جديدة الآن. يرجى المحاولة مرة أخرى.",
                parse_mode=None,
            )
            return

        await send_reply_with_retry(
            update.message,
            "تم بدء محادثة جديدة! 🆕\n\n"
            "يمكنك الآن طرح سؤال جديد، وسأنسى المحادثة السابقة.\n\n"
            "فقط أرسل سؤالك! 📚",
            parse_mode=None,
        )

async def reset_persona_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user and update.message:
        record_user_engagement(update)
        await forward_to_agent(update, context, "/reset_persona")
        # The agent handles resetting the persona. We also reset conversation history.
        reset_succeeded = await reset_local_session_history(update.effective_user.id)
        if not reset_succeeded:
            await send_reply_with_retry(
                update.message,
                "تنبيه: تمت محاولة إعادة تعيين الشخصية، لكن لم أتمكن من مسح سجل المحادثة. يرجى استخدام /new أو المحاولة مرة أخرى.",
                parse_mode=None,
            )


# Message Handlers
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user and update.message and update.message.text:
        record_user_engagement(update)
        await forward_to_agent(update, context, update.message.text.strip())


async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    record_user_engagement(update)
    query_text = (update.message.caption or "ما هذا؟").strip()
    photo_bytes, mime_type = await download_photo(update, context)
    
    if photo_bytes is None:
        await send_reply_with_retry(update.message, "لم أتمكن من تحميل الصورة.", parse_mode=None)
        return

    await forward_to_agent(update, context, query_text, photo_bytes, mime_type)


async def download_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[Optional[bytes], str, int]:
    if not update.message or not update.message.voice:
        return None, "", 0
    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        audio_bytes = await file.download_as_bytearray()
        mime_type = voice.mime_type or "audio/ogg"
        return bytes(audio_bytes), mime_type, voice.duration
    except Exception as e:
        logger.error(f"Failed to download voice message: {e}")
        return None, "", 0


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.effective_chat:
        return

    record_user_engagement(update)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    try:
        audio_bytes, mime_type, duration = await download_voice(update, context)
        
        if audio_bytes is None:
            await send_reply_with_retry(update.message, "لم أتمكن من تحميل الرسالة الصوتية.", parse_mode=None)
            return
            
        if duration > 120:
            await send_reply_with_retry(update.message, "عذراً، الرسالة الصوتية طويلة جداً. الحد الأقصى هو ٢ دقيقة.", parse_mode=None)
            return
            
        # Transcribe locally in the Telegram service and pass text to Bulbul.
        from .transcription import transcribe_audio
        transcription_result = await transcribe_audio(audio_data=audio_bytes, mime_type=mime_type, language_code="ar-XA")
        
        if not transcription_result.success:
            await send_reply_with_retry(update.message, "لم أتمكن من فهم الرسالة الصوتية.", parse_mode=None)
            return
            
        transcribed_text = transcription_result.text
        await forward_to_agent(update, context, transcribed_text)
        
    except Exception as e:
        logger.exception(f"Error handling voice message: {e}")
        await send_reply_with_retry(update.message, format_error_message(e), parse_mode=None)


async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    poll_answer = update.poll_answer
    if not poll_answer:
        return

    poll_context = POLL_CONTEXTS.get(poll_answer.poll_id)
    if not poll_context:
        return

    selected = poll_answer.option_ids[0] if poll_answer.option_ids else None
    is_correct = selected == poll_context["correct_index"]
    result_text = "صحيحة" if is_correct else "غير صحيحة"
    prompt = (
        f"نتيجة اختبار الهدف {poll_context['goal_id']}: إجابة المستخدم {result_text}. "
        "حدّث تقدم الهدف باختصار، وإذا كانت الإجابة غير صحيحة فاقترح مراجعة صغيرة."
    )
    await send_agent_text(
        user_id=poll_context["user_id"],
        chat_id=poll_context["chat_id"],
        context=context,
        query_text=prompt,
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                format_error_message(context.error if isinstance(context.error, Exception) else None)
            )
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
