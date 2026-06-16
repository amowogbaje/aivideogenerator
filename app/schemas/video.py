from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum

class AspectRatioEnum(str, Enum):
    HORIZONTAL = "16:9"
    VERTICAL = "9:16"

class VideoCreateSchema(BaseModel):
    prompt: Optional[str] = Field(None, description="Core idea for AI to expand from scratch")
    story_text: Optional[str] = Field(None, description="Pre-written entire script/manuscript text")
    aspect_ratio: AspectRatioEnum = AspectRatioEnum.VERTICAL
    audio_url: Optional[str] = Field(None, description="Provide an existing audio/voiceover file URL.")
    voice_id: str = "pNInz6obpgmqHCgfkJZx"
    art_style: str = "Cinematic realism"
    target_duration_seconds: int = 60

class ProjectResponseSchema(BaseModel):
    project_id: UUID
    status: str
    message: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True