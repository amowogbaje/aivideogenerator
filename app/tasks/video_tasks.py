import asyncio
import os
import logging
import httpx

from app.celery_app import celery_app
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.models.video import VideoProject
from app.services.gemini_service import GeminiService
from app.services.audio_api_service import AudioAPIService
from app.services.video_api_service import VideoAPIService
from app.services.ffmpeg_engine import FFmpegEngine


# ─────────────────────────────────────────────
# LOGGING SETUP
# ─────────────────────────────────────────────
LOG_DIR = "/app/logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE_PATH = os.path.join(LOG_DIR, "pipeline.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("app.tasks.video_pipeline")


# ─────────────────────────────────────────────
# FIX 1: Replaced deprecated asyncio.get_event_loop()
# with asyncio.run() which is the correct Python 3.10+
# approach. get_event_loop() raises a DeprecationWarning
# in 3.10 and can crash in 3.12 inside Celery fork workers.
# ─────────────────────────────────────────────
def run_async(coro):
    return asyncio.run(coro)


# ─────────────────────────────────────────────
# CELERY TASK ENTRY POINT
# ─────────────────────────────────────────────
@celery_app.task(name="app.tasks.video_tasks.run_video_pipeline")
def run_video_pipeline(project_id: str, payload_data: dict):
    logger.info(f"--- [START] Celery worker accepted Task Job for Project ID: {project_id} ---")
    try:
        result = run_async(async_pipeline_executor(project_id, payload_data))
        logger.info(f"--- [SUCCESS] Task executed cleanly for Project ID: {project_id} ---")
        return result
    except Exception as exc:
        logger.critical(
            f"--- [CRASH] Pipeline execution failed unexpectedly for Project: {project_id}. Error: {exc}"
        )
        raise exc


# ─────────────────────────────────────────────
# HELPER: Stream-download a single video clip to disk
#
# FIX 2 (core crash fix): Instead of client.get() which
# loads the ENTIRE file into memory before writing, we use
# client.stream() + aiter_bytes() to write in 1 MB chunks.
# This prevents the ReadTimeout that was killing the pipeline
# mid-download on large files like oceans.mp4 (~98 MB).
#
# FIX 3: httpx.AsyncClient now carries explicit timeouts:
#   - connect=15s  : time to open the TCP connection
#   - read=300s    : time to receive each chunk (5 min total budget)
#   - write=15s    : time to send the request body
#   - pool=10s     : time to acquire a connection from the pool
# Without this, httpx falls back to a 5-second read timeout
# which is far too short for large video files.
# ─────────────────────────────────────────────
async def download_clip(
    client: httpx.AsyncClient,
    idx: int,
    url_or_path: str,
    project_id: str
) -> str:
    """
    Returns the local filesystem path of the downloaded clip.
    Skips the network entirely if the destination file already
    exists on disk — covers both retries of the same project
    and local/mock paths returned by VideoAPIService.
    """
    # Already a local file path (mock mode) — nothing to download
    if not url_or_path.startswith("http") and os.path.exists(url_or_path):
        logger.info(f" -> Local asset already on disk, skipping download: {url_or_path}")
        return url_or_path

    dest_path = f"/tmp/clip_{project_id}_{idx}.mp4"

    # Cache hit: destination file already downloaded in a previous run or retry
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        logger.info(f" -> Cache hit, skipping re-download for clip #{idx}: {dest_path}")
        return dest_path

    logger.info(f" -> Streaming clip #{idx} → {dest_path}  (source: {url_or_path})")

    # FIX 2: stream=True avoids buffering the whole file in RAM
    async with client.stream("GET", url_or_path, follow_redirects=True) as response:
        response.raise_for_status()
        total_bytes = 0
        with open(dest_path, "wb") as f:
            async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):  # 1 MB chunks
                f.write(chunk)
                total_bytes += len(chunk)
        logger.info(f" -> Clip #{idx} download complete: {total_bytes / (1024 * 1024):.1f} MB saved.")

    return dest_path


# ─────────────────────────────────────────────
# MAIN ASYNC PIPELINE
# ─────────────────────────────────────────────
async def async_pipeline_executor(project_id: str, payload: dict):
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as db:
        logger.info(f"Connecting to database to verify project {project_id} state status...")
        stmt = select(VideoProject).where(VideoProject.id == project_id)
        project = (await db.execute(stmt)).scalar_one_or_none()

        if not project:
            logger.warning(
                f"Aborting execution. Project ID: {project_id} was not found in PostgreSQL."
            )
            return

        logger.info("Flipping project database status row to: 'PROCESSING'")
        project.status = "PROCESSING"
        await db.commit()

        try:
            # ────────────────────────────────────────
            # STEP 1: SCRIPT & TIMELINE DISTRIBUTION
            # ────────────────────────────────────────
            logger.info("Initializing Step 1: Script Layout Scene Partitioning via Gemini...")
            scenes_data = await GeminiService.parse_story_to_scenes(
                prompt=project.prompt,
                story_text=project.story_text,
                art_style=payload.get("art_style")
            )

            # ────────────────────────────────────────
            # STEP 2: VOICE SYNTHESIS GENERATION
            # ────────────────────────────────────────
            full_narration = " ".join([s["narration_chunk"] for s in scenes_data])
            voice_output = f"/tmp/audio_{project_id}.mp3"

            logger.info(
                f"Initializing Step 2: Combining narration blocks "
                f"({len(full_narration)} chars) -> Streaming to Audio Engine."
            )
            await AudioAPIService.generate_voiceover(
                text=full_narration,
                voice_id=payload.get("voice_id", "en-US-ChristopherNeural"),
                output_path=voice_output
            )
            logger.info(f"Audio asset cached locally at: {voice_output}")

            # ────────────────────────────────────────
            # STEP 3: CONCURRENT VISUAL CLIP GENERATION
            # ────────────────────────────────────────
            logger.info(
                f"Initializing Step 3: Triggering concurrent visual asset "
                f"loops for {len(scenes_data)} scenes."
            )
            video_tasks = []
            for idx, scene in enumerate(scenes_data):
                logger.info(
                    f" -> Queueing rendering job for Scene #{scene['scene_number']}. "
                    f"Prompt: '{scene['visual_prompt'][:40]}...'"
                )
                video_tasks.append(VideoAPIService.generate_image_to_video(
                    visual_prompt=scene["visual_prompt"],
                    aspect_ratio=project.aspect_ratio,
                    scene_index=idx
                ))

            logger.info("Awaiting simultaneous resolution of remote video engine workloads...")
            resolved_video_urls = await asyncio.gather(*video_tasks)
            logger.info("All remote video stream components resolved successfully.")

            # ────────────────────────────────────────
            # STEP 3b: DOWNLOAD CLIPS
            #
            # FIX 3: Explicit timeout config on the shared client.
            # FIX 4: Downloads are now concurrent via asyncio.gather
            #         instead of sequential, cutting total download
            #         time dramatically (9 clips → ~parallel time of
            #         the slowest single clip rather than sum of all).
            # FIX 2: Each download uses streaming (see download_clip).
            # ────────────────────────────────────────
            # FIX 3: Explicit per-phase timeouts — no more silent 5s default
            clip_timeout = httpx.Timeout(
                connect=15.0,   # TCP handshake budget
                read=300.0,     # 5 min to receive response body chunks
                write=15.0,     # request send budget
                pool=10.0       # connection pool acquisition budget
            )

            # FIX 4: One shared client, all downloads fire concurrently
            async with httpx.AsyncClient(timeout=clip_timeout) as client:
                local_clips = await asyncio.gather(*[
                    download_clip(client, idx, url, project_id)
                    for idx, url in enumerate(resolved_video_urls)
                ])

            logger.info(f"All {len(local_clips)} clips downloaded successfully.")

            # ────────────────────────────────────────
            # STEP 4: FFMPEG COMPOSITING
            # ────────────────────────────────────────
            logger.info("Flipping project database status row to: 'COMPILING'")
            project.status = "COMPILING"
            await db.commit()

            final_output = f"/tmp/final_{project_id}.mp4"
            logger.info(
                f"Initializing Step 4: FFmpeg stitching {len(local_clips)} "
                f"video tracks onto master narration file..."
            )
            FFmpegEngine.stitch_scenes(local_clips, voice_output, final_output)
            logger.info(f"FFmpeg composition complete. Output: {final_output}")

            # ────────────────────────────────────────
            # COMPLETION
            # ────────────────────────────────────────
            project.final_video_url = final_output
            project.status = "COMPLETED"
            await db.commit()
            logger.info(f"Database status updated to 'COMPLETED' for project {project_id}.")

        except Exception as e:
            logger.error(f"Pipeline failure for project {project_id}: {str(e)}", exc_info=True)
            project.status = "FAILED"
            await db.commit()
            raise e