# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only compatibility snapshots stay inside native history ownership."""
import threading
import types
import os
import socket
import subprocess

import pytest
from pydantic import BaseModel, ConfigDict

from lampway_server.engine import hermes_features as F


@pytest.fixture(autouse=True)
def refuse_effects(monkeypatch):
    def refused(*args, **kwargs):
        pytest.fail("pure history control attempted process, network or signal")
    monkeypatch.setattr(subprocess.Popen, "__init__", refused)
    monkeypatch.setattr(socket.socket, "connect", refused)
    monkeypatch.setattr(os, "kill", refused)
    monkeypatch.setattr(os, "killpg", refused)


@pytest.fixture
def native(tmp_path):
    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")
        session_id: str
    class History(BaseModel):
        model_config = ConfigDict(extra="forbid")
        count: int
        messages: list[dict]
    module = types.ModuleType("tui_gateway.server")
    session = {"history_lock": threading.Lock(), "history_version": 2,
               "history": [{"role": "user", "text": "keep"}], "running": False}
    module._sessions = {"sid": session}
    module._sess_nowait = lambda params, rid: (module._sessions.get(params.get("session_id")),
        None if params.get("session_id") in module._sessions else {"error": {"code": 4001}})
    module._err = lambda rid, code, message: {"id": rid, "error": {"code": code, "message": message}}
    module._ok = lambda rid, result: {"id": rid, "result": result}
    def history(rid, params):
        if hasattr(module, "projection_read"):
            module.projection_read()
        return module._ok(rid, {"count": len(session["history"]), "messages": list(session["history"])})
    calls = []
    def undo(rid, params):
        calls.append("native undo")
        if session["running"]:
            return {"error": {"code": 4009}}
        with session["history_lock"]:
            session["history"].clear()
            session["history_version"] += 1
        return module._ok(rid, {"removed": 1})
    module._methods = {"session.history": history, "session.undo": undo}
    module.register_method = lambda name, fn: module._methods.__setitem__(name, fn)
    module._contracts = types.SimpleNamespace(METHODS={"session.history": types.SimpleNamespace(params=Params, result=History)})
    events = []
    module._emit = lambda *args: events.append(args) or True
    module._fallback_session_info = lambda current: {"running": current["running"]}
    module._spawn_side_agent = lambda *args, **kwargs: None
    F.install_module(module, F.Policy(tmp_path))
    return module, session, calls, events


def test_snapshot_uses_native_projection_and_revision_in_one_lock(native):
    module, session, _, _ = native
    original = module._methods["session.history"]
    result = module._methods["lampway.history_snapshot"](7, {"session_id": "sid"})["result"]
    assert result == {"protocol": 1, "session_id": "sid", "revision": 2,
                      "history": original(8, {"session_id": "sid"})["result"]}
    assert not session["history_lock"].locked()


def test_undo_runs_once_and_notifies_only_success(native):
    module, session, calls, events = native
    assert module._methods["session.undo"](7, {"session_id": "sid"})["result"] == {"removed": 1}
    assert calls == ["native undo"]
    assert events == [("session.info", "sid", {"running": False,
        "lampway_history": {"protocol": 1, "revision": 3}})]
    session["running"] = True
    assert module._methods["session.undo"](8, {"session_id": "sid"})["error"]["code"] == 4009
    assert calls == ["native undo", "native undo"]
    assert len(events) == 1


def test_snapshot_refuses_busy_and_missing_session(native):
    module, session, _, _ = native
    snapshot = module._methods["lampway.history_snapshot"]
    assert snapshot(7, {"session_id": "missing"})["error"]["code"] == 4001
    session["running"] = True
    assert snapshot(8, {"session_id": "sid"})["error"]["code"] == 4009


def test_failed_notification_cannot_fail_or_repeat_committed_undo(native):
    module, session, calls, _ = native
    def broken(*args):
        raise RuntimeError("owned transport closed")
    module._emit = broken
    assert module._methods["session.undo"](7, {"session_id": "sid"})["result"] == {"removed": 1}
    assert calls == ["native undo"]
    assert session["history_version"] == 3


def test_snapshot_projection_is_locked_and_removed_runtime_cannot_revive(native):
    module, session, _, _ = native
    def read():
        assert session["history_lock"].locked()
        module._sessions.pop("sid")
    module.projection_read = read
    assert module._methods["lampway.history_snapshot"](7, {"session_id": "sid"})["error"]["code"] == 4001


def test_full_native_info_and_original_history_contract_preserved(native):
    module, _, _, events = native
    payload = {"model": "pinned", "title": "Native title", "usage": {"total": 10}, "running": False}
    module._emit("session.info", "sid", payload)
    assert events[-1][2] == {**payload, "lampway_history": {"protocol": 1, "revision": 2}}
    assert payload == {"model": "pinned", "title": "Native title", "usage": {"total": 10}, "running": False}
    contract = module._contracts.METHODS["lampway.history_snapshot"]
    response = module._methods["lampway.history_snapshot"](7, {"session_id": "sid"})["result"]
    contract.result.model_validate(response)
    with pytest.raises(ValueError):
        contract.params.model_validate({"session_id": "sid", "foreign": True})


@pytest.mark.parametrize("params", [None, {}, {"session_id": []}, {"session_id": ""},
    {"session_id": "sid", "foreign": True}])
def test_snapshot_requires_exact_native_session_parameters(native, params):
    module, session, _, _ = native
    assert module._methods["lampway.history_snapshot"](7, params)["error"]["code"] == 4000
    assert session["history_version"] == 2
