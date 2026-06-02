import asyncio
import os
import logging
from app.celery_app import celery_app
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from app.config import settings
from app.models.video import VideoProject
from app.services.gemini_service import GeminiService
from app.services.elevenlabs_service import ElevenLabsService
from app.services.video_api_service import VideoAPIService
from app.services.ffmpeg_engine import FFmpegEngine

# Set up centralized process logging output pattern
LOG_DIR = "/app/logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE_PATH = os.path.join(LOG_DIR, "pipeline.log")

# 2. Configure multi-handler logging (File + Terminal Console)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        # Writes everything to your persistent file
        logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
        # Keeps streaming live output to your terminal screen
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("app.tasks.video_pipeline")

def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

@celery_app.task(name="app.tasks.video_tasks.run_video_pipeline")
def run_video_pipeline(project_id: str, payload_data: dict):
    logger.info(f"--- [START] Celery worker accepted Task Job for Project ID: {project_id} ---")
    try:
        result = run_async(async_pipeline_executor(project_id, payload_data))
        logger.info(f"--- [SUCCESS] Task executed cleanly for Project ID: {project_id} ---")
        return result
    except Exception as exc:
        logger.critical(f"--- [CRASH] Pipeline execution failed unexpectedly for Project: {project_id}. Error: {exc}")
        raise exc

async def async_pipeline_executor(project_id: str, payload: dict):
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as db:
        logger.info(f"Connecting to database to verify project {project_id} state status...")
        stmt = select(VideoProject).where(VideoProject.id == project_id)
        project = (await db.execute(stmt)).scalar_one_or_none()
        
        if not project:
            logger.warning(f"Aborting execution. Project ID: {project_id} was not discovered in PostgreSQL records.")
            return

        logger.info(f"Flipping project database status row to: 'PROCESSING'")
        project.status = "PROCESSING"
        await db.commit()

        try:
            # ----------------------------------------------------
            # STEP 1: SCRIPT & TIMELINE DISTRIBUTION
            # ----------------------------------------------------
            logger.info("Initializing Step 1: Script Layout Scene Partitioning via Gemini...")
            scenes_data = await GeminiService.parse_story_to_scenes(
                prompt=project.prompt,
                story_text=project.story_text,
                art_style=payload.get("art_style")
            )

            # ----------------------------------------------------
            # STEP 2: VOICE SYNTHESIS GENERATION
            # ----------------------------------------------------
            full_narration = " ".join([s["narration_chunk"] for s in scenes_data])
            voice_output = f"/tmp/audio_{project_id}.mp3"
            
            logger.info(f"Initializing Step 2: Combining narration blocks ({len(full_narration)} chars) -> Streaming to ElevenLabs.")
            await ElevenLabsService.generate_voiceover(full_narration, payload.get("voice_id"), voice_output)
            logger.info(f"Audio asset safely downloaded and cached locally at: {voice_output}")

            # ----------------------------------------------------
            # STEP 3: CONCURRENT VISUAL CLIPS ENGINE TRACKING
            # ----------------------------------------------------
            logger.info(f"Initializing Step 3: Triggering concurrent visual asset loops for {len(scenes_data)} scenes.")
            video_tasks = []
            for scene in scenes_data:
                logger.info(f" -> Queueing rendering job for Scene #{scene['scene_number']}. Prompt: '{scene['visual_prompt'][:40]}...'")
                video_tasks.append(VideoAPIService.generate_image_to_video(
                    scene["visual_prompt"], project.aspect_ratio
                ))
            
            logger.info("Awaiting simultaneous resolution of remote video engine workloads...")
            resolved_video_urls = await asyncio.gather(*video_tasks)
            logger.info("All remote video stream components resolved successfully.")

            local_clips = []
            for idx, url in enumerate(resolved_video_urls):
                mock_clip_path = f"/tmp/clip_{project_id}_{idx}.mp4"
                if settings.MOCK_AI:
                    logger.info(f" -> [MOCK] Creating local placeholder canvas file asset: {mock_clip_path}")
                    os.system(f"ffmpeg -y -f lavfi -i testsrc=duration=5:size=1280x720 -pix_fmt yuv420p {mock_clip_path} > /dev/null 2>&1")
                else:
                    logger.info(f" -> Downloading remote asset track file stream into workspace container: {mock_clip_path}")
                    import httpx
                    async with httpx.AsyncClient() as client:
                        res = await client.get(url)
                        with open(mock_clip_path, "wb") as f:
                            f.write(res.content)
                local_clips.append(mock_clip_path)

            # ----------------------------------------------------
            # STEP 4: NATIVE SYSTEM COMPOSITING
            # ----------------------------------------------------
            logger.info("Flipping project database status row to: 'COMPILING'")
            project.status = "COMPILING"
            await db.commit()

            final_output = f"/tmp/final_{project_id}.mp4"
            logger.info(f"Initializing Step 4: Invoking local system FFmpeg to stitch {len(local_clips)} video tracks onto master narration file...")
            
            FFmpegEngine.stitch_scenes(local_clips, voice_output, final_output)
            logger.info(f"FFmpeg composition completed. Master media asset file instantiated at: {final_output}")

            # ----------------------------------------------------
            # SYSTEM COMPLETION DATA SYNC
            # ----------------------------------------------------
            project.final_video_url = final_output
            project.status = "COMPLETED"
            await db.commit()
            logger.info(f"Database status updated to 'COMPLETED' for project {project_id}.")

        except Exception as e:
            logger.error(f"Execution failure encountered inside main pipeline loop processing tracker: {str(e)}")
            project.status = "FAILED"
            await db.commit()
            raise e