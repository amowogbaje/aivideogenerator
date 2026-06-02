import httpx
import asyncio
from app.config import settings

class VideoAPIService:
    @staticmethod
    async def generate_image_to_video(visual_prompt: str, aspect_ratio: str) -> str:
        if settings.MOCK_AI:
            return "https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4"

        # Using Fal.ai hosting Flux.1 for image generation as a starting asset point
        headers = {"Authorization": f"Key {settings.FAL_AI_API_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient() as client:
            img_res = await client.post(
                "https://queue.fal.run/fal-ai/flux/schnell",
                headers=headers,
                json={"prompt": visual_prompt, "image_size": "16:9" if aspect_ratio == "16:9" else "9:16"},
                timeout=30.0
            )
            # Simplistic representation of asset polling logic
            img_url = img_res.json().get("images", [{}])[0].get("url", "")
            
            # Forward the image url target directly over to Luma AI API endpoints
            luma_headers = {"Authorization": f"Bearer {settings.LUMA_API_KEY}", "Content-Type": "application/json"}
            v_res = await client.post(
                "https://api.lumalabs.ai/v1/generations",
                headers=luma_headers,
                json={"prompt": visual_prompt, "keyframes": {"frame0": {"type": "image", "url": img_url}}},
                timeout=30.0
            )
            gen_id = v_res.json().get("id")
            
            # Synchronously poll asset state safely for early MVP build
            for _ in range(30):
                await asyncio.sleep(10)
                status_res = await client.get(f"https://api.lumalabs.ai/v1/generations/{gen_id}", headers=luma_headers)
                data = status_res.json()
                if data.get("state") == "completed":
                    return data.get("assets", {}).get("video")
            raise Exception("Luma Video generation execution timeout reached.")