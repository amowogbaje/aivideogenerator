"""
Data model.

    Series ──< Episode ──< Scene
       │          │
       └──< Asset >──(episode_assets)

An Asset is a character, environment or prop. Assets belong to the SERIES (so
a character looks and sounds the same in every episode) and are linked to each
episode they appear in. Nothing is turned into scene images until every asset
the episode uses has been approved by a human — that gate is the core of the
workflow (see pipeline/orchestrator.py).
"""
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# ── status vocabularies ───────────────────────────────────────────────
ASSET_KINDS = ("character", "environment", "prop")

ASSET_PENDING = "pending_review"
ASSET_APPROVED = "approved"

IMG_NONE = "none"
IMG_GENERATING = "generating"
IMG_READY = "ready"
IMG_FAILED = "failed"

EP_DRAFT = "draft"              # script saved, nothing run yet
EP_ANALYZING = "analyzing"      # extracting characters / environments / props
EP_REVIEW = "review"            # waiting for the human to approve the assets
EP_PLANNING = "planning"        # splitting the script into scenes
EP_IMAGING = "imaging"          # generating scene images
EP_SCENES_READY = "scenes_ready"  # images done — fix any with a correction prompt, then render
EP_RENDERING = "rendering"      # voice + captions + video
EP_COMPLETED = "completed"
EP_FAILED = "failed"

BUSY_STATES = (EP_ANALYZING, EP_PLANNING, EP_IMAGING, EP_RENDERING)

episode_assets = Table(
    "episode_assets",
    Base.metadata,
    Column("episode_id", ForeignKey("episodes.id", ondelete="CASCADE"), primary_key=True),
    Column("asset_id", ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
)


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    premise: Mapped[str] = mapped_column(Text, default="")
    art_style: Mapped[str] = mapped_column(String(300), default="Cinematic digital illustration, rich lighting")
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="9:16")
    narrator_voice: Mapped[str] = mapped_column(String(50), default="narrator_male")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    episodes = relationship("Episode", back_populates="series", cascade="all, delete-orphan",
                            order_by="Episode.number")
    assets = relationship("Asset", back_populates="series", cascade="all, delete-orphan")


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (UniqueConstraint("series_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    script: Mapped[str] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(20), default=EP_DRAFT)
    failed_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    video_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    series = relationship("Series", back_populates="episodes")
    scenes = relationship("Scene", back_populates="episode", cascade="all, delete-orphan",
                          order_by="Scene.number")
    assets = relationship("Asset", secondary=episode_assets, back_populates="episodes")


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("series_id", "kind", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120))  # lower-cased name, used to match across episodes
    description: Mapped[str] = mapped_column(Text, default="")  # the VISUAL description fed to the image model

    # characters only
    voice_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=ASSET_PENDING)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_status: Mapped[str] = mapped_column(String(12), default=IMG_NONE)
    image_attempts: Mapped[int] = mapped_column(Integer, default=0)
    # What the user said was wrong with the last image. Applied to the next render only, then cleared.
    correction_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    series = relationship("Series", back_populates="assets")
    episodes = relationship("Episode", secondary=episode_assets, back_populates="assets")


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("episode_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)

    narration_text: Mapped[str] = mapped_column(Text)
    speaker_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"), nullable=True)
    visual_prompt: Mapped[str] = mapped_column(Text, default="")
    environment_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"), nullable=True)
    character_ids: Mapped[list] = mapped_column(JSON, default=list)
    prop_ids: Mapped[list] = mapped_column(JSON, default=list)

    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_status: Mapped[str] = mapped_column(String(12), default=IMG_NONE)
    image_attempts: Mapped[int] = mapped_column(Integer, default=0)
    correction_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_duration: Mapped[float | None] = mapped_column(nullable=True)
    clip_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    episode = relationship("Episode", back_populates="scenes")
