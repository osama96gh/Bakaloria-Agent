"""
Telegram bot handlers for messages and commands, acting purely as a delivery hub to Goa.
"""

import asyncio
import logging
import time
from typing import Optional
import httpx

from telegram import Update
from telegram.constants import ChatAction
from telegram.error import BadRequest, TimedOut
from telegram.ext import ContextTypes

from .config import GOA_URL, GOA_API_KEY, BULBUL_PARTICIPANT_ID
from .utils import (
    format_error_message,
    log_user_interaction,
    sanitize_html_for_telegram,
    split_message,
)
from bulbul_agent.core.outreach_service import outreach_service

logger = logging.getLogger(__name__)

MAX_SEND_RETRIES = 3
RETRY_DELAY_SECONDS = 1.0


async def _goa_request(method: str, path: str, **kwargs) -> httpx.Response:
    """Helper for making requests to the Goa API."""
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {GOA_API_KEY}"
    if "files" not in kwargs:
        headers["Content-Type"] = "application/json"
    
    url = f"{GOA_URL}{path}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await client.request(method, url, headers=headers, **kwargs)


async def get_or_create_goa_task(user_id: int) -> str:
    """Finds or creates a Goa task (session) for the Telegram user."""
    resp = await _goa_request("POST", "/tasks/upsert", json={
        "external_ref": f"telegram_{user_id}",
        "on_create": {}
    })
    resp.raise_for_status()
    data = resp.json()
    return data["task"]["id"]


async def reset_goa_task(user_id: int) -> bool:
    """Closes the current Goa task for the user, forcing a fresh session on next upsert."""
    try:
        task_id = await get_or_create_goa_task(user_id)
        resp = await _goa_request("POST", f"/tasks/{task_id}/close")
        resp.raise_for_status()
        logger.info(f"Closed Goa task {task_id} for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to reset task for user {user_id}: {e}")
        return False


def record_user_engagement(update: Update) -> None:
    """Record a Telegram user interaction for proactive outreach."""
    if not outreach_service or not update.effective_user or not update.effective_chat:
        return

    outreach_service.update_interaction(
        "telegram",
        str(update.effective_user.id),
        update.effective_chat.id,
    )


async def ask_agent_via_goa(task_id: str, text: str, image_bytes: Optional[bytes] = None, image_mime: str = "") -> dict:
    """Sends a QuestionEvent to Goa and polls for the AnswerEvent."""
    try:
        attachments = []
        if image_bytes:
            files = {"file": ("image", image_bytes, image_mime)}
            blob_resp = await _goa_request("POST", f"/tasks/{task_id}/blobs", files=files)
            blob_resp.raise_for_status()
            attachment = blob_resp.json()
            attachments.append(attachment)
            logger.info(f"Uploaded blob {attachment['blob_id']} to task {task_id}")
        
        # 1. Post the Question
        question_payload = {
            "event_type": "question",
            "content": {
                "text": text,
                "attachments": attachments
            },
            "payload": {
                "to": [BULBUL_PARTICIPANT_ID]
            }
        }
        
        q_resp = await _goa_request("POST", f"/tasks/{task_id}/events", json=question_payload)
        q_resp.raise_for_status()
        question_event = q_resp.json()["event"]
        question_id = question_event["id"]
        
        logger.info(f"Posted QuestionEvent {question_id} to task {task_id}")
        
        # 2. Poll for the Answer
        max_polls = 120  # 1 minute max (poll every 0.5s)
        for _ in range(max_polls):
            await asyncio.sleep(0.5)
            events_resp = await _goa_request("GET", f"/tasks/{task_id}")
            if events_resp.status_code != 200:
                continue
                
            events = events_resp.json().get("events", [])
            for ev in events:
                if ev.get("event_type") == "answer" and ev.get("in_reply_to") == question_id:
                    answer_text = ev.get("content", {}).get("text", "")
                    return {"status": "success", "response": answer_text}
                    
        return {"status": "error", "error": "Timeout waiting for agent response"}
        
    except Exception as e:
        logger.error(f"Error communicating with Goa: {e}")
        return {"status": "error", "error": str(e)}


async def send_reply_with_retry(message, text: str, parse_mode: Optional[str] = "HTML", max_retries: int = MAX_SEND_RETRIES) -> bool:
    """Send a reply message with retry logic for timeouts and formatting issues."""
    for attempt in range(max_retries):
        try:
            await message.reply_text(text, parse_mode=parse_mode)
            return True
        except BadRequest as e:
            if "Can't parse entities" in str(e) and parse_mode == "HTML":
                try:
                    await message.reply_text(text, parse_mode=None)
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
    """Core logic to forward any message/command to Goa and return the agent's response."""
    if not update.effective_user or not update.effective_chat or not update.message:
        return
        
    user_id = update.effective_user.id
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        task_id = await get_or_create_goa_task(user_id)
        result = await ask_agent_via_goa(task_id, query_text, photo_bytes, mime_type)

        if result["status"] == "success":
            sanitized = sanitize_html_for_telegram(result["response"])
            chunks = split_message(sanitized)
            for chunk in chunks:
                await send_reply_with_retry(update.message, chunk)
        else:
            await send_reply_with_retry(update.message, "عذراً، واجهت مشكلة في الاتصال بالوكيل الذكي.", parse_mode=None)
    except Exception as e:
        logger.exception(f"Error handling message: {e}")
        await send_reply_with_retry(update.message, format_error_message(e), parse_mode=None)


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
            "/reset_persona - إعادة تعيين شخصيتي والبدء من جديد\n\n"
            "كيفية تخصيصي:\n"
            "• أخبرني باسمك المفضل لي\n"
            "• حدد دوري (مدرس، صديق، مستشار، إلخ)\n"
            "• اختر أسلوب التواصل (رسمي، ودود، مرح)\n"
            "• حدد المجالات التي تريد مساعدة فيها\n\n"
            "فقط أرسل رسالتك وسأساعدك! 💡",
            parse_mode=None,
        )

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user and update.message:
        record_user_engagement(update)
        # Reset the Goa task on our side so we get a fresh session
        reset_succeeded = await reset_goa_task(update.effective_user.id)
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
        # The agent handles resetting the persona in Supabase. We also reset the task.
        reset_succeeded = await reset_goa_task(update.effective_user.id)
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
            
        # Note: Depending on your exact infrastructure, you might want to either:
        # A. Transcribe locally in telegram service and pass text to Goa
        # B. Send audio blob to Goa and let Agent handle transcription
        # For simplicity here (assuming Agent handles it or you have local transcription package):
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


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                format_error_message(context.error if isinstance(context.error, Exception) else None)
            )
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
