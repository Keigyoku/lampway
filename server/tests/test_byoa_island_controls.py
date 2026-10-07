# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The island's controls for a tab in Your agent mode (docs/reports/agent-modes-spec.md B2, B4), over the client's own socket:

- **Stop** (``agent.byoa.interrupt``, and ``agent.cancel`` for such a tab) types the harness's own interrupt keys into the tab's
  pane, as herdr 0.9.3 spells them: only from the user's own socket, only into a live pane Lampway bound to that tab.
- **Images** go with the text to a harness that takes an image by its path: written into a Lampway-owned folder inside the pane's
  project root (never outside it, never under a name or type the client chose), their paths typed before the text; a harness that
  cannot take one is refused, saying why.
- **An ended pane** is offered for Resume (the adapter's resume with the stored native id) or Unbind; both are the user's click,
  never automatic (law 5), never an agent's. A pane shown by its screen reports herdr's own working/idle reading.
herdr is a recording fake as strict as herdr 0.9.3 (agent names, keys); nothing is started."""
import base64
import json
import os
import stat
import time
from pathlib import Path

import pytest

from lampway_server.auth import mint_jwt

from .byoa_fixtures import PI_SESSION, PI_TURNS, jsonl
from .test_byoa_view import SCENE, append, claude_pane, observe, reply_to, stack, until  # noqa: F401 - stack is a fixture

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def _rpc(fake, ws, method, payload):
    return reply_to(ws, fake.request(ws, method, {"command_id": f"c-{method}-{time.time()}", "payload": payload}))


def _agent_token(settings):
    now = int(time.time())
    return mint_jwt(settings.jwt_secret, {"sub": settings.user_email, "iat": now, "exp": now + 600, "origin": "agent"})


def _keys(herdr):
    return [c["args"][2:] for c in herdr.calls if c["args"][:2] == ["pane", "send-keys"]]


def _end(cockpit, rid):
    def f(d):
        for s in d["sessions"]:
            if s["id"] == rid:
                s.update(state="ended", ended_at=time.time(), end_reason="the agent process is no longer running")
    cockpit._update(f)


# ------------------------------------------------------------------------------------------------------------------- Stop
@pytest.mark.parametrize("harness,keys", [("claude", ["esc"]), ("codex", ["esc"]), ("opencode", ["esc", "esc"]), ("hermes", ["ctrl+c"])])
def test_stop_types_the_harness_own_interrupt_keys_into_the_bound_pane(stack, harness, keys):
    fake, cockpit, herdr, proj, _ = stack
    rec = cockpit.create_session(harness, "Chest fit audit", str(proj), by="user", scene_session_id=SCENE)
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        out = _rpc(fake, ws, "agent.byoa.interrupt", {"session_id": SCENE})
    assert out["result"]["ok"] is True and out["result"]["keys"] == keys and out["result"]["pane"] == rec["id"]
    assert _keys(herdr) == [[rec["pane_id"], *keys]]


def test_the_islands_cancel_for_a_tab_in_your_agent_mode_is_the_same_stop(stack):
    fake, cockpit, herdr, proj, _ = stack
    rec, _ = claude_pane(cockpit, proj)
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        out = _rpc(fake, ws, "agent.cancel", {"session_id": SCENE})
    assert out["result"]["ok"] is True and out["result"]["cancelled"] is True
    assert _keys(herdr) == [[rec["pane_id"], "esc"]]


def test_an_agent_socket_never_stops_the_users_pane(stack):
    fake, cockpit, herdr, proj, settings = stack
    claude_pane(cockpit, proj)
    with fake.connect_ws(token=_agent_token(settings)) as ws:
        fake.handshake(ws)
        out = _rpc(fake, ws, "agent.byoa.interrupt", {"session_id": SCENE})
        cancel = _rpc(fake, ws, "agent.cancel", {"session_id": SCENE})
    assert out["result"]["ok"] is False and out["result"]["code"] == "agent_origin"
    assert cancel["result"]["ok"] is False and cancel["result"]["code"] == "agent_origin"
    assert _keys(herdr) == []


def test_stop_with_no_running_pane_says_so_and_types_nothing(stack):
    fake, cockpit, herdr, proj, _ = stack
    rec, _ = claude_pane(cockpit, proj)
    _end(cockpit, rec["id"])
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        ended = _rpc(fake, ws, "agent.byoa.interrupt", {"session_id": SCENE})
        none = _rpc(fake, ws, "agent.byoa.interrupt", {"session_id": "5c1e0000-0000-4000-8000-0000000000aa"})
    assert ended["result"]["code"] == "not_bound" and none["result"]["code"] == "not_bound" and _keys(herdr) == []


def test_the_cockpits_own_interrupt_sends_ctrl_c_the_way_herdr_spells_it(stack, tmp_path):
    """herdr 0.9.3 refuses ``ctrl-c`` (invalid_key, measured on the real server); a shell or command pane gets ``ctrl+c``."""
    fake, cockpit, herdr, proj, _ = stack
    rec = cockpit.create_session("command", "Chest fit audit", str(proj), command="python3 -i", by="user")
    assert cockpit.interrupt(rec["id"]) == ["ctrl+c"]
    assert _keys(herdr) == [[rec["pane_id"], "ctrl+c"]]


# ------------------------------------------------------------------------------------------------------------------- images
def _send(fake, ws, text, images, session_id=SCENE):
    payload = {"session_id": session_id, "text": text, "images": [{"data": base64.b64encode(b).decode(), "name": "../../evil.sh",
                                                                    "mime": "text/x-shellscript"} for b in images]}
    return _rpc(fake, ws, "agent.byoa.send", payload)


def test_images_are_written_inside_the_project_root_and_their_paths_typed_before_the_text(stack):
    fake, cockpit, herdr, proj, _ = stack
    rec, _ = claude_pane(cockpit, proj)
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        out = _send(fake, ws, "What is wrong with this render?", [PNG, JPEG])
    assert out["result"]["ok"] is True
    folder = proj / ".lampway" / "panes" / rec["id"] / "images"
    files = sorted(folder.iterdir())
    assert [f.suffix for f in sorted(files, key=lambda f: f.read_bytes() != PNG)] == [".png", ".jpg"]       # the bytes decide the type
    assert {f.read_bytes() for f in files} == {PNG, JPEG}
    for f in files:
        assert stat.S_IMODE(f.stat().st_mode) == 0o600 and str(f.resolve()).startswith(str(proj.resolve()) + os.sep)
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700 and not (proj / "evil.sh").exists()
    typed = next(c["args"][3] for c in herdr.calls if c["args"][:2] == ["pane", "send-text"])
    first, second, text = typed.split(" ", 2)
    assert text == "What is wrong with this render?"                                             # the paths first, in order, then the text
    assert Path(first).read_bytes() == PNG and Path(second).read_bytes() == JPEG
    assert {first, second} == {str(f.resolve()) for f in files}


def test_a_harness_that_takes_no_image_is_refused_saying_why_and_nothing_is_written_or_typed(stack):
    fake, cockpit, herdr, proj, _ = stack
    cockpit.create_session("cursor", "Chest fit audit", str(proj), by="user", scene_session_id=SCENE)
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        out = _send(fake, ws, "look", [PNG])
    assert out["result"]["ok"] is False and out["result"]["code"] == "images_unsupported"
    assert "Cursor" in out["result"]["message"] and "image" in out["result"]["message"]
    assert not (proj / ".lampway").exists() and not [c for c in herdr.calls if c["args"][:2] == ["pane", "send-text"]]


def test_what_is_not_an_image_is_refused_and_nothing_is_typed(stack):
    fake, cockpit, herdr, proj, _ = stack
    claude_pane(cockpit, proj)
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        out = _send(fake, ws, "look", [b"#!/bin/sh\nrm -rf /\n"])
    assert out["result"]["ok"] is False and out["result"]["code"] == "images_refused"
    assert not [c for c in herdr.calls if c["args"][:2] == ["pane", "send-text"]]


def test_an_image_never_lands_outside_the_project_root_through_a_symlink(stack, tmp_path):
    fake, cockpit, herdr, proj, _ = stack
    claude_pane(cockpit, proj)
    outside = tmp_path / "outside"
    outside.mkdir()
    (proj / ".lampway").symlink_to(outside)
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        out = _send(fake, ws, "look", [PNG])
    assert out["result"]["ok"] is False and "outside the project root" in out["result"]["message"]
    assert list(outside.iterdir()) == [] and not [c for c in herdr.calls if c["args"][:2] == ["pane", "send-text"]]


def test_an_agent_socket_never_carries_images_into_a_pane(stack):
    fake, cockpit, herdr, proj, settings = stack
    rec, _ = claude_pane(cockpit, proj)
    cockpit.set_agent_sends(rec["id"], True)
    with fake.connect_ws(token=_agent_token(settings)) as ws:
        fake.handshake(ws)
        out = _send(fake, ws, "look", [PNG])
    assert out["result"]["code"] == "agent_origin" and not (proj / ".lampway").exists()


# ------------------------------------------------------------------------------------------------------------------- ended panes
def test_an_ended_pane_with_a_session_id_is_offered_for_resume_and_one_without_is_not(stack):
    fake, cockpit, herdr, proj, _ = stack
    rec, _ = claude_pane(cockpit, proj)
    _end(cockpit, rec["id"])
    other = "5c1e0000-0000-4000-8000-00000000001b"
    oc = cockpit.create_session("opencode", "Look dev pass", str(proj), by="user", scene_session_id=other)   # OpenCode picks its own id
    _end(cockpit, oc["id"])
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        got = observe(fake, ws)
        no = observe(fake, ws, session_id=other)
    assert got["view"] == "ended" and got["resumable"] is True and "Resume" in got["help"][0]
    assert no["view"] == "ended" and no["resumable"] is False and "cannot be resumed" in no["help"][0]


def test_resume_is_the_users_click_a_new_pane_resumes_the_stored_session_bound_to_the_same_tab(stack):
    fake, cockpit, herdr, proj, _ = stack
    rec, _ = claude_pane(cockpit, proj)
    _end(cockpit, rec["id"])
    starts_before = len([c for c in herdr.calls if c["args"][:2] == ["agent", "start"]])
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        out = _rpc(fake, ws, "agent.byoa.resume", {"session_id": SCENE})
        again = observe(fake, ws)
    assert out["result"]["ok"] is True and out["result"]["resumed"] == rec["id"] and out["result"]["harness"] == "claude"
    starts = [c["args"] for c in herdr.calls if c["args"][:2] == ["agent", "start"]][starts_before:]
    assert len(starts) == 1 and starts[0][starts[0].index("--") + 1:][:2] == ["--resume", rec["native_id"]]
    new = next(s for s in cockpit.list_sessions() if s["id"] == out["result"]["pane"])
    old = next(s for s in cockpit.list_sessions() if s["id"] == rec["id"])
    assert new["scene_session_id"] == SCENE and new["native_id"] == rec["native_id"] and new["state"] == "live"
    assert old["scene_session_id"] is None and old["state"] == "ended"                            # kept, unbound: never deleted
    assert again["view"] == "transcript" and again["pane"] == new["id"]


def test_nothing_resumes_by_itself_or_for_an_agent(stack):
    fake, cockpit, herdr, proj, settings = stack
    rec, _ = claude_pane(cockpit, proj)
    _end(cockpit, rec["id"])
    starts_before = len([c for c in herdr.calls if c["args"][:2] == ["agent", "start"]])
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        observe(fake, ws)                                                                          # reopening the file only looks
    cockpit.reconcile()
    with fake.connect_ws(token=_agent_token(settings)) as ws:
        fake.handshake(ws)
        out = _rpc(fake, ws, "agent.byoa.resume", {"session_id": SCENE})
        unbind = _rpc(fake, ws, "agent.byoa.unbind", {"session_id": SCENE})
    assert out["result"]["code"] == "agent_origin" and unbind["result"]["code"] == "agent_origin"
    assert len([c for c in herdr.calls if c["args"][:2] == ["agent", "start"]]) == starts_before
    assert next(s for s in cockpit.list_sessions() if s["id"] == rec["id"])["scene_session_id"] == SCENE


def test_resume_needs_the_byoa_switch_and_a_session_id(stack, monkeypatch):
    fake, cockpit, herdr, proj, _ = stack
    oc = cockpit.create_session("opencode", "Look dev pass", str(proj), by="user", scene_session_id=SCENE)
    _end(cockpit, oc["id"])
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        no_id = _rpc(fake, ws, "agent.byoa.resume", {"session_id": SCENE})
        monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "0")
        off = _rpc(fake, ws, "agent.byoa.resume", {"session_id": SCENE})
    assert no_id["result"]["code"] == "resume_refused" and "no OpenCode session id" in no_id["result"]["message"]
    assert off["result"]["code"] == "resume_refused" and "off" in off["result"]["message"]


def test_unbind_lets_the_tab_go_and_keeps_the_panes_record(stack):
    fake, cockpit, herdr, proj, _ = stack
    rec, _ = claude_pane(cockpit, proj)
    _end(cockpit, rec["id"])
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        out = _rpc(fake, ws, "agent.byoa.unbind", {"session_id": SCENE})
        after = observe(fake, ws)
    assert out["result"]["ok"] is True and out["result"]["unbound"] == [rec["id"]]
    assert after["view"] == "none" and after["code"] == "not_bound"
    assert next(s for s in cockpit.list_sessions() if s["id"] == rec["id"])["state"] == "ended"
    assert not [c for c in herdr.calls if c["args"][:2] == ["pane", "close"]]


# ------------------------------------------------------------------------------------------------------------------- observation
def test_a_pane_shown_by_its_screen_reports_herdrs_own_working_or_idle_reading(stack):
    fake, cockpit, herdr, proj, _ = stack
    rec = cockpit.create_session("opencode", "Look dev pass", str(proj), by="user", scene_session_id=SCENE)
    real = herdr.__class__.__call__

    def answer(self, root, args, timeout=30, input=None):
        args = [str(a) for a in args]
        if args[:2] == ["pane", "get"]:
            self.calls.append({"args": args, "sends_before": []})
            return json.dumps({"result": {"pane": {"pane_id": args[2], "agent": "opencode", "agent_status": "working"}}})
        return real(self, root, args, timeout, input)
    herdr.__class__ = type("WorkingHerdr", (herdr.__class__,), {"__call__": answer})
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        got = observe(fake, ws)
    assert got["view"] == "screen" and got["agent_status"] == "working"
    assert ["pane", "get", rec["pane_id"]] in [c["args"] for c in herdr.calls]


def test_a_pi_pane_streams_its_own_session_file_as_observed_turns(stack, tmp_path, monkeypatch):
    fake, cockpit, herdr, proj, _ = stack
    from lampway_server.herdr.observers import native as N
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "pi-agent"))
    rec = cockpit.create_session("pi", "Cone pass", str(proj), by="user", scene_session_id=SCENE)
    start = next(c["args"] for c in herdr.calls if c["args"][:2] == ["agent", "start"])
    assert start[start.index("--") + 1:][:2] == ["--session-id", rec["native_id"]] and "-e" in start      # Lampway picked the id
    path = tmp_path / "pi-agent" / "sessions" / N.pi_session_folder(rec["cwd"]) / f"2026-10-07T10-00-00-000Z_{rec['native_id']}.jsonl"
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        assert observe(fake, ws)["view"] == "transcript"
        path.parent.mkdir(parents=True)
        path.write_text(jsonl([dict(PI_TURNS[0], id=rec["native_id"]), *PI_TURNS[1:7]]))
        frames = until(ws, lambda f: f.get("method") == "agent.turn.ended")
    started = next(f["params"] for f in frames if f.get("method") == "agent.turn.started")
    assert started["user_text"] == "Add a cone" and started["harness"] == "pi" and PI_SESSION != rec["native_id"]


def test_a_codex_panes_session_id_is_recorded_from_its_rollout_so_it_can_be_resumed(stack, tmp_path):
    fake, cockpit, herdr, proj, _ = stack
    from .byoa_fixtures import CODEX_SESSION, CODEX_TURNS
    rec = cockpit.create_session("codex", "Boots seed read", str(proj), by="user", scene_session_id=SCENE)
    assert rec["native_id"] is None                                                              # Codex picks its own
    day = tmp_path / "codex-home" / "sessions" / "2026" / "10" / "07"
    meta = dict(CODEX_TURNS[0], payload=dict(CODEX_TURNS[0]["payload"], cwd=rec["cwd"],
                                              timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(rec["created_at"] + 1))))
    append(day / "rollout-mine.jsonl", [meta])
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        assert observe(fake, ws)["view"] == "transcript"
    assert next(s for s in cockpit.list_sessions() if s["id"] == rec["id"])["native_id"] == CODEX_SESSION
