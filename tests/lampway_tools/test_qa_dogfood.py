# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Defects found dogfooding Mesh QA on real Tripo pieces: the turn is applied in the analysis frame (and drawn back to the live
frame), two pieces in one scene keep their own config / collection / marker names, and proposals recolour markers without ever
becoming rulings. REAL binary."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_qa_live import SCENE  # noqa: E402

TWO = '''
from mixar.modules.lampway_tools import api
root = work
def second(name, loc):
    me2 = ob.data.copy(); me2.name = name
    o2 = bpy.data.objects.new(name, me2); o2.location = loc
    bpy.context.scene.collection.objects.link(o2)
    return o2
ob2 = second("piece_b", (3, 0, 0.5))
bpy.context.view_layer.update()
def call(fn, **kw):
    return api.call(fn, json.dumps(kw))
rel = lambda p: os.path.relpath(p, work)
common = dict(recipe=rel(work + "/recipe.json"), owner=rel(work + "/owner.npy"))
'''


def run(tmp_path, body, **kw):
    env = {"LAMPWAY_PROJECT_ROOT": str(tmp_path), "LAMPWAY_HOME": str(tmp_path / "home")}
    return run_script(SCENE.replace("ARGS_DIR", repr(str(tmp_path))) + TWO + body, env=env, **kw)


def test_the_turn_puts_a_plus_x_facing_piece_in_the_minus_y_frame_and_draw_puts_the_marker_back_on_the_live_hole(tmp_path):
    r = run(tmp_path, '''
cfg0 = L.QAConfig(object="piece", recipe=work + "/recipe.json", owner=work + "/owner.npy", rulings_dir=work + "/r0", piece="p0", offset=(0, 0, 0.5))
cfg1 = L.QAConfig(object="piece", recipe=work + "/recipe.json", owner=work + "/owner.npy", rulings_dir=work + "/r1", piece="p1", offset=(0, 0, 0.5), turn=-90.0)
out = {}
for k, cfg in (("t0", cfg0), ("t90", cfg1)):
    rep = L.compute_candidates(cfg)
    c = next(c for c in json.load(open(rep["path"]))["candidates"] if c["kind"] == "open_loop")
    out[k] = {"side": c["side"], "centroid": c["centroid_m"], "facing": c["facing"], "front_pct": c["seen_from_pct"]["front"]}
L.draw_candidates(cfg1)
lab = next(o for o in bpy.data.objects if o.name.endswith("L000_label"))
out["label"] = list(lab.location)
print("RESULT", json.dumps(out))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["t0"]["side"] == "left", "no turn: +x is the body's left"
    assert o["t90"]["side"] == "front", o["t90"]
    assert o["t90"]["centroid"][1] < -0.25 and abs(o["t90"]["centroid"][0]) < 0.05, "stored in the analysis frame"
    assert o["t90"]["facing"][1] < -0.9
    assert o["label"][0] > 0.25 and abs(o["label"][1]) < 0.1 and o["label"][2] > 0.4, "drawn where the hole is live"


def test_two_pieces_in_one_scene_keep_their_own_config_collection_and_marker_names(tmp_path):
    r = run(tmp_path, '''
a = call("qa_setup", object="piece", piece="a", offset=[0, 0, 0.5], **common)
b = call("qa_setup", object="piece_b", piece="b", offset=[3, 0, 0.5], **common)
ca = call("qa_candidates", piece="a", draw=True)
names_a = sorted(o.name for o in bpy.data.collections["QA_a"].objects)
cb = call("qa_candidates", piece="b", draw=True)
names_b = sorted(o.name for o in bpy.data.collections["QA_b"].objects)
call("qa_draw", piece="a")                                   # a re-run must not wipe b
cfg_a = L.load_config(bpy.context.scene, "a"); cfg_b = L.load_config(bpy.context.scene, "b")
print("RESULT", json.dumps({"a": a, "b": b, "ca": ca, "cb": cb, "names_a": names_a, "names_b": names_b,
    "names_b_after": sorted(o.name for o in bpy.data.collections["QA_b"].objects), "cols": sorted(c.name for c in bpy.data.collections),
    "off_a": list(cfg_a.offset), "off_b": list(cfg_b.offset), "active": L.load_config(bpy.context.scene).piece,
    "files": sorted(p for p in os.listdir(work + "/a/rulings")) if os.path.isdir(work + "/a/rulings") else None}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["a"]["ok"] and o["b"]["ok"] and o["ca"]["ok"] and o["cb"]["ok"], o
    assert o["names_a"] == ["a_L000", "a_L000_label", "a_S000", "a_S000_label"]
    assert o["names_b"] == ["b_L000", "b_L000_label", "b_S000", "b_S000_label"] == o["names_b_after"]
    assert "QA_candidates" not in o["cols"] and {"QA_a", "QA_b"} <= set(o["cols"])
    assert o["off_a"] == [0, 0, 0.5] and o["off_b"] == [3, 0, 0.5] and o["active"] == "b"
    assert o["files"] == ["a_candidates.json"]


def test_proposals_recolour_the_markers_and_never_become_rulings(tmp_path):
    r = run(tmp_path, '''
call("qa_setup", object="piece", piece="a", offset=[0, 0, 0.5], **common)
call("qa_candidates", piece="a", draw=True)
bad_verdict = call("qa_propose", piece="a", proposals={"L000": {"verdict": "maybe"}})
bad_id = call("qa_propose", piece="a", proposals={"L999": {"verdict": "delete"}})
ok = call("qa_propose", piece="a", proposals={"L000": {"verdict": "hole", "note": "open collar"}, "S000": {"verdict": "delete"}})
def colour(name):
    m = bpy.data.objects[name].data.materials[0]
    return [round(x, 2) for x in m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value[:3]]
ok2 = call("qa_propose", piece="a", proposals={"L000": {"verdict": "keep"}})
state = {n: colour(n) for n in ("a_L000", "a_S000")}
labels = {n: bpy.data.objects[n].data.body for n in ("a_L000_label", "a_S000_label")}
rd = work + "/a/rulings"
prop = json.load(open(rd + "/a_proposals.json"))
read = call("qa_read_tags", piece="a", apply=True)
print("RESULT", json.dumps({"bad_verdict": bad_verdict, "bad_id": bad_id, "ok": ok, "ok2": ok2, "state": state, "labels": labels, "prop": prop,
    "has_decisions": os.path.exists(rd + "/decisions.jsonl") and os.path.getsize(rd + "/decisions.jsonl") > 0,
    "has_deletions": os.path.exists(rd + "/a_deletions.json"), "read": read}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["bad_verdict"]["ok"] is False and "verdict" in o["bad_verdict"]["error"]
    assert o["bad_id"]["ok"] is False and "L999" in o["bad_id"]["error"]
    assert o["ok"]["ok"] is True and o["ok2"]["ok"] is True
    assert o["state"]["a_S000"][0] > 0.8 and o["state"]["a_S000"][1] < 0.3, "DELETE is red"
    assert abs(o["state"]["a_L000"][0] - o["state"]["a_L000"][2]) < 0.1 and o["state"]["a_L000"][0] < 0.7, "KEEP is grey"
    assert o["labels"] == {"a_L000_label": "L000 KEEP", "a_S000_label": "S000 DELETE"}
    assert o["prop"]["proposals"]["L000"]["verdict"] == "keep" and o["prop"]["proposals"]["S000"]["verdict"] == "delete"
    assert o["has_decisions"] is False and o["has_deletions"] is False, "a proposal is not a ruling"
    assert o["read"]["ok"] is True and o["read"]["decisions"] == 0
