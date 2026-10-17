# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Q2: native ended-only visibility policy, with resumable Hermes records retained."""
import json
import os
import subprocess
from pathlib import Path

import pytest

from lampway_server.engine import session_retention as R
from .test_engine_hermes_config import ENGINE


def test_native_candidate_policy_uses_ended_tips_and_oldest_visible_overflow():
    class DB:
        def __init__(self):
            self.rows = [{"id": str(i), "ended_at": 1, "hidden": i == 0, "archived": False} for i in range(202)]
            self.asked = []
            self.archived = []

        def archive_sessions(self, **kw):
            self.asked.append(kw)
            return 2

        def list_prune_candidates(self, **kw):
            self.asked.append(kw)
            return self.rows

        def get_session(self, sid):
            return self.rows[int(sid)]

        def set_session_archived(self, sid, archived):
            self.archived.append((sid, archived))
            return True

    db = DB()
    assert R.maintain(db) == {"aged": 2, "overflow": 1}
    assert db.asked == [{"older_than_days": 30, "include_pinned": True},
                        {"archived": False, "lineage_tips_only": True, "include_pinned": True}]
    assert db.archived == [("1", True)]


NATIVE_PROOF = r'''
import json, runpy, sys, time
from pathlib import Path
from unittest.mock import patch
from hermes_state import SessionDB
maintain = runpy.run_path(sys.argv[2])["maintain"]
db = SessionDB(Path(sys.argv[1]) / "state.db")
now = time.time()
try:
    def create(sid, at, ended=True, parent=None, reason="user_close"):
        with patch("time.time", return_value=at):
            db.create_session(sid, source="cli", **({"parent_session_id": parent} if parent else {}))
            db.append_message(sid, "user", "Synthetic history " + sid)
            if ended:
                db.end_session(sid, reason)
    create("aged", now-35*86400)
    create("open-old", now-40*86400, ended=False)
    create("compressed-root", now-40*86400, reason="compression")
    create("open-tip", now-10, ended=False, parent="compressed-root")
    for i in range(201):
        create("recent-%03d" % i, now-1000+i)
    before = {row["id"]: db.get_messages_as_conversation(row["id"])
              for row in db.list_sessions_rich(limit=1000, include_children=True, include_archived=True)}
    # Causal RED state before the policy: the old ended row and 201 fresh ended rows are visible.
    assert not db.get_session("aged")["archived"]
    assert len(db.list_prune_candidates(archived=False, lineage_tips_only=True)) == 202
    assert maintain(db) == {"aged": 1, "overflow": 1}
    assert db.get_session("aged")["archived"] == 1
    assert db.get_session("recent-000")["archived"] == 1
    assert len(db.list_prune_candidates(archived=False, lineage_tips_only=True)) == 200
    for sid in ("open-old", "open-tip", "compressed-root"):
        assert db.get_session(sid)["archived"] == 0
    assert maintain(db) == {"aged": 0, "overflow": 0}
    for sid, messages in before.items():
        assert db.get_session(sid) is not None
        assert db.get_messages_as_conversation(sid) == messages
    db.reopen_session("aged")
    assert db.get_session("aged")["ended_at"] is None
    assert db.get_messages_as_conversation("aged") == before["aged"]
    print(json.dumps({"aged": 1, "overflow": 1, "visible_ended": 200, "active_preserved": True,
                      "compression_lineage_preserved": True, "messages_preserved": True, "resume": True,
                      "native_module": __import__("hermes_state").__file__}))
finally:
    db.close()
'''


@pytest.mark.skipif(ENGINE is None, reason="pinned Hermes engine missing; native retention unverified")
def test_actual_native_helpers_hide_30_day_and_200_overflow_but_keep_resume(tmp_path):
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path), "HERMES_HOME": str(tmp_path),
           "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([str(ENGINE.parent / "python"), "-c", NATIVE_PROOF, str(tmp_path), str(Path(R.__file__))],
                            env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    proof = json.loads(result.stdout)
    assert proof["visible_ended"] == 200 and proof["messages_preserved"] and proof["resume"]


@pytest.mark.anyio
@pytest.mark.skipif(ENGINE is None, reason="pinned Hermes engine missing; owned-home maintenance unverified")
async def test_maintenance_runs_native_helper_only_for_recorded_owned_home_and_pins_restart_config(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import yaml
    from lampway_server.engine.units import Mode1Units
    from lampway_server import connections

    state = tmp_path / "state"
    home = state / "agent" / "hermes" / "scene-1"
    home.mkdir(parents=True)
    test_actual_native_helpers_hide_30_day_and_200_overflow_but_keep_resume(home)
    config = {"compression": {"threshold": 0.37}, "sessions": {"auto_prune": True, "auto_archive": True}}
    (home / "config.yaml").write_text(yaml.safe_dump(config))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "config.yaml").write_text("sessions: {auto_prune: true}\n")
    before = (outside / "config.yaml").read_bytes()
    units = Mode1Units.__new__(Mode1Units)
    units.engine = {"dir": str(ENGINE.parents[2])}
    units.state_dir = state
    units.cockpit = SimpleNamespace(list_sessions=lambda: [
        {"agent": "lampway_hermes", "home": str(home), "state": "ended"},
        {"agent": "lampway_hermes", "home": str(outside), "state": "ended"},
        {"agent": "codex", "home": str(outside), "state": "live"}])
    monkeypatch.setattr(connections, "env_for", lambda ids: {"PATH": os.environ.get("PATH", "")})
    await units.maintain_sessions()
    final = yaml.safe_load((home / "config.yaml").read_text())
    assert final["sessions"] == {"auto_prune": False, "auto_archive": False}
    assert final["compression"] == config["compression"]
    assert (outside / "config.yaml").read_bytes() == before


GLOBAL_NATIVE_PROOF = r'''
import json, subprocess, sys, time
from pathlib import Path
from unittest.mock import patch
from hermes_state import SessionDB
root = Path(sys.argv[1])
now = time.time()
dbs = []
before = {}
def apply_global_policy():
    homes = [str(root / ("home%d" % index)) for index in range(2)]
    result = subprocess.run([sys.executable, sys.argv[2]], input=json.dumps(homes),
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)
try:
    for index in range(2):
        home = root / ("home%d" % index)
        home.mkdir()
        db = SessionDB(home / "state.db")
        dbs.append(db)
        for i in range(125):
            sid = "recent-%03d" % i
            with patch("time.time", return_value=now-1000+index*500+i):
                db.create_session(sid, source="cli")
                db.append_message(sid, "user", "Synthetic two-home history " + sid)
                db.end_session(sid, "user_close")
            before[index, sid] = db.get_messages_as_conversation(sid)
        with patch("time.time", return_value=now-40*86400):
            for sid in ("aged", "open-old"):
                db.create_session(sid, source="cli")
                db.append_message(sid, "user", "Synthetic two-home " + sid)
            db.end_session("aged", "user_close")
        before[index, "aged"] = db.get_messages_as_conversation("aged")
        before[index, "open-old"] = db.get_messages_as_conversation("open-old")
    assert sum(len(db.list_prune_candidates(archived=False, lineage_tips_only=True)) for db in dbs) == 252
    assert apply_global_policy() == {"aged": 2, "overflow": 50}
    counts = [len(db.list_prune_candidates(archived=False, lineage_tips_only=True)) for db in dbs]
    assert counts == [75, 125] and sum(counts) == 200
    assert dbs[0].get_session("recent-049")["archived"] == 1
    assert dbs[0].get_session("recent-050")["archived"] == 0
    assert apply_global_policy() == {"aged": 0, "overflow": 0}
    for (index, sid), messages in before.items():
        assert dbs[index].get_messages_as_conversation(sid) == messages
    for db in dbs:
        assert db.get_session("open-old")["ended_at"] is None
        assert not db.get_session("open-old")["archived"]
        db.reopen_session("aged")
        assert db.get_session("aged")["ended_at"] is None
    print(json.dumps({"visible_ended_global": sum(counts), "per_home": counts, "aged": 2, "overflow": 50,
                      "active_preserved": True, "resumable_messages_preserved": True}))
finally:
    for db in dbs: db.close()
'''


@pytest.mark.skipif(ENGINE is None, reason="pinned Hermes engine missing; global retention unverified")
def test_actual_two_native_homes_share_one_200_visible_ended_limit(tmp_path):
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path), "HERMES_HOME": str(tmp_path),
           "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([str(ENGINE.parent / "python"), "-c", GLOBAL_NATIVE_PROOF,
                             str(tmp_path), str(Path(R.__file__))], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    proof = json.loads(result.stdout)
    assert proof["visible_ended_global"] == 200 and proof["per_home"] == [75, 125]
