import json
import subprocess

import pytest

from tests.conftest import wait_for

SCRIPT = (
    'Ada walked into the old lighthouse at dawn. She carried a brass lantern and a worn map. "We are late," said Ada.\n'
    'Her brother Tunde looked at the sea. He had never seen the harbor so quiet. "Then we should hurry," Tunde whispered.\n'
    "Inside the lighthouse the stairs were steep. Ada lit the lantern and climbed."
)


def make_series(client, **kw):
    r = client.post("/api/series", json={"title": "The Lighthouse Keepers", "premise": "Siblings and a lighthouse",
                                         "art_style": "Watercolor storybook", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def make_episode(client, series_id, script=SCRIPT, title="Pilot"):
    r = client.post(f"/api/series/{series_id}/episodes", json={"title": title, "script": script})
    assert r.status_code == 201, r.text
    return r.json()


def reach_review(client, ep_id):
    ep = wait_for(client, f"/api/episodes/{ep_id}", lambda e: e["status"] == "review", what="review")
    # reference images are generated in the background after analysis
    return wait_for(client, f"/api/episodes/{ep_id}", lambda e: all(a["image_status"] == "ready" for a in e["assets"]),
                    what="asset images")


def approve_all(client, ep_id):
    r = client.post(f"/api/episodes/{ep_id}/assets/approve-all")
    assert r.status_code == 200, r.text
    assert r.json()["skipped_without_image"] == []


def test_full_pipeline_with_approval_gate_corrections_and_render(client, monkeypatch):
    s = make_series(client)
    ep = make_episode(client, s["id"])
    ep = reach_review(client, ep["id"])

    kinds = {a["kind"] for a in ep["assets"]}
    names = {a["name"] for a in ep["assets"]}
    assert {"character", "environment", "prop"} <= kinds
    assert {"Ada", "Tunde"} <= names
    assert all(not a["approved"] for a in ep["assets"])
    assert ep["actions"]["produce"] is False

    # ── THE GATE: nothing is produced until every asset is approved ──
    r = client.post(f"/api/episodes/{ep['id']}/produce")
    assert r.status_code == 409
    assert len(r.json()["detail"]["unapproved"]) == len(ep["assets"])

    # voices can be previewed before approving a character
    ada = next(a for a in ep["assets"] if a["name"] == "Ada")
    pv = client.post("/api/voices/preview", json={"voice_id": ada["voice_id"]})
    assert pv.status_code == 200 and client.get(pv.json()["url"]).status_code == 200

    # changing a character's voice, then approving
    r = client.patch(f"/api/assets/{ada['id']}", json={"voice_id": "british_female"})
    assert r.status_code == 200 and r.json()["voice_id"] == "british_female"

    # correction prompt on a reference image -> new image, and it goes back to "pending" for re-approval
    old_url = ada["image_url"]
    r = client.post(f"/api/assets/{ada['id']}/regenerate-image", json={"correction": "make her hands look natural"})
    assert r.status_code == 202
    new_ada = wait_for(client, f"/api/episodes/{ep['id']}",
                       lambda e: next(a for a in e["assets"] if a["id"] == ada["id"])["image_status"] == "ready",
                       what="ada regenerated")
    assert next(a for a in new_ada["assets"] if a["id"] == ada["id"])["image_url"] != old_url
    assert next(a for a in new_ada["assets"] if a["id"] == ada["id"])["correction_pending"] is False

    approve_all(client, ep["id"])
    ep = client.get(f"/api/episodes/{ep['id']}").json()
    assert ep["actions"]["produce"] is True and ep["blocking_assets"] == []

    # ── produce: plan scenes + scene images ──
    assert client.post(f"/api/episodes/{ep['id']}/produce").status_code == 202
    ep = wait_for(client, f"/api/episodes/{ep['id']}", lambda e: e["status"] in ("scenes_ready", "failed"), what="scenes")
    assert ep["status"] == "scenes_ready", ep.get("error")
    scenes = ep["scenes"]
    assert len(scenes) >= 3 and all(sc["image_url"] for sc in scenes)
    speakers = {sc["speaker"]["name"] if sc["speaker"] else "Narrator" for sc in scenes}
    assert {"Narrator", "Ada", "Tunde"} <= speakers  # dialogue lines are assigned to their characters

    # ── correction prompt on a scene image ──
    target = scenes[1]
    from app.pipeline import orchestrator
    original = orchestrator.generate_scene_image

    async def slow(scene_id):          # the mock is instant; hold the job open so we can observe the in-between state
        import asyncio
        await asyncio.sleep(1.5)
        await original(scene_id)

    monkeypatch.setattr(orchestrator, "generate_scene_image", slow)
    r = client.post(f"/api/scenes/{target['id']}/regenerate-image", json={"correction": "remove the extra person"})
    assert r.status_code == 202
    assert r.json()["image_status"] == "generating" and r.json()["image_url"] is None
    assert client.get(f"/api/episodes/{ep['id']}").json()["actions"]["render"] is False  # can't render mid-regeneration
    assert client.post(f"/api/episodes/{ep['id']}/render").status_code == 409
    monkeypatch.setattr(orchestrator, "generate_scene_image", original)
    ep = wait_for(client, f"/api/episodes/{ep['id']}",
                  lambda e: e["scenes"][1]["image_status"] == "ready", what="scene regenerated")
    assert ep["scenes"][1]["image_url"] != target["image_url"]
    assert ep["scenes"][1]["correction_pending"] is False

    # ── render: per-scene voice + captions + Ken Burns, joined ──
    assert client.post(f"/api/episodes/{ep['id']}/render").status_code == 202
    ep = wait_for(client, f"/api/episodes/{ep['id']}", lambda e: e["status"] in ("completed", "failed"), timeout=240, what="render")
    assert ep["status"] == "completed", ep.get("error")
    assert ep["video_url"] and ep["duration_seconds"] > 3

    video = client.get(ep["video_url"])
    assert video.status_code == 200 and len(video.content) > 10_000
    path = f"/tmp/_e2e_{ep['id']}.mp4"
    open(path, "wb").write(video.content)
    probe = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path]))
    kinds = {st["codec_type"] for st in probe["streams"]}
    vs = next(st for st in probe["streams"] if st["codec_type"] == "video")
    assert kinds == {"video", "audio"}
    assert (vs["width"], vs["height"]) == (1080, 1920)
    assert abs(float(probe["format"]["duration"]) - ep["duration_seconds"]) < 1.0

    # fixing a scene image after render drops the episode back so the stale video can't be shipped
    client.post(f"/api/scenes/{ep['scenes'][0]['id']}/regenerate-image", json={})
    ep2 = wait_for(client, f"/api/episodes/{ep['id']}", lambda e: e["scenes"][0]["image_status"] == "ready", what="regen")
    assert ep2["status"] == "scenes_ready" and ep2["video_url"] is None


def test_editing_an_approved_asset_requires_reapproval(client):
    s = make_series(client)
    ep = reach_review(client, make_episode(client, s["id"])["id"])
    approve_all(client, ep["id"])
    ada = next(a for a in client.get(f"/api/episodes/{ep['id']}").json()["assets"] if a["name"] == "Ada")
    assert ada["approved"]
    client.patch(f"/api/assets/{ada['id']}", json={"description": "Ada, tall, red scarf, braided hair"})
    ep = client.get(f"/api/episodes/{ep['id']}").json()
    assert "Ada" in ep["blocking_assets"]
    assert client.post(f"/api/episodes/{ep['id']}/produce").status_code == 409


def test_second_episode_reuses_approved_assets(client):
    s = make_series(client)
    ep1 = reach_review(client, make_episode(client, s["id"])["id"])
    approve_all(client, ep1["id"])
    ep2 = make_episode(client, s["id"], title="Episode 2", script=(
        'Ada climbed down from the old lighthouse. "Tunde, look at the harbor," said Ada. He nodded and picked up the brass lantern.'))
    ep2 = wait_for(client, f"/api/episodes/{ep2['id']}", lambda e: e["status"] == "review", what="ep2 review")
    assert ep2["number"] == 2
    ada2 = next(a for a in ep2["assets"] if a["name"] == "Ada")
    assert ada2["approved"], "characters approved in episode 1 must carry over to episode 2"


def test_failed_image_stage_is_resumable(client, monkeypatch):
    from app.pipeline import orchestrator
    from app.services.providers.image import MockImage

    s = make_series(client)
    ep = reach_review(client, make_episode(client, s["id"])["id"])
    approve_all(client, ep["id"])

    class Flaky(MockImage):
        calls = 0
        async def generate(self, prompt, aspect, refs):
            Flaky.calls += 1
            if Flaky.calls <= 3 * 4:   # first scenes exhaust all retries
                raise RuntimeError("provider down")
            return await super().generate(prompt, aspect, refs)

    monkeypatch.setattr(orchestrator, "get_image_provider", lambda: Flaky())
    monkeypatch.setattr("app.config.settings.MAX_ATTEMPTS", 1)
    monkeypatch.setattr(orchestrator.asyncio, "sleep", lambda *_: _noop())
    client.post(f"/api/episodes/{ep['id']}/produce")
    failed = wait_for(client, f"/api/episodes/{ep['id']}", lambda e: e["status"] == "failed", what="failure")
    assert failed["failed_stage"] == "imaging"
    assert any(sc["image_status"] == "failed" for sc in failed["scenes"])

    monkeypatch.setattr(orchestrator, "get_image_provider", lambda: MockImage())
    assert client.post(f"/api/episodes/{ep['id']}/retry").status_code == 202
    ok = wait_for(client, f"/api/episodes/{ep['id']}", lambda e: e["status"] == "scenes_ready", what="recovery")
    assert all(sc["image_url"] for sc in ok["scenes"])


async def _noop():
    return None


def test_series_crud_and_validation(client):
    assert client.post("/api/series", json={"title": ""}).status_code == 422
    s = make_series(client)
    assert client.post(f"/api/series/{s['id']}/episodes", json={"title": "x", "script": "short"}).status_code == 422
    assert client.get("/api/series/9999").status_code == 404
    assert any(x["id"] == s["id"] for x in client.get("/api/series").json())
    cfg = client.get("/api/config").json()
    assert cfg["providers"] == {"text": "heuristic", "image": "mock", "voice": "espeak"} and cfg["placeholder_mode"]
    assert client.delete(f"/api/series/{s['id']}").status_code == 204
    assert client.get(f"/api/series/{s['id']}").status_code == 404
