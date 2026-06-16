import httpx
import asyncio
import logging
from app.config import settings
from huggingface_hub import InferenceClient
from io import BytesIO

logger = logging.getLogger("app.services.ai_providers")

http_client = httpx.AsyncClient(timeout=60.0)

hf_client = InferenceClient(
    provider="hf-inference",
    token=settings.HF_API_KEY,
    timeout=60  # optional but recommended
)

class DeepInfraProvider:
    @staticmethod
    async def generate_image(prompt: str, aspect_ratio: str) -> str:
        """Generates an image via DeepInfra using FLUX.1-schnell"""
        logger.info("Triggering image generation via DeepInfra...")
        url = "https://api.deepinfra.com/v1/openai/images/generations"
        headers = {
            "Authorization": f"Bearer {settings.DEEPINFRA_API_KEY}",
            "Content-Type": "application/json"
        }
        size = "1024x576" if aspect_ratio == "16:9" else "576x1024"
        payload = {
            "model": "black-forest-labs/FLUX-1-schnell",
            "prompt": prompt,
            "size": size
        }
        async with httpx.AsyncClient() as client:
            res = await client.post(url, headers=headers, json=payload, timeout=30.0)
            res.raise_for_status()
            return res.json()["data"][0]["url"]


class TogetherAIProvider:
    @staticmethod
    async def generate_image(prompt: str, aspect_ratio: str) -> str:
        """Generates an image via Together AI using FLUX.1-schnell-Free"""
        logger.info("Triggering image generation via Together AI...")
        url = "https://api.together.xyz/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {settings.TOGETHER_API_KEY}",
            "Content-Type": "application/json"
        }
        width, height = (1024, 576) if aspect_ratio == "16:9" else (576, 1024)
        payload = {
            "model": "black-forest-labs/FLUX.1-schnell-Free",
            "prompt": prompt,
            "width": width,
            "height": height,
            "steps": 4,
            "n": 1
        }
        async with httpx.AsyncClient() as client:
            res = await client.post(url, headers=headers, json=payload, timeout=30.0)
            res.raise_for_status()
            return res.json()["data"][0]["url"]


class HuggingFaceProvider:
    API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"

    @staticmethod
    async def generate_image_bytes(prompt: str) -> bytes:
        logger.info("Triggering image generation via Hugging Face (FLUX.1-schnell)...")

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                HuggingFaceProvider.API_URL,
                headers={
                    "Authorization": f"Bearer {settings.HF_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"inputs": prompt},
            )

        if response.status_code == 503:
            raise RuntimeError("Model is loading, retry in ~20 seconds")

        response.raise_for_status()
        return response.content


class FalProvider:
    @staticmethod
    async def generate_video_url(visual_prompt: str, aspect_ratio: str) -> str:
        """Runs the fully premium, two-step Fal.ai Image + Video pipeline"""
        logger.info("Triggering comprehensive Image-to-Video pipeline via Fal.ai...")
        headers = {
            "Authorization": f"Key {settings.FAL_AI_API_KEY}", 
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            # STEP 1: FAL IMAGE GENERATION
            logger.info("Submitting image generation task to Fal.ai Flux...")
            img_submit_res = await client.post(
                "https://queue.fal.run/fal-ai/flux/schnell",
                headers=headers,
                json={
                    "prompt": visual_prompt, 
                    "image_size": "16:9" if aspect_ratio == "16:9" else "9:16"
                },
                timeout=30.0
                )
            img_submit_res.raise_for_status()
            img_req_id = img_submit_res.json().get("request_id")
            img_url = ""
            
            for _ in range(20):
                await asyncio.sleep(2)
                img_status_res = await client.get(
                    f"https://queue.fal.run/requests/{img_req_id}", headers=headers
                )
                img_status_data = img_status_res.json()
                if img_status_data.get("status") == "COMPLETED":
                    img_url = img_status_data.get("response", {}).get("images", [{}])[0].get("url", "")
                    break
                elif img_status_data.get("status") == "FAILED":
                    raise Exception("Fal.ai Flux image generation failed in queue.")
            
            if not img_url:
                raise Exception("Fal.ai Image generation execution timeout reached.")

            # STEP 2: FAL VIDEO CONVERSION
            logger.info("Image resolved. Submitting Image-to-Video task to Fal.ai Video Engine...")
            video_submit_res = await client.post(
                "https://queue.fal.run/fal-ai/stable-video-diffusion",
                headers=headers,
                json={"image_url": img_url, "motion_bucket_id": 127, "fps": 6},
                timeout=30.0
            )
            video_submit_res.raise_for_status()
            video_req_id = video_submit_res.json().get("request_id")

            for _ in range(30):
                await asyncio.sleep(5)
                video_status_res = await client.get(
                    f"https://queue.fal.run/requests/{video_req_id}", headers=headers
                )
                video_status_data = video_status_res.json()
                if video_status_data.get("status") == "COMPLETED":
                    final_video_url = video_status_data.get("response", {}).get("video", {}).get("url", "")
                    if final_video_url:
                        return final_video_url
                elif video_status_data.get("status") == "FAILED":
                    raise Exception("Fal.ai Video generation failed in queue processing.")
                    
            raise Exception("Fal.ai Video generation execution timeout reached.")


class PollinationsProvider:
    BASE_URL = "https://image.pollinations.ai/prompt"

    @staticmethod
    async def generate_image_bytes(prompt: str) -> bytes:
        encoded = httpx.URL(f"{PollinationsProvider.BASE_URL}/{prompt}")
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(str(encoded))
            response.raise_for_status()
            return response.content


