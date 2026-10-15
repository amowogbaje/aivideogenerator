"""
The production pipeline for one episode.

    draft ──analyze──▶ review ──(human approves every asset)──▶ produce ──▶ scenes_ready ──render──▶ completed
                         ▲                                        │              │
                         │                                   planning→imaging    └─ fix any scene image with a
                    characters, environments, props                                 correction prompt, re-render
                    get reference images + voices

Every stage is IDEMPOTENT and driven by DB state (it only does the work that is still missing), so a failed or
interrupted run is resumed by simply running the stage again. This mirrors CraftProfessor's "awaiting image / awaiting
video" queues.
"""
import asyncio
import logging
import math
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import SessionLocal
from app.models import (ASSET_APPROVED, ASSET_PENDING, BUSY_STATES, EP_ANALYZING, EP_COMPLETED, EP_DRAFT, EP_FAILED,
                        EP_IMAGING, EP_PLANNING, EP_RENDERING, EP_REVIEW, EP_SCENES_READY, IMG_FAILED, IMG_GENERATING,
                        IMG_NONE, IMG_READY, Asset, Episode, Scene, Series)
from app.pipeline import runner
from app.pipeline.prompts import ASSET_ASPECT, apply_correction, asset_prompt, clean_correction, scene_prompt
from app.services import storage, voices
from app.services.ffmpeg_util import probe_duration
from app.services.providers.image import finalize, get_image_provider
from app.services.providers.text import NARRATOR, AssetInfo, Context, get_text_provider
from app.services.providers.voice import get_voice_service
from app.services.video import build_scene_clip, concat_clips

logger = logging.getLogger("app.pipeline")


# ───────────────────────── helpers ─────────────────────────
async def load_episode(db, episode_id: int) -> Episode | None:
    q = (select(Episode).where(Episode.id == episode_id)
         .options(selectinload(Episode.series), selectinload(Episode.assets), selectinload(Episode.scenes)))
    return (await db.execute(q)).scalar_one_or_none()


def unapproved_assets(ep: Episode) -> list[Asset]:
    return [a for a in ep.assets if a.status != ASSET_APPROVED]


async def _fail(db, ep: Episode, stage: str, exc: Exception) -> None:
    logger.exception("episode %s failed during %s", ep.id, stage)
    ep.status, ep.failed_stage, ep.progress_note = EP_FAILED, stage, None
    ep.error = f"{type(exc).__name__}: {exc}"[:2000]
    await db.commit()


async def _generate_image(provider, prompt: str, aspect: str, refs: list[bytes]) -> bytes:
    """Provider call + a couple of outer retries (providers already retry transient HTTP errors themselves; this also
    covers one-off refusals/glitches). Returns a finalized JPEG."""
    last: Exception | None = None
    async with runner.image_semaphore(settings.IMAGE_CONCURRENCY):
        for attempt in range(1, settings.MAX_ATTEMPTS + 1):
            try:
                return finalize(await provider.generate(prompt, aspect, refs), aspect)
            except Exception as e:  # noqa: BLE001
                last = e
                logger.warning("image attempt %s/%s failed: %s", attempt, settings.MAX_ATTEMPTS, e)
                if attempt < settings.MAX_ATTEMPTS:
                    await asyncio.sleep(2 * attempt)
    raise RuntimeError(f"Image generation failed after {settings.MAX_ATTEMPTS} attempts: {last}")


# ───────────────────────── 1. analyze: build the story bible ─────────────────────────
async def analyze_episode(episode_id: int) -> None:
    to_illustrate: list[int] = []
    async with SessionLocal() as db:
        ep = await load_episode(db, episode_id)
        if not ep:
            return
        series = ep.series
        ep.status, ep.error, ep.failed_stage, ep.progress_note = EP_ANALYZING, None, None, "Reading the script…"
        await db.commit()
        try:
            known = (await db.execute(select(Asset).where(Asset.series_id == series.id))).scalars().all()
            info = lambda kind: [AssetInfo(a.name, a.description) for a in known if a.kind == kind]  # noqa: E731
            bible = await get_text_provider().extract_bible(Context(
                series.title, series.premise, series.art_style, ep.script,
                known_characters=info("character"), known_environments=info("environment"), known_props=info("prop")))

            by_key = {(a.kind, a.slug): a for a in known}
            linked: dict[int, Asset] = {}

            def upsert(kind: str, name: str, desc: str, voice: str | None = None) -> None:
                name = (name or "").strip()[:120]
                if not name:
                    return
                key = (kind, storage.slugify(name))
                asset = by_key.get(key)
                if asset is None:  # existing assets (possibly already approved in an earlier episode) are never overwritten
                    asset = Asset(series_id=series.id, kind=kind, name=name, slug=key[1], description=(desc or "").strip(),
                                  voice_id=voice if kind == "character" else None, status=ASSET_PENDING)
                    db.add(asset)
                    by_key[key] = asset
                linked[id(asset)] = asset

            for c in bible.characters:
                upsert("character", c.name, c.description, voices.suggest(c.gender, c.age))
            for e in bible.environments:
                upsert("environment", e.name, e.description)
            for p in bible.props:
                upsert("prop", p.name, p.description)

            await db.flush()
            ep.assets = list(linked.values())
            ep.status, ep.progress_note = EP_REVIEW, None
            await db.commit()
            to_illustrate = [a.id for a in linked.values() if not a.image_path and a.image_status != IMG_GENERATING]
        except Exception as e:  # noqa: BLE001
            await _fail(db, ep, EP_ANALYZING, e)
            return
    for aid in to_illustrate:
        runner.spawn(f"asset-image-{aid}", generate_asset_image, aid)


# ───────────────────────── 1b. reference image for a character / environment / prop ─────────────────────────
async def generate_asset_image(asset_id: int) -> None:
    async with SessionLocal() as db:
        asset = await db.get(Asset, asset_id)
        if not asset:
            return
        series = await db.get(Series, asset.series_id)
        asset.image_status, asset.last_error = IMG_GENERATING, None
        await db.commit()
        try:
            raw = await _generate_image(get_image_provider(), asset_prompt(series, asset), ASSET_ASPECT[asset.kind], [])
            rel, path = storage.new_path(f"series_{series.id}", "assets", ext="jpg")
            path.write_bytes(raw)
            old, asset.image_path = asset.image_path, rel
            storage.delete(old)
            asset.image_status, asset.image_attempts = IMG_READY, asset.image_attempts + 1
            asset.correction_prompt = None  # applied once; a later plain regenerate starts clean
            # A new look is a new thing to approve.
            asset.status, asset.approved_at = ASSET_PENDING, None
        except Exception as e:  # noqa: BLE001
            logger.exception("asset image %s failed", asset_id)
            asset.image_status, asset.last_error = IMG_FAILED, str(e)[:1000]
        await db.commit()


def queue_asset_regeneration(asset: Asset, correction: str | None) -> None:
    """Marks the asset as regenerating (the caller commits, then spawns generate_asset_image)."""
    asset.correction_prompt = clean_correction(correction)
    asset.image_status, asset.last_error = IMG_GENERATING, None
    asset.status, asset.approved_at = ASSET_PENDING, None


# ───────────────────────── 2. produce: plan scenes + scene images ─────────────────────────
async def produce_episode(episode_id: int, replan: bool = False) -> None:
    async with SessionLocal() as db:
        ep = await load_episode(db, episode_id)
        if not ep:
            return
        if unapproved_assets(ep):  # the API checks too; this is the backstop for retries / direct calls
            await _fail(db, ep, EP_PLANNING, RuntimeError("All characters, environments and props must be approved first"))
            return
        ep.status, ep.error, ep.failed_stage = EP_PLANNING, None, None
        ep.progress_note = "Planning scenes…"
        await db.commit()
        try:
            if replan or not ep.scenes:
                await _plan_scenes(db, ep)
            ep.status, ep.progress_note = EP_IMAGING, "Generating scene images…"
            await db.commit()
        except Exception as e:  # noqa: BLE001
            await _fail(db, ep, EP_PLANNING, e)
            return

    await _generate_missing_scene_images(episode_id)

    async with SessionLocal() as db:
        ep = await load_episode(db, episode_id)
        missing = [s for s in ep.scenes if not s.image_path]
        if missing:
            await _fail(db, ep, EP_IMAGING, RuntimeError(
                f"{len(missing)} of {len(ep.scenes)} scene images failed — fix or regenerate them, then press Retry"))
        else:
            ep.status, ep.progress_note = EP_SCENES_READY, None
            await db.commit()


async def _plan_scenes(db, ep: Episode) -> None:
    series = ep.series
    assets = list(ep.assets)
    of = lambda kind: [a for a in assets if a.kind == kind]  # noqa: E731
    ctx = Context(series.title, series.premise, series.art_style, ep.script,
                  known_characters=[AssetInfo(a.name, a.description) for a in of("character")],
                  known_environments=[AssetInfo(a.name, a.description) for a in of("environment")],
                  known_props=[AssetInfo(a.name, a.description) for a in of("prop")])
    max_scenes = max(2, min(40, math.ceil(len(ep.script.split()) / 22)))
    planned = [p for p in (await get_text_provider().plan_scenes(ctx, max_scenes))[:60] if (p.narration_text or "").strip()]
    if not planned:
        raise RuntimeError("The planner returned no scenes")

    by_slug = {k: {storage.slugify(a.name): a for a in of(k)} for k in ("character", "environment", "prop")}
    for old in list(ep.scenes):
        for rel in (old.image_path, old.audio_path, old.clip_path):
            storage.delete(rel)
    ep.scenes.clear()
    await db.flush()

    for i, p in enumerate(planned, start=1):
        speaker = None
        if storage.slugify(p.speaker or NARRATOR) != storage.slugify(NARRATOR):
            speaker = by_slug["character"].get(storage.slugify(p.speaker))
        env = by_slug["environment"].get(storage.slugify(p.environment or ""))
        chars = [by_slug["character"][s] for s in (storage.slugify(n) for n in p.characters) if s in by_slug["character"]]
        if speaker and speaker.id not in {c.id for c in chars}:
            chars.append(speaker)
        props = [by_slug["prop"][s] for s in (storage.slugify(n) for n in p.props) if s in by_slug["prop"]]
        db.add(Scene(episode_id=ep.id, number=i, narration_text=p.narration_text.strip(),
                     speaker_asset_id=speaker.id if speaker else None, visual_prompt=(p.visual_prompt or p.narration_text).strip(),
                     environment_asset_id=env.id if env else None, character_ids=list(dict.fromkeys(c.id for c in chars)),
                     prop_ids=list(dict.fromkeys(x.id for x in props))))
    await db.flush()


async def _generate_missing_scene_images(episode_id: int) -> None:
    async with SessionLocal() as db:
        ids = (await db.execute(select(Scene.id).where(Scene.episode_id == episode_id, Scene.image_path.is_(None))
                                .order_by(Scene.number))).scalars().all()
    await asyncio.gather(*(generate_scene_image(sid) for sid in ids))


async def generate_scene_image(scene_id: int) -> None:
    async with SessionLocal() as db:
        scene = await db.get(Scene, scene_id)
        if not scene:
            return
        ep = await db.get(Episode, scene.episode_id)
        series = await db.get(Series, ep.series_id)
        wanted = [*scene.character_ids, *scene.prop_ids, *([scene.environment_asset_id] if scene.environment_asset_id else [])]
        found = {a.id: a for a in (await db.execute(select(Asset).where(Asset.id.in_(wanted)))).scalars()} if wanted else {}
        env = found.get(scene.environment_asset_id)
        chars = [found[i] for i in scene.character_ids if i in found]
        props = [found[i] for i in scene.prop_ids if i in found]
        scene.image_status, scene.last_error = IMG_GENERATING, None
        await db.commit()

        # Approved reference art goes to providers that can use it (Gemini); the rest rely on the text descriptions.
        refs: list[bytes] = []
        for a in [*chars[:3], *([env] if env else [])]:
            if a.image_path and storage.abs_path(a.image_path).exists():
                refs.append(storage.abs_path(a.image_path).read_bytes())
        try:
            raw = await _generate_image(get_image_provider(), scene_prompt(series, scene, env, chars, props),
                                        series.aspect_ratio, refs)
            rel, path = storage.new_path(f"series_{series.id}", f"ep_{ep.id}", "scenes", ext="jpg")
            path.write_bytes(raw)
            storage.delete(scene.image_path)
            storage.delete(scene.clip_path)  # the clip was built from the old image
            scene.image_path, scene.clip_path = rel, None
            scene.image_status, scene.image_attempts = IMG_READY, scene.image_attempts + 1
            scene.correction_prompt = None
        except Exception as e:  # noqa: BLE001
            logger.exception("scene %s image failed", scene_id)
            scene.image_status, scene.last_error = IMG_FAILED, str(e)[:1000]
        await db.commit()


async def queue_scene_regeneration(db, ep: Episode, scene: Scene, correction: str | None) -> None:
    """Throws away the scene's image and queues a new one carrying the user's correction note. If the episode had
    already been rendered, it drops back to scenes_ready (the old video no longer matches)."""
    storage.delete(scene.image_path)
    storage.delete(scene.clip_path)
    scene.image_path, scene.clip_path = None, None
    scene.correction_prompt = clean_correction(correction)
    scene.image_status, scene.last_error = IMG_GENERATING, None
    if ep.status in (EP_COMPLETED, EP_FAILED):
        storage.delete(ep.video_path)
        ep.video_path, ep.duration_seconds = None, None
        ep.status, ep.error, ep.failed_stage = EP_SCENES_READY, None, None
    await db.commit()


# ───────────────────────── 3. render: voice + captions + video ─────────────────────────
async def render_episode(episode_id: int) -> None:
    async with SessionLocal() as db:
        ep = await load_episode(db, episode_id)
        if not ep:
            return
        series = ep.series
        scenes = list(ep.scenes)
        ep.status, ep.error, ep.failed_stage = EP_RENDERING, None, None
        await db.commit()
        try:
            if not scenes or any(not s.image_path for s in scenes):
                raise RuntimeError("Every scene needs an image before rendering")
            voice = get_voice_service()
            clips: list[Path] = []
            for i, sc in enumerate(scenes, start=1):
                ep.progress_note = f"Voicing and rendering scene {i}/{len(scenes)}…"
                await db.commit()

                if not sc.audio_path or sc.audio_duration is None or not storage.abs_path(sc.audio_path).exists():
                    speaker = await db.get(Asset, sc.speaker_asset_id) if sc.speaker_asset_id else None
                    voice_id = (speaker.voice_id if speaker else None) or series.narrator_voice
                    rel, path = storage.new_path(f"series_{series.id}", f"ep_{ep.id}", "audio", ext="mp3")
                    await voice.synthesize(sc.narration_text, voice_id, path)
                    storage.delete(sc.audio_path)
                    sc.audio_path, sc.audio_duration = rel, await probe_duration(path)
                    await db.commit()

                if not sc.clip_path or not storage.abs_path(sc.clip_path).exists():
                    rel, path = storage.new_path(f"series_{series.id}", f"ep_{ep.id}", "clips", ext="mp4")
                    await build_scene_clip(image=storage.abs_path(sc.image_path), audio=storage.abs_path(sc.audio_path),
                                           audio_duration=sc.audio_duration, text=sc.narration_text,
                                           aspect=series.aspect_ratio, index=i - 1, out=path)
                    sc.clip_path = rel
                    await db.commit()
                clips.append(storage.abs_path(sc.clip_path))

            ep.progress_note = "Joining scenes…"
            await db.commit()
            rel, path = storage.new_path(f"series_{series.id}", f"ep_{ep.id}", ext="mp4")
            await concat_clips(clips, path)
            storage.delete(ep.video_path)
            ep.video_path, ep.duration_seconds = rel, await probe_duration(path)
            ep.status, ep.progress_note = EP_COMPLETED, None
            await db.commit()
        except Exception as e:  # noqa: BLE001
            await _fail(db, ep, EP_RENDERING, e)


# ───────────────────────── maintenance ─────────────────────────
async def recover_interrupted() -> None:
    """Jobs die with the process. On boot, anything still marked 'running' is flipped to failed so the UI offers Retry
    instead of spinning forever."""
    async with SessionLocal() as db:
        for ep in (await db.execute(select(Episode).where(Episode.status.in_(BUSY_STATES)))).scalars():
            ep.failed_stage, ep.status, ep.progress_note = ep.status, EP_FAILED, None
            ep.error = "Interrupted by a server restart — press Retry to continue where it left off."
        for model in (Asset, Scene):
            for row in (await db.execute(select(model).where(model.image_status == IMG_GENERATING))).scalars():
                row.image_status, row.last_error = IMG_FAILED, "Interrupted by a server restart — regenerate."
        await db.commit()


def delete_episode_files(series_id: int, episode_id: int) -> None:
    shutil.rmtree(storage.abs_path(f"series_{series_id}/ep_{episode_id}"), ignore_errors=True)


def delete_series_files(series_id: int) -> None:
    shutil.rmtree(storage.abs_path(f"series_{series_id}"), ignore_errors=True)
