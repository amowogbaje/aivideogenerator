import httpx
import edge_tts
import aiofiles
from app.config import settings

class ElevenLabsService:
    @staticmethod
    async def generate_voiceover(text: str, voice_id: str, output_path: str):
        # ----------------------------------------------------
        # 🛠️ DEVELOPER MOCK MODE: Free Unlimited Azure Audio
        # ----------------------------------------------------
        if settings.MOCK_AI:
            # Premium Azure neural voice used for local pipeline testing
            target_voice = "en-US-ChristopherNeural"
            try:
                communicate = edge_tts.Communicate(text, target_voice)
                await communicate.save(output_path)
                return
            except Exception as e:
                raise Exception(f"Edge-TTS fallback voice generation failure: {str(e)}")

        # ----------------------------------------------------
        # 💳 PRODUCTION MODE: Paid Premium ElevenLabs API
        # ----------------------------------------------------
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