import os
import json
import logging
import re
import httpx
from google import genai
from google.genai.types import GenerateContentConfig
from pydantic import BaseModel, Field
from typing import List
from app.config import settings
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.genai.errors import ServerError

# Initialize named module logger
logger = logging.getLogger("app.services.gemini")

class SceneItem(BaseModel):
    scene_number: int = Field(description="Sequential numerical list placement coordinate value starting from 1")
    narration_chunk: str = Field(description="The narrative vocal transcript segment script to read aloud for this frame sequence")
    visual_prompt: str = Field(description="An evocative imagery instruction layout string describing the scene environment")

class SceneContainer(BaseModel):
    scenes: List[SceneItem] = Field(description="Ordered array block parsing elements matching the story progression mapping")

class GeminiService:
    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(ServerError)
    )
    async def parse_story_to_scenes(prompt: str, story_text: str, art_style: str) -> list:
        if settings.MOCK_AI:
            logger.info("[MOCK MODE] Skipping Gemini API call. Simulating layout.")
            
            # Logic: If story_text exists, break into sentences, otherwise return generic mock
            if story_text and story_text.strip():
                # Split by sentence delimiters (.!?)
                sentences = re.split(r'(?<=[.!?]) +', story_text)
                scenes = [
                    {
                        "scene_number": i + 1, 
                        "narration_chunk": sentence, 
                        "visual_prompt": f"{art_style} scene depicting: {sentence[:30]}..."
                    }
                    for i, sentence in enumerate(sentences)
                ]
                return scenes
            else:
                # Fallback for when only a prompt is provided
                return [
                    {"scene_number": 1, "narration_chunk": "A creative beginning.", "visual_prompt": f"{art_style} wide shot of concept"},
                    {"scene_number": 2, "narration_chunk": "The plot thickens.", "visual_prompt": f"{art_style} medium shot of climax"}
                ]

        # Check whether we are expanding an idea or parsing a full manuscript
        if story_text:
            logger.info(f"Gemini received complete story text manuscript ({len(story_text)} characters). Mode: Extract & Partition.")
            input_content = story_text
        else:
            logger.info(f"Gemini received a short creative concept prompt. Mode: Generation from scratch.")
            input_content = f"Compose a gripping cinematic script about: {prompt}"
        
        system_instructions = (
            "You are an expert film director and content extraction program. Dissect input text chronologically "
            "into specific storyboard frames. Maintain tone and explicit progression detail throughout."
        )
        user_prompt = f"Target Art Direction Style: {art_style}. Raw Manuscript Narrative: {input_content}"

        try:
            logger.info("Dispatching asynchronous network request to Gemini 2.5 Flash...")
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_prompt,
                config=GenerateContentConfig(
                    system_instruction=system_instructions,
                    response_mime_type="application/json",
                    response_schema=SceneContainer,
                )
            )
            
            logger.info("Gemini raw text generation response successfully intercepted.")
            # parsed_data = json.loads(response.text)
            # scenes = parsed_data.get("scenes", [])
            
            scenes = response.parsed.scenes
            logger.info(f"Successfully validated Gemini schema payload. Formatted {len(scenes)} distinct visual scenes.")
            return [s.model_dump() for s in scenes]

        except ServerError as e:
            logger.warning("Gemini 503 detected, retrying...")
            raise e
        except json.JSONDecodeError as jde:
            logger.error(f"Failed to parse Gemini response text stream into valid JSON: {jde}")
            raise jde
        except Exception as e:
            logger.error(f"Critical exception occurred inside Gemini request layer: {str(e)}")
            raise e



    @staticmethod
    async def process_audio_to_scenes(audio_url: str) -> list[dict]:
        """
        Asynchronously downloads source audio, passes it to Gemini's 
        multimodal infrastructure, and outputs the structured scene array.
        """
        local_path = f"/tmp/gemini_input_{os.getpid()}.mp3"
        
        # 1. Non-blocking stream download for Gemini's File ingestion engine
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            async with http_client.stream("GET", audio_url, follow_redirects=True) as response:
                response.raise_for_status()
                with open(local_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
        
        try:
            # 2. Upload using the async client (.aio)
            uploaded_audio = await client.aio.files.upload(file=local_path)
            
            instruction = """
            Analyze this audio file. Transcribe the narration spoken, and partition 
            the timeline sequentially into descriptive scene blocks.
            Return a strict JSON array matching this data model structure:
            [
              {
                "scene_number": 1,
                "narration_chunk": "The exact snippet of transcribed spoken text for this moment",
                "visual_prompt": "A vivid, descriptive prompt suitable for generating an image asset"
              }
            ]
            Return ONLY the raw JSON block. No markdown strings.
            """
            
            # 3. Request multi-modal inference
            response = await client.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=[instruction, uploaded_audio]
            )
            
            raw_json = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(raw_json)
            
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)