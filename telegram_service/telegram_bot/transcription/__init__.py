"""
Audio transcription module for the Telegram bot.

Uses Gemini's native audio understanding for speech-to-text.
Only requires a GEMINI_API_KEY - no Google Cloud setup needed.
"""

from .base import STTProvider, TranscriptionResult
from .gemini_stt import GeminiSTTProvider

# Default provider instance (lazy initialization)
_default_provider: GeminiSTTProvider | None = None

# Default language for Arabic transcription
DEFAULT_LANGUAGE_CODE = "ar-XA"


def _get_provider() -> GeminiSTTProvider:
    """Get or create the default STT provider."""
    global _default_provider
    if _default_provider is None:
        _default_provider = GeminiSTTProvider()
    return _default_provider


async def transcribe_audio(
    audio_data: bytes,
    mime_type: str = "audio/ogg",
    language_code: str = DEFAULT_LANGUAGE_CODE,
) -> TranscriptionResult:
    """
    Transcribe audio to text using Gemini.

    Args:
        audio_data: Raw audio bytes
        mime_type: Audio MIME type (default: "audio/ogg" for Telegram voice)
        language_code: Language code for transcription (default: "ar-XA" for Arabic)

    Returns:
        TranscriptionResult with transcribed text and confidence score
    """
    provider = _get_provider()
    return await provider.transcribe(audio_data, mime_type, language_code)


__all__ = [
    "transcribe_audio",
    "TranscriptionResult",
    "STTProvider",
    "GeminiSTTProvider",
    "DEFAULT_LANGUAGE_CODE",
]
