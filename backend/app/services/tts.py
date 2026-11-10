"""Neural Text-to-Speech (TTS) service using Kokoro-ONNX.

Dynamically operates on GPU (CUDA) or CPU based on environment hardware detection.
Synthesizes speech entirely in RAM (io.BytesIO) with zero disk writes.
"""

import io
import re
from pathlib import Path
from typing import Optional
import numpy as np
import soundfile
import logging
import hashlib
import onnxruntime as rt
from kokoro_onnx import Kokoro
from backend.app.core.cache import get_cache_backend
from backend.app.core.device import get_device_profile

logger = logging.getLogger(__name__)

def sanitize_for_speech(text: str) -> str:
    """Strip markdown formatting symbols so Kokoro speaks words instead of 'asterisk', 'hashtag', etc."""
    if not text:
        return ""
    # Strip markdown links [text](url) -> text
    cleaned = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Strip bold / italics asterisks and underscores: **bold**, *italic*, _italic_
    cleaned = re.sub(r'[\*_]{1,3}([^\*_]+)[\*_]{1,3}', r'\1', cleaned)
    # Strip stray asterisks, hashes, backticks, tildes
    cleaned = re.sub(r'[\*#`~]', '', cleaned)
    # Normalize multiple whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


class KokoroTTS:
    """Wrapper around kokoro-onnx engine for zero-disk audio streaming."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        voices_path: Optional[str] = None,
        default_voice: str = "af_sarah",
    ):
        """Initialize Kokoro ONNX model dynamically using DeviceProfile."""
        weights_dir = Path(__file__).resolve().parent.parent.parent / "weights" / "kokoro"
        if model_path is None:
            model_path = str(weights_dir / "kokoro-v0_19.onnx")
        if voices_path is None:
            voices_path = str(weights_dir / "voices-v1.0.bin")

        profile = get_device_profile()
        logger.info(f"Initializing Kokoro TTS using profile: {profile.summary()}")

        try:
            sess = rt.InferenceSession(
                model_path,
                sess_options=profile.onnx_session_options,
                providers=profile.onnx_providers
            )
            active_providers = sess.get_providers()
            logger.info(f"[+] Kokoro ONNX active providers: {active_providers}")
            self.kokoro = Kokoro.from_session(sess, voices_path)
        except Exception as e:
            logger.warning(f"[-] Failed to initialize Kokoro with {profile.onnx_providers}: {e}. Falling back to default CPU session.")
            self.kokoro = Kokoro(model_path, voices_path)

        self.default_voice = default_voice
        self.cache = get_cache_backend()

    def synthesize_to_bytes(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> io.BytesIO:
        """Synthesize text to raw WAV in-memory bytes buffer.

        Args:
            text: Text to synthesize.
            voice: Voice ID to use (e.g. 'af_sarah', 'af_heart', 'am_adam', etc.).
            speed: Playback speed multiplier (default 1.0).

        Returns:
            io.BytesIO buffer positioned at offset 0 containing the encoded WAV audio.
        """
        clean_text = sanitize_for_speech(text)
        selected_voice = voice or self.default_voice
        text_hash = hashlib.md5(clean_text.encode("utf-8")).hexdigest()
        cache_key = f"tts:{selected_voice}:{speed}:{text_hash}"
        cached_data = self.cache.get(cache_key)

        if cached_data:
            logger.info(f"[CACHE HIT] Serving cached audio ({len(cached_data)} bytes)")
            return io.BytesIO(cached_data)

        samples, sample_rate = self.kokoro.create(text=clean_text, voice=selected_voice, speed=speed, lang="en-us")
        buffer = io.BytesIO()
        soundfile.write(buffer, samples, sample_rate, format="WAV")
        buffer.seek(0)

        audio_bytes = buffer.getvalue()
        self.cache.set(cache_key, audio_bytes, ttl_seconds=86400)

        return buffer


_tts_instance: Optional[KokoroTTS] = None

def get_tts() -> KokoroTTS:
    """Singleton getter for KokoroTTS instance."""
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = KokoroTTS()
    return _tts_instance
