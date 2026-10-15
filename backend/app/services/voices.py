"""
Voice PROFILES.

A character stores a profile id ("hero_male", "elder_female"...), never a provider-specific voice string. Each profile
maps to a concrete voice for every voice provider, so you can switch VOICE_PROVIDER (e.g. from free Edge TTS to
ElevenLabs) without every saved character losing its voice.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceProfile:
    id: str
    label: str
    gender: str          # male | female
    age: str             # child | young | adult | elder
    edge: str            # Microsoft Edge neural voice
    eleven: str          # ElevenLabs premade voice id
    espeak: str          # espeak-ng voice+variant (offline, robotic — for testing / no-internet use)
    espeak_pitch: int    # 0-99
    tone_hz: int         # last-resort placeholder "voice" (a pitched hum) so the pipeline still runs with nothing installed


VOICES: list[VoiceProfile] = [
    VoiceProfile("narrator_male",  "Narrator — warm male",   "male",   "adult", "en-US-ChristopherNeural", "pNInz6obpgmqHCgfkJZx", "en-us+m3", 40, 150),
    VoiceProfile("narrator_female", "Narrator — calm female", "female", "adult", "en-US-JennyNeural",       "21m00Tcm4TlvDq8ikWAM", "en-us+f3", 55, 260),
    VoiceProfile("hero_male",      "Young man — confident",  "male",   "young", "en-US-GuyNeural",         "TxGEqnHWrfWFTfGW9XjX", "en-us+m1", 50, 180),
    VoiceProfile("hero_female",    "Young woman — bright",   "female", "young", "en-US-AriaNeural",        "EXAVITQu4vr4xnSDxMaL", "en-us+f2", 60, 300),
    VoiceProfile("deep_male",      "Man — deep & serious",   "male",   "adult", "en-GB-RyanNeural",        "ErXwobaYiN019PkySvjV", "en-gb+m2", 25, 120),
    VoiceProfile("british_female", "Woman — British",        "female", "adult", "en-GB-SoniaNeural",       "MF3mGyEYCl7XYWbV9V6O", "en-gb+f4", 50, 280),
    VoiceProfile("elder_male",     "Elder man — gravelly",   "male",   "elder", "en-AU-WilliamNeural",     "pNInz6obpgmqHCgfkJZx", "en-gb+m4", 15, 100),
    VoiceProfile("elder_female",   "Elder woman — gentle",   "female", "elder", "en-AU-NatashaNeural",     "21m00Tcm4TlvDq8ikWAM", "en-us+f5", 35, 230),
    VoiceProfile("nigerian_male",  "Nigerian English — male", "male",  "adult", "en-NG-AbeoNeural",        "pNInz6obpgmqHCgfkJZx", "en-us+m5", 45, 165),
    VoiceProfile("nigerian_female", "Nigerian English — female", "female", "adult", "en-NG-EzinneNeural",  "21m00Tcm4TlvDq8ikWAM", "en-us+f1", 55, 270),
    VoiceProfile("child",          "Child — playful",        "female", "child", "en-US-AnaNeural",         "MF3mGyEYCl7XYWbV9V6O", "en-us+f2", 85, 340),
    VoiceProfile("neutral_robot",  "Robot / AI",             "male",   "adult", "en-US-EricNeural",        "ErXwobaYiN019PkySvjV", "en-us+croak", 30, 200),
]

BY_ID = {v.id: v for v in VOICES}
DEFAULT_NARRATOR = "narrator_male"


def get(voice_id: str | None) -> VoiceProfile:
    return BY_ID.get(voice_id or "", BY_ID[DEFAULT_NARRATOR])


def suggest(gender: str | None, age: str | None) -> str:
    """Picks a sensible starting profile for a character; the human can change it during review."""
    g = (gender or "").lower()
    a = (age or "").lower()
    if a == "child":
        return "child"
    if a == "elder":
        return "elder_female" if g == "female" else "elder_male"
    if g == "female":
        return "hero_female" if a == "young" else "british_female"
    if g == "male":
        return "hero_male" if a == "young" else "deep_male"
    return "narrator_female"
