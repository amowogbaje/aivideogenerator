from typing import Literal

from pydantic import BaseModel, Field

Aspect = Literal["9:16", "16:9"]
Kind = Literal["character", "environment", "prop"]


class SeriesCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    premise: str = ""
    art_style: str = "Cinematic digital illustration, rich lighting"
    aspect_ratio: Aspect = "9:16"
    narrator_voice: str = "narrator_male"


class SeriesUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    premise: str | None = None
    art_style: str | None = None
    aspect_ratio: Aspect | None = None
    narrator_voice: str | None = None


class EpisodeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    script: str = Field(min_length=10)
    auto_analyze: bool = True


class EpisodeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    script: str | None = Field(default=None, min_length=10)


class AssetCreate(BaseModel):
    kind: Kind
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    voice_id: str | None = None
    episode_id: int | None = None  # also link it to this episode


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    voice_id: str | None = None


class Correction(BaseModel):
    """`correction` = what is wrong with the current image. Optional: empty means a plain regenerate."""
    correction: str | None = Field(default=None, max_length=1000)


class ScenePatch(BaseModel):
    narration_text: str | None = Field(default=None, min_length=1)
    visual_prompt: str | None = None
    speaker_asset_id: int | None = None  # null = narrator (only applied when the key is present in the request)


class VoicePreview(BaseModel):
    voice_id: str
    text: str = "Hello. This is how I will sound in the story."
