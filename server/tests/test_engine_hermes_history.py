# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only compatibility snapshots stay inside native history ownership."""
import threading
import ast
import contextlib
from pathlib import Path
import types
import os
import socket
import subprocess

import pytest
from pydantic import BaseModel, ConfigDict

from lampway_server.engine import hermes_features as F
from lampway_server.engine import hermes_history


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
    module._session_db = lambda current: contextlib.nullcontext(None)
    def display(current, db, fallback):
        if hasattr(module, "projection_read"):
            module.projection_read()
        return fallback
    module._live_visible_history = display
    module._history_to_messages = lambda rows, **kwargs: rows
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
        "lampway_history": {"protocol": 1, "revision": 3, "reason": "undo"}})]
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


ROOT = Path(__file__).resolve().parents[2]

def functions(path, names, namespace):
    tree = ast.parse(path.read_text())
    found = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            node.decorator_list = []
            found.append(node)
    assert len(found) == len(names)
    exec(compile(ast.Module(body=found, type_ignores=[]), str(path), 'exec'), namespace)

@pytest.fixture
def compacted_native(monkeypatch):

    def deny(*args, **kwargs):
        pytest.fail('pure snapshot test attempted external effect')
    monkeypatch.setattr(subprocess.Popen, '__init__', deny)
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(os, 'kill', deny)
    monkeypatch.setattr(os, 'killpg', deny)

    class Params(BaseModel):
        model_config = ConfigDict(extra='forbid')
        session_id: str

    class History(BaseModel):
        model_config = ConfigDict(extra='forbid')
        count: int
        messages: list[dict]
    import threading
    module = types.ModuleType('tui_gateway.server')
    rows = [{'role': 'user', 'content': 'ARCHIVED_KEEP', 'active': 0, 'compacted': 1}, {'role': 'assistant', 'content': 'ARCHIVED_ANSWER', 'active': 0, 'compacted': 1}, {'role': 'user', 'content': 'UNDO_REMOVED', 'active': 0, 'compacted': 0}, {'role': 'assistant', 'content': 'RECENT_KEEP', 'active': 1, 'compacted': 0}]
    reads = []

    class DB:

        def get_messages_as_conversation(self, key, **kwargs):
            reads.append(kwargs)
            return [dict(row) for row in rows if row['active'] or (kwargs.get('include_compacted') and row['compacted'])]
    db = DB()
    session = {'session_key': 'durable', 'history_lock': threading.Lock(), 'history_version': 9, 'history': [rows[-1]], 'running': False}
    module._sessions = {'sid': session}
    module._sess_nowait = lambda params, rid: (session, None)
    module._ok = lambda rid, value: {'id': rid, 'result': value}
    module._err = lambda rid, code, text: {'id': rid, 'error': {'code': code, 'message': text}}
    module._session_db = lambda s: contextlib.nullcontext(db)
    # The formatter is synthetic; projection functions below are pinned native source.
    module._history_to_messages = lambda rows, **kwargs: rows
    module._coerce_message_text = lambda value: value
    module.logger = types.SimpleNamespace(debug=lambda *args: None)
    functions(ROOT / 'third_party/hermes-agent/tui_gateway/server.py', {'_live_visible_history', '_reconcile_display_with_live'}, module.__dict__)
    source = ast.parse((ROOT / 'third_party/hermes-agent/tui_gateway/methods_session.py').read_text())
    for node in source.body:
        if isinstance(node, ast.FunctionDef) and any((isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant) and (d.args[0].value == 'session.history') for d in node.decorator_list)):
            node.decorator_list = []
            node.name = 'native_history'
            break
    else:
        raise AssertionError('native history handler missing')
    module.contextlib = contextlib
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'actual_native_history', 'exec'), module.__dict__)
    module._methods = {'session.history': lambda rid, params: module.native_history(rid, params, session), 'session.undo': lambda rid, params: module._ok(rid, {'removed': 2})}
    module.register_method = lambda name, fn: module._methods.__setitem__(name, fn)
    module._contracts = types.SimpleNamespace(METHODS={'session.history': types.SimpleNamespace(params=Params, result=History)})
    module._emit = lambda *args: True
    module._fallback_session_info = lambda s: {'model': 'native', 'running': False}
    implementation = hermes_history
    implementation.install_module(module)
    return (module, reads)

def test_snapshot_retains_native_compacted_display_and_excludes_undo_rows(compacted_native):
    module, reads = compacted_native
    result = module._methods['lampway.history_snapshot'](7, {'session_id': 'sid'})['result']
    assert reads[-1] == {'include_ancestors': True, 'include_row_ids': True, 'include_compacted': True}
    assert [row['content'] for row in result['history']['messages']] == ['ARCHIVED_KEEP', 'ARCHIVED_ANSWER', 'RECENT_KEEP']
    assert result['revision'] == 9

def test_original_public_history_is_unchanged(compacted_native):
    module, reads = compacted_native
    result = module._methods['session.history'](7, {'session_id': 'sid'})['result']
    assert 'include_compacted' not in reads[-1]
    assert [r['content'] for r in result['messages']] == ['RECENT_KEEP']

@pytest.mark.parametrize('marker', [None, True, 'undo', ['undo']])
def test_nonmapping_reserved_info_marker_cannot_break_native_emit(compacted_native, marker):
    module, _ = compacted_native
    assert module._emit('session.info', 'sid', {'running': False, 'lampway_history': marker}) is True


def test_display_count_retains_native_hidden_seed_count(native):
    module, session, _, _ = native
    session["history"].append({"role": "system", "text": "hidden native seed"})
    module._history_to_messages = lambda rows, **kwargs: rows[:1]
    result = module._methods["lampway.history_snapshot"](7, {"session_id": "sid"})["result"]["history"]
    # Like native session.history, count describes source rows, not rendered blocks.
    assert result["count"] == 2
    assert len(result["messages"]) == 1
