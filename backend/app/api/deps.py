from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import BUSY_STATES, Asset, Episode, Scene, Series, episode_assets
from app.pipeline.orchestrator import load_episode


async def get_series_or_404(db, series_id: int) -> Series:
    s = await db.get(Series, series_id)
    if not s:
        raise HTTPException(404, "Series not found")
    return s


async def get_episode_or_404(db, episode_id: int) -> Episode:
    ep = await load_episode(db, episode_id)
    if not ep:
        raise HTTPException(404, "Episode not found")
    return ep


async def get_asset_or_404(db, asset_id: int) -> Asset:
    a = await db.get(Asset, asset_id)
    if not a:
        raise HTTPException(404, "Asset not found")
    return a


async def get_scene_or_404(db, scene_id: int) -> Scene:
    s = await db.get(Scene, scene_id)
    if not s:
        raise HTTPException(404, "Scene not found")
    return s


async def ensure_asset_not_in_use(db, asset: Asset) -> None:
    """Blocks edits to an asset while an episode that uses it is mid-pipeline."""
    busy = (await db.execute(
        select(Episode.id).join(episode_assets, episode_assets.c.episode_id == Episode.id)
        .where(episode_assets.c.asset_id == asset.id, Episode.status.in_(BUSY_STATES)))).first()
    if busy:
        raise HTTPException(409, "An episode using this asset is being processed right now — try again in a moment.")
