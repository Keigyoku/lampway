# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The client's execution harness (harness v3) against the REAL binary: why workers must be separate processes, and how their work
gets into the user's scene.

  * workers in ONE process (the old lane-scene design) share bpy.data, so three workers that each draw the collection by name leave
    one collection standing;
  * three worker PROCESSES each stage their own native artifact and the parent's typed ``append_collection`` commit lands all three;
  * the commit is refused for a stale epoch, a stale fence, a revoked task; an operation id is applied once and replayed by payload hash;
    the journal records PREPARED then APPLIED;
  * ``staging.export_copies`` / ``import_artifact`` (a Lampway addition) hand a worker the objects it must work on.
"""

import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

INSTANCE = "inst1"


def dirs(tmp_path):
    cache = tmp_path / "cache"
    stage = cache / "agent_artifacts" / INSTANCE
    stage.mkdir(parents=True, exist_ok=True)
    return str(cache), str(stage)


def worker(tmp_path, name, objs, extra=""):
    """One worker PROCESS: build the objects in a collection named QA_candidates (the same name in every worker), stage them."""
    cache, stage = dirs(tmp_path)
    aid = str(uuid.uuid4())
    r = run_script(f'''
import bpy, json
from mixar.modules.common.agent_execution import staging
col = bpy.data.collections.new("QA_candidates"); bpy.context.scene.collection.children.link(col)
for n in {objs!r}:
    me = bpy.data.meshes.new(n); ob = bpy.data.objects.new(n, me); col.objects.link(ob)
{extra}
m = staging.stage_collection({aid!r}, {name!r}, {objs!r})
print("RESULT", json.dumps(m))
''', env={"LAMPWAY_SANDBOX_STAGING_DIR": stage, "LAMPWAY_AGENT_CACHE_DIR": cache, "LAMPWAY_HOME": str(tmp_path / "home")})
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


PARENT = '''
import bpy, json, hashlib
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.common.agent_execution import handlers, bindings, journal as J, paths
bpy.context.window_manager.mixie_instance_id = "inst1"
bpy.context.scene.mixie_session_id = "S1"
D = handlers.dispatch
def commit(art, task, op, epoch, fence, name=None, payload=None):
    base = {"op": "append_collection", "run_id": "R1", "task_id": task, "artifact_id": art["artifact_id"],
            "content_hash": art["content_hash"], "collection_name": name or art["collection_name"], "target_collection": "Lampway Agent"}
    h = hashlib.sha256(json.dumps(payload or base, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return D("agent.execution.commit", {**base, "turn_epoch": epoch, "generation": 0, "fence_token": fence, "operation_id": op, "payload_hash": h})
def activate(epoch=100, run="R1"):
    return D("agent.execution.activate", {"protocol_version": "v3", "run_id": run, "session_id": "S1", "turn_epoch": epoch})
def bind(task, fence=1, epoch=100, run="R1", worker="w"):
    return D("agent.execution.bind_task", {"run_id": run, "turn_epoch": epoch, "task_id": task, "generation": 0, "attempt": 1,
                                           "fence_token": fence, "worker_connection_id": worker, "execution_class": "worker"})
'''


def parent(tmp_path, body, env=None):
    cache, _ = dirs(tmp_path)
    e = {"MIXAR_AGENT_CACHE_DIR": cache, "LAMPWAY_HOME": str(tmp_path / "home")}
    e.update(env or {})
    r = run_script(PARENT + body, env=e)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_workers_in_one_process_share_bpy_data_so_three_by_name_draws_leave_one_collection():
    r = run_script('''
import bpy, json
def draw(scene_name, marker):
    # what the old swarm's lane workers did: "replace the collection by name" in the ONE bpy.data they all share
    old = bpy.data.collections.get("QA_candidates")
    if old:
        for o in list(old.objects): bpy.data.objects.remove(o)
        bpy.data.collections.remove(old)
    col = bpy.data.collections.new("QA_candidates")
    sc = bpy.data.scenes.get(scene_name) or bpy.data.scenes.new(scene_name)
    sc.collection.children.link(col)
    col.objects.link(bpy.data.objects.new(marker, bpy.data.meshes.new(marker)))
for i in (1, 2, 3): draw(f"lane{i}", f"w{i}_L000")
print("RESULT", json.dumps({"collections": [c.name for c in bpy.data.collections], "objects": sorted(o.name for o in bpy.data.objects if o.name.startswith("w"))}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    assert out["collections"].count("QA_candidates") == 1 and out["objects"] == ["w3_L000"], "two of the three workers' markers are gone"


def test_three_worker_processes_each_stage_their_own_artifact_and_all_three_commit(tmp_path):
    arts = [worker(tmp_path, f"w{i}", [f"w{i}_L000", f"w{i}_label"]) for i in (1, 2, 3)]
    assert len({a["artifact_id"] for a in arts}) == 3 and all(a["finite"] is False or a["object_count"] == 2 for a in arts)
    out = parent(tmp_path, f'''
arts = {arts!r}
res = {{"activate": activate(), "binds": [bind(f"w{{i}}", 1) for i in (1, 2, 3)]}}
res["commits"] = [commit(a, f"w{{i + 1}}", f"op{{i}}", 100, 1) for i, a in enumerate(arts)]
agent = bpy.data.collections["Lampway Agent"]
res["children"] = sorted(c.name for c in agent.children)
res["objects"] = sorted(o.name for c in agent.children for o in c.all_objects)
res["status"] = D("agent.execution.status", {{"operation_ids": ["op0", "op1", "op2", "nope"]}})
print("RESULT", json.dumps(res, default=str))
''')
    assert out["activate"]["success"] and all(b["success"] for b in out["binds"])
    assert all(c["success"] and c["state"] == "applied" for c in out["commits"]), out["commits"]
    assert len(out["children"]) == 3 and out["objects"] == sorted(f"w{i}_{s}" for i in (1, 2, 3) for s in ("L000", "label"))
    st = out["status"]["operations"]
    assert [st[f"op{i}"]["state"] for i in range(3)] == ["applied"] * 3 and st["nope"]["state"] == "unknown"


def test_a_commit_is_refused_for_an_unbound_task_a_stale_fence_a_wrong_epoch_and_a_revoked_task(tmp_path):
    a1, a2, a3, a4 = (worker(tmp_path, f"w{i}", [f"w{i}_x"]) for i in (1, 2, 3, 4))
    out = parent(tmp_path, f'''
a1, a2, a3, a4 = {[a1, a2, a3, a4]!r}
res = {{"activate": activate(), "bind1": bind("t1", fence=5)}}
res["unbound"] = commit(a2, "t2", "o2", 100, 1)
res["stale_fence"] = commit(a1, "t1", "o1", 100, 4)
res["wrong_epoch"] = commit(a1, "t1", "o1b", 99, 5)
D("agent.execution.bind_task", {{"run_id": "R1", "turn_epoch": 100, "task_id": "t3", "generation": 0, "attempt": 1, "fence_token": 1,
                                  "worker_connection_id": "w", "execution_class": "worker"}})
res["revoke"] = D("agent.execution.revoke", {{"run_id": "R1", "task_id": "t3"}})
res["revoked_task"] = commit(a3, "t3", "o3", 100, 1)
res["ok_after"] = commit(a1, "t1", "o1c", 100, 5)
res["older_epoch_activate"] = activate(epoch=100, run="R2")
res["newer_epoch_activate"] = activate(epoch=101, run="R2")
res["old_run_commit"] = commit(a4, "t1", "o4", 100, 5)
print("RESULT", json.dumps(res, default=str))
''')
    assert out["unbound"]["error_type"] == "stale_fence"
    assert out["stale_fence"]["error_type"] == "stale_fence" and out["wrong_epoch"]["error_type"] == "stale_epoch"
    assert out["revoked_task"]["error_type"] == "stale_fence"
    assert out["ok_after"]["success"] is True, "a refusal did not poison a legitimate commit"
    assert out["older_epoch_activate"]["error_type"] == "stale_epoch" and out["newer_epoch_activate"]["success"] is True
    assert out["old_run_commit"]["error_type"] == "stale_epoch", "a newer epoch revoked the previous run"


def test_an_operation_is_applied_once_replayed_by_hash_and_refused_for_a_different_payload(tmp_path):
    a = worker(tmp_path, "w1", ["w1_x"])
    out = parent(tmp_path, f'''
a = {a!r}
activate(); bind("t1", 1)
first = commit(a, "t1", "opX", 100, 1)
replay = commit(a, "t1", "opX", 100, 1)
other = commit(a, "t1", "opX", 100, 1, name="different")
J_ = J.get_journal()
rec = J_.op_get("opX")
print("RESULT", json.dumps({{"first": first, "replay": replay, "other": other, "state": rec["state"],
                              "children": [c.name for c in bpy.data.collections["Lampway Agent"].children]}}, default=str))
''')
    assert out["first"]["success"] and out["first"]["state"] == "applied"
    assert out["replay"]["success"] and out["replay"]["replayed"] is True and len(out["children"]) == 1
    assert out["other"]["error_type"] == "payload_mismatch" and out["state"] == "applied"


def test_export_copies_and_import_artifact_hand_a_worker_the_objects_it_works_on(tmp_path):
    cache, stage = dirs(tmp_path)
    aid = str(uuid.uuid4())
    out = parent(tmp_path, f'''
import bmesh
me = bpy.data.meshes.new("Boots1_uv"); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("Boots1_uv", me); ob.location = (1, 2, 3); bpy.context.scene.collection.objects.link(ob)
from mixar.modules.common.agent_execution import staging
before = len(bpy.data.collections)
res = staging.export_copies({aid!r}, ["Boots1_uv"])
print("RESULT", json.dumps({{"res": res, "still_in_scene": ob.name in bpy.context.scene.collection.objects, "colls_added": len(bpy.data.collections) - before}}))
''')
    assert out["res"]["object_names"] == ["Boots1_uv"] and out["still_in_scene"] is True and out["colls_added"] == 0, "the parent is left as it was"
    r = run_script(f'''
import bpy, json
from mixar.modules.common.agent_execution import staging
res = staging.import_artifact({aid!r})
ob = bpy.data.objects["Boots1_uv"]
print("RESULT", json.dumps({{"res": res, "faces": len(ob.data.polygons), "loc": list(ob.location), "in_scene": ob.name in bpy.context.scene.collection.all_objects}}))
''', env={"LAMPWAY_SANDBOX_STAGING_DIR": stage, "LAMPWAY_AGENT_CACHE_DIR": cache, "LAMPWAY_HOME": str(tmp_path / "home")})
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["res"]["object_names"] == ["Boots1_uv"] and o["faces"] == 6 and o["loc"] == [1.0, 2.0, 3.0] and o["in_scene"] is True


def test_stage_scene_keeps_the_workers_own_collections_so_qa_markers_land_as_qa_piece(tmp_path):
    cache, stage = dirs(tmp_path)
    aid = str(uuid.uuid4())
    r = run_script(f'''
import bpy, json
from mixar.modules.common.agent_execution import staging
staging.reset_worker_scene()
sc = bpy.context.scene
col = bpy.data.collections.new("QA_boots"); sc.collection.children.link(col)
col.objects.link(bpy.data.objects.new("boots_L000", bpy.data.meshes.new("a")))
sc.collection.objects.link(bpy.data.objects.new("loose_cube", bpy.data.meshes.new("b")))
sc.collection.objects.link(bpy.data.objects.new("Boots1_uv", bpy.data.meshes.new("c")))     # a seeded input: skipped
m = staging.stage_scene({aid!r}, "boots", ["Boots1_uv"])
print("RESULT", json.dumps(m))
''', env={"LAMPWAY_SANDBOX_STAGING_DIR": stage, "LAMPWAY_AGENT_CACHE_DIR": cache, "LAMPWAY_HOME": str(tmp_path / "home")})
    assert r.rc == 0, r.out[-2500:]
    art = r.results[0]
    assert sorted(art["object_names"]) == ["boots_L000", "loose_cube"] and art["collections"] == ["QA_boots"] and art["object_count"] == 2
    out = parent(tmp_path, f'''
art = {art!r}
activate(); bind("t1", 1)
res = commit(art, "t1", "op1", 100, 1)
top = bpy.data.collections["Lampway Agent"]
boots = top.children["boots"]
print("RESULT", json.dumps({{"res": res, "children": [c.name for c in boots.children], "qa": sorted(o.name for o in boots.children["QA_boots"].objects),
                             "direct": sorted(o.name for o in boots.objects)}}, default=str))
''')
    assert out["res"]["success"] and out["children"] == ["QA_boots"] and out["qa"] == ["boots_L000"] and out["direct"] == ["loose_cube"]
