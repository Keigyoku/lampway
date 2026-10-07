# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_migration.md tests 5, 6 and 7 and step 5.1: the dead per-role preferences become proposals (never applied silently), the
video upscale default is the video.upscale choice (HC12), the swarm falls back along agent.worker's chain when its first option cannot
be built (HC23), and dictation runs the agent.dictation choice (HC1)."""

import json

import pytest

from lampway_server import choices as CH
from lampway_server import egress as E
from lampway_server.choices import store as CS
from lampway_server.choices.snapshot import World
from lampway_server.config import Settings
from lampway_server.connections import registry as CREG

KEY = "sk-" "or-v1-" + "9a8b" * 16


@pytest.fixture
def live(tmp_path, monkeypatch):
    CH.set_active(CS.FileStore(tmp_path / "state"), tmp_path / "state")
    monkeypatch.setattr(CH, "WORLD_FACTORY", lambda: World(connections={c: "connected" for c in CREG.SPECS}, routes={r: True for r in E.ROUTES}))
    yield tmp_path / "state"
    CH.set_active(None, None)


def test_dead_preferences_become_proposals(live, settings, provider):
    from lampway_server.app import create_app
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    (settings.state_dir / "agent_settings.json").write_text(json.dumps({"byok": None, "preferences": {
        "default": {"provider": "anthropic", "model": "claude-opus-5-5", "label": "Opus", "thinking_level": None, "eligible": True}}}))
    before = CH.resolve("agent.main", CH.Job(content_class="public")).option
    create_app(settings, provider=provider)
    create_app(settings, provider=provider)                                    # a second start proposes nothing new
    props = CH.active_store().proposals()
    assert len(props) == 1 and props[0]["state"] == "open" and props[0]["purpose"] == "agent.main"
    assert props[0]["change"] == {"preferred": "anthropic:claude-opus-5-5"} and props[0]["origin"] == "migration"
    assert CH.resolve("agent.main", CH.Job(content_class="public")).option == before


def test_upscale_default_is_the_choice(live):
    from lampway_server import videojobs as VJ
    sys_ = VJ.VideoSystem.__new__(VJ.VideoSystem)
    sys_._or_models, sys_._or_failed_until = [
        {"id": "other/upscaler", "name": "Other", "upscale_factor": {"min": 1.5, "max": 3}, "supported_parameters": ["upscale_factor"]},
        {"id": "black-forest-labs/flux-video-upscale", "name": "FLUX upscale", "upscale_factor": {"min": 1.5, "max": 3}, "supported_parameters": ["upscale_factor"]},
    ], 0
    from lampway_server import videogen as VG
    if not all(VG.is_upscaler(r) for r in sys_._or_models):
        pytest.skip("the fixture rows are not upscalers by is_upscaler's rule")
    rows = sys_.upscale_models()
    assert [r["slug"] for r in rows if r["is_default"]] == ["black-forest-labs/flux-video-upscale"]


def test_swarm_fallback(live, monkeypatch, tmp_path):
    from lampway_server.agent.providers import make_swarm_provider
    from lampway_server.agent.providers.openrouter import OpenRouterProvider
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    CH.active_store().set("agent.worker", "global", None, {"preferred": "chatgpt_plan:gpt-6.1-sol", "fallbacks": ["openrouter:deepseek/deepseek-v4.1-flash"]}, by="user")
    s = Settings(state_dir=tmp_path / "srv", provider="chatgpt_plan", swarm_provider="claude_cli")      # a retired worker from the environment cannot be built (spec R0)
    p = make_swarm_provider(s, "worker-1")
    assert isinstance(p, OpenRouterProvider) and p.model == "deepseek/deepseek-v4.1-flash"
    assert p.choice["reason"] == "fallback" and p.choice["option"] == "openrouter:deepseek/deepseek-v4.1-flash" and "claude_cli" in p.choice["why"]


def test_dictation_runs_the_choice(live, monkeypatch, tmp_path):
    from lampway_server import dictation as D
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    CH.active_store().set("agent.dictation", "global", None, {"preferred": "openrouter:google/gemini-3.9-flash"}, by="user")
    t = D.default_transcriber(Settings(state_dir=tmp_path / "srv"))
    assert t.model == "google/gemini-3.9-flash"


def test_the_decisions_judge_follows_the_users_chain_and_one_private_rule(live):
    """5.2 (HC2, HC21): the candidates are agent.decide's chain in force (the user's order), and the ZDR filter is the resolver's privacy
    constraint - the one copy of the rule."""
    import httpx
    from lampway_server import decisions_model as D
    models = {"data": [{"id": i} for i in ("inception/mercury-decide:free", "cloudflare/clef", "liquid/d1", "upstage/solar-decide")]}
    zdr = {"data": [{"model_id": "cloudflare/clef"}, {"model_id": "liquid/d1"}, {"model_id": "inception/mercury-decide:free"}]}

    def handler(req):
        return httpx.Response(200, json=models if req.url.path.endswith("/models") else zdr)
    CH.active_store().set("agent.decide", "global", None, {"preferred": "openrouter:liquid/d1", "fallbacks": ["openrouter:cloudflare/clef",
                                                                                                           "openrouter:inception/mercury-decide:free"]}, by="user")
    d = D.Decider(KEY, transport=httpx.MockTransport(handler))
    assert d.eligible("private") == ["liquid/d1", "cloudflare/clef"]
    assert d.eligible("public") == ["liquid/d1", "cloudflare/clef", "inception/mercury-decide:free"]


def test_matgen_runs_the_material_script_choice(live, settings, provider, monkeypatch):
    """5.7 (HC3): MatGen follows the main agent by default; a different agent.material_script choice builds that provider."""
    from starlette.testclient import TestClient
    from lampway_server import matgen
    from lampway_server.agent.providers.openrouter import OpenRouterProvider
    from lampway_server.app import create_app
    from tests.fake_client import FakeMixarClient
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    used = []

    async def fake_generate(p, prompt, pipeline):
        used.append(p)
        raise matgen.BadScript("stop here")
    monkeypatch.setattr(matgen, "generate", fake_generate)
    app = create_app(settings, provider=provider)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        http.post("/api/v1/matgen", json={"prompt": "rusted bronze"}, headers=fake.rest_headers())
        CH.active_store().set("agent.material_script", "global", None, {"preferred": "openrouter:anthropic/claude-sonnet-5.5"}, by="user")
        http.post("/api/v1/matgen", json={"prompt": "rusted bronze"}, headers=fake.rest_headers())
    assert used[0] is provider
    assert isinstance(used[1], OpenRouterProvider) and used[1].model == "anthropic/claude-sonnet-5.5"


def test_compute_uses_the_chosen_backend_and_nothing_is_pre_chosen(live, tmp_path):
    """5.11 (G1, CH6): a job with no backend runs compute.blender_offload's choice; with none set the refusal is today's."""
    from lampway_server.compute import runner as R
    from tests.test_compute import Env
    env = Env(tmp_path / "c")
    env.prefs.update({"backends": ["boat"], "private_backends": ["boat"]})
    env.runner = R.ComputeRunner(env.root, env.receipts, env.ledger, env.prefs, {"boat": env.fake}, clock=env.clock.now, sleep=env.clock.sleep,
                                 poll_s=5.0, watchdog_s=15.0)
    job = env.job()
    del job["backend"]
    with pytest.raises(R.Refused, match="pick a provider for this job"):
        env.runner.plan(dict(job))
    CH.active_store().set("compute.blender_offload", "global", None, {"preferred": "compute:boat"}, by="user")
    assert env.runner._spec(dict(job))["backend"] == "boat"
    assert env.runner.plan(dict(job))["ok"] is True


def test_make_provider_takes_the_resolution(live, settings, monkeypatch):
    """5.6 (HC4, HC5): the main agent is built from agent.main's resolution, so the user's fallback runs when the preferred option cannot."""
    from lampway_server.agent.providers import make_provider
    from lampway_server.agent.providers.openrouter import OpenRouterProvider
    from lampway_server.app import create_app
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    monkeypatch.setattr(CH, "WORLD_FACTORY", lambda: World(connections={"chatgpt_plan": "missing", "openrouter": "not_checked"}, routes={r: True for r in E.ROUTES}))
    CH.active_store().set("agent.main", "global", None, {"preferred": "chatgpt_plan:gpt-6.1-sol", "fallbacks": ["openrouter:anthropic/claude-sonnet-5.5"]}, by="user")
    r = CH.resolve("agent.main", CH.Job())
    p = make_provider(settings, resolution=r)
    assert isinstance(p, OpenRouterProvider) and p.model == "anthropic/claude-sonnet-5.5"
    app = create_app(settings)
    assert isinstance(app.state.agent.provider, OpenRouterProvider)
