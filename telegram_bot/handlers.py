"""
Telegram bot handlers for commands and messages.

Handles all user interactions with the Educational Assistant bot.
"""

import asyncio
import logging
import time
from typing import Optional

from telegram import Update
from telegram.constants import ChatAction
from telegram.error import BadRequest, TimedOut
from telegram.ext import ContextTypes

from core import process_agent_query, reset_user_persona
from core.outreach_service import outreach_service

from .config import APP_NAME
from .session_manager import SessionManager
from .utils import (
    format_error_message,
    log_user_interaction,
    sanitize_html_for_telegram,
    split_message,
)

logger = logging.getLogger(__name__)

# Module-level session manager instance
session_manager = SessionManager()

# Constants for retry logic
MAX_SEND_RETRIES = 3
RETRY_DELAY_SECONDS = 1.0


async def send_reply_with_retry(
    message,
    text: str,
    parse_mode: Optional[str] = "HTML",
    max_retries: int = MAX_SEND_RETRIES,
) -> bool:
    """
    Send a reply message with retry logic for timeouts.

    Args:
        message: The Telegram message to reply to
        text: The text to send
        parse_mode: HTML or None
        max_retries: Maximum number of retry attempts

    Returns:
        True if message was sent successfully, False otherwise
    """
    for attempt in range(max_retries):
        try:
            await message.reply_text(text, parse_mode=parse_mode)
            return True
        except BadRequest as e:
            if "Can't parse entities" in str(e) and parse_mode == "HTML":
                # Fallback: send without HTML formatting
                try:
                    await message.reply_text(text, parse_mode=None)
                    return True
                except TimedOut:
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Timeout sending reply (attempt {attempt + 1}), retrying..."
                        )
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                        continue
                    logger.error("Failed to send reply after max retries")
                    return False
            else:
                raise
        except TimedOut:
            if attempt < max_retries - 1:
                logger.warning(
                    f"Timeout sending reply (attempt {attempt + 1}), retrying..."
                )
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            else:
                logger.error("Failed to send reply after max retries")
                return False
    return False


async def download_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> tuple[Optional[bytes], str]:
    """
    Download the largest available photo from a Telegram message.

    Args:
        update: The Telegram update containing the photo
        context: The callback context

    Returns:
        Tuple of (photo_bytes, mime_type) or (None, "") on failure
    """
    if not update.message or not update.message.photo:
        return None, ""

    try:
        # Get the largest photo (last in the list has highest resolution)
        photo = update.message.photo[-1]

        # Download the photo file
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()

        # Telegram photos are typically JPEG
        mime_type = "image/jpeg"

        return bytes(photo_bytes), mime_type

    except Exception as e:
        logger.error(f"Failed to download photo: {e}")
        return None, ""


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /start command - welcome message in Arabic.

    Args:
        update: The Telegram update object
        context: The callback context

    Example:
        User sends: /start
        Bot responds: Welcome message in Arabic with instructions
    """
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username

    logger.info(f"User {user_id} (@{username}) started the bot")

    welcome_message = """مرحباً! أنا مساعدك الذكي القابل للتخصيص ✨

يمكنني التكيف مع احتياجاتك وتفضيلاتك - فقط أخبرني كيف تريدني أن أكون!

الأوامر المتاحة:
/help - عرض المساعدة
/new - بدء محادثة جديدة
/reset_persona - إعادة تعيين شخصيتي والبدء من جديد

أرسل أي رسالة وسأتعرف عليك! 🎓"""

    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /help command - usage instructions in Arabic.

    Args:
        update: The Telegram update object
        context: The callback context

    Example:
        User sends: /help
        Bot responds: Help message with instructions
    """
    if not update.message:
        return

    help_message = """📖 كيفية استخدام المساعد الذكي

أنا مساعد قابل للتخصيص - يمكنك تحديد شخصيتي ودوري وأسلوبي!

الأوامر المتاحة:
/start - رسالة الترحيب
/help - عرض هذه المساعدة
/new - بدء محادثة جديدة (نسيان المحادثة السابقة)
/reset_persona - إعادة تعيين شخصيتي والبدء من جديد

كيفية تخصيصي:
• أخبرني باسمك المفضل لي
• حدد دوري (مدرس، صديق، مستشار، إلخ)
• اختر أسلوب التواصل (رسمي، ودود، مرح)
• حدد المجالات التي تريد مساعدة فيها

نصائح:
• يمكنني تذكر المحادثة والتفضيلات السابقة
• إذا أردت تغيير شخصيتي، فقط أخبرني
• استخدم /reset_persona للبدء من الصفر

فقط أرسل رسالتك وسأساعدك! 💡"""

    await update.message.reply_text(help_message)


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /new command - reset conversation and start fresh.

    Args:
        update: The Telegram update object
        context: The callback context

    Example:
        User sends: /new
        Bot responds: Confirmation that conversation was reset
    """
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username

    # Reset the session
    session_manager.reset_session(user_id)

    logger.info(f"User {user_id} (@{username}) reset their conversation")

    confirmation_message = """تم بدء محادثة جديدة! 🆕

يمكنك الآن طرح سؤال جديد، وسأنسى المحادثة السابقة.

فقط أرسل سؤالك! 📚"""

    await update.message.reply_text(confirmation_message)


async def reset_persona_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /reset_persona command - reset agent persona to defaults.

    This clears all saved personality, mission, and preferences,
    allowing the user to reconfigure the agent from scratch.

    Args:
        update: The Telegram update object
        context: The callback context

    Example:
        User sends: /reset_persona
        Bot responds: Confirmation that persona was reset
    """
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username

    # Reset persona
    success = await reset_user_persona(str(user_id))

    # Also reset the session to start fresh
    session_manager.reset_session(user_id)

    if success:
        logger.info(f"User {user_id} (@{username}) reset their agent persona")

        confirmation_message = """تم إعادة تعيين شخصية المساعد! 🔄

تم مسح جميع التفضيلات والإعدادات السابقة.
في المحادثة القادمة، سأتعرف عليك من جديد وأتكيف مع تفضيلاتك.

أرسل أي رسالة للبدء! ✨"""
    else:
        logger.error(f"Failed to reset persona for user {user_id} (@{username})")

        confirmation_message = """عذراً، حدث خطأ أثناء إعادة التعيين.
يرجى المحاولة مرة أخرى لاحقاً."""

    await update.message.reply_text(confirmation_message)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle text messages - process user queries with the educational agent.

    Args:
        update: The Telegram update object
        context: The callback context

    Example:
        User sends: "ما هي نظرية فيثاغورس؟"
        Bot responds: Arabic explanation from Claude
    """
    if not update.effective_user or not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username
    message_text = update.message.text.strip()

    # Validate message
    if not message_text:
        await update.message.reply_text(
            "الرجاء إرسال سؤال أو نص غير فارغ."
        )
        return

    logger.info(
        f"Received message from user {user_id} (@{username}): "
        f'"{message_text[:50]}..."'
    )

    # Track engagement for proactive outreach
    if outreach_service:
        outreach_service.update_interaction(
            "telegram", str(user_id), update.effective_chat.id
        )

    # Show typing indicator
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    start_time = time.time()

    try:
        # Get or create session ID
        session_id = session_manager.get_or_create_session(user_id)

        # Process query with the agent
        result = await process_agent_query(
            query=message_text,
            user_id=str(user_id),
            session_id=session_id,
            app_name=APP_NAME,
        )

        # Store updated session ID (may be new)
        session_manager.store_session(user_id, result["session_id"])

        duration = time.time() - start_time

        # Handle response based on status
        if result["status"] == "success":
            response_text = result["response"]

            # Log interaction
            log_user_interaction(
                user_id=user_id,
                username=username,
                query=message_text,
                status="success",
                duration=duration,
            )

            # Sanitize HTML for Telegram and split message if too long
            sanitized_response = sanitize_html_for_telegram(response_text)
            chunks = split_message(sanitized_response)

            # Send message(s) to user with HTML formatting
            for i, chunk in enumerate(chunks):
                await send_reply_with_retry(update.message, chunk)

                # Small delay between chunks for better UX
                if i < len(chunks) - 1:
                    await asyncio.sleep(0.5)

        else:
            # Agent returned error status
            error_msg = result.get("error", "Unknown error")
            logger.error(
                f"Agent error for user {user_id}: {error_msg}"
            )

            # Log interaction
            log_user_interaction(
                user_id=user_id,
                username=username,
                query=message_text,
                status="error",
                duration=duration,
            )

            # Send user-friendly error message
            await update.message.reply_text(
                "عذراً، واجهت مشكلة في معالجة سؤالك. "
                "يرجى إعادة صياغة السؤال أو المحاولة مرة أخرى."
            )

    except Exception as e:
        duration = time.time() - start_time

        logger.exception(
            f"Error processing message from user {user_id}: {e}"
        )

        # Log interaction
        log_user_interaction(
            user_id=user_id,
            username=username,
            query=message_text,
            status="error",
            duration=duration,
        )

        # Send user-friendly error message
        error_message = format_error_message(e)
        await update.message.reply_text(error_message)


async def handle_photo_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle photo messages - process images with optional caption.

    Supports:
    - Photo with caption: Uses caption as the query
    - Photo without caption: Uses default educational prompt

    Args:
        update: The Telegram update object
        context: The callback context
    """
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username

    # Get caption (text accompanying the photo)
    caption = update.message.caption
    if caption:
        caption = caption.strip()

    query_text = caption or ""

    logger.info(
        f"Received photo from user {user_id} (@{username})"
        + (f' with caption: "{query_text[:50]}..."' if query_text else " (no caption)")
    )

    # Track engagement for proactive outreach
    if outreach_service:
        outreach_service.update_interaction(
            "telegram", str(user_id), update.effective_chat.id
        )

    # Show typing indicator
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    start_time = time.time()

    try:
        # Download the photo
        photo_bytes, mime_type = await download_photo(update, context)

        if photo_bytes is None:
            await update.message.reply_text(
                "عذراً، لم أتمكن من تحميل الصورة. يرجى المحاولة مرة أخرى."
            )
            return

        # Get or create session ID
        session_id = session_manager.get_or_create_session(user_id)

        # Process query with the agent (including image)
        result = await process_agent_query(
            query=query_text,
            user_id=str(user_id),
            session_id=session_id,
            app_name=APP_NAME,
            image_data=photo_bytes,
            image_mime_type=mime_type,
        )

        # Store updated session ID
        session_manager.store_session(user_id, result["session_id"])

        duration = time.time() - start_time

        # Handle response based on status
        if result["status"] == "success":
            response_text = result["response"]

            # Log interaction
            log_user_interaction(
                user_id=user_id,
                username=username,
                query=f"[IMAGE] {query_text}" if query_text else "[IMAGE]",
                status="success",
                duration=duration,
            )

            # Sanitize HTML for Telegram and split message if too long
            sanitized_response = sanitize_html_for_telegram(response_text)
            chunks = split_message(sanitized_response)

            # Send message(s) to user with HTML formatting
            for i, chunk in enumerate(chunks):
                await send_reply_with_retry(update.message, chunk)

                # Small delay between chunks for better UX
                if i < len(chunks) - 1:
                    await asyncio.sleep(0.5)

        else:
            # Agent returned error status
            error_msg = result.get("error", "Unknown error")
            logger.error(f"Agent error for user {user_id}: {error_msg}")

            # Log interaction
            log_user_interaction(
                user_id=user_id,
                username=username,
                query=f"[IMAGE] {query_text}" if query_text else "[IMAGE]",
                status="error",
                duration=duration,
            )

            # Send user-friendly error message
            await update.message.reply_text(
                "عذراً، واجهت مشكلة في معالجة الصورة. "
                "يرجى المحاولة مرة أخرى أو إرسال صورة أوضح."
            )

    except Exception as e:
        duration = time.time() - start_time

        logger.exception(f"Error processing photo from user {user_id}: {e}")

        # Log interaction
        log_user_interaction(
            user_id=user_id,
            username=username,
            query=f"[IMAGE] {query_text}" if query_text else "[IMAGE]",
            status="error",
            duration=duration,
        )

        # Send user-friendly error message
        error_message = format_error_message(e)
        await update.message.reply_text(error_message)


async def download_voice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[Optional[bytes], str, int]:
    """
    Download voice message from a Telegram message.

    Args:
        update: The Telegram update containing the voice
        context: The callback context

    Returns:
        Tuple of (audio_bytes, mime_type, duration_seconds) or (None, "", 0) on failure
    """
    if not update.message or not update.message.voice:
        return None, "", 0

    try:
        voice = update.message.voice

        # Download the voice file
        file = await context.bot.get_file(voice.file_id)
        audio_bytes = await file.download_as_bytearray()

        # Telegram voice messages are OGG with Opus codec
        mime_type = voice.mime_type or "audio/ogg"
        duration = voice.duration

        return bytes(audio_bytes), mime_type, duration

    except Exception as e:
        logger.error(f"Failed to download voice message: {e}")
        return None, "", 0


async def handle_voice_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Handle voice messages - transcribe and process with the educational agent.

    Flow:
    1. Download voice file from Telegram
    2. Transcribe using Google Chirp 3
    3. Pass transcribed text to agent
    4. Return response to user

    Args:
        update: The Telegram update object
        context: The callback context
    """
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    username = update.effective_user.username

    logger.info(f"Received voice message from user {user_id} (@{username})")

    # Track engagement for proactive outreach
    if outreach_service:
        outreach_service.update_interaction(
            "telegram", str(user_id), update.effective_chat.id
        )

    # Show typing indicator
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )

    start_time = time.time()

    try:
        # Download the voice file
        audio_bytes, mime_type, duration = await download_voice(update, context)

        if audio_bytes is None:
            await update.message.reply_text(
                "عذراً، لم أتمكن من تحميل الرسالة الصوتية. يرجى المحاولة مرة أخرى."
            )
            return

        # Check duration limit (max 2 minutes)
        max_duration_seconds = 120
        if duration > max_duration_seconds:
            await update.message.reply_text(
                "عذراً، الرسالة الصوتية طويلة جداً. "
                "الحد الأقصى هو ٢ دقيقة."
            )
            return

        # Transcribe audio
        from .transcription import transcribe_audio

        transcription_result = await transcribe_audio(
            audio_data=audio_bytes,
            mime_type=mime_type,
            language_code="ar-XA",  # Standard Arabic
        )

        if not transcription_result.success:
            error_msg = "لم أتمكن من فهم الرسالة الصوتية."
            if "No speech detected" in (transcription_result.error or ""):
                error_msg = (
                    "لم أتمكن من سماع أي كلام في الرسالة الصوتية. "
                    "يرجى المحاولة مرة أخرى."
                )

            await update.message.reply_text(error_msg)

            log_user_interaction(
                user_id=user_id,
                username=username,
                query="[VOICE] (transcription failed)",
                status="error",
                duration=time.time() - start_time,
            )
            return

        transcribed_text = transcription_result.text

        logger.info(
            f"Transcribed voice from user {user_id}: "
            f'"{transcribed_text[:50]}..." (confidence: {transcription_result.confidence:.2f})'
        )

        # Get or create session ID
        session_id = session_manager.get_or_create_session(user_id)

        # Process query with the agent
        result = await process_agent_query(
            query=transcribed_text,
            user_id=str(user_id),
            session_id=session_id,
            app_name=APP_NAME,
        )

        # Store updated session ID
        session_manager.store_session(user_id, result["session_id"])

        duration_total = time.time() - start_time

        # Handle response based on status
        if result["status"] == "success":
            response_text = result["response"]

            # Log interaction
            log_user_interaction(
                user_id=user_id,
                username=username,
                query=f"[VOICE] {transcribed_text}",
                status="success",
                duration=duration_total,
            )

            # Sanitize HTML for Telegram and split message if too long
            sanitized_response = sanitize_html_for_telegram(response_text)
            chunks = split_message(sanitized_response)

            # Send message(s) to user with HTML formatting
            for i, chunk in enumerate(chunks):
                await send_reply_with_retry(update.message, chunk)

                # Small delay between chunks for better UX
                if i < len(chunks) - 1:
                    await asyncio.sleep(0.5)

        else:
            # Agent returned error status
            error_msg = result.get("error", "Unknown error")
            logger.error(f"Agent error for user {user_id}: {error_msg}")

            log_user_interaction(
                user_id=user_id,
                username=username,
                query=f"[VOICE] {transcribed_text}",
                status="error",
                duration=duration_total,
            )

            await send_reply_with_retry(
                update.message,
                "عذراً، واجهت مشكلة في معالجة سؤالك. "
                "يرجى إعادة صياغة السؤال أو المحاولة مرة أخرى.",
                parse_mode=None,
            )

    except Exception as e:
        duration_total = time.time() - start_time

        logger.exception(f"Error processing voice message from user {user_id}: {e}")

        log_user_interaction(
            user_id=user_id,
            username=username,
            query="[VOICE] (processing error)",
            status="error",
            duration=duration_total,
        )

        error_message = format_error_message(e)
        await update.message.reply_text(error_message)


async def error_handler(
    update: Optional[Update],
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Handle errors that occur during bot operation.

    Args:
        update: The Telegram update object (may be None)
        context: The callback context containing error information

    Example:
        When any handler raises an exception, this logs it and
        optionally notifies the user.
    """
    logger.error("Exception while handling an update:", exc_info=context.error)

    # Try to notify the user if possible
    if update and update.effective_message:
        try:
            error_message = format_error_message(
                context.error if isinstance(context.error, Exception) else None
            )
            await update.effective_message.reply_text(error_message)
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")
