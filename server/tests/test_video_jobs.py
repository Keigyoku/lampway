"""Video in the Client: the video_gen / video_upscale services on the job queue, from OpenRouter's videos API and from Higgsfield, with staged
uploads (POST /api/v1/uploads/<kind> -> an s3_key), results as result_files VIDEO, and the credit spend on Higgsfield behind the SAME confirm
gate as the Studios (only the captain confirms; nothing is submitted before). Fakes: an OpenRouter videos API (catalogue fixture) and the
Higgsfield fake built from the SPEC."""

import json
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

from lampway_server import higgsfield as HF
from lampway_server import higgsfield_auth as HA
from lampway_server import higgsfield_mcp as HM
from lampway_server import videogen as VG
from lampway_server.agent.providers.openrouter import SpendLedger
from lampway_server.app import create_app
from lampway_server.videojobs import VideoSystem

from .fake_client import FakeMixarClient
from .fake_higgsfield import FakeHiggsfield

FIX = json.loads((Path(__file__).parent / "fixtures" / "video_models.json").read_text())
MODELS = FIX.get("data", FIX)
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"video-bytes"
PNG = b"\x89PNG\r\n\x1a\n" + b"x"


class FakeOpenRouterVideo:
    def __init__(self):
        self.posts, self.cost = [], 0.12

    def handle(self, request):
        path = request.url.path
        if request.method == "GET" and path.endswith("/videos/models"):
            return httpx.Response(200, json={"data": MODELS})
        if request.method == "POST" and path.endswith("/videos"):
            self.posts.append(json.loads(request.content))
            return httpx.Response(202, json={"id": "j1", "polling_url": "/api/v1/videos/j1", "status": "pending"})
        if request.method == "GET" and path.endswith("/videos/j1"):
            return httpx.Response(200, json={"id": "j1", "status": "completed", "unsigned_urls": ["https://openrouter.ai/api/v1/videos/j1/content?index=0"],
                                              "usage": {"cost": self.cost}})
        if "/content" in path:
            return httpx.Response(200, content=MP4, headers={"content-type": "video/mp4"})
        return httpx.Response(404)


@pytest.fixture
def stack(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(settings.state_dir))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-" + "ab12" * 16)
    orv, hf = FakeOpenRouterVideo(), FakeHiggsfield()
    ledger = SpendLedger(5.0, tmp_path / "spend.jsonl")
    client = VG.VideoClient(transport=httpx.MockTransport(orv.handle), ledger=ledger, poll_s=0.0, max_job_usd=2.0)
    auth = HA.HiggsfieldAuth(settings.state_dir, http=httpx.Client(transport=hf.transport()))
    higgs = HF.Higgsfield(HM.HiggsfieldMCP(auth, transport=hf.transport()), http_transport=hf.transport(), poll_s=0.0, wait_timeout_s=5.0)
    system = VideoSystem(settings, client, higgs, auth, root=tmp_path / "root", probe=lambda path: {"duration": 4.0, "width": 640, "height": 360})
    app = create_app(settings, video=system, higgsfield_auth=auth)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        yield fake, orv, hf, auth, ledger, app


def sign_in_higgsfield(auth, hf):
    a = auth.start_login()
    auth.complete_login(hf.authorize(a.url))


def submit(fake, service, model, payload):
    r = fake.post("/api/v1/job-queue/jobs", json={"service": service, "model": model, "payload": payload})
    assert r.status_code == 200, r.text
    return r.json()["data"]["job_id"]


def wait_for(fake, job_id, states=("succeeded", "failed", "cancelled"), timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        snap = fake.get(f"/api/v1/job-queue/jobs/{job_id}").json()["data"]
        if snap["state"] in states:
            return snap
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} never reached {states}: {snap}")


def upload(fake, kind, data, name="a.bin", ctype="application/octet-stream"):
    r = fake.post(f"/api/v1/uploads/{kind}", content=data, headers={"Content-Type": ctype, "X-File-Name": name})
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ------------------------------------------------------------------------------------------ catalogue
def test_without_a_key_and_a_sign_in_no_video_capability_is_advertised(settings, monkeypatch, tmp_path):
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(settings.state_dir))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LAMPWAY_OPENROUTER_KEY_FILE", raising=False)
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        keys = [c["key"] for c in fake.get("/api/v1/generation-catalog").json()["data"]["capabilities"]]
        assert "video_gen" not in keys and "video_upscale" not in keys


def test_the_catalogue_fills_the_clients_video_surface_from_the_models_own_lists(stack):
    fake, orv, hf, auth, *_ = stack
    caps = {c["key"]: c for c in fake.get("/api/v1/generation-catalog").json()["data"]["capabilities"]}
    assert {"video_gen", "video_upscale"} <= set(caps)
    svc = caps["video_gen"]["services"][0]
    assert svc["key"] == "video_gen"
    models = {m["slug"]: m for m in svc["models"]}
    assert len(models) == 28 and "black-forest-labs/flux-video-upscale" not in models
    hey = models["heygen/heygen-video-1"]
    assert hey["is_default"] is True and hey["parameters"]["duration"]["enum"][:2] == [5, 6] and hey["parameters"]["resolution"]["enum"] == ["480p", "768p"]
    assert hey["parameters"]["resolution"]["default"] == "768p" and "generate_audio" not in hey["parameters"]
    seed = models["bytedance/seedance-1-5-pro"]
    assert seed["parameters"]["image_mode"]["enum"] == ["first_frame", "first_last_frame", "reference"] and seed["parameters"]["generate_audio"]["type"] == "boolean"
    spec = {i["kind"]: i for i in svc["input_spec"]["inputs"]}
    assert spec["image"]["multiple"] and spec["video"]["multiple"] and spec["video"]["max_count"] >= 1 and spec["video"]["extensions"] and svc["input_spec"]["max_materials"] > 0
    up = caps["video_upscale"]["services"][0]["models"][0]
    assert up["slug"] == "black-forest-labs/flux-video-upscale" and up["parameters"]["upscale_factor"]["min"] == 1.5 and up["parameters"]["upscale_factor"]["max"] == 3


def test_higgsfield_models_join_the_catalogue_once_signed_in(stack):
    fake, orv, hf, auth, *_ = stack
    before = {m["slug"] for c in fake.get("/api/v1/generation-catalog").json()["data"]["capabilities"] if c["key"] == "video_gen" for m in c["services"][0]["models"]}
    assert not [s for s in before if s.startswith("higgsfield/")]
    sign_in_higgsfield(auth, hf)
    caps = {c["key"]: c for c in fake.get("/api/v1/generation-catalog").json()["data"]["capabilities"]}
    vids = {m["slug"]: m for m in caps["video_gen"]["services"][0]["models"]}
    assert {"higgsfield/seedance1_5", "higgsfield/seedance_2_0", "higgsfield/hf_mult_motion_control", "higgsfield/kling_motion_control"} <= set(vids)
    assert vids["higgsfield/seedance1_5"]["parameters"]["duration"]["enum"] == [4, 8, 12] and "Higgsfield" in vids["higgsfield/seedance1_5"]["label"]
    imgs = {m["slug"] for m in caps["image_gen"]["services"][0]["models"]}
    assert "higgsfield/gpt_image_2_5" in imgs


# ------------------------------------------------------------------------------------------- uploads
def test_uploads_need_a_token_return_a_key_and_the_videos_duration(stack, settings):
    fake, *_ = stack
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as anon:
        assert anon.post("/api/v1/uploads/image", content=PNG).status_code == 401
    img = upload(fake, "image", PNG, "a.png", "image/png")
    vid = upload(fake, "video", MP4, "clip.mp4", "video/mp4")
    assert img["s3_key"] and vid["s3_key"] != img["s3_key"] and vid["duration_seconds"] == 4.0
    assert fake.post("/api/v1/uploads/audio", content=b"x").status_code == 400
    assert fake.post("/api/v1/uploads/image", content=b"").status_code == 400


# --------------------------------------------------------------------------------------- OpenRouter
def test_a_bulk_clip_runs_end_to_end_and_lands_as_a_video_result_file(stack):
    fake, orv, hf, auth, ledger, _ = stack
    jid = submit(fake, "video_gen", "heygen/heygen-video-1", {"prompt": "a lamp dances", "params": {"duration": 5, "resolution": "480p"}})
    snap = wait_for(fake, jid)
    assert snap["state"] == "succeeded", snap
    files = snap["result"]["result_files"]
    assert files[0]["type"] == "VIDEO" and files[0]["url"].endswith(".mp4")
    got = httpx.get(files[0]["url"].replace("http://127.0.0.1:8787", ""), base_url="http://testserver") if False else fake.get(files[0]["url"].split("8787")[1])
    assert got.status_code == 200 and got.content == MP4
    body = orv.posts[0]
    assert body["model"] == "heygen/heygen-video-1" and body["duration"] == 5 and body["resolution"] == "480p"
    assert snap["result"]["actual_usd"] == pytest.approx(0.12) and snap["result"]["estimate_usd"] == pytest.approx(0.10)
    assert ledger.spent == pytest.approx(0.12)


def test_a_job_over_the_per_job_cap_fails_before_anything_is_sent(stack):
    fake, orv, *_ = stack
    jid = submit(fake, "video_gen", "kwaivgi/kling-v3.0-pro", {"prompt": "x", "params": {"duration": 15, "generate_audio": True}})
    snap = wait_for(fake, jid)
    assert snap["state"] == "failed" and "per-job cap" in snap["error"] and orv.posts == []


def test_a_loop_uses_one_image_as_first_and_last_frame(stack):
    fake, orv, *_ = stack
    img = upload(fake, "image", PNG, "a.png", "image/png")
    jid = submit(fake, "video_gen", "bytedance/seedance-1-5-pro", {"prompt": "loop", "params": {"duration": 4, "resolution": "480p", "image_mode": "first_last_frame",
                                                                                     "generate_audio": False}, "reference_image_s3_keys": [img["s3_key"]]})
    assert wait_for(fake, jid)["state"] == "succeeded"
    frames = orv.posts[0]["frame_images"]
    assert [f["frame_type"] for f in frames] == ["first_frame", "last_frame"] and frames[0]["image_url"]["url"] == frames[1]["image_url"]["url"]


def test_motion_transfer_sends_the_reference_video(stack):
    fake, orv, *_ = stack
    img = upload(fake, "image", PNG, "c.png", "image/png")
    vid = upload(fake, "video", MP4, "d.mp4", "video/mp4")
    jid = submit(fake, "video_gen", "bytedance/seedance-2.0-mini", {"prompt": "move like the video", "params": {"duration": 5, "resolution": "480p", "generate_audio": False,
                                                                                                         "image_mode": "reference"},
                                                                 "reference_image_s3_keys": [img["s3_key"]], "reference_video_s3_keys": [vid["s3_key"]]})
    assert wait_for(fake, jid)["state"] == "succeeded"
    kinds = [r["type"] for r in orv.posts[0]["input_references"]]
    assert kinds == ["image_url", "video_url"]


def test_an_upscale_prices_the_output_and_sends_the_source_video(stack):
    fake, orv, hf, auth, ledger, _ = stack
    vid = upload(fake, "video", MP4, "d.mp4", "video/mp4")
    jid = submit(fake, "video_upscale", "black-forest-labs/flux-video-upscale", {"prompt": "", "params": {"upscale_factor": 2, "creativity": 0}, "video_s3_key": vid["s3_key"]})
    snap = wait_for(fake, jid)
    assert snap["state"] == "succeeded", snap
    body = orv.posts[0]
    assert body["upscale_factor"] == 2.0 and body["creativity"] == 0 and body["input_references"][0]["type"] == "video_url"
    assert snap["result"]["estimate_usd"] == pytest.approx((640 * 2) * (360 * 2) / 1e6 * 4.0 * 0.075)


# --------------------------------------------------------------------------------------- Higgsfield
def hf_calls(hf, real_only=True):
    return [(t, a) for t, a in hf.calls if t in ("generate_video", "generate_image", "motion_control") and (not real_only or not a.get("get_cost"))]


def test_a_higgsfield_job_waits_for_the_captain_and_nothing_is_submitted_before(stack):
    fake, orv, hf, auth, *_ = stack
    sign_in_higgsfield(auth, hf)
    jid = submit(fake, "video_gen", "higgsfield/seedance1_5", {"prompt": "x", "params": {"duration": 8, "resolution": "720p"}})
    snap = wait_for(fake, jid, states=("pending",))
    time.sleep(0.2)
    snap = fake.get(f"/api/v1/job-queue/jobs/{jid}").json()["data"]
    assert snap["state"] == "pending" and "9.6 credits" in snap["user_message"] and "confirm" in snap["user_message"].lower()
    assert hf_calls(hf) == [], "get_cost only: no generation was submitted"
    approvals = fake.get("/app/studio").json()["approvals"]
    ap = next(a for a in approvals if a["state"] == "pending")
    assert ap["studio"] == "higgsfield" and ap["price"] == pytest.approx(9.6) and ap["settings"]["unit"] == "credits"


def test_the_captains_confirm_runs_it_downloads_the_clip_and_records_the_credits(stack):
    fake, orv, hf, auth, *_ = stack
    sign_in_higgsfield(auth, hf)
    jid = submit(fake, "video_gen", "higgsfield/seedance1_5", {"prompt": "x", "params": {"duration": 8, "resolution": "720p"}})
    time.sleep(0.2)
    ap = next(a for a in fake.get("/app/studio").json()["approvals"] if a["state"] == "pending")
    wrong = fake.post(f"/app/studio/approvals/{ap['id']}/confirm", json={"price": 1})
    assert wrong.status_code == 409 and hf_calls(hf) == []
    ok = fake.post(f"/app/studio/approvals/{ap['id']}/confirm", json={"price": 9.6})
    assert ok.status_code == 200, ok.text
    snap = wait_for(fake, jid)
    assert snap["state"] == "succeeded", snap
    assert snap["result"]["result_files"][0]["type"] == "VIDEO" and snap["result"]["credits"] == pytest.approx(9.6) and snap["result"]["provider"] == "higgsfield"
    assert len(hf_calls(hf)) == 1 and hf_calls(hf)[0][1]["model"] == "seedance1_5"
    assert "use_unlim" not in hf_calls(hf)[0][1], "the use_unlim choice is the captain's, never ours"


def test_rejecting_cancels_the_job_without_a_submit(stack):
    fake, orv, hf, auth, *_ = stack
    sign_in_higgsfield(auth, hf)
    jid = submit(fake, "video_gen", "higgsfield/seedance1_5", {"prompt": "x", "params": {"duration": 8, "resolution": "720p"}})
    time.sleep(0.2)
    ap = next(a for a in fake.get("/app/studio").json()["approvals"] if a["state"] == "pending")
    assert fake.post(f"/app/studio/approvals/{ap['id']}/reject").status_code == 200
    assert wait_for(fake, jid)["state"] == "cancelled" and hf_calls(hf) == []


def test_an_unlim_choice_becomes_a_question_for_the_captain_and_is_answered_only_by_his_confirm(stack):
    fake, orv, hf, auth, *_ = stack
    sign_in_higgsfield(auth, hf)
    hf.unlim_question = True
    jid = submit(fake, "video_gen", "higgsfield/seedance_2_0", {"prompt": "x", "params": {"duration": 10, "resolution": "720p"}})
    time.sleep(0.2)
    first = next(a for a in fake.get("/app/studio").json()["approvals"] if a["state"] == "pending")
    assert fake.post(f"/app/studio/approvals/{first['id']}/confirm", json={"price": 45.0}).status_code == 200
    q = None
    for _ in range(100):
        pend = [a for a in fake.get("/app/studio").json()["approvals"] if a["state"] == "pending"]
        if pend:
            q = pend[0]
            break
        time.sleep(0.02)
    assert q and q["settings"]["question"].startswith("Use your unlimited") and q["settings"]["unit"] == "answer"
    assert hf_calls(hf) == [("generate_video", hf_calls(hf)[0][1])] and "use_unlim" not in hf_calls(hf)[0][1], "asked once, no jobs yet"
    assert fake.post(f"/app/studio/approvals/{q['id']}/confirm", json={"price": 0}).status_code == 409, "an answer is required"
    assert fake.post(f"/app/studio/approvals/{q['id']}/confirm", json={"price": 0, "answer": False}).status_code == 200
    snap = wait_for(fake, jid)
    assert snap["state"] == "succeeded" and hf_calls(hf)[-1][1]["use_unlim"] is False


def test_a_submit_timeout_fails_the_job_and_is_never_resubmitted(stack):
    fake, orv, hf, auth, *_ = stack
    sign_in_higgsfield(auth, hf)
    jid = submit(fake, "video_gen", "higgsfield/seedance1_5", {"prompt": "x", "params": {"duration": 8, "resolution": "720p"}})
    time.sleep(0.2)
    ap = next(a for a in fake.get("/app/studio").json()["approvals"] if a["state"] == "pending")
    hf.fail_next_generate = "timeout"
    fake.post(f"/app/studio/approvals/{ap['id']}/confirm", json={"price": 9.6})
    snap = wait_for(fake, jid)
    assert snap["state"] == "failed" and "NOT resubmitted" in snap["error"]
    assert len(hf_calls(hf)) == 0 or len(hf_calls(hf)) == 1, "never more than one attempt"


def test_genjutsu_and_kling_motion_transfer_take_a_character_image_and_a_driving_video(stack):
    fake, orv, hf, auth, *_ = stack
    sign_in_higgsfield(auth, hf)
    img = upload(fake, "image", PNG, "c.png", "image/png")
    vid = upload(fake, "video", MP4, "d.mp4", "video/mp4")
    for slug, tool in (("higgsfield/hf_mult_motion_control", "generate_video"), ("higgsfield/kling_motion_control", "motion_control")):
        jid = submit(fake, "video_gen", slug, {"prompt": "dance", "params": {"duration": 5, "resolution": "720p"},
                                                "reference_image_s3_keys": [img["s3_key"]], "reference_video_s3_keys": [vid["s3_key"]]})
        time.sleep(0.25)
        ap = next(a for a in fake.get("/app/studio").json()["approvals"] if a["state"] == "pending" and a["label"].lower().find("higgsfield") >= 0)
        assert fake.post(f"/app/studio/approvals/{ap['id']}/confirm", json={"price": ap["price"]}).status_code == 200
        assert wait_for(fake, jid)["state"] == "succeeded"
        call = hf_calls(hf)[-1]
        assert call[0] == tool
    assert any(m["role"] == "video_references" for m in hf_calls(hf)[0][1]["medias"])
    assert hf_calls(hf)[1][1]["image_id"] and hf_calls(hf)[1][1]["motion_video_id"]


def test_a_higgsfield_image_job_is_gated_too(stack):
    fake, orv, hf, auth, *_ = stack
    sign_in_higgsfield(auth, hf)
    jid = submit(fake, "image_gen", "higgsfield/gpt_image_2_5", {"prompt": "a lamp", "params": {"number_of_images": 1}})
    time.sleep(0.2)
    ap = next(a for a in fake.get("/app/studio").json()["approvals"] if a["state"] == "pending")
    assert hf_calls(hf) == []
    fake.post(f"/app/studio/approvals/{ap['id']}/confirm", json={"price": ap["price"]})
    snap = wait_for(fake, jid)
    assert snap["state"] == "succeeded" and snap["result"]["images"][0]["url"]


# ----------------------------------------------------------------------------- the sign-in and the agent
def test_the_higgsfield_page_start_callback_and_status(stack, settings):
    fake, orv, hf, auth, *_ = stack
    home = fake.http.get("/app/higgsfield")
    assert home.status_code == 200 and "Continue with Higgsfield" in home.text
    assert fake.http.post("/app/higgsfield/start", headers={"origin": "https://evil.example"}).status_code == 403
    start = fake.http.post("/app/higgsfield/start", follow_redirects=False)
    assert start.status_code == 302 and start.headers["location"].startswith("https://clerk.higgsfield.ai/oauth/authorize")
    cb = hf.authorize(start.headers["location"])
    done = fake.http.get("/auth/higgsfield/callback", params=cb)
    assert done.status_code == 200 and "Signed in" in done.text
    assert fake.http.get("/app/higgsfield/status").json()["signed_in"] is True
    assert fake.http.post("/app/higgsfield/signout", follow_redirects=False).status_code == 303
    assert fake.http.get("/app/higgsfield/status").json()["signed_in"] is False


def test_the_agent_tool_plans_a_higgsfield_clip_and_cannot_spend_it(stack):
    from lampway_server.agent import video_tools as VT
    import asyncio
    fake, orv, hf, auth, ledger, app = stack
    sign_in_higgsfield(auth, hf)
    system = app.state.video
    out, err = asyncio.run(VT.call(system, "lampway_video_gen", {"model": "higgsfield/seedance1_5", "prompt": "x", "duration": 8, "resolution": "720p"}))
    data = json.loads(out)
    assert err is False and data["state"] == "needs_approval" and data["credits"] == pytest.approx(9.6) and hf_calls(hf) == []
    plan, err2 = asyncio.run(VT.call(system, "lampway_video_gen", {"model": "heygen/heygen-video-1", "prompt": "x", "duration": 5, "resolution": "480p"}))
    p = json.loads(plan)
    assert p["dry_run"] is True and p["estimate_usd"] == pytest.approx(0.10) and orv.posts == []
    live, err3 = asyncio.run(VT.call(system, "lampway_video_gen", {"model": "heygen/heygen-video-1", "prompt": "x", "duration": 5, "resolution": "480p", "dry_run": False}))
    assert err3 is False and json.loads(live)["video_file"].endswith(".mp4") and len(orv.posts) == 1
