"""
Voice providers. Every provider takes a voice PROFILE id (services/voices.py) and writes an mp3.

  elevenlabs — premium (ELEVENLABS_API_KEY)
  edgetts    — free Microsoft neural voices, needs internet
  espeak     — offline, robotic (apt install espeak-ng). For testing / no internet
  tone       — last-resort placeholder hum so the pipeline can run with nothing installed
"""
import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

import httpx

from app.config import settings
from app.services import voices
from app.services.ffmpeg_util import run, to_mp3

logger = logging.getLogger("app.voice")


class EdgeTTS:
    name = "edgetts"

    async def synthesize(self, text: str, voice_id: str, out_mp3: Path) -> None:
        import edge_tts
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.mp3"
            await edge_tts.Communicate(text, voices.get(voice_id).edge).save(str(raw))
            await to_mp3(raw, out_mp3)


class ElevenLabs:
    name = "elevenlabs"

    async def synthesize(self, text: str, voice_id: str, out_mp3: Path) -> None:
        v = voices.get(voice_id)
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{v.eleven}",
                headers={"xi-api-key": settings.ELEVENLABS_API_KEY, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_multilingual_v2"},
            )
        if r.status_code != 200:
            raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.mp3"
            raw.write_bytes(r.content)
            await to_mp3(raw, out_mp3)


class ESpeak:
    name = "espeak"

    @staticmethod
    def available() -> bool:
        return shutil.which("espeak-ng") is not None

    async def synthesize(self, text: str, voice_id: str, out_mp3: Path) -> None:
        v = voices.get(voice_id)
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "raw.wav"
            await run(["espeak-ng", "-v", v.espeak, "-p", str(v.espeak_pitch), "-s", "155", "-w", str(wav), text], timeout=120)
            await to_mp3(wav, out_mp3)


class Tone:
    name = "tone"

    async def synthesize(self, text: str, voice_id: str, out_mp3: Path) -> None:
        seconds = max(1.5, len(text.split()) / 2.6)  # roughly speaking pace
        hz = voices.get(voice_id).tone_hz
        await run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={hz}:duration={seconds:.2f}",
                   "-af", "volume=0.15,tremolo=f=5:d=0.7", "-ac", "1", "-ar", "44100", str(out_mp3)], timeout=60)


_PROVIDERS = {"elevenlabs": ElevenLabs, "edgetts": EdgeTTS, "espeak": ESpeak, "tone": Tone}


class VoiceService:
    """Tries the chosen provider; in `auto` mode it degrades to offline voices instead of failing the whole episode."""

    def __init__(self, chain: list):
        self.chain = chain

    @property
    def primary(self) -> str:
        return self.chain[0].name

    async def synthesize(self, text: str, voice_id: str, out_mp3: Path) -> str:
        last: Exception | None = None
        for provider in self.chain:
            try:
                await provider.synthesize(text, voice_id, out_mp3)
                if out_mp3.exists() and out_mp3.stat().st_size > 0:
                    return provider.name
                raise RuntimeError("provider produced an empty file")
            except Exception as e:  # noqa: BLE001 — we want to try the next provider on anything
                last = e
                logger.warning("voice provider %s failed (%s); trying next", provider.name, e)
        raise RuntimeError(f"All voice providers failed. Last error: {last}")


def get_voice_service() -> VoiceService:
    choice = settings.VOICE_PROVIDER.lower()
    if choice == "auto":
        chain = [ElevenLabs()] if settings.ELEVENLABS_API_KEY else []
        chain.append(EdgeTTS())
        chain.append(ESpeak() if ESpeak.available() else Tone())
        if ESpeak.available():
            chain.append(Tone())
        return VoiceService(chain)
    if choice not in _PROVIDERS:
        raise ValueError(f"Unknown VOICE_PROVIDER '{settings.VOICE_PROVIDER}'")
    if choice == "elevenlabs" and not settings.ELEVENLABS_API_KEY:
        raise RuntimeError("VOICE_PROVIDER=elevenlabs but ELEVENLABS_API_KEY is empty")
    return VoiceService([_PROVIDERS[choice]()])
