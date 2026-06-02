import json
import httpx
from app.config import settings

class OpenAIService:
    @staticmethod
    async def parse_story_to_scenes(prompt: str, story_text: str, art_style: str) -> list:
        if settings.MOCK_AI:
            return [
                {"scene_number": 1, "narration_chunk": "The machine hummed in the dark room.", "visual_prompt": f"{art_style} close up of humming futuristic computer engine"},
                {"scene_number": 2, "narration_chunk": "Suddenly, a bright white light flashed.", "visual_prompt": f"{art_style} blinding light explosion inside dark technical server room"}
            ]

        input_content = story_text if story_text else f"Write a complete video script about: {prompt}"
        
        system_instructions = (
            "You are a video editor. Breakdown input text into a chronological array of distinct visual scenes. "
            "Respond ONLY with a valid minified JSON array matching this exact format: "
            '[{"scene_number": 1, "narration_chunk": "text description to speak", "visual_prompt": "highly detailed descriptive prompt"}]'
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_instructions},
                        {"role": "user", "content": f"Style: {art_style}. Content: {input_content}"}
                    ],
                    "response_format": {"type": "json_object"}
                },
                timeout=30.0
            )
            result = response.json()
            raw_content = result["choices"][0]["message"]["content"]
            # Handle potential nested JSON dictionary wrappers safely
            parsed = json.loads(raw_content)
            return parsed if isinstance(parsed, list) else parsed.get("scenes", [])