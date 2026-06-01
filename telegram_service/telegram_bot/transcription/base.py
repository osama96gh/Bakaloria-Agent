"""
Abstract base class for speech-to-text providers.

Enables easy swapping of transcription backends (Google, OpenAI Whisper, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class TranscriptionResult:
    """Result of a transcription operation."""

    text: str
    confidence: float
    language_code: str
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if transcription was successful."""
        return self.error is None and bool(self.text.strip())


class STTProvider(ABC):
    """Abstract base class for speech-to-text providers."""

    @abstractmethod
    async def transcribe(
        self,
        audio_data: bytes,
        mime_type: str,
        language_code: str,
    ) -> TranscriptionResult:
        """
        Transcribe audio to text.

        Args:
            audio_data: Raw audio bytes
            mime_type: Audio MIME type (e.g., "audio/ogg")
            language_code: Target language code (e.g., "ar-XA")

        Returns:
            TranscriptionResult with transcribed text or error
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        pass
