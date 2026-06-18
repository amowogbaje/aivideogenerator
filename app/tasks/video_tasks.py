import asyncio
import os
import logging
import httpx

from app.celery_app import celery_app
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
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


async def download_clip(
    client: httpx.AsyncClient,
    idx: int,
    url_or_path: str,
    project_id: str
) -> str:
    if not url_or_path.startswith("http") and os.path.exists(url_or_path):
        logger.info(f" -> Local asset already on disk, skipping download: {url_or_path}")
        return url_or_path

    dest_path = f"/tmp/clip_{project_id}_{idx}.mp4"

    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        logger.info(f" -> Cache hit, skipping re-download for clip #{idx}: {dest_path}")
        return dest_path

    logger.info(f" -> Streaming clip #{idx} → {dest_path}  (source: {url_or_path})")

    async with client.stream("GET", url_or_path, follow_redirects=True) as response:
        response.raise_for_status()
        total_bytes = 0
        with open(dest_path, "wb") as f:
            async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                f.write(chunk)
                total_bytes += len(chunk)
        logger.info(f" -> Clip #{idx} download complete: {total_bytes / (1024 * 1024):.1f} MB saved.")

    return dest_path


# ─────────────────────────────────────────────
# MAIN ASYNC PIPELINE EXECUTOR
# ─────────────────────────────────────────────
async def async_pipeline_executor(project_id: str, payload: dict):
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as db:
        logger.info(f"Connecting to database to verify project {project_id} state status...")
        stmt = select(VideoProject).where(VideoProject.id == project_id)
        project = (await db.execute(stmt)).scalar_one_or_none()

        if not project:
            logger.warning(f"Aborting execution. Project ID: {project_id} was not found in PostgreSQL.")
            return

        logger.info("Flipping project database status row to: 'PROCESSING'")
        project.status = "PROCESSING"
        await db.commit()

        try:
            # ────────────────────────────────────────
            # STEP 1: SCRIPT & TIMELINE DISTRIBUTION
            # ────────────────────────────────────────
            scenes_data = []
            voice_output = f"/tmp/audio_{project_id}.mp3"

            if project.audio_url:
                logger.info("Initializing Step 1: Processing Native Audio to Scene breakdown via Gemini Multimodal...")
                scenes_data = await GeminiService.process_audio_to_scenes(project.audio_url)
                
                # ────────────────────────────────────────
                # STEP 2: USER VOICE CACHING ROUTE
                # ────────────────────────────────────────
                logger.info("Initializing Step 2: Streaming user audio file to pipeline master track...")
                async with httpx.AsyncClient(timeout=60.0) as download_client:
                    async with download_client.stream("GET", project.audio_url, follow_redirects=True) as response:
                        response.raise_for_status()
                        with open(voice_output, "wb") as f:
                            async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                                f.write(chunk)
                logger.info(f"User track verified and locked at: {voice_output}")
                
            else:
                logger.info("Initializing Step 1: Script Layout Scene Partitioning via Gemini Text Prompts...")
                scenes_data = await GeminiService.parse_story_to_scenes(
                    prompt=project.prompt,
                    story_text=project.story_text,
                    art_style=payload.get("art_style")
                )
                
                # ────────────────────────────────────────
                # STEP 2: VOICE SYNTHESIS GENERATION ROUTE
                # ────────────────────────────────────────
                full_narration = " ".join([s["narration_chunk"] for s in scenes_data])
                logger.info(f"Initializing Step 2: Generating ElevenLabs voiceover integration ({len(full_narration)} chars)...")
                await AudioAPIService.generate_voiceover(
                    text=full_narration,
                    voice_id=payload.get("voice_id", "en-US-ChristopherNeural"),
                    output_path=voice_output
                )
                logger.info(f"Synthesized voiceover track compiled to: {voice_output}")

            # ────────────────────────────────────────
            # STEP 3: CONCURRENT VISUAL CLIP GENERATION
            # ────────────────────────────────────────
            logger.info(f"Initializing Step 3: Triggering visual generation tasks for {len(scenes_data)} segments.")
            video_tasks = []
            for idx, scene in enumerate(scenes_data):
                logger.info(f" -> Queueing composition layer for Scene #{scene['scene_number']}.")
                video_tasks.append(VideoAPIService.generate_image_to_video(
                    visual_prompt=scene["visual_prompt"],
                    aspect_ratio=project.aspect_ratio,
                    scene_index=idx
                ))

            logger.info("Awaiting simultaneous resolution of remote video workloads...")
            resolved_video_urls = await asyncio.gather(*video_tasks)

            # ────────────────────────────────────────
            # STEP 3b: DOWNLOAD SCENE ASSETS
            # ────────────────────────────────────────
            clip_timeout = httpx.Timeout(connect=15.0, read=300.0, write=15.0, pool=10.0)
            async with httpx.AsyncClient(timeout=clip_timeout) as client:
                local_clips = await asyncio.gather(*[
                    download_clip(client, idx, url, project_id)
                    for idx, url in enumerate(resolved_video_urls)
                ])

            logger.info(f"All {len(local_clips)} production assets verified locally.")

            # ────────────────────────────────────────
            # STEP 4: FFMPEG COMPOSITING
            # ────────────────────────────────────────
            logger.info("Flipping project database status row to: 'COMPILING'")
            project.status = "COMPILING"
            await db.commit()

            final_output = f"/tmp/final_{project_id}.mp4"
            logger.info(f"Initializing Step 4: Stitching scene arrays onto master voiceover path...")
            FFmpegEngine.stitch_scenes(local_clips, voice_output, final_output)
            logger.info(f"Rendering phase complete. Destination: {final_output}")

            # ────────────────────────────────────────
            # DATA PERSISTENCE UPDATE
            # ────────────────────────────────────────
            project.final_video_url = final_output
            project.status = "COMPLETED"
            await db.commit()
            logger.info(f"Pipeline executed successfully for layout index: {project_id}.")

        except Exception as e:
            logger.error(f"Pipeline process exception for project {project_id}: {str(e)}", exc_info=True)
            project.status = "FAILED"
            await db.commit()
            raise e