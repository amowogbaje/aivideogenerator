from app.models import (ASSET_APPROVED, BUSY_STATES, EP_COMPLETED, EP_DRAFT, EP_FAILED, EP_IMAGING, EP_PLANNING,
                        EP_REVIEW, EP_SCENES_READY, IMG_GENERATING, Asset, Episode, Scene, Series)
from app.services import storage


def series_out(s: Series, *, episode_count: int | None = None, asset_counts: dict | None = None) -> dict:
    return {
        "id": s.id, "title": s.title, "premise": s.premise, "art_style": s.art_style, "aspect_ratio": s.aspect_ratio,
        "narrator_voice": s.narrator_voice, "created_at": s.created_at.isoformat(),
        **({"episode_count": episode_count} if episode_count is not None else {}),
        **({"asset_counts": asset_counts} if asset_counts is not None else {}),
    }


def asset_out(a: Asset) -> dict:
    return {
        "id": a.id, "series_id": a.series_id, "kind": a.kind, "name": a.name, "description": a.description,
        "voice_id": a.voice_id, "status": a.status, "approved": a.status == ASSET_APPROVED,
        "image_url": storage.url(a.image_path), "image_status": a.image_status, "last_error": a.last_error,
        "correction_pending": bool(a.correction_prompt),
    }


def scene_out(s: Scene, assets: dict[int, Asset]) -> dict:
    ref = lambda i: {"id": i, "name": assets[i].name} if i in assets else None  # noqa: E731
    return {
        "id": s.id, "episode_id": s.episode_id, "number": s.number, "narration_text": s.narration_text,
        "visual_prompt": s.visual_prompt, "speaker": ref(s.speaker_asset_id), "environment": ref(s.environment_asset_id),
        "characters": [r for r in map(ref, s.character_ids or []) if r], "props": [r for r in map(ref, s.prop_ids or []) if r],
        "image_url": storage.url(s.image_path), "image_status": s.image_status, "last_error": s.last_error,
        "correction_pending": bool(s.correction_prompt), "audio_duration": s.audio_duration,
        "has_audio": bool(s.audio_path), "has_clip": bool(s.clip_path),
    }


def episode_actions(ep: Episode) -> dict:
    """What the UI may offer right now. The API enforces the same rules; this just saves the client from guessing."""
    busy = ep.status in BUSY_STATES
    unapproved = [a for a in ep.assets if a.status != ASSET_APPROVED]
    scenes_ok = bool(ep.scenes) and all(s.image_path and s.image_status != IMG_GENERATING for s in ep.scenes)
    return {
        "edit_script": not busy and not ep.scenes,
        "analyze": not busy and not ep.scenes and ep.status in (EP_DRAFT, EP_REVIEW, EP_FAILED),
        "produce": ep.status == EP_REVIEW and not unapproved and not ep.scenes,
        "render": ep.status == EP_SCENES_READY and scenes_ok,
        "retry": ep.status == EP_FAILED,
        "reset": not busy and (bool(ep.scenes) or ep.status == EP_FAILED),
        "edit_scenes": not busy and bool(ep.scenes),
    }


def episode_out(ep: Episode, *, full: bool = False) -> dict:
    unapproved = [a.name for a in ep.assets if a.status != ASSET_APPROVED]
    out = {
        "id": ep.id, "series_id": ep.series_id, "aspect_ratio": ep.series.aspect_ratio, "number": ep.number, "title": ep.title, "status": ep.status,
        "failed_stage": ep.failed_stage, "error": ep.error, "progress_note": ep.progress_note,
        "video_url": storage.url(ep.video_path), "duration_seconds": ep.duration_seconds,
        "asset_total": len(ep.assets), "asset_approved": len(ep.assets) - len(unapproved), "blocking_assets": unapproved,
        "scene_count": len(ep.scenes), "actions": episode_actions(ep),
        "created_at": ep.created_at.isoformat(), "updated_at": ep.updated_at.isoformat(),
    }
    if full:
        by_id = {a.id: a for a in ep.assets}
        out["script"] = ep.script
        out["assets"] = [asset_out(a) for a in sorted(ep.assets, key=lambda a: (a.kind, a.name))]
        out["scenes"] = [scene_out(s, by_id) for s in ep.scenes]
    return out
