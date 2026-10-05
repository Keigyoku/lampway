# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The paint library's "AI Generate" box, against Lampway's server: enqueue_matgen_job posts the prompt to
POST /api/v1/matgen (bearer from the stored login) on a worker thread, and on the main thread registers and saves the
material the server returns, sets wm.mixar_matgen_status to "done:<name>" and lists it under "Just Generated". A
failure lands in the status as "error:<reason>"; a prompt already in flight is refused (None) like upstream did."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.paint.procedural_materials import matgen_queue as Q  # noqa: E402
from mixar.modules.paint.procedural_materials import material_registry as R  # noqa: E402

REPLY = {"material_id": "matgen_abc123", "name": "Worn Copper", "node_group_name": "LW_WornCopper_1a2b",
         "script": "import bpy\ng = bpy.data.node_groups.new('LW_WornCopper_1a2b', 'ShaderNodeTree')\n",
         "description": "worn copper", "category": "ai_generated"}


@pytest.fixture
def wiring(monkeypatch):
    posted, timers, saved = [], [], []
    wm = SimpleNamespace(mixar_matgen_status="generating", mixar_matgen_recent=MagicMock())

    def post(path, body):
        posted.append((path, body))
        return dict(REPLY)
    monkeypatch.setattr(Q, "_post", post)
    monkeypatch.setattr(Q, "_run_in_thread", lambda fn: fn())                      # synchronous for the test
    monkeypatch.setattr(Q, "_on_main_thread", lambda fn: timers.append(fn))
    monkeypatch.setattr(Q, "_window_manager", lambda: wm)
    monkeypatch.setattr(Q.matgen_persistence, "save_material", lambda m: saved.append(m) or m)
    R.unload_all_materials()
    Q._in_flight.clear()
    return posted, timers, saved, wm


def test_a_prompt_becomes_a_registered_saved_material_listed_as_just_generated(wiring):
    posted, timers, saved, wm = wiring
    job = Q.enqueue_matgen_job(prompt="worn copper", pipeline="fast")
    assert job is not None and job.id and job.state.value == "queued"
    assert posted == [("/api/v1/matgen", {"prompt": "worn copper", "pipeline": "fast"})]
    assert len(timers) == 1
    timers[0]()                                                   # the main-thread tail
    material = R.get_material("matgen_abc123")
    assert material is not None and material.node_group_name == "LW_WornCopper_1a2b" and material.script.startswith("import bpy")
    assert saved and saved[0].material_id == "matgen_abc123"
    assert wm.mixar_matgen_status == "done:Worn Copper"
    item = wm.mixar_matgen_recent.add.return_value
    assert item.material_id == "matgen_abc123" and item.display_name == "Worn Copper"
    assert job.state.value == "done"


def test_a_server_refusal_lands_in_the_status_as_an_error(wiring, monkeypatch):
    posted, timers, saved, wm = wiring

    def refuse(path, body):
        raise Q.MatgenUnavailable("no usable script: the script imports os")
    monkeypatch.setattr(Q, "_post", refuse)
    job = Q.enqueue_matgen_job(prompt="glass")
    timers[0]()
    assert wm.mixar_matgen_status.startswith("error:") and "imports os" in wm.mixar_matgen_status
    assert job.state.value == "failed" and not saved


def test_the_same_prompt_in_flight_is_refused(wiring, monkeypatch):
    posted, timers, saved, wm = wiring
    monkeypatch.setattr(Q, "_run_in_thread", lambda fn: None)      # never finishes
    assert Q.enqueue_matgen_job(prompt="glass") is not None
    assert Q.enqueue_matgen_job(prompt="glass") is None


def test_the_post_carries_the_bearer_to_the_servers_url(monkeypatch):
    import urllib.request
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(REPLY).encode()

    def urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        seen["body"] = json.loads(req.data)
        return Resp()
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(Q, "_server_url", lambda: "http://127.0.0.1:8787")
    monkeypatch.setattr(Q, "_access_token", lambda: "tok")
    assert Q._post("/api/v1/matgen", {"prompt": "x"})["material_id"] == "matgen_abc123"
    assert seen == {"url": "http://127.0.0.1:8787/api/v1/matgen", "auth": "Bearer tok", "body": {"prompt": "x"}}
