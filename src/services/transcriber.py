"""OpenAI Whisper integration for voice message transcription."""

import io
import logging
from typing import Optional

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def _get_client() -> Optional[AsyncOpenAI]:
    """Lazy-init OpenAI client. Returns None if no API key."""
    global _client
    if _client is not None:
        return _client
    if not settings.openai_api_key:
        return None
    _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def transcribe_voice(audio_bytes: bytes, filename: str = "voice.ogg") -> Optional[str]:
    """
    Transcribe audio bytes using OpenAI Whisper API.

    Args:
        audio_bytes: Raw audio file bytes (downloaded from Telegram)
        filename: Filename hint for Whisper (determines format detection)

    Returns:
        Transcribed text string, or None if transcription failed or
        the result is too short/unintelligible.
    """
    client = _get_client()
    if not client:
        logger.warning("OpenAI client not available for transcription")
        return None

    try:
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = filename

        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="ru",
        )

        text = response.text.strip()

        # Reject very short or noise-only transcriptions
        if not text or len(text) < 3:
            logger.info(f"Whisper returned too short text: '{text}'")
            return None

        logger.info(f"Whisper transcription: '{text[:80]}...'")
        return text

    except Exception as e:
        logger.error(f"Whisper API error: {e}")
        return None
