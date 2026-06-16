import httpx
import edge_tts
import aiofiles
import logging
from app.config import settings

logger = logging.getLogger("app.services.audio_providers")

class EdgeTTSProvider:
    @staticmethod
    async def generate_audio(text: str, voice_id: str, output_path: str):
        """Generates completely free audio using Microsoft Azure's serverless Edge TTS"""
        logger.info("Generating voiceover via Edge-TTS...")
        
        # 🛡️ SANITATION: If the voice_id looks like an ElevenLabs hash, fall back to a valid Edge voice
        target_voice = voice_id
        if "-" not in voice_id or "Neural" not in voice_id:
            logger.warning(f"Invalid Edge-TTS voice string '{voice_id}'. Falling back to default neural profile.")
            target_voice = "en-US-ChristopherNeural"

        try:
            communicate = edge_tts.Communicate(text, target_voice)
            await communicate.save(output_path)
        except Exception as e:
            raise Exception(f"Edge-TTS voice generation failure: {str(e)}")


class ElevenLabsProvider:
    @staticmethod
    async def generate_audio(text: str, voice_id: str, output_path: str):
        """Generates premium neural audio using paid ElevenLabs credits"""
        logger.info(f"Generating premium voiceover via ElevenLabs [Voice ID: {voice_id}]...")
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": settings.ELEVENLABS_API_KEY, 
            "Content-Type": "application/json"
        }
        payload = {
            "text": text, 
            "model_id": "eleven_multilingual_v2"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=60.0)
            
            if response.status_code == 200:
                async with aiofiles.open(output_path, "wb") as f:
                    await f.write(response.content)
            else:
                raise Exception(f"ElevenLabs TTS generation failure: {response.text}")