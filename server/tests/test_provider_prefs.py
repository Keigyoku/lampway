"""Provider setup that is not env-only: the main agent, the swarm workers and the image backend (provider, model, effort / size /
quality) are chosen from the Client and saved in the server's state dir; the environment is the default, a saved choice wins, a bad
choice is refused with the reason and changes nothing. No key is ever part of this."""

import base64
import json
import os
import stat

import httpx
import pytest
from starlette.testclient import TestClient

from lampway_server import imagegen as IG
from lampway_server import provider_prefs as PP
from lampway_server.app import create_app

from .fake_client import FakeMixarClient


@pytest.fixture
def client(settings, monkeypatch):
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(settings.state_dir))
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        yield fake, app


def test_the_routes_need_a_token(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as http:
        assert http.get("/app/provider-settings").status_code == 401
        assert http.put("/app/provider-settings", json={"values": {}}).status_code == 401


def test_get_shows_the_effective_values_where_each_comes_from_and_the_choices(client):
    fake, _ = client
    out = fake.get("/app/provider-settings").json()
    v = out["values"]
    assert v["provider"] == "mock" and v["swarm_provider"] == "" and v["openrouter_image_model"] and "chatgpt_effort" in v and "image_backend" in v
    assert set(out["source"].values()) <= {"env", "saved", "default"}
    c = out["choices"]
    assert {"mock", "chatgpt_plan", "claude_cli", "openrouter"} <= set(c["main_providers"]) and {"", "claude_cli", "openrouter"} <= set(c["swarm_providers"])
    assert set(c["image_backends"]) == {"tripo", "codex_cli", "openrouter"} and "high" in c["image_qualities"] and "medium" in c["efforts"]
    assert not [k for k in v if "key" in k or "token" in k or "secret" in k], "no credential is part of the provider settings"


def test_put_saves_applies_and_survives_a_restart(client, settings, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-" + "cd34" * 16)             # a swarm on OpenRouter must be buildable to be saved
    fake, app = client
    out = fake.put("/app/provider-settings", json={"values": {
        "swarm_provider": "openrouter", "openrouter_swarm_model": "deepseek/deepseek-v4.1-flash", "chatgpt_effort": "medium",
        "image_backend": "openrouter", "openrouter_image_model": "openai/gpt-image-2.5-sunburst", "openrouter_image_size": "2880x2880",
        "openrouter_image_quality": "high"}})
    assert out.status_code == 200, out.text
    got = out.json()
    assert got["values"]["openrouter_image_size"] == "2880x2880" and got["source"]["openrouter_image_size"] == "saved" and got["source"]["provider"] in ("env", "default")
    path = settings.state_dir / "provider_prefs.json"
    assert path.exists() and stat.S_IMODE(os.stat(path).st_mode) == 0o600 and json.loads(path.read_text())["openrouter_image_quality"] == "high"
    assert app.state.settings.swarm_provider == "openrouter"
    reopened = create_app(settings.__class__.from_env({"LAMPWAY_STATE_DIR": str(settings.state_dir), "LAMPWAY_USER_PASSWORD": "x", "LAMPWAY_JWT_SECRET": "j"}))
    assert reopened.state.settings.openrouter_image_model == "openai/gpt-image-2.5-sunburst" and reopened.state.settings.swarm_provider == "openrouter"


def test_a_swarm_provider_that_cannot_be_built_is_refused_with_why(client, monkeypatch):
    fake, app = client
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LAMPWAY_OPENROUTER_KEY_FILE", raising=False)
    r = fake.put("/app/provider-settings", json={"values": {"swarm_provider": "openrouter"}})
    assert r.status_code == 400 and "OpenRouter key" in r.json()["detail"] and app.state.settings.swarm_provider == ""
    r = fake.put("/app/provider-settings", json={"values": {"swarm_provider": "claude_cli"}})        # the local CLI switch is off
    assert r.status_code == 400 and "claude_cli" in r.json()["detail"].lower() or "cli" in r.json()["detail"].lower()


def test_a_bad_choice_is_refused_with_the_reason_and_nothing_changes(client, settings):
    fake, app = client
    for bad in ({"provider": "skynet"}, {"image_backend": "dalle"}, {"openrouter_image_size": "4K"}, {"openrouter_image_size": "3840x3840"},
                {"chatgpt_effort": "extreme"}, {"openrouter_image_quality": "ultra"}, {"jwt_secret": "x"}, {"openrouter_api_key": "k"}):
        r = fake.put("/app/provider-settings", json={"values": bad})
        assert r.status_code == 400, bad
    assert "size" in fake.put("/app/provider-settings", json={"values": {"openrouter_image_size": "4K"}}).json()["detail"].lower()
    assert app.state.settings.provider == "mock" and not (settings.state_dir / "provider_prefs.json").exists()


def test_a_main_provider_that_cannot_be_built_is_refused_and_the_old_one_stays(client, settings):
    fake, app = client
    before = app.state.agent.provider
    r = fake.put("/app/provider-settings", json={"values": {"provider": "openai"}})          # needs LAMPWAY_OPENAI_MODEL
    assert r.status_code == 400 and "OPENAI_MODEL" in r.json()["detail"]
    assert app.state.agent.provider is before and app.state.settings.provider == "mock"


def test_a_saved_main_provider_replaces_the_one_new_turns_use(client, settings):
    fake, app = client
    assert app.state.agent.provider.name == "mock"
    r = fake.put("/app/provider-settings", json={"values": {"provider": "openai", "openai_model": "m"}})
    assert r.status_code == 200 and app.state.agent.provider.name == "openai"


# ------------------------------------------------------------------ the image settings reach the request, per call too
PNG = b"\x89PNG\r\n\x1a\n" + b"x"


@pytest.fixture
def seen(settings, monkeypatch):
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(settings.state_dir))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-" + "ab12" * 16)
    monkeypatch.setenv("LAMPWAY_OPENROUTER_BUDGET_USD", "5")
    rows = []

    def handler(request):
        if request.method == "GET":                      # the endpoints lookup: unreadable here, so the model family decides
            return httpx.Response(404, json={})
        rows.append(json.loads(request.content))
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode(), "media_type": "image/png"}], "usage": {"cost": 0.01}})
    monkeypatch.setattr(IG, "openrouter_transport", httpx.MockTransport(handler))
    return rows


def test_the_saved_image_size_and_quality_ride_on_the_images_request(client, seen):
    fake, _ = client
    fake.put("/app/provider-settings", json={"values": {"openrouter_image_model": "openai/gpt-image-2.5-sunburst", "openrouter_image_size": "2880x2880", "openrouter_image_quality": "high"}})
    IG.openrouter_images("p", [], 1)
    assert seen[0]["model"] == "openai/gpt-image-2.5-sunburst" and seen[0]["size"] == "2880x2880" and seen[0]["quality"] == "high"


def test_a_call_can_choose_its_own_size_or_aspect_ratio_for_a_non_square_plate(seen):
    IG.openrouter_images("p", [], 1, size="2048x1152")
    assert seen[-1]["size"] == "2048x1152"
    IG.openrouter_images("p", [], 1, aspect_ratio="3:2")
    w, h = (int(x) for x in seen[-1]["size"].split("x"))
    assert abs(w / h - 1.5) < 0.01 and w * h <= 2880 * 2880 and w % 16 == 0 and h % 16 == 0
    IG.openrouter_images("p", [], 1, aspect_ratio="1:1")
    assert seen[-1]["size"] == "2880x2880"
    with pytest.raises(ValueError, match="size"):
        IG.openrouter_images("p", [], 1, size="4K")
    with pytest.raises(ValueError, match="budget"):
        IG.openrouter_images("p", [], 1, size="3840x3840")
    with pytest.raises(ValueError, match="aspect"):
        IG.openrouter_images("p", [], 1, aspect_ratio="wide")


def test_the_job_queue_image_gen_payload_may_carry_size_or_aspect_ratio(seen):
    from lampway_server import imagegen
    imagegen.openrouter_image_backend("default", {"prompt": "x", "params": {"number_of_images": 1, "aspect_ratio": "16:9"}})
    w, h = (int(x) for x in seen[-1]["size"].split("x"))
    assert abs(w / h - 16 / 9) < 0.02


def test_the_studio_image_tool_accepts_size_and_aspect_ratio():
    from lampway_server.agent import server_tools as ST
    props = ST.BY_NAME["studio_image_generate"].spec().parameters["properties"]
    assert "size" in props and "aspect_ratio" in props
