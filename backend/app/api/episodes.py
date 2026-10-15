from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import get_episode_or_404
from app.api.serializers import asset_out, episode_actions, episode_out
from app.database import get_db
from app.models import (ASSET_APPROVED, BUSY_STATES, EP_ANALYZING, EP_DRAFT, EP_IMAGING, EP_PLANNING, EP_RENDERING,
                        EP_REVIEW, IMG_READY, Asset, Episode)
from app.pipeline import orchestrator, runner
from app.schemas import EpisodeUpdate
from app.services import storage

router = APIRouter(prefix="/episodes", tags=["Episodes"])


def _require(ep: Episode, action: str) -> None:
    if not episode_actions(ep)[action]:
        raise HTTPException(409, f"'{action}' isn't available while the episode is '{ep.status}'.")


@router.get("/{episode_id}")
async def get_episode(episode_id: int, db=Depends(get_db)):
    return episode_out(await get_episode_or_404(db, episode_id), full=True)


@router.patch("/{episode_id}")
async def update_episode(episode_id: int, body: EpisodeUpdate, db=Depends(get_db)):
    ep = await get_episode_or_404(db, episode_id)
    data = body.model_dump(exclude_unset=True)
    if "script" in data and data["script"] != ep.script:
        _require(ep, "edit_script")
    for k, v in data.items():
        setattr(ep, k, v.strip() if isinstance(v, str) else v)
    await db.commit()
    return episode_out(await get_episode_or_404(db, episode_id), full=True)


@router.delete("/{episode_id}", status_code=204)
async def delete_episode(episode_id: int, db=Depends(get_db)):
    ep = await get_episode_or_404(db, episode_id)
    if ep.status in BUSY_STATES:
        raise HTTPException(409, "Wait for the current step to finish.")
    sid = ep.series_id
    await db.delete(ep)
    await db.commit()
    orchestrator.delete_episode_files(sid, episode_id)


@router.post("/{episode_id}/analyze", status_code=202)
async def analyze(episode_id: int, db=Depends(get_db)):
    """(Re)reads the script and extracts characters / environments / props for human review."""
    ep = await get_episode_or_404(db, episode_id)
    _require(ep, "analyze")
    ep.status, ep.error, ep.failed_stage = EP_ANALYZING, None, None   # flip now so the UI reacts immediately
    await db.commit()
    runner.spawn(f"analyze-{episode_id}", orchestrator.analyze_episode, episode_id)
    return episode_out(await get_episode_or_404(db, episode_id))


@router.post("/{episode_id}/assets/approve-all")
async def approve_all(episode_id: int, db=Depends(get_db)):
    ep = await get_episode_or_404(db, episode_id)
    if ep.status in BUSY_STATES:
        raise HTTPException(409, "Wait for the current step to finish.")
    from datetime import datetime
    skipped = []
    for a in ep.assets:
        if a.status == ASSET_APPROVED:
            continue
        if a.image_status != IMG_READY or not a.image_path:
            skipped.append(a.name)  # you can't approve something you haven't seen
            continue
        a.status, a.approved_at = ASSET_APPROVED, datetime.utcnow()
    await db.commit()
    ep = await get_episode_or_404(db, episode_id)
    return {"episode": episode_out(ep), "skipped_without_image": skipped}


@router.post("/{episode_id}/produce", status_code=202)
async def produce(episode_id: int, db=Depends(get_db)):
    """THE GATE: refuses until every character, environment and prop in this episode has been approved."""
    ep = await get_episode_or_404(db, episode_id)
    unapproved = [a for a in ep.assets if a.status != ASSET_APPROVED]
    if unapproved:
        raise HTTPException(409, {
            "message": "Approve every character, environment and prop before scene images are generated.",
            "unapproved": [{"id": a.id, "kind": a.kind, "name": a.name} for a in unapproved]})
    _require(ep, "produce")
    ep.status, ep.error, ep.failed_stage, ep.progress_note = EP_PLANNING, None, None, "Planning scenes…"
    await db.commit()
    runner.spawn(f"produce-{episode_id}", orchestrator.produce_episode, episode_id)
    return episode_out(await get_episode_or_404(db, episode_id))


@router.post("/{episode_id}/render", status_code=202)
async def render(episode_id: int, db=Depends(get_db)):
    ep = await get_episode_or_404(db, episode_id)
    _require(ep, "render")
    ep.status, ep.error, ep.failed_stage, ep.progress_note = EP_RENDERING, None, None, "Starting render…"
    await db.commit()
    runner.spawn(f"render-{episode_id}", orchestrator.render_episode, episode_id)
    return episode_out(await get_episode_or_404(db, episode_id))


@router.post("/{episode_id}/retry", status_code=202)
async def retry(episode_id: int, db=Depends(get_db)):
    """Resumes a failed run from the stage that failed. Finished work (images, voices, clips) is kept."""
    ep = await get_episode_or_404(db, episode_id)
    _require(ep, "retry")
    stage = ep.failed_stage
    ep.error = None
    if stage == EP_ANALYZING:
        ep.status = EP_ANALYZING
        job, fn = f"analyze-{episode_id}", orchestrator.analyze_episode
    elif stage in (EP_PLANNING, EP_IMAGING):
        ep.status = EP_PLANNING if stage == EP_PLANNING else EP_IMAGING
        job, fn = f"produce-{episode_id}", orchestrator.produce_episode
    elif stage == EP_RENDERING:
        ep.status = EP_RENDERING
        job, fn = f"render-{episode_id}", orchestrator.render_episode
    else:
        raise HTTPException(409, "Nothing to retry")
    ep.failed_stage = None
    await db.commit()
    runner.spawn(job, fn, episode_id)
    return episode_out(await get_episode_or_404(db, episode_id))


@router.post("/{episode_id}/reset")
async def reset(episode_id: int, db=Depends(get_db)):
    """Discards scenes, audio and video (assets and their approvals are kept) so the script can be edited or re-planned."""
    ep = await get_episode_or_404(db, episode_id)
    _require(ep, "reset")
    analysed = ep.failed_stage != EP_ANALYZING and (ep.status != "failed" or bool(ep.assets))
    for s in list(ep.scenes):
        for rel in (s.image_path, s.audio_path, s.clip_path):
            storage.delete(rel)
    ep.scenes.clear()
    storage.delete(ep.video_path)
    ep.video_path = ep.duration_seconds = None
    ep.status = EP_REVIEW if analysed else EP_DRAFT
    ep.error = ep.failed_stage = ep.progress_note = None
    await db.commit()
    return episode_out(await get_episode_or_404(db, episode_id), full=True)
