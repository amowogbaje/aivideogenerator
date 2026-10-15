"""
Image providers. All implement  generate(prompt, aspect, references) -> image bytes.

`references` are the approved reference images of the characters/environment in the shot. Only Gemini can use them as
true visual references; the other providers rely on the character descriptions that are always written into the prompt.
"""
import hashlib
import logging
import random
import textwrap
from urllib.parse import quote
from io import BytesIO

import httpx
from PIL import Image, ImageDraw, ImageFont
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger("app.image")

# aspect -> (api size for the model, final stored size)
API_SIZES = {"9:16": (576, 1024), "16:9": (1024, 576), "3:4": (768, 1024), "1:1": (1024, 1024)}
FINAL_SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080), "3:4": (768, 1024), "1:1": (1024, 1024)}


def _transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (408, 425, 429, 500, 502, 503, 504)
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError, RuntimeError)) and "loading" in str(exc).lower() \
        or isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


_retry = retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=30),
               retry=retry_if_exception(_transient), reraise=True)


def finalize(raw: bytes, aspect: str) -> bytes:
    """Cover-crops to the exact target size and stores as JPEG, so every provider yields identical framing."""
    tw, th = FINAL_SIZES[aspect]
    img = Image.open(BytesIO(raw)).convert("RGB")
    scale = max(tw / img.width, th / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - tw) // 2, (img.height - th) // 2
    img = img.crop((left, top, left + tw, top + th))
    out = BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue()


# ───────────────────────── mock (offline) ─────────────────────────
class MockImage:
    name = "mock"

    async def generate(self, prompt: str, aspect: str, references: list[bytes]) -> bytes:
        w, h = API_SIZES[aspect]
        seed = int(hashlib.md5((prompt + str(random.random())).encode()).hexdigest()[:8], 16)
        rnd = random.Random(seed)
        c1 = tuple(rnd.randint(30, 140) for _ in range(3))
        c2 = tuple(rnd.randint(90, 230) for _ in range(3))
        img = Image.new("RGB", (w, h), c1)
        px = ImageDraw.Draw(img)
        for y in range(h):  # vertical gradient
            t = y / h
            px.line([(0, y), (w, y)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
        d = ImageDraw.Draw(img)
        try:
            big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(22, w // 18))
            small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(14, w // 32))
        except OSError:
            big = small = ImageFont.load_default()
        # a crude figure so mock scenes look like "scenes", not blank cards
        cx, cy = w // 2, int(h * 0.55)
        d.ellipse([cx - w // 10, cy - h // 6, cx + w // 10, cy - h // 6 + w // 5], fill=(20, 20, 30))
        d.rounded_rectangle([cx - w // 6, cy - h // 6 + w // 5, cx + w // 6, cy + h // 4], radius=w // 14, fill=(20, 20, 30))
        d.text((w // 20, h // 24), f"MOCK · {aspect}", font=small, fill=(255, 255, 255))
        y = h // 12
        fix = None
        if "fix this:" in prompt:  # surface the correction note so it's visible that it reached the model
            body, fix = prompt.rsplit("fix this:", 1)
        else:
            body = prompt
        body = body.split("CORRECTION REQUIRED")[0]
        for line in textwrap.wrap(body.replace("\n", " "), width=max(18, w // 22))[:9]:
            d.text((w // 20, y), line, font=big if y == h // 12 else small, fill=(255, 255, 255)); y += max(24, w // 16)
        if fix:
            y = int(h * 0.82)
            d.rectangle([0, y - 10, w, h], fill=(120, 20, 20))
            for line in textwrap.wrap("APPLIED FIX: " + fix.strip(), width=max(18, w // 24))[:6]:
                d.text((w // 20, y), line, font=small, fill=(255, 255, 255)); y += max(20, w // 28)
        out = BytesIO(); img.save(out, "PNG")
        return out.getvalue()


# ───────────────────────── Gemini ─────────────────────────
class GeminiImage:
    name = "gemini"
    MODEL = "gemini-2.5-flash-image"

    async def generate(self, prompt: str, aspect: str, references: list[bytes]) -> bytes:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        parts: list = []
        if references:
            parts.append("Reference images of the characters/setting follow. Keep every character's face, hair, clothing "
                         "and the setting's look consistent with them.")
            parts += [types.Part.from_bytes(data=r, mime_type="image/jpeg") for r in references[:4]]
        parts.append(f"{prompt}\nCompose for a {aspect} frame.")
        resp = await client.aio.models.generate_content(
            model=self.MODEL, contents=parts,
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]))
        for cand in resp.candidates or []:
            for part in cand.content.parts or []:
                if part.inline_data and part.inline_data.data:
                    return part.inline_data.data
        raise RuntimeError("Gemini returned no image (it may have refused the prompt)")


# ───────────────────────── FLUX hosts ─────────────────────────
class HuggingFaceImage:
    name = "huggingface"
    URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"

    @_retry
    async def generate(self, prompt: str, aspect: str, references: list[bytes]) -> bytes:
        w, h = API_SIZES[aspect]
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(self.URL, headers={"Authorization": f"Bearer {settings.HF_API_KEY}"},
                             json={"inputs": prompt, "parameters": {"width": w, "height": h}})
        if r.status_code == 503:
            raise RuntimeError("Model is loading, retry shortly")
        r.raise_for_status()
        return r.content


class DeepInfraImage:
    name = "deepinfra"

    @_retry
    async def generate(self, prompt: str, aspect: str, references: list[bytes]) -> bytes:
        w, h = API_SIZES[aspect]
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post("https://api.deepinfra.com/v1/openai/images/generations",
                             headers={"Authorization": f"Bearer {settings.DEEPINFRA_API_KEY}"},
                             json={"model": "black-forest-labs/FLUX-1-schnell", "prompt": prompt, "size": f"{w}x{h}"})
            r.raise_for_status()
            item = r.json()["data"][0]
            if item.get("b64_json"):
                import base64
                return base64.b64decode(item["b64_json"])
            img = await c.get(item["url"]); img.raise_for_status()
            return img.content


class TogetherImage:
    name = "together"

    @_retry
    async def generate(self, prompt: str, aspect: str, references: list[bytes]) -> bytes:
        w, h = API_SIZES[aspect]
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post("https://api.together.xyz/v1/images/generations",
                             headers={"Authorization": f"Bearer {settings.TOGETHER_API_KEY}"},
                             json={"model": "black-forest-labs/FLUX.1-schnell-Free", "prompt": prompt,
                                   "width": w, "height": h, "steps": 4, "n": 1})
            r.raise_for_status()
            item = r.json()["data"][0]
            if item.get("b64_json"):
                import base64
                return base64.b64decode(item["b64_json"])
            img = await c.get(item["url"]); img.raise_for_status()
            return img.content


class PollinationsImage:
    name = "pollinations"

    @_retry
    async def generate(self, prompt: str, aspect: str, references: list[bytes]) -> bytes:
        w, h = API_SIZES[aspect]
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as c:
            r = await c.get("https://image.pollinations.ai/prompt/" + quote(prompt[:1500], safe=""),
                            params={"width": w, "height": h, "nologo": "true"})
            r.raise_for_status()
            return r.content


def get_image_provider():
    choice = settings.IMAGE_PROVIDER.lower()
    if choice == "auto":
        choice = ("gemini" if settings.GEMINI_API_KEY else "huggingface" if settings.HF_API_KEY
                  else "together" if settings.TOGETHER_API_KEY else "deepinfra" if settings.DEEPINFRA_API_KEY else "mock")
    table = {"mock": (MockImage, None), "gemini": (GeminiImage, settings.GEMINI_API_KEY),
             "huggingface": (HuggingFaceImage, settings.HF_API_KEY), "deepinfra": (DeepInfraImage, settings.DEEPINFRA_API_KEY),
             "together": (TogetherImage, settings.TOGETHER_API_KEY), "pollinations": (PollinationsImage, None)}
    if choice not in table:
        raise ValueError(f"Unknown IMAGE_PROVIDER '{settings.IMAGE_PROVIDER}'")
    cls, key = table[choice]
    if choice in ("gemini", "huggingface", "deepinfra", "together") and not key:
        raise RuntimeError(f"IMAGE_PROVIDER={choice} but its API key is empty")
    return cls()
