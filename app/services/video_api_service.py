import logging
import os
import subprocess
import aiofiles
from app.config import settings
from app.services.ai_providers import (
    DeepInfraProvider, 
    TogetherAIProvider, 
    HuggingFaceProvider, 
    FalProvider,
    GeminiImageProvider
)

logger = logging.getLogger("app.tasks.video_pipeline")

class VideoAPIService:
    @staticmethod
    def _compile_image_to_mp4(image_input: bytes | str, output_path: str, duration: int = 5) -> str:
        """
        Helper method: Takes a local image path or raw image bytes, and uses FFmpeg 
        to render a mathematically valid, browser-compatible MP4 clip.
        """
        temp_img_path = f"{output_path}.img.tmp"
        
        # If we received raw image bytes (like from HuggingFace), write them to a temp file first
        if isinstance(image_input, bytes):
            with open(temp_img_path, "wb") as f:
                f.write(image_input)
            img_source = temp_img_path
        else:
            img_source = image_input  # It's already a local file path or URL

        try:
            logger.info(f"FFmpeg converting static image ({img_source}) into a {duration}s MP4 clip...")
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", img_source,
                "-f", "lavfi", "-i", "anullsrc=cl=stereo:r=44100",  # Injects essential silent audio track
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-c:a", "aac",
                "-pix_fmt", "yuv420p",
                "-t", str(duration),
                output_path
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return output_path
        finally:
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

    @staticmethod
    async def generate_image_to_video(visual_prompt: str, aspect_ratio: str, scene_index: int = 0, project_id: str = "default") -> str:
        # 🧪 DEFINITIVE LIST OF OPEN-SOURCE TEST VIDEOS (ONLY used when MOCK_AI is True)
        mock_videos = [
            "https://vjs.zencdn.net/v/oceans.mp4",
            "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
            "https://www.w3schools.com/html/mov_bbb.mp4",
            "https://media.w3.org/2010/05/sintel/trailer_hd.mp4"
        ]

        # ----------------------------------------------------
        # 🛠️ GLOBAL DEVELOPMENT MOCK MODE (Bypass everything)
        # ----------------------------------------------------
        if settings.MOCK_AI:
            logger.info(f"Mock Mode active: Cycling straight to open-source fallback video asset index {scene_index}")
            return mock_videos[scene_index % len(mock_videos)]

        provider = settings.AI_PROVIDER.lower()
        target_clip_path = f"/tmp/clip_{project_id}_{scene_index}.mp4"

        # ----------------------------------------------------
        # 💳 LIVE PRODUCTION: IMAGE GENERATION ENGINE ROUTING
        # ----------------------------------------------------
        if provider == "deepinfra":
            img_url = await DeepInfraProvider.generate_image(visual_prompt, aspect_ratio)
            logger.info(f"DeepInfra image successful: {img_url[:60]}...")
            # Compile the generated image URL into a local MP4 file path
            return VideoAPIService._compile_image_to_mp4(img_url, target_clip_path)

        elif provider == "together":
            img_url = await TogetherAIProvider.generate_image(visual_prompt, aspect_ratio)
            logger.info(f"Together AI image successful: {img_url[:60]}...")
            # Compile the generated image URL into a local MP4 file path
            return VideoAPIService._compile_image_to_mp4(img_url, target_clip_path)

        elif provider == "huggingface":
            img_bytes = await HuggingFaceProvider.generate_image_bytes(visual_prompt)
            logger.info(f"Hugging Face generation successful. Received {len(img_bytes)} bytes.")
            # Compile raw binary picture bytes directly into a local MP4 file path
            return VideoAPIService._compile_image_to_mp4(img_bytes, target_clip_path)
        
        elif provider == "gemini":
            img_bytes = await GeminiImageProvider.generate_image_bytes(visual_prompt, aspect_ratio)
            logger.info(f"Gemini Imagen generation successful. Received {len(img_bytes)} bytes.")
            # Compiles raw binary bytes from Imagen straight into a local MP4 file path
            return VideoAPIService._compile_image_to_mp4(img_bytes, target_clip_path)
            
        # ----------------------------------------------------
        # 🎥 LIVE PRODUCTION: PREMIUM NATIVE TEXT-TO-VIDEO PIPELINE
        # ----------------------------------------------------
        elif provider == "fal":
            return await FalProvider.generate_video_url(visual_prompt, aspect_ratio)
        
        else:
            raise ValueError(f"Unknown or unsupported AI Provider: {settings.AI_PROVIDER}")