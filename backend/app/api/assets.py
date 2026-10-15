from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import ensure_asset_not_in_use, get_asset_or_404
from app.api.serializers import asset_out
from app.database import get_db
from app.models import ASSET_APPROVED, ASSET_PENDING, IMG_GENERATING, IMG_READY, Episode, Scene, episode_assets
from app.pipeline import orchestrator, runner
from app.schemas import AssetUpdate, Correction
from app.services import storage, voices

router = APIRouter(prefix="/assets", tags=["Assets"])


@router.patch("/{asset_id}")
async def update_asset(asset_id: int, body: AssetUpdate, db=Depends(get_db)):
    a = await get_asset_or_404(db, asset_id)
    await ensure_asset_not_in_use(db, a)
    data = body.model_dump(exclude_unset=True)
    if "voice_id" in data and data["voice_id"] is not None and data["voice_id"] not in voices.BY_ID:
        raise HTTPException(422, "Unknown voice_id")
    if "name" in data:
        slug = storage.slugify(data["name"])
        clash = (await db.execute(select(type(a).id).where(type(a).series_id == a.series_id, type(a).kind == a.kind,
                                                            type(a).slug == slug, type(a).id != a.id))).first()
        if clash:
            raise HTTPException(409, "Another asset with that name already exists")
        a.name, a.slug = data["name"].strip(), slug
    if "description" in data:
        a.description = data["description"].strip()
    if "voice_id" in data and a.kind == "character":
        a.voice_id = data["voice_id"]
    # Any change to what the asset IS invalidates the earlier approval.
    a.status, a.approved_at = ASSET_PENDING, None
    await db.commit()
    return asset_out(a)


@router.post("/{asset_id}/regenerate-image", status_code=202)
async def regenerate_image(asset_id: int, body: Correction | None = None, db=Depends(get_db)):
    """Generates a new reference image. `correction` says what was wrong with the current one (applied to this render only)."""
    a = await get_asset_or_404(db, asset_id)
    await ensure_asset_not_in_use(db, a)
    if a.image_status == IMG_GENERATING:
        raise HTTPException(409, "Already generating")
    orchestrator.queue_asset_regeneration(a, body.correction if body else None)
    await db.commit()
    runner.spawn(f"asset-image-{a.id}", orchestrator.generate_asset_image, a.id)
    return asset_out(a)


@router.post("/{asset_id}/approve")
async def approve(asset_id: int, db=Depends(get_db)):
    a = await get_asset_or_404(db, asset_id)
    if a.image_status != IMG_READY or not a.image_path:
        raise HTTPException(409, "There's no reference image to approve yet.")
    a.status, a.approved_at = ASSET_APPROVED, datetime.utcnow()
    await db.commit()
    return asset_out(a)


@router.post("/{asset_id}/unapprove")
async def unapprove(asset_id: int, db=Depends(get_db)):
    a = await get_asset_or_404(db, asset_id)
    await ensure_asset_not_in_use(db, a)
    a.status, a.approved_at = ASSET_PENDING, None
    await db.commit()
    return asset_out(a)


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(asset_id: int, db=Depends(get_db)):
    a = await get_asset_or_404(db, asset_id)
    await ensure_asset_not_in_use(db, a)
    used = (await db.execute(
        select(Scene.id).join(Episode, Episode.id == Scene.episode_id).join(episode_assets, episode_assets.c.episode_id == Episode.id)
        .where(episode_assets.c.asset_id == a.id).limit(1))).first()
    if used:
        raise HTTPException(409, "This asset belongs to an episode that already has scenes. Reset that episode first.")
    path = a.image_path
    await db.delete(a)
    await db.commit()
    storage.delete(path)
