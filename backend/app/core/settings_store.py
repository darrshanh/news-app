"""Runtime-tunable AI, retrieval, and TTS settings persisted in SQLite."""

import json
import logging
import threading
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from backend.app.core.database import get_setting_raw, save_setting_raw

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "ai_config"

SUPPORTED_TTS_VOICES = (
    "af_sarah",
    "af_heart",
    "af_bella",
    "am_adam",
    "am_michael",
    "bf_emma",
    "bm_george",
)


class AppSettings(BaseModel):
    """Validated user-configurable parameters for summarization, LangGraph context, and TTS."""

    llm_temperature: float = Field(default=0.35, ge=0.0, le=1.0)
    summary_target_words: int = Field(default=250, ge=100, le=400)
    context_min_score: float = Field(default=0.42, ge=0.20, le=0.75)
    context_max_precedents: int = Field(default=4, ge=1, le=6)
    articles_per_feed: int = Field(default=5, ge=1, le=10)
    bandit_alpha: float = Field(default=0.40, ge=0.0, le=1.5)
    tts_voice: str = Field(default="af_sarah")

    @field_validator("tts_voice")
    @classmethod
    def validate_tts_voice(cls, value: str) -> str:
        clean = (value or "").strip()
        if clean not in SUPPORTED_TTS_VOICES:
            raise ValueError(
                f"Unsupported voice '{clean}'. Choose from: {', '.join(SUPPORTED_TTS_VOICES)}"
            )
        return clean


_settings_lock = threading.Lock()
_cached_settings: Optional[AppSettings] = None


def get_runtime_settings() -> AppSettings:
    """Return cached runtime settings, hydrating from SQLite on first call."""
    global _cached_settings
    with _settings_lock:
        if _cached_settings is not None:
            return _cached_settings

        raw = None
        try:
            raw = get_setting_raw(_SETTINGS_KEY)
        except Exception as e:
            logger.debug(f"Settings table not ready yet, using defaults: {e}")

        if raw:
            try:
                _cached_settings = AppSettings.model_validate(json.loads(raw))
                return _cached_settings
            except Exception as e:
                logger.warning(f"[-] Invalid stored settings JSON, using defaults: {e}")

        _cached_settings = AppSettings()
        return _cached_settings


def update_runtime_settings(new_settings: AppSettings) -> AppSettings:
    """Persist validated settings to SQLite and update the in-memory cache."""
    global _cached_settings
    validated = AppSettings.model_validate(new_settings.model_dump())
    save_setting_raw(_SETTINGS_KEY, validated.model_dump_json())
    with _settings_lock:
        _cached_settings = validated
    logger.info(f"[+] Updated runtime settings: {validated.model_dump()}")
    return validated


def reset_runtime_settings_cache() -> None:
    """Clear the in-memory settings cache so the next read re-hydrates from SQLite."""
    global _cached_settings
    with _settings_lock:
        _cached_settings = None
