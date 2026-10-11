# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The archive Lampway's server serves from Hermes's sessions (docs/reports/agent-modes-spec.md R2) is one the client's own store
writes: the server's packets (``server/lampway_server/engine/history.py``, standard library only, loaded here by path) go
through the real ``agent_history/core/store.py`` ``write_batch``. A rewrite of Hermes's session (an undo) comes as a new epoch,
which the store records as a gap, never a replay conflict."""
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def server_history(monkeypatch):
    spec = importlib.util.spec_from_file_location("lampway_engine_history_under_test",
                                                  ROOT / "server/lampway_server/engine/history.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client_store(tmp_path, monkeypatch):
    root = ROOT / 'src/scripts/mixar/modules/common/agent_history'
    package = types.ModuleType('archive_hermes_fixture')
    package.__path__ = [str(root)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    spec = importlib.util.spec_from_file_location(package.__name__ + '.core.store', root / 'core/store.py')
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'root', lambda: tmp_path)
    return module


# session.history rows as the pinned serve answers them (measured 2026-10-07): user and assistant rows with a row id, a tool row
# with its name and context instead
HISTORY = [{"role": "user", "text": "what is in my scene?", "timestamp": 1791397513.16, "row_id": 1},
           {"role": "tool", "name": "tool_call", "context": "Lampway · scene summary", "tool_call_id": "call_1",
            "args": {"calls": [{"name": "mcp__lampway__scene_summary", "arguments": {}}]}},
           {"role": "assistant", "text": "There is one cube.", "row_id": 3},
           {"role": "user", "text": "make it red", "row_id": 4},
           {"role": "assistant", "text": "Red it is.", "row_id": 5}]


def test_the_servers_packets_are_written_by_the_clients_store_and_a_rewrite_is_a_new_epoch(server_history, client_store):
    H = server_history
    ledger = H.Ledger()
    stored = "20261007_182509_74b2bb"
    recs = H.records(stored, HISTORY)
    st = ledger.settle(stored, [H.event_id(r) for r in recs])
    p, ids = H.packet("scene-1", stored, st, recs)
    ack = client_store.write_batch(H.OWNER_ID, json.loads(json.dumps(p)), "scene-history")
    assert ack == {"session_id": "scene-1", "epoch": p["epoch"], "seq": 5}
    assert ledger.acknowledge(stored, st["gen"], ack["seq"], ids)
    read = client_store.read(H.OWNER_ID, "scene-1", limit=20)
    assert read["status"] == "available" and len(read["records"]) == 5 and "Red it is." in read["records"][0]["text"]
    # Hermes's undo dropped the last turn and a new one followed: delivered again, whole, under a new epoch
    rewritten = HISTORY[:3] + [{"role": "user", "text": "make it blue", "row_id": 6}, {"role": "assistant", "text": "Blue.", "row_id": 7}]
    recs2 = H.records(stored, rewritten)
    st2 = ledger.settle(stored, [H.event_id(r) for r in recs2])
    p2, _ = H.packet("scene-1", stored, st2, recs2)
    assert p2["epoch"] != p["epoch"] and [r["seq"] for r in p2["records"]] == [1, 2, 3, 4, 5]
    ack2 = client_store.write_batch(H.OWNER_ID, json.loads(json.dumps(p2)), "scene-history")
    assert ack2["seq"] == 5 and ack2["epoch"] == p2["epoch"]
    manifest = json.loads((client_store.root() / "scene-1" / "manifest.json").read_text())
    assert {"epoch": p2["epoch"], "reason": "delivery_epoch_changed"} in manifest["gaps"]
    # nothing new after the acknowledgement: no packet
    assert ledger.acknowledge(stored, st2["gen"], 5, [H.event_id(r) for r in recs2])
    st3 = ledger.settle(stored, [H.event_id(r) for r in recs2])
    assert H.packet("scene-1", stored, st3, recs2)[0] is None
