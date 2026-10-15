from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_series_or_404
from app.api.serializers import asset_out, episode_out, series_out
from app.database import get_db
from app.models import Asset, Episode, Series
from app.pipeline import orchestrator, runner
from app.schemas import AssetCreate, EpisodeCreate, SeriesCreate, SeriesUpdate
from app.services import storage, voices

router = APIRouter(prefix="/series", tags=["Series"])


async def _counts(db, series_id: int) -> dict:
    rows = (await db.execute(select(Asset.status, func.count()).where(Asset.series_id == series_id).group_by(Asset.status))).all()
    d = {"total": 0, "approved": 0, "pending_review": 0}
    for status, n in rows:
        d[status] = n
        d["total"] += n
    return d


@router.get("")
async def list_series(db=Depends(get_db)):
    out = []
    for s in (await db.execute(select(Series).order_by(Series.created_at.desc()))).scalars():
        n = (await db.execute(select(func.count()).select_from(Episode).where(Episode.series_id == s.id))).scalar_one()
        out.append(series_out(s, episode_count=n, asset_counts=await _counts(db, s.id)))
    return out


@router.post("", status_code=201)
async def create_series(body: SeriesCreate, db=Depends(get_db)):
    if body.narrator_voice not in voices.BY_ID:
        raise HTTPException(422, f"Unknown narrator_voice '{body.narrator_voice}'")
    s = Series(**body.model_dump())
    db.add(s)
    await db.commit()
    return series_out(s, episode_count=0, asset_counts=await _counts(db, s.id))


@router.get("/{series_id}")
async def get_series(series_id: int, db=Depends(get_db)):
    s = await get_series_or_404(db, series_id)
    n = (await db.execute(select(func.count()).select_from(Episode).where(Episode.series_id == s.id))).scalar_one()
    return series_out(s, episode_count=n, asset_counts=await _counts(db, s.id))


@router.patch("/{series_id}")
async def update_series(series_id: int, body: SeriesUpdate, db=Depends(get_db)):
    s = await get_series_or_404(db, series_id)
    data = body.model_dump(exclude_unset=True)
    if "narrator_voice" in data and data["narrator_voice"] not in voices.BY_ID:
        raise HTTPException(422, "Unknown narrator_voice")
    if "aspect_ratio" in data and data["aspect_ratio"] != s.aspect_ratio:
        # Existing scene images were composed for the old frame; changing it mid-series would mix formats.
        has_scenes = (await db.execute(select(func.count()).select_from(Episode).where(
            Episode.series_id == s.id, Episode.status != "draft", Episode.status != "review", Episode.status != "analyzing"))).scalar_one()
        if has_scenes:
            raise HTTPException(409, "Aspect ratio can't change once episodes have been produced.")
    for k, v in data.items():
        setattr(s, k, v)
    await db.commit()
    return series_out(s)


@router.delete("/{series_id}", status_code=204)
async def delete_series(series_id: int, db=Depends(get_db)):
    s = await get_series_or_404(db, series_id)
    await db.delete(s)
    await db.commit()
    orchestrator.delete_series_files(series_id)


# ── episodes ──
@router.get("/{series_id}/episodes")
async def list_episodes(series_id: int, db=Depends(get_db)):
    await get_series_or_404(db, series_id)
    ids = (await db.execute(select(Episode.id).where(Episode.series_id == series_id).order_by(Episode.number))).scalars().all()
    out = []
    for i in ids:
        out.append(episode_out(await orchestrator.load_episode(db, i)))
    return out


@router.post("/{series_id}/episodes", status_code=201)
async def create_episode(series_id: int, body: EpisodeCreate, db=Depends(get_db)):
    await get_series_or_404(db, series_id)
    nxt = ((await db.execute(select(func.max(Episode.number)).where(Episode.series_id == series_id))).scalar() or 0) + 1
    ep = Episode(series_id=series_id, number=nxt, title=body.title, script=body.script.strip())
    db.add(ep)
    try:
        await db.commit()
    except IntegrityError:  # two requests raced for the same number
        await db.rollback()
        raise HTTPException(409, "Episode number collision — please retry")
    if body.auto_analyze:
        runner.spawn(f"analyze-{ep.id}", orchestrator.analyze_episode, ep.id)
    return episode_out(await orchestrator.load_episode(db, ep.id), full=True)


# ── assets (the series "story bible") ──
@router.get("/{series_id}/assets")
async def list_assets(series_id: int, kind: str | None = None, db=Depends(get_db)):
    await get_series_or_404(db, series_id)
    q = select(Asset).where(Asset.series_id == series_id).order_by(Asset.kind, Asset.name)
    if kind:
        q = q.where(Asset.kind == kind)
    return [asset_out(a) for a in (await db.execute(q)).scalars()]


@router.post("/{series_id}/assets", status_code=201)
async def create_asset(series_id: int, body: AssetCreate, db=Depends(get_db)):
    """Add something the analysis missed (a character, a place, a prop) and optionally attach it to an episode."""
    await get_series_or_404(db, series_id)
    slug = storage.slugify(body.name)
    if (await db.execute(select(Asset.id).where(Asset.series_id == series_id, Asset.kind == body.kind, Asset.slug == slug))).first():
        raise HTTPException(409, f"A {body.kind} named '{body.name}' already exists in this series")
    voice = body.voice_id if body.kind == "character" else None
    if voice and voice not in voices.BY_ID:
        raise HTTPException(422, "Unknown voice_id")
    a = Asset(series_id=series_id, kind=body.kind, name=body.name.strip(), slug=slug, description=body.description.strip(),
              voice_id=voice or (voices.suggest(None, None) if body.kind == "character" else None))
    db.add(a)
    await db.flush()
    if body.episode_id:
        ep = await orchestrator.load_episode(db, body.episode_id)
        if not ep or ep.series_id != series_id:
            raise HTTPException(404, "Episode not found in this series")
        if ep.scenes:
            raise HTTPException(409, "This episode already has scenes; reset it before adding assets.")
        ep.assets.append(a)
    await db.commit()
    runner.spawn(f"asset-image-{a.id}", orchestrator.generate_asset_image, a.id)
    return asset_out(a)
