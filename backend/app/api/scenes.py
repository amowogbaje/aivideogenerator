from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_episode_or_404, get_scene_or_404
from app.api.serializers import scene_out
from app.database import get_db
from app.models import BUSY_STATES, EP_COMPLETED, EP_SCENES_READY, IMG_GENERATING, Asset, Episode
from app.pipeline import orchestrator, runner
from app.schemas import Correction, ScenePatch
from app.services import storage

router = APIRouter(prefix="/scenes", tags=["Scenes"])


async def _out(db, scene):
    ep = await get_episode_or_404(db, scene.episode_id)
    return scene_out(await db.get(type(scene), scene.id), {a.id: a for a in ep.assets})


@router.patch("/{scene_id}")
async def patch_scene(scene_id: int, body: ScenePatch, db=Depends(get_db)):
    """Edit what a scene says / who says it. Voice, clip and final video are invalidated and rebuilt on the next render."""
    scene = await get_scene_or_404(db, scene_id)
    ep = await get_episode_or_404(db, scene.episode_id)
    if ep.status in BUSY_STATES:
        raise HTTPException(409, "Wait for the current step to finish.")
    sent = body.model_fields_set
    if "speaker_asset_id" in sent and body.speaker_asset_id is not None:
        speaker = next((a for a in ep.assets if a.id == body.speaker_asset_id and a.kind == "character"), None)
        if not speaker:
            raise HTTPException(422, "speaker_asset_id must be a character in this episode")
    if "narration_text" in sent:
        scene.narration_text = body.narration_text.strip()
    if "visual_prompt" in sent:
        scene.visual_prompt = (body.visual_prompt or "").strip()
    if "speaker_asset_id" in sent:
        scene.speaker_asset_id = body.speaker_asset_id
    if sent & {"narration_text", "speaker_asset_id"}:
        storage.delete(scene.audio_path)
        scene.audio_path = scene.audio_duration = None
    if sent & {"narration_text", "speaker_asset_id"}:
        storage.delete(scene.clip_path)
        scene.clip_path = None
        if ep.status == EP_COMPLETED:
            storage.delete(ep.video_path)
            ep.video_path = ep.duration_seconds = None
            ep.status = EP_SCENES_READY
    await db.commit()
    return await _out(db, scene)


@router.post("/{scene_id}/regenerate-image", status_code=202)
async def regenerate_scene_image(scene_id: int, body: Correction | None = None, db=Depends(get_db)):
    """The correction prompt: discard this scene's image and generate a new one, telling the model what was wrong."""
    scene = await get_scene_or_404(db, scene_id)
    ep = await get_episode_or_404(db, scene.episode_id)
    if ep.status in BUSY_STATES:
        raise HTTPException(409, "Wait for the current step to finish.")
    if scene.image_status == IMG_GENERATING:
        raise HTTPException(409, "Already generating")
    await orchestrator.queue_scene_regeneration(db, ep, scene, body.correction if body else None)
    runner.spawn(f"scene-image-{scene.id}", orchestrator.generate_scene_image, scene.id)
    return await _out(db, scene)
