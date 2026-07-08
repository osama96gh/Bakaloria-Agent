"""
Gemini API provider for audio transcription.

Uses Gemini's native audio understanding capabilities - no Google Cloud setup required.
Just needs a GEMINI_API_KEY.
"""

import logging
import os

from google import genai
from google.genai import types

from .base import STTProvider, TranscriptionResult

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_STT_MODEL = "gemini-3.1-flash-lite"
GEMINI_STT_MODEL_ENV = "GEMINI_TRANSCRIPTION_MODEL"


class GeminiSTTProvider(STTProvider):
    """Gemini API provider for speech-to-text using native audio understanding."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        """
        Initialize the Gemini STT provider.

        Args:
            api_key: Gemini API key. If not provided, uses GEMINI_API_KEY env var.
            model: Gemini model to use. If not provided, uses
                GEMINI_TRANSCRIPTION_MODEL or Gemini Flash-Lite.
        """
        self._api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._model = model or os.getenv(GEMINI_STT_MODEL_ENV, DEFAULT_GEMINI_STT_MODEL)
        self._client: genai.Client | None = None

    @property
    def name(self) -> str:
        return f"Gemini Audio ({self._model})"

    def _get_client(self) -> genai.Client:
        """Lazily initialize the Gemini client."""
        if self._client is None:
            if not self._api_key:
                raise ValueError(
                    "Gemini API key not found. "
                    "Set GEMINI_API_KEY environment variable."
                )
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def transcribe(
        self,
        audio_data: bytes,
        mime_type: str,
        language_code: str,
    ) -> TranscriptionResult:
        """
        Transcribe audio using Gemini's native audio understanding.

        Args:
            audio_data: Raw audio bytes
            mime_type: Audio MIME type (e.g., "audio/ogg")
            language_code: Target language code (used in prompt)

        Returns:
            TranscriptionResult with transcribed text
        """
        try:
            client = self._get_client()

            # Map language codes to language names for the prompt
            language_map = {
                "ar-XA": "Arabic",
                "ar-SA": "Arabic",
                "ar-EG": "Arabic",
                "ar": "Arabic",
                "en-US": "English",
                "en": "English",
            }
            language_name = language_map.get(language_code, "Arabic")

            # Create the transcription prompt
            prompt = f"""Transcribe this audio to text. The audio is in {language_name}.

Rules:
- Output ONLY the transcribed text, nothing else
- Do not add any explanations, translations, or commentary
- Preserve the original language (do not translate)
- Include punctuation where appropriate
- If no speech is detected, respond with exactly: [NO_SPEECH]"""

            # Create audio part from bytes
            audio_part = types.Part.from_bytes(data=audio_data, mime_type=mime_type)

            # Generate transcription
            response = client.models.generate_content(
                model=self._model,
                contents=[prompt, audio_part],
            )

            # Extract transcribed text
            transcript = response.text.strip() if response.text else ""

            # Check for no speech
            if transcript == "[NO_SPEECH]" or not transcript:
                return TranscriptionResult(
                    text="",
                    confidence=0.0,
                    language_code=language_code,
                    error="No speech detected in audio",
                )

            logger.info(
                f"Transcription successful via Gemini: text_length={len(transcript)}"
            )

            return TranscriptionResult(
                text=transcript,
                confidence=0.95,  # Gemini doesn't provide confidence scores
                language_code=language_code,
            )

        except Exception as e:
            logger.error(f"Gemini transcription failed: {e}")
            return TranscriptionResult(
                text="",
                confidence=0.0,
                language_code=language_code,
                error=str(e),
            )
