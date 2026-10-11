# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""BYOA B4 (docs/reports/agent-modes-spec.md) over the client's own socket: showing a pane bound to a scene tab in the island.

- ``agent.byoa.observe`` finds the pane from the binding table (never from a body field), tails the harness's own session file
  (Claude Code, Codex) and streams it as observed turns: ``agent.turn.started`` with ``observed: true``, numbered
  ``agent.turn.event`` payloads, ``agent.turn.ended``; ``agent.attach`` replays them like any turn. History before the observation
  is never replayed unless the client names the offset it rendered up to.
- A pane with no readable session file (OpenCode, the user's own Hermes, Pi, Grok, Cursor) is shown as its screen text; the
  user's own Hermes home is never read (E1.10).
- ``agent.byoa.send`` types the user's text into the bound pane; who typed is decided from the socket (an agent token or a
  worker socket is an agent), and an agent's send right after the user's is held back by the 2.5 s quiet window (B6).
herdr is a recording fake; the harness files are fixtures under tmp_path; nothing is started."""
import builtins
import json
import time
from pathlib import Path

from .launch_notice_support import prior_human_disclosure  # noqa: F401

import pytest
from starlette.testclient import TestClient

from lampway_server.agent import byoa as BY
from lampway_server.app import create_app
from lampway_server.auth import mint_jwt
from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L
from lampway_server.herdr.observers.native import claude_transcript

from .byoa_fixtures import CLAUDE_TURNS, CODEX_TURNS, jsonl
from .fake_client import FakeMixarClient
from .test_byoa_egress import FakeHerdr

SCENE = "5c1e0000-0000-4000-8000-00000000000a"


@pytest.fixture
def stack(settings, provider, tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    monkeypatch.setenv("LAMPWAY_MCP_LAUNCHER", "/opt/lw/connector/lampway-mcp")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-cfg"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setattr(BY, "POLL_S", 0.02)
    herdr = FakeHerdr()
    monkeypatch.setattr(L, "run", herdr)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    proj = tmp_path / "proj"
    proj.mkdir()
    cockpit = H.Cockpit(tmp_path / "herdr", project_root=str(proj))
    app = create_app(settings, provider=provider, cockpit=cockpit)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        yield fake, cockpit, herdr, proj, settings


def until(ws, pred, limit=400):
    frames = []
    for _ in range(limit):
        f = ws.receive_json()
        frames.append(f)
        if pred(f):
            return frames
    raise AssertionError(f"never seen; frames={frames!r}")


def reply_to(ws, rid):
    return until(ws, lambda f: f.get("id") == rid)[-1]["result"]


def observe(fake, ws, session_id=SCENE, **extra):
    return reply_to(ws, fake.request(ws, "agent.byoa.observe", {"session_id": session_id, **extra}))


def append(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(jsonl(records))


def claude_pane(cockpit, proj, scene=SCENE):
    rec = cockpit.create_session("claude", "Chest fit audit", str(proj), by="user", scene_session_id=scene)
    return rec, Path(claude_transcript(rec["cwd"], rec["native_id"]))


def test_a_bound_claude_pane_streams_its_own_transcript_as_observed_turns(stack):
    fake, cockpit, herdr, proj, _ = stack
    rec, path = claude_pane(cockpit, proj)
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        got = observe(fake, ws)
        assert got["view"] == "transcript" and got["pane"] == rec["id"] and got["harness"] == "claude"
        append(path, CLAUDE_TURNS[3:12])
        frames = until(ws, lambda f: f.get("method") == "agent.turn.ended")
    started = next(f["params"] for f in frames if f.get("method") == "agent.turn.started")
    assert started["observed"] is True and started["session_id"] == SCENE and started["user_text"] == "Add a cube and tell me its name"
    assert started["harness"] == "claude"
    events = [f["params"] for f in frames if f.get("method") == "agent.turn.event"]
    assert [e["seq"] for e in events] == list(range(len(events)))                                        # numbered from 0, contiguous
    assert events[0]["event"] == {"type": "run_status", "run_id": started["run_id"], "status": "in_progress"}
    assert any(e["event"].get("content", {}).get("set") == "I'll add the cube.\n\nThe cube is called Cube." for e in events)
    assert any("steps" in e["event"] for e in events)
    end = events[-1]["event"]
    assert end["type"] == "turn_end" and end["status"] == "completed"
    assert end["offset"] == path.stat().st_size                                                        # where a reopened tab resumes from


def test_history_written_before_the_observation_is_not_replayed_unless_the_client_names_its_offset(stack):
    fake, cockpit, herdr, proj, _ = stack
    rec, path = claude_pane(cockpit, proj)
    append(path, CLAUDE_TURNS[3:12])                                                                    # an old turn, already in the file
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        observe(fake, ws)
        append(path, CLAUDE_TURNS[12:15])
        frames = until(ws, lambda f: f.get("method") == "agent.turn.ended")
    assert [f["params"]["user_text"] for f in frames if f.get("method") == "agent.turn.started"] == ["Now bevel it"]


def test_a_client_that_names_its_offset_gets_what_it_has_not_rendered(stack):
    fake, cockpit, herdr, proj, _ = stack
    rec, path = claude_pane(cockpit, proj, scene="5c1e0000-0000-4000-8000-00000000000b")
    append(path, CLAUDE_TURNS[3:12])
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        observe(fake, ws, session_id="5c1e0000-0000-4000-8000-00000000000b", after_offset=0)
        frames = until(ws, lambda f: f.get("method") == "agent.turn.ended")
    assert next(f for f in frames if f.get("method") == "agent.turn.started")["params"]["user_text"] == "Add a cube and tell me its name"


def test_an_observed_turn_replays_through_attach_and_shows_in_status(stack):
    fake, cockpit, herdr, proj, _ = stack
    rec, path = claude_pane(cockpit, proj)
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        observe(fake, ws)
        append(path, CLAUDE_TURNS[3:12])
        frames = until(ws, lambda f: f.get("method") == "agent.turn.ended")
        tid = frames[-1]["params"]["turn_id"]
        status = reply_to(ws, fake.request(ws, "agent.status", {"session_ids": [SCENE]}))
        assert status["turns"][SCENE]["turn_id"] == tid and status["turns"][SCENE]["status"] == "ended"
        rid = fake.request(ws, "agent.attach", {"session_id": SCENE, "turn_id": tid, "after_seq": 0})
        replay = until(ws, lambda f: f.get("id") == rid)
    assert [f["params"]["seq"] for f in replay if f.get("method") == "agent.turn.event"][0] == 1
    assert replay[-1]["result"]["status"] == "ok"


def test_a_codex_pane_streams_its_rollout_found_by_folder_and_start_time(stack, tmp_path):
    fake, cockpit, herdr, proj, _ = stack
    scene = "5c1e0000-0000-4000-8000-00000000000c"
    rec = cockpit.create_session("codex", "Boots seed read", str(proj), by="user", scene_session_id=scene)
    day = tmp_path / "codex-home" / "sessions" / "2026" / "10" / "07"
    meta = dict(CODEX_TURNS[0], payload=dict(CODEX_TURNS[0]["payload"], cwd=rec["cwd"],
                                              timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(rec["created_at"] + 1))))
    other = dict(meta, payload=dict(meta["payload"], cwd=str(tmp_path / "elsewhere")))
    append(day / "rollout-other.jsonl", [other, CODEX_TURNS[4]])                                         # another folder: never this pane's
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        assert observe(fake, ws, session_id=scene)["view"] == "transcript"
        append(day / "rollout-mine.jsonl", [meta, *CODEX_TURNS[1:15]])
        frames = until(ws, lambda f: f.get("method") == "agent.turn.ended")
    started = next(f["params"] for f in frames if f.get("method") == "agent.turn.started")
    assert started["user_text"] == "Add a sphere" and started["harness"] == "codex"


def test_a_pane_without_a_session_file_is_shown_as_its_screen(stack):
    fake, cockpit, herdr, proj, _ = stack
    scene = "5c1e0000-0000-4000-8000-00000000000d"
    rec = cockpit.create_session("opencode", "Look dev pass", str(proj), by="user", scene_session_id=scene)
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        got = observe(fake, ws, session_id=scene)
    assert got["view"] == "screen" and got["pane"] == rec["id"] and "user@box" in got["screen"]
    assert any(c["args"][:3] == ["pane", "read", rec["pane_id"]] for c in herdr.calls)


def test_the_users_own_hermes_is_shown_as_its_screen_and_its_home_is_never_opened(stack, monkeypatch, tmp_path):
    fake, cockpit, herdr, proj, _ = stack
    scene = "5c1e0000-0000-4000-8000-00000000000e"
    cockpit.create_session("hermes", "Hermes look pass", str(proj), by="user", scene_session_id=scene)
    opened = []
    real_open = builtins.open
    monkeypatch.setattr(builtins, "open", lambda f, *a, **k: (opened.append(str(f)), real_open(f, *a, **k))[1])
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        assert observe(fake, ws, session_id=scene)["view"] == "screen"
    assert not [p for p in opened if ".hermes" in p]


def test_a_tab_with_no_bound_pane_is_told_how_to_bind_one(stack):
    fake, cockpit, herdr, proj, _ = stack
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        got = observe(fake, ws, session_id="5c1e0000-0000-4000-8000-0000000000ff")
    assert got["view"] == "none" and got["code"] == "not_bound" and any("Your agent" in h for h in got["help"])


def _send(fake, ws, text, session_id=SCENE):
    return reply_to(ws, fake.request(ws, "agent.byoa.send", {"command_id": "c-" + text[:8], "payload": {"session_id": session_id, "text": text}}))


def test_the_island_sends_the_users_text_into_the_bound_pane(stack):
    fake, cockpit, herdr, proj, _ = stack
    rec, _ = claude_pane(cockpit, proj)
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        out = _send(fake, ws, "Add a torus")
    assert out == {"state": "complete", "result": {"ok": True, "pane": rec["id"]}}
    sent = [c["args"] for c in herdr.calls if c["args"][:2] in (["pane", "send-text"], ["pane", "send-keys"])]
    assert sent == [["pane", "send-text", rec["pane_id"], "Add a torus"], ["pane", "send-keys", rec["pane_id"], "enter"]]


def test_a_send_with_no_bound_pane_is_refused_with_help(stack):
    fake, cockpit, herdr, proj, _ = stack
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        out = _send(fake, ws, "hello", session_id="5c1e0000-0000-4000-8000-0000000000fe")
    assert out["result"]["ok"] is False and out["result"]["code"] == "not_bound" and out["result"]["help"]


def test_an_agent_socket_is_an_agent_send_whatever_it_claims_and_the_quiet_window_holds_it_back(stack):
    fake, cockpit, herdr, proj, settings = stack
    rec, _ = claude_pane(cockpit, proj)
    now = int(time.time())
    agent_token = mint_jwt(settings.jwt_secret, {"sub": settings.user_email, "iat": now, "exp": now + 600, "origin": "agent"})
    with fake.connect_ws(token=agent_token) as ws:
        fake.handshake(ws)
        out = _send(fake, ws, "rm -rf renders")
    assert out["result"]["ok"] is False and "agent sends are off" in out["result"]["message"]
    cockpit.set_agent_sends(rec["id"], True)
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        assert _send(fake, ws, "the user's words")["result"]["ok"] is True
    with fake.connect_ws(token=agent_token) as ws:
        fake.handshake(ws)
        held = _send(fake, ws, "the agent's words")
    assert held["result"]["ok"] is False and "typing" in held["result"]["message"]
    assert not any(c["args"][-1] == "the agent's words" for c in herdr.calls)


def test_a_tab_switched_back_to_lampway_agent_stops_streaming_its_old_pane(stack):
    fake, cockpit, herdr, proj, _ = stack
    rec, path = claude_pane(cockpit, proj)
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        assert observe(fake, ws)["view"] == "transcript"
        r = fake.http.post("/app/workbench/mode", headers=fake.rest_headers(), json={"scene_session_id": SCENE, "mode": "runtime"})
        assert r.status_code == 200 and r.json()["unbound"] == [rec["id"]]
        append(path, CLAUDE_TURNS[3:12])
        time.sleep(0.3)                                                                                  # fifteen polls' worth
        rid = fake.request(ws, "system.ping", {})
        assert ws.receive_json().get("id") == rid                                                        # nothing was streamed first
