"""Model selection helpers for Bulbul agents."""

from __future__ import annotations

import os

from google.adk.models import Gemini
from google.adk.models.lite_llm import LiteLlm


DEFAULT_TEXT_MODEL = "deepseek/deepseek-v4-flash"
DEFAULT_GEMINI_FALLBACK_MODEL = "gemini-3.1-flash-lite"

BULBUL_AGENT_MODEL_ENV = "BULBUL_AGENT_MODEL"
BULBUL_GEMINI_FALLBACK_MODEL_ENV = "BULBUL_GEMINI_FALLBACK_MODEL"


def text_model_name() -> str:
    """Return the text-only model, preferring the lower-cost DeepSeek setting."""
    return os.getenv(BULBUL_AGENT_MODEL_ENV, DEFAULT_TEXT_MODEL)


def gemini_fallback_model_name() -> str:
    """Return the cheap Gemini model for multimodal and Gemini-native tools."""
    return os.getenv(BULBUL_GEMINI_FALLBACK_MODEL_ENV, DEFAULT_GEMINI_FALLBACK_MODEL)


def build_text_model():
    """Build the configured text model for standard chat/function-calling turns."""
    model = text_model_name()
    if model.startswith("gemini"):
        return Gemini(model=model)
    return LiteLlm(model=model)


def build_gemini_fallback_model():
    """Build the Gemini fallback model for image/audio/native-tool use cases."""
    return Gemini(model=gemini_fallback_model_name())
