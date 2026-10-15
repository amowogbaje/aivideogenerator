import shutil

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.schemas import VoicePreview
from app.services import storage, voices
from app.services.providers.image import get_image_provider
from app.services.providers.text import get_text_provider
from app.services.providers.voice import get_voice_service

router = APIRouter(tags=["Config"])


def _name(factory) -> str:
    try:
        return factory().name if not hasattr(factory(), "primary") else factory().primary
    except Exception as e:  # noqa: BLE001 — surface misconfiguration in the UI instead of 500ing
        return f"misconfigured: {e}"


@router.get("/config")
async def config():
    text, image, voice = _name(get_text_provider), _name(get_image_provider), _name(get_voice_service)
    offline = {text, image, voice} & {"heuristic", "mock", "espeak", "tone"}
    return {
        "providers": {"text": text, "image": image, "voice": voice},
        "placeholder_mode": bool(offline),  # tells the UI to show "demo providers — add API keys for real output"
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "voices": [{"id": v.id, "label": v.label, "gender": v.gender, "age": v.age} for v in voices.VOICES],
        "aspect_ratios": ["9:16", "16:9"],
    }


@router.post("/voices/preview")
async def preview_voice(body: VoicePreview):
    if body.voice_id not in voices.BY_ID:
        raise HTTPException(422, "Unknown voice_id")
    rel, path = storage.new_path("previews", ext="mp3")
    try:
        used = await get_voice_service().synthesize(body.text[:300], body.voice_id, path)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Voice preview failed: {e}")
    return {"url": storage.url(rel), "provider": used}
