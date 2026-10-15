"""
Text providers: turn a script into (1) a "story bible" of characters / environments / props and (2) a scene plan.

  gemini     — real analysis (needs GEMINI_API_KEY)
  heuristic  — offline, rule-based. Crude by design: it exists so the whole app runs end-to-end with no keys, and
               because the human reviews every extracted asset anyway. Don't judge output quality by it.
"""
import logging
import re
from collections import Counter
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.services import voices

logger = logging.getLogger("app.text")

NARRATOR = "Narrator"


# ── shared data shapes (also used as Gemini response schemas) ─────────────────────────────
class CharacterOut(BaseModel):
    name: str = Field(description="Character's name exactly as used in the script")
    description: str = Field(description="Purely VISUAL description: age, build, face, hair, clothing, distinguishing features")
    gender: str = Field(default="unknown", description="male, female or unknown")
    age: str = Field(default="adult", description="child, young, adult or elder")


class PlaceOut(BaseModel):
    name: str = Field(description="Short name of the location or object")
    description: str = Field(description="Purely VISUAL description: architecture/materials/lighting/mood for places; shape/material/colour for objects")


class BibleOut(BaseModel):
    characters: list[CharacterOut] = Field(default_factory=list)
    environments: list[PlaceOut] = Field(default_factory=list)
    props: list[PlaceOut] = Field(default_factory=list)


class SceneOut(BaseModel):
    narration_text: str = Field(description="Exactly what is spoken aloud in this scene")
    speaker: str = Field(description="'Narrator' or the exact name of the character speaking")
    visual_prompt: str = Field(description="What the image shows: action, framing, mood. No text/captions in the image")
    environment: str = Field(default="", description="Exact name of one environment from the provided list, or empty")
    characters: list[str] = Field(default_factory=list, description="Exact names of characters visible in the frame")
    props: list[str] = Field(default_factory=list, description="Exact names of props visible in the frame")


class PlanOut(BaseModel):
    scenes: list[SceneOut]


@dataclass
class AssetInfo:
    name: str
    description: str


@dataclass
class Context:
    series_title: str
    premise: str
    art_style: str
    script: str
    known_characters: list[AssetInfo] = field(default_factory=list)
    known_environments: list[AssetInfo] = field(default_factory=list)
    known_props: list[AssetInfo] = field(default_factory=list)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text.strip())
    parts = re.split(r'(?<=[.!?])["”\']?\s+(?=["“A-Z0-9])', text)
    return [p.strip() for p in parts if p.strip()]


# ═══════════════════════════ Gemini ═══════════════════════════
class GeminiText:
    name = "gemini"
    MODEL = "gemini-2.5-flash"

    async def _generate(self, system: str, prompt: str, schema):
        from google import genai
        from google.genai.errors import ServerError
        from google.genai.types import GenerateContentConfig

        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10),
               retry=retry_if_exception_type(ServerError), reraise=True)
        async def call():
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            resp = await client.aio.models.generate_content(
                model=self.MODEL,
                contents=prompt,
                config=GenerateContentConfig(system_instruction=system, response_mime_type="application/json",
                                             response_schema=schema, temperature=0.4),
            )
            if resp.parsed is None:
                raise RuntimeError("Gemini returned no parseable JSON")
            return resp.parsed

        return await call()

    async def extract_bible(self, ctx: Context) -> BibleOut:
        known = _known_block(ctx)
        system = (
            "You are a film pre-production assistant. From a story script you extract the recurring visual assets a "
            "storyboard artist needs. Descriptions must be purely visual (never plot or personality) and detailed "
            "enough to draw the same thing consistently across many images. Do not invent characters, places or "
            "objects that are not in the script."
        )
        prompt = (
            f"Series: {ctx.series_title}\nPremise: {ctx.premise}\nArt style: {ctx.art_style}\n\n{known}\n"
            "Extract: every named or recurring CHARACTER (with gender and age bracket), every distinct ENVIRONMENT, "
            "and only the PROPS that matter visually or to the plot (max 8). If an item is the same entity as a KNOWN "
            "asset, reuse its exact name. For narration-only scripts do not invent a character for the narrator.\n\n"
            f"SCRIPT:\n{ctx.script}"
        )
        return await self._generate(system, prompt, BibleOut)

    async def plan_scenes(self, ctx: Context, max_scenes: int) -> list[SceneOut]:
        names = lambda xs: ", ".join(a.name for a in xs) or "(none)"
        system = (
            "You are a storyboard director turning a script into scenes for a short vertical video. Cover the ENTIRE "
            "script in order; do not summarise or skip text. Each scene is spoken by one voice."
        )
        prompt = (
            f"Art style: {ctx.art_style}\n"
            f"CHARACTERS: {names(ctx.known_characters)}\nENVIRONMENTS: {names(ctx.known_environments)}\nPROPS: {names(ctx.known_props)}\n\n"
            f"Rules:\n- Produce at most {max_scenes} scenes, each roughly 8-20 seconds of speech (about 20-50 words).\n"
            "- speaker is 'Narrator' for narration, or one CHARACTER name for a line of dialogue. For dialogue, "
            "narration_text is only the words spoken (no quotation marks, no 'he said').\n"
            "- environment, characters and props must use the EXACT names listed above (or be empty).\n"
            "- visual_prompt describes what is SEEN (action, camera framing, mood) and must not include text or captions.\n\n"
            f"SCRIPT:\n{ctx.script}"
        )
        plan = await self._generate(system, prompt, PlanOut)
        return plan.scenes


def _known_block(ctx: Context) -> str:
    def fmt(title, items):
        return f"{title}:\n" + ("\n".join(f"- {a.name}: {a.description}" for a in items) if items else "- (none yet)")
    return "\n".join([fmt("KNOWN CHARACTERS", ctx.known_characters), fmt("KNOWN ENVIRONMENTS", ctx.known_environments),
                      fmt("KNOWN PROPS", ctx.known_props)])


# ═══════════════════════════ Heuristic (offline) ═══════════════════════════
_STOP = set("""The A An He She They It We You I His Her Their Its Our My Your But And Or So Then When While As If Because
After Before Suddenly Finally Meanwhile One Once Every Each All Some Many Most Then There Here This That These Those What
Who Why How Where Which Not No Yes Now Today Tomorrow Yesterday Monday Tuesday Wednesday Thursday Friday Saturday Sunday
January February March April May June July August September October November December Chapter Episode Part Inside Outside
Under Over Behind Beyond Across Through Into Onto Upon Within Without Still Soon Later Maybe Perhaps Just Even Only Also
Again Never Always Often Sometimes However Instead Yet Though Although Until Since""".split())
_TITLES = r"(?:Captain|Dr|Mr|Mrs|Ms|Miss|Professor|King|Queen|Prince|Princess|Aunty|Auntie|Uncle|Mama|Papa|Chief|Old)"
_SPEECH_VERBS = r"(?:said|asked|whispered|replied|shouted|called|cried|laughed|smiled|nodded|sighed|answered|muttered|yelled)"
_PLACE_NOUNS = ("forest cave castle village city town market beach river house room kitchen lab laboratory street mountain "
                "desert ship station garden school hospital office shop tower temple farm harbor harbour lagoon island road "
                "bridge palace hut compound lake field stadium church mosque cafe bedroom hallway library tavern inn port "
                "jungle valley hill cliff ocean sea sky camp base ruins basement attic yard courtyard square rooftop alley "
                "workshop studio palace classroom hall lighthouse").split()
_PROP_NOUNS = ("sword key lantern map book letter phone necklace ring bag box knife camera car bicycle umbrella basket drum "
               "mask crown staff scroll coin diary radio torch rope shield bottle mirror clock watch cup pot suitcase laptop "
               "flower wand amulet compass backpack notebook photograph painting guitar candle hammer lamp trophy ticket "
               "package parcel helmet cloak robe hat bracelet pendant spear bow arrow flag boat canoe").split()
_AGE_CHILD = r"\b(child|kid|boy|girl|toddler|little)\b"
_AGE_ELDER = r"\b(elderly|aged|grandmother|grandfather|granny|grandpa|old (man|woman|lady|gentleman)|wise old)\b"
_AGE_YOUNG = r"\b(young|teen|teenage|teenager|student|youth)\b"


class HeuristicText:
    name = "heuristic"

    async def extract_bible(self, ctx: Context) -> BibleOut:
        text = ctx.script
        sents = split_sentences(text)
        return BibleOut(
            characters=self._characters(text, sents),
            environments=self._places(text, sents, _PLACE_NOUNS, prepositional=True),
            props=self._places(text, sents, _PROP_NOUNS, prepositional=False)[:6],
        )

    # characters ------------------------------------------------------
    def _characters(self, text: str, sents: list[str]) -> list[CharacterOut]:
        pat = re.compile(rf"\b({_TITLES}\.?\s)?([A-Z][a-z]{{2,}})\b")
        counts: Counter = Counter()
        place_prefixed: Counter = Counter()
        strong: set[str] = set()
        display: dict[str, str] = {}
        for m in pat.finditer(text):
            title, word = m.group(1), m.group(2)
            if word in _STOP or word in {t.title() for t in _PLACE_NOUNS}:
                continue
            key = word
            display.setdefault(key, f"{title.strip('. ').strip()} {word}".strip() if title else word)
            counts[key] += 1
            before = text[max(0, m.start() - 12):m.start()].lower()
            after = text[m.end():m.end() + 14].lower()
            if re.search(r"\b(in|at|to|from|near|of|across|through|into)\s+$", before):
                place_prefixed[key] += 1
            if re.search(rf"\b(named|called)\s+$", before) or re.search(rf"\b{_SPEECH_VERBS}\s+$", before) \
                    or re.match(rf"\s*{_SPEECH_VERBS}\b", after) or re.match(r"\s*(had|was|is|ran|walked|looked|opened|took)\b", after):
                strong.add(key)
        out: list[CharacterOut] = []
        for key, n in counts.most_common():
            if place_prefixed[key] > n / 2:
                continue
            if n < 2 and key not in strong:
                continue
            ctx_sent = next((s for s in sents if re.search(rf"\b{key}\b", s)), "")
            # Pronouns/age cues are read from the first mention onward — the same sentence AFTER the name plus the next
            # one — so "Her brother Tunde looked up. He smiled." counts "He", not the "Her" that refers to someone else.
            i = next((k for k, x in enumerate(sents) if re.search(rf"\b{key}\b", x)), 0)
            tail = sents[i][re.search(rf"\b{key}\b", sents[i]).end():] + " " + (sents[i + 1] if i + 1 < len(sents) else "")
            he = len(re.findall(r"\b(he|him|his)\b", tail, re.I))
            she = len(re.findall(r"\b(she|her|hers)\b", tail, re.I))
            gender = "male" if he > she else "female" if she > he else "unknown"
            cue = f"{sents[i]} {tail}"
            age = ("child" if re.search(_AGE_CHILD, cue, re.I) else "elder" if re.search(_AGE_ELDER, cue, re.I)
                   else "young" if re.search(_AGE_YOUNG, cue, re.I) else "adult")
            noun = {"male": "man", "female": "woman"}.get(gender, "person")
            if age == "child":
                noun = {"male": "boy", "female": "girl"}.get(gender, "child")
            desc = f"{display[key]}, {'an' if age in ('elder', 'adult') else 'a'} {age} {noun}. From the script: {ctx_sent[:220]}"
            out.append(CharacterOut(name=display[key], description=desc, gender=gender, age=age))
            if len(out) >= 8:
                break
        return out

    # environments / props --------------------------------------------
    def _places(self, text: str, sents: list[str], nouns: list[str], prepositional: bool) -> list[PlaceOut]:
        alt = "|".join(nouns)
        lead = r"(?:in|inside|at|into|through|near|across|beneath|under|outside|toward|towards|from|to)\s+" if prepositional \
            else r"(?:a|an|the|his|her|their|its|my|our)\s+"
        pat = re.compile(rf"\b{lead}(?:the\s+|a\s+|an\s+|his\s+|her\s+|their\s+)?((?:[a-z]+\s+){{0,2}}(?:{alt}))\b", re.I)
        seen: dict[str, str] = {}
        for s in sents:
            for m in pat.finditer(s):
                phrase = m.group(1).lower()
                words = [w for w in phrase.split() if w not in {"the", "a", "an", "his", "her", "their", "its", "my", "our",
                                                               "and", "with", "of", "to", "in", "on", "that", "was", "were", "had"}]
                if not words or words[-1] not in nouns:
                    continue
                key = " ".join(words[-2:]) if len(words) > 1 else words[0]
                seen.setdefault(key, s)
        # "brass lantern" and "lantern" are the same thing: keep only the longer phrase.
        keys = [k for k in seen if not any(o != k and o.endswith(" " + k) for o in seen)]
        return [PlaceOut(name=k.title(), description=f"{k.title()}. From the script: {seen[k][:220]}") for k in keys[:5 if prepositional else 8]]

    # scene plan ------------------------------------------------------
    async def plan_scenes(self, ctx: Context, max_scenes: int) -> list[SceneOut]:
        chars = ctx.known_characters
        envs = ctx.known_environments
        props = ctx.known_props
        beats: list[dict] = []
        for s in split_sentences(ctx.script):
            quotes = re.findall(r'[“"]([^”"]+)[”"]', s)
            qlen = sum(len(q) for q in quotes)
            if quotes and qlen >= 0.5 * len(s):
                outside = re.sub(r'[“"][^”"]+[”"]', " ", s)
                who = next((c.name for c in chars if re.search(rf"\b{re.escape(c.name.split()[-1])}\b", outside)), None)
                beats.append({"text": " ".join(q.strip() for q in quotes), "speaker": who or NARRATOR, "src": s, "dialogue": bool(who)})
            else:
                beats.append({"text": re.sub(r'[“”"]', "", s), "speaker": NARRATOR, "src": s, "dialogue": False})

        # merge consecutive narrator beats into scenes of up to ~220 chars / 2 sentences
        merged: list[dict] = []
        for b in beats:
            prev = merged[-1] if merged else None
            if prev and not b["dialogue"] and not prev["dialogue"] and prev["n"] < 2 and len(prev["text"]) + len(b["text"]) < 220:
                prev["text"] += " " + b["text"]
                prev["src"] += " " + b["src"]
                prev["n"] += 1
            else:
                merged.append({**b, "n": 1})
        # respect the cap by merging the shortest neighbours
        while len(merged) > max_scenes and len(merged) > 1:
            i = min(range(len(merged) - 1), key=lambda k: len(merged[k]["text"]) + len(merged[k + 1]["text"]))
            merged[i]["text"] += " " + merged[i + 1]["text"]
            merged[i]["src"] += " " + merged[i + 1]["src"]
            del merged[i + 1]

        scenes: list[SceneOut] = []
        last_env = envs[0].name if envs else ""
        for b in merged:
            src = b["src"]
            env = last_env
            for e in envs:
                if re.search(rf"\b{re.escape(e.name.lower())}\b", src.lower()) or re.search(rf"\b{re.escape(e.name.lower().split()[-1])}\b", src.lower()):
                    env = e.name
            last_env = env
            present = [c.name for c in chars if re.search(rf"\b{re.escape(c.name.split()[-1])}\b", src)]
            if b["speaker"] != NARRATOR and b["speaker"] not in present:
                present.append(b["speaker"])
            used_props = [p.name for p in props if re.search(rf"\b{re.escape(p.name.lower().split()[-1])}\b", src.lower())]
            action = re.sub(r'[“”"]', "", src)
            scenes.append(SceneOut(narration_text=b["text"], speaker=b["speaker"], visual_prompt=action[:300],
                                   environment=env, characters=present, props=used_props))
        return scenes


# ═══════════════════════════ factory ═══════════════════════════
def get_text_provider():
    choice = settings.TEXT_PROVIDER.lower()
    if choice == "auto":
        choice = "gemini" if settings.GEMINI_API_KEY else "heuristic"
    if choice == "gemini":
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("TEXT_PROVIDER=gemini but GEMINI_API_KEY is empty")
        return GeminiText()
    if choice == "heuristic":
        return HeuristicText()
    raise ValueError(f"Unknown TEXT_PROVIDER '{settings.TEXT_PROVIDER}'")
