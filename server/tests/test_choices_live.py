# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_store.md tests 4, 7 and 13 and the routes of section 4.1, against the live document: the shipped defaults reproduce what runs
today, the Providers dialog's saved values are the global scope until the user sets a choice, the environment is a session layer shown
as a conflict (CH4), resolving never touches a route, and only the user writes through the routes."""

import json

import pytest

from lampway_server import choices as CH
from lampway_server import egress as E
from lampway_server import provider_prefs as PP
from lampway_server.choices import store as CS
from lampway_server.config import Settings

FLARE = "openrouter:openai/gpt-image-2.5-flare"


def _everything_works():
    from lampway_server.choices.snapshot import World
    from lampway_server.connections import registry as CREG
    return World(connections={c: "connected" for c in CREG.SPECS}, routes={r: True for r in E.ROUTES})


@pytest.fixture
def live(tmp_path, monkeypatch):
    for k in list(PP.ENV_VARS.values()) + ["LAMPWAY_OPENROUTER_STT_MODEL", "LAMPWAY_CODEX_MODEL", "LAMPWAY_CLAUDE_MODEL"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(tmp_path / "state"))
    CH.set_active(CS.FileStore(tmp_path / "state"), tmp_path / "state")
    monkeypatch.setattr(CH, "WORLD_FACTORY", _everything_works)        # the views below are about scopes, not about what is connected
    yield tmp_path / "state"
    CH.set_active(None, None)


def test_the_shipped_chains_reproduce_what_runs_today(live):
    d = CH.document()
    assert d["shipped"]["agent.main"]["preferred"] == "mock"                               # config.py: provider mock
    plates = d["shipped"]["image.plates"]
    assert plates["preferred"] == "studio:tripo.image" and plates["fallbacks"] == [FLARE]   # image_backend tripo; the plates model on OpenRouter
    assert plates["params"]["size"] == "2880x2880"
    assert d["shipped"]["video.bulk"]["preferred"] == "openrouter:heygen/heygen-video-1"
    assert d["shipped"]["agent.dictation"]["preferred"] == "openrouter:google/gemini-3.8-flash"


def test_the_providers_dialogs_saved_values_are_the_global_scope(live):
    PP.save(live, {"provider": "chatgpt_plan", "chatgpt_model": "gpt-6.1-sol", "chatgpt_effort": "medium"})
    d = CH.document()
    assert d["global"]["agent.main"]["preferred"] == "chatgpt_plan:gpt-6.1-sol" and d["global"]["agent.main"]["source"] == "providers"
    assert d["global"]["agent.main"]["params"] == {"effort": "medium"}
    CH.active_store().set("agent.main", "global", None, {"preferred": "anthropic:claude-sonnet-5-5"}, by="user")
    assert CH.document()["global"]["agent.main"]["preferred"] == "anthropic:claude-sonnet-5-5", "a choice set in Choices wins over the dialog's projection"


def test_environment_is_a_session_layer_with_the_conflict_shown(live, monkeypatch):
    CH.active_store().set("agent.main", "global", None, {"preferred": "chatgpt_plan:gpt-6.1-sol"}, by="user")
    monkeypatch.setenv("LAMPWAY_PROVIDER", "openrouter")
    v = CH.purpose_view("agent.main")
    assert v["now"]["option"] == "openrouter:anthropic/claude-sonnet-5.5" and v["now"]["scope"] == "env"
    assert v["conflict"] == "this session: LAMPWAY_PROVIDER sets openrouter:anthropic/claude-sonnet-5.5; your choice is chatgpt_plan:gpt-6.1-sol"
    monkeypatch.delenv("LAMPWAY_PROVIDER")
    assert CH.purpose_view("agent.main")["now"]["option"] == "chatgpt_plan:gpt-6.1-sol"


def test_the_image_job_resolves_to_what_its_backend_can_run(live, monkeypatch):
    monkeypatch.setattr(CH, "WORLD_FACTORY", None)                       # the live world: the key in the environment, the routes on
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-" "or-v1-FAKE-LIVE-0000000000000000000000")
    r = CH.resolve("image.plates", CH.Job(content_class="private", needs={"runs_on": ["openrouter"]}))
    assert r.option == FLARE and r.reason == "fallback" and "studio:tripo.image cannot run here" in r.why


def test_route_off_never_switches_a_route(live, tmp_path, monkeypatch):
    monkeypatch.setattr(CH, "WORLD_FACTORY", None)
    eg = E.Egress(tmp_path / "eg")
    eg.set_route("openrouter", False)
    E.set_active(eg)
    before = (tmp_path / "eg" / "egress.json").read_bytes()
    log_before = eg.log()
    from lampway_server.choices import registry as REG
    for pid in REG.PURPOSES:
        try:
            CH.resolve(pid, CH.Job())
        except CH.NoChoice:
            pass
    assert (tmp_path / "eg" / "egress.json").read_bytes() == before and eg.log() == log_before


# ------------------------------------------------------------------------------------------------ the routes
@pytest.fixture
def auth(fake, monkeypatch):
    fake.login()
    monkeypatch.setattr(CH, "WORLD_FACTORY", _everything_works)
    return fake.rest_headers()


def test_the_routes_need_the_bearer(http):
    for method, path in (("GET", "/app/choices"), ("GET", "/app/choices/image.plates"), ("PUT", "/app/choices/image.plates"),
                         ("DELETE", "/app/choices/image.plates"), ("POST", "/app/choices/resolve"), ("POST", "/app/choices/acknowledge"),
                         ("GET", "/app/choices/proposals")):
        assert http.request(method, path, json={}).status_code == 401, path


def test_agent_cannot_write(http, auth, settings):
    for method, path, body in (("PUT", "/app/choices/image.plates", {"scope": "global", "preferred": FLARE}),
                               ("DELETE", "/app/choices/image.plates", None),
                               ("POST", "/app/choices/acknowledge", {"option": "studio:tripo.image", "private": True})):
        r = http.request(method, path, json=body, headers={**auth, "x-lampway-origin": "agent"})
        assert r.status_code == 403 and r.json()["detail"] == "only your click in Choices can change a choice: an agent may propose one"
    assert not (settings.state_dir / "choices.json").exists()


def test_list_view_set_resolve_and_a_saved_note(http, auth):
    groups = http.get("/app/choices", headers=auth).json()["groups"]
    assert [g["id"] for g in groups][:2] == ["agents", "images"] and sum(len(g["purposes"]) for g in groups) == 57
    r = http.put("/app/choices/image.plates", json={"scope": "global", "preferred": "studio:meshy.image_to_3d"}, headers=auth)
    assert r.status_code == 400 and "is not an option for image.plates" in r.json()["detail"]
    r = http.put("/app/choices/image.plates", json={"scope": "global", "preferred": FLARE, "fallbacks": ["studio:tripo.image"]}, headers=auth)
    assert r.status_code == 200 and r.json()["now"]["option"] in (FLARE, "studio:tripo.image")
    view = http.get("/app/choices/image.plates", headers=auth).json()
    assert [o["id"] for o in view["chain"]] == [FLARE, "studio:tripo.image"] and view["now"]["scope"] == "global"
    dry = http.post("/app/choices/resolve", json={"purpose": "image.plates", "job": {"content_class": "public"}}, headers=auth).json()
    assert dry["option"]["id"] == FLARE and dry["reason"] == "preferred"


def test_a_proposal_waits_for_the_users_click(http, auth):
    CH.active_store().propose("agent:s1", "image.plates", {"preferred": "openrouter:sourceful/riverflow-v2.5-pro"}, "rated higher", [])
    props = http.get("/app/choices/proposals", headers=auth).json()["proposals"]
    assert props[0]["state"] == "open"
    r = http.post(f"/app/choices/proposals/{props[0]['id']}/accept", json={}, headers=auth)
    assert r.status_code == 200 and r.json()["now"]["option"] == "openrouter:sourceful/riverflow-v2.5-pro"
