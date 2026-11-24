from fastapi import APIRouter

from backend.app.core.settings_store import (
    AppSettings,
    SUPPORTED_TTS_VOICES,
    get_runtime_settings,
    update_runtime_settings,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def read_settings():
    """Return current runtime AI, retrieval, and TTS settings."""
    data = get_runtime_settings().model_dump()
    data["supported_voices"] = list(SUPPORTED_TTS_VOICES)
    return data


@router.put("")
def write_settings(payload: AppSettings):
    """Validate and persist updated runtime AI, retrieval, and TTS settings."""
    saved = update_runtime_settings(payload).model_dump()
    saved["supported_voices"] = list(SUPPORTED_TTS_VOICES)
    return saved
