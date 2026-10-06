# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""model_compare (specs/mrmak/05-model-compare.md): 2..4 models normalised into one box, statistics read from the files, interior-aware pair numbers, a blind alias and a user pick. The windowed
3D viewer (synchronised cameras, mode switch) is NOT built: it needs the pop-out probe (section 6.4); these tests cover everything else, in the real binary."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
from features_support import run  # noqa: E402
from test_wave2b_glb_stats import glb  # noqa: E402

EXPORT = '''
def export_sphere(path, scale=1.0, offset=(0, 0, 0), kind="plain", radius=0.5):
    bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=4, radius=radius)
    if kind == "dimple":
        for v in bm.verts:
            if v.co.y < -0.3 * radius / 0.5 and abs(v.co.x) < 0.2 * radius / 0.5 and abs(v.co.z) < 0.2 * radius / 0.5:
                v.co.y += 0.12 * (1 - (v.co.x ** 2 + v.co.z ** 2) / (0.04 * (radius / 0.5) ** 2))
    me = bpy.data.meshes.new("tmp_exp"); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    ob = bpy.data.objects.new("tmp_exp", me); link(ob)
    me.transform(Matrix.Translation(offset))                                       # the origin ends up OFF the centre of the geometry
    ob.scale = (scale, scale, scale)
    for o in bpy.context.selected_objects: o.select_set(False)
    ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_format="GLB")
    bpy.data.objects.remove(ob)
'''


def go(tmp_path, body, **kw):
    return run(tmp_path, EXPORT + body, **kw)


def test_stats_are_read_from_the_files_and_name_what_was_baked(tmp_path):
    (tmp_path / "meshopt.glb").write_bytes(glb(compress="meshopt"))
    r = go(tmp_path, '''
export_sphere(os.path.join(root, "a.glb"))
res = call("model_compare", action="stats", set={"models": [{"file": "a.glb"}, {"file": "meshopt.glb"}]})
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    a, m = res["stats"]
    assert res["ok"] and a["triangles"] == 1280 and a["vertices"] > 600
    assert a["channels"]["normal"] is False and m["compressed"] == "meshopt" and any("meshopt decoder" in w for w in m["warnings"])


def test_normalise_scales_the_longest_axis_to_two_and_only_then_centres(tmp_path):
    r = go(tmp_path, '''
export_sphere(os.path.join(root, "big.glb"), scale=100.0, offset=(3, 0, 0))
export_sphere(os.path.join(root, "small.glb"), scale=1.0, offset=(0, 0, -2))
res = call("model_compare", action="build", set={"id": "s1", "piece": "P", "models": [{"file": "big.glb", "label": "A"}, {"file": "small.glb", "label": "B"}]})
out = {"res": res}
for m in res["models"]:
    ob = bpy.data.objects[m["object"]]
    xs = [v.co.x for v in ob.data.vertices]; ys = [v.co.y for v in ob.data.vertices]; zs = [v.co.z for v in ob.data.vertices]
    out[m["object"]] = {"dim": [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)], "center": [(max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, (max(zs) + min(zs)) / 2]}
print("RESULT", json.dumps(out))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    assert out["res"]["ok"]
    for m in out["res"]["models"]:
        d = out[m["object"]]
        assert abs(max(d["dim"]) - 2.0) < 1e-4 and max(abs(c) for c in d["center"]) < 1e-4, (m, d)       # longest edge 2.0 and the box centre at the origin, whatever the scale and offset


def test_the_pair_numbers_carry_iou_and_the_interior_difference_the_dimple_iou_cannot_see(tmp_path):
    r = go(tmp_path, '''
export_sphere(os.path.join(root, "a.glb")); export_sphere(os.path.join(root, "b.glb")); export_sphere(os.path.join(root, "c.glb"), kind="dimple")
call("model_compare", action="build", set={"id": "s2", "piece": "P", "models": [{"file": "a.glb"}, {"file": "b.glb"}, {"file": "c.glb"}]})
res = call("model_compare", action="numbers", set={"id": "s2", "piece": "P"}, views=["Front"], size=256)
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-2500:]
    pairs = {(p["a"], p["b"]): p for p in r.results[0]["pairs"]}
    assert set(pairs) == {(0, 1), (0, 2), (1, 2)}
    assert pairs[(0, 1)]["views"][0]["interior_diff"] < 1e-3 and pairs[(0, 2)]["views"][0]["interior_diff"] > 0.01 and pairs[(0, 2)]["views"][0]["iou"] > 0.99
    assert pairs[(0, 2)]["worst_interior"] == pairs[(0, 2)]["views"][0]["interior_diff"]


def test_refusals_one_model_a_file_outside_the_root_not_a_glb_and_the_meshopt_3d_view(tmp_path):
    (tmp_path / "notglb.glb").write_bytes(b"nope")
    (tmp_path / "meshopt.glb").write_bytes(glb(compress="meshopt"))
    r = go(tmp_path, '''
export_sphere(os.path.join(root, "a.glb"))
out = {"one": call("model_compare", action="build", set={"models": [{"file": "a.glb"}]}),
       "out": call("model_compare", action="build", set={"models": [{"file": "a.glb"}, {"file": "/etc/hostname"}]}),
       "bad": call("model_compare", action="build", set={"models": [{"file": "a.glb"}, {"file": "notglb.glb"}]}),
       "meshopt": call("model_compare", action="build", set={"models": [{"file": "a.glb"}, {"file": "meshopt.glb"}]}),
       "five": call("model_compare", action="build", set={"models": [{"file": "a.glb"}] * 5}),
       "rot": call("model_compare", action="build", set={"models": [{"file": "a.glb", "rotation_deg": 400}, {"file": "a.glb"}]}),
       "pick": call("model_compare", action="pick", set={"id": "x"}, pick={"model": 0})}
print("RESULT", json.dumps(out))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert "compare needs two models" in d["one"]["error"] and "outside the project root" in d["out"]["error"] and "not a glTF binary" in d["bad"]["error"]
    assert "needs the meshopt decoder: stats are shown, the 3D view is not" in d["meshopt"]["error"] and "2..4 models" in d["five"]["error"] and "rotation_deg" in d["rot"]["error"]
    assert "only the user picks" in d["pick"]["error"]


def test_blind_aliases_follow_the_hash_order_hide_the_labels_until_the_pick_and_the_pick_is_a_user_row(tmp_path):
    r = go(tmp_path, '''
export_sphere(os.path.join(root, "a.glb")); export_sphere(os.path.join(root, "b.glb"), kind="dimple")
res = call("model_compare", action="build", blind=True, set={"id": "bl", "piece": "P", "models": [{"file": "a.glb", "label": "TripoSecret"}, {"file": "b.glb", "label": "MeshySecret"}]})
sealed_on_disk = open(os.path.join(root, "P", "compare", "bl", "compare.json")).read()
early = call("model_compare", action="reveal", set={"id": "bl", "piece": "P"})
strict = call("model_compare", action="reveal", set={"id": "bl", "piece": "P"}, require_pick=True)
from mixar.modules.lampway_tools.features import model_compare as MC
pick = MC.record_pick("bl", "P", 1, "blind", "the dimple reads better", by="user", root=root)
after = call("model_compare", action="reveal", set={"id": "bl", "piece": "P"})
rows = [json.loads(l) for l in open(os.path.join(root, "ledger", "runs.jsonl"))]
print("RESULT", json.dumps({"res": res, "disk": sealed_on_disk, "early": early, "strict": strict, "after": after, "rows": rows, "pick": pick}))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    blob = json.dumps(d["res"]) + d["disk"]
    assert "TripoSecret" not in blob and "MeshySecret" not in blob and [m["alias"] for m in d["res"]["models"]] == ["A", "B"]
    assert d["early"]["ok"] is True and d["strict"]["ok"] is False and "reveal after the pick" in d["strict"]["error"]
    assert d["after"]["ok"] and {m["label"] for m in d["after"]["models"]} == {"TripoSecret", "MeshySecret"}
    row = d["rows"][-1]
    assert row["kind"] == "decision" and row["question"] == "model_pick" and row["by"] == "user" and row["how"] == "blind" and len(row["options"]) == 2 and row["answer"] in row["options"]
