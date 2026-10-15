# AI Story Studio

Write a **series**, add **episodes**, review and approve the **cast, places and props**, then let the studio turn each
episode into **scene images → a narrated, captioned video**.

```
Series ─ Episode script ─▶ ① analyze ─▶ ② YOU review & approve ─▶ ③ scene images ─▶ ④ voice + captions + video
                            characters       (look, voice,            (consistent with        per-scene voices,
                            environments      description,             the approved             burned-in captions,
                            props             fix with a note)         references)             Ken Burns, one MP4
```

The approval gate is enforced by the API, not just the UI: `POST /api/episodes/{id}/produce` returns **409** until every
character, environment and prop of that episode is approved. Approved assets belong to the **series**, so a character
looks and sounds the same in every episode.

## Run it

**Needs:** Python 3.11+, Node 20+, `ffmpeg` (with libass). Optional: `espeak-ng` (offline voices).

```bash
# 1. backend  (http://localhost:8000, API docs at /docs)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # works as-is: with no keys it uses demo providers
uvicorn app.main:app --reload

# 2. frontend (http://localhost:5173, proxies /api and /media to :8000)
cd frontend
npm install
npm run dev
```

Single process instead: `cd frontend && npm run build`, then run only the backend — it serves the built UI on :8000.
Docker: `cp backend/.env.example backend/.env && docker compose up --build` (not tested in my environment).

### Real output vs. demo mode
With no API keys everything still runs end to end using **demo providers** (rule-based script analysis, placeholder
images, robotic offline voice). A banner in the UI tells you. For real output set keys in `backend/.env`:

| What | Setting | Notes |
|---|---|---|
| Script analysis + scene planning | `GEMINI_API_KEY` | `TEXT_PROVIDER=auto` picks Gemini when a key exists |
| Images | `GEMINI_API_KEY` (uses your approved references for consistency) or `HF_API_KEY` / `TOGETHER_API_KEY` / `DEEPINFRA_API_KEY` / `pollinations` (no key) | other providers rely on the text descriptions |
| Voices | `ELEVENLABS_API_KEY`, or free Edge TTS (default, needs internet), or `espeak` offline | characters store a voice *profile*, so switching provider never loses their voice |

## Using it
1. **New series** — title, premise, art style (applied to every image), format (9:16 / 16:9), narrator voice.
2. **Add episode** — paste the script. Dialogue in "quotes" is voiced by the character who says it.
3. **Review** — each character/environment/prop has a reference image and a visual description. You can edit the
   description, change a character's voice (▶ Preview), **Fix image…** with a note (“hands look wrong”), regenerate, add
   anything that was missed, then **Approve**. Editing something un-approves it.
4. **Generate scene images**, then use **Fix image…** on any scene that came out wrong. You can also edit what a scene
   says or who speaks it.
5. **Render video** — per-scene voice, captions timed to the real audio length, gentle zoom, joined into one MP4.

Failures are resumable: **Retry** continues from the stage that failed and keeps finished images/voices/clips.

## Layout
```
backend/app
  models.py                  Series / Episode / Asset / Scene + status vocabularies
  pipeline/orchestrator.py   analyze → produce → render (idempotent, DB-driven stages)
  pipeline/prompts.py        prompt composition + the correction-note contract
  pipeline/runner.py         in-process background jobs
  api/                       series, episodes, assets, scenes, config/voice-preview
  services/providers/        text (Gemini | heuristic), image (Gemini, HF, Together, DeepInfra, Pollinations, mock), voice
  services/{video,captions,ffmpeg_util,voices,storage}.py
frontend/src                 React + TypeScript + Vite (pages/, components/)
```

## Tests
```bash
cd backend && pytest -q                  # API workflow: gate, approvals, corrections, render, resume (real ffmpeg)
# UI test: start the backend with demo providers (TEXT_PROVIDER=heuristic IMAGE_PROVIDER=mock VOICE_PROVIDER=espeak), then
cd frontend && npm run test:e2e          # drives the real React app through the whole flow
```

## Honest limits
- Gemini, ElevenLabs, Edge TTS, HF/Together/DeepInfra/Pollinations code paths are written but were **not exercised** here
  (no keys/network in my sandbox); the demo providers and the whole pipeline were.
- Single user, no auth. Tables are created with `create_all` (add Alembic before you evolve the schema).
- Jobs run in-process; a restart marks in-flight work failed and you press Retry. Moving to Celery/RQ means wrapping the
  orchestrator functions in tasks — they're already idempotent.
- Captions are phrase-timed across each scene's real audio length, not word-synced.
- The old Fal image-to-video path was not ported; scenes use a Ken Burns move on the still.
