import json
import logging
from google import genai
from google.genai.types import GenerateContentConfig
from pydantic import BaseModel, Field
from typing import List
from app.config import settings

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
    async def parse_story_to_scenes(prompt: str, story_text: str, art_style: str) -> list:
        if settings.MOCK_AI:
            logger.info("[MOCK MODE] Skipping Gemini API call. Returning simulated layout array.")
            return [
                {"scene_number": 1, "narration_chunk": "The machine hummed in the dark room.", "visual_prompt": f"{art_style} close up of humming futuristic computer engine"},
                {"scene_number": 2, "narration_chunk": "Suddenly, a bright white light flashed.", "visual_prompt": f"{art_style} blinding light explosion inside dark technical server room"}
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
            parsed_data = json.loads(response.text)
            scenes = parsed_data.get("scenes", [])
            
            logger.info(f"Successfully validated Gemini schema payload. Formatted {len(scenes)} distinct visual scenes.")
            return scenes

        except json.JSONDecodeError as jde:
            logger.error(f"Failed to parse Gemini response text stream into valid JSON: {jde}")
            raise jde
        except Exception as e:
            logger.error(f"Critical exception occurred inside Gemini request layer: {str(e)}")
            raise e