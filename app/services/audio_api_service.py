import logging
from app.config import settings
from app.services.audio_providers import EdgeTTSProvider, ElevenLabsProvider

logger = logging.getLogger("app.tasks.audio_pipeline")

class AudioAPIService:
    @staticmethod
    async def generate_voiceover(text: str, voice_id: str, output_path: str):
        # ----------------------------------------------------
        # 🛠️ GLOBAL DEVELOPMENT MOCK MODE
        # ----------------------------------------------------
        if settings.MOCK_AI:
            logger.info("Mock Mode active: Routing voiceover generation straight to Edge-TTS.")
            await EdgeTTSProvider.generate_audio(text, voice_id, output_path)
            return

        provider = settings.AUDIO_AI_PROVIDER.lower()

        # ----------------------------------------------------
        # 🔀 AUDIO ROUTING MATRIX
        # ----------------------------------------------------
        if provider == "edgetts":
            await EdgeTTSProvider.generate_audio(text, voice_id, output_path)
            
        elif provider == "elevenlabs":
            await ElevenLabsProvider.generate_audio(text, voice_id, output_path)
            
        else:
            raise ValueError(f"Unknown or unsupported Audio Provider: {settings.AUDIO_AI_PROVIDER}")