import httpx
import aiofiles
from app.config import settings

class ElevenLabsService:
    @staticmethod
    async def generate_voiceover(text: str, voice_id: str, output_path: str):
        if settings.MOCK_AI:
            # Writes an empty shell file locally to prevent FFmpeg pipeline breaks during testing
            async with aiofiles.open(output_path, "wb") as f:
                await f.write(b"mock_audio_data")
            return

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": settings.ELEVENLABS_API_KEY, "Content-Type": "application/json"}
        payload = {"text": text, "model_id": "eleven_monolingual_v1"}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=60.0)
            if response.status_code == 200:
                async with aiofiles.open(output_path, "wb") as f:
                    await f.write(response.content)
            else:
                raise Exception(f"ElevenLabs TTS generation failure: {response.text}")