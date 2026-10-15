"""Prompt composition for image generation. Kept separate so the wording can be tuned without touching the pipeline."""
from app.models import Asset, Scene, Series
from app.services.providers.text import NARRATOR  # noqa: F401  (re-exported for convenience)

MAX_CORRECTION = 1000


def clean_correction(text: str | None) -> str | None:
    text = (text or "").strip()
    return text[:MAX_CORRECTION] or None


def apply_correction(prompt: str, correction: str | None) -> str:
    """Same contract as CraftProfessor's ImageCorrection: the user's note is added LAST so it outranks the original
    wording, and the caller clears it once an image renders so a plain regenerate starts clean."""
    correction = clean_correction(correction)
    if not correction:
        return prompt
    return (f"{prompt}\n\nCORRECTION REQUIRED: an earlier render of this same image had a problem. "
            f"Keep the concept, composition and style described above, but fix this: {correction}")


ASSET_ASPECT = {"character": "3:4", "environment": "16:9", "prop": "1:1"}


def asset_prompt(series: Series, asset: Asset) -> str:
    style = series.art_style.strip().rstrip(".")
    if asset.kind == "character":
        base = (f"{style}. Character reference portrait: full-body, front-facing, centered, neutral studio background. "
                f"{asset.name} — {asset.description}. No text, no watermark.")
    elif asset.kind == "environment":
        base = (f"{style}. Establishing shot of the location '{asset.name}': {asset.description}. "
                "No people in frame. No text, no watermark.")
    else:
        base = (f"{style}. A single object, '{asset.name}': {asset.description}. Centered on a plain neutral background. "
                "No text, no watermark.")
    return apply_correction(base, asset.correction_prompt)


def scene_prompt(series: Series, scene: Scene, env: Asset | None, chars: list[Asset], props: list[Asset]) -> str:
    parts = [f"{series.art_style.strip().rstrip('.')}.", scene.visual_prompt.strip()]
    if env:
        parts.append(f"Setting — {env.name}: {env.description}")
    if chars:
        parts.append("Characters in frame (they must look exactly like their reference): "
                     + "; ".join(f"{c.name}: {c.description}" for c in chars))
    if props:
        parts.append("Props: " + "; ".join(f"{p.name}: {p.description}" for p in props))
    parts.append(f"Cinematic {series.aspect_ratio} composition. No text, no captions, no watermark, no borders.")
    return apply_correction("\n".join(p for p in parts if p), scene.correction_prompt)
