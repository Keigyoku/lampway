# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""batch_export (specs/mixar_docs/batch_export.md) in the real binary: plan first (the default), one convention pass, each object exported from a temporary copy to its own file, verified by re-import,
undoable through rename_map.json, and a project convention that cannot silently change."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE_BX = '''
CONV = {"prefix": "SM_", "set": "Hoplite", "pattern": "{prefix}{set}_{piece}_{nn}", "origin": "base", "unit_scale": 1.0, "forward": "-Y", "up": "Z"}
def cube(name, dims, loc=(0, 0, 0), scale=0.01):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Diagonal((dims[0], dims[1], dims[2], 1.0)))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.location = loc; ob.scale = (scale, scale, scale)
    return link(ob)
def world_dims(ob):
    bpy.context.view_layer.update()
    pts = [ob.matrix_world @ v.co for v in ob.data.vertices]
    return [round(max(p[i] for p in pts) - min(p[i] for p in pts), 6) for i in range(3)]
def three():
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    return [cube("Cube.001", (100, 200, 300), (1, 0, 0)), cube("Cube.002", (200, 200, 100), (2, 0, 0)), cube("Cube.003", (300, 100, 100), (3, 0, 0))]
'''


def go(tmp_path, body, **kw):
    return run(tmp_path, PRE_BX + body, **kw)


def one(r):
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_plan_lists_the_violations_and_changes_nothing_and_writes_nothing(tmp_path):
    d = one(go(tmp_path, '''
obs = three()
before = [(o.name, tuple(o.scale), tuple(o.location)) for o in obs]
res = call("batch_export", objects=[o.name for o in obs], convention=CONV, format="fbx", out_dir="export")
after = [(o.name, tuple(o.scale), tuple(o.location)) for o in bpy.data.objects]
print("RESULT", json.dumps({"res": res, "same": before == after, "files": sorted(os.listdir(root + "/export")) if os.path.isdir(root + "/export") else []}))
'''))
    res = d["res"]
    assert res["ok"] and res["plan_only"] is True and d["same"] and d["files"] == [] and res["violations"] == 3 and res["exported"] == []
    assert [p["new_name"] for p in res["plan"]] == ["SM_Hoplite_Cube_01", "SM_Hoplite_Cube_02", "SM_Hoplite_Cube_03"]
    assert all({"name", "scale", "origin"} <= set(p["fixes"]) for p in res["plan"])


def test_a_real_run_renames_applies_scale_sets_origins_exports_three_files_verified_and_undo_restores_names(tmp_path):
    d = one(go(tmp_path, '''
obs = three()
dims0 = {o.name: world_dims(o) for o in obs}
res = call("batch_export", objects=[o.name for o in obs], convention=CONV, format="fbx", out_dir="export", plan_only=False)
names = sorted(o.name for o in bpy.data.objects)
scales = {o.name: [round(x, 6) for x in o.scale] for o in bpy.data.objects}
dims1 = {o.name: world_dims(o) for o in bpy.data.objects}
files = sorted(os.listdir(root + "/export"))
undo = call("batch_export", undo=root + "/export/rename_map.json")
print("RESULT", json.dumps({"res": res, "dims0": dims0, "dims1": dims1, "names": names, "scales": scales, "files": files, "undo": undo, "names_after_undo": sorted(o.name for o in bpy.data.objects)}))
'''))
    res = d["res"]
    assert res["ok"] and d["names"] == ["SM_Hoplite_Cube_01", "SM_Hoplite_Cube_02", "SM_Hoplite_Cube_03"]
    assert all(s == [1.0, 1.0, 1.0] for s in d["scales"].values())
    assert sorted(d["dims0"].values()) == sorted(d["dims1"].values())                               # applying the scale did not change the world size
    assert [e["verified"] for e in res["exported"]] == [True, True, True] and all(e["file"].endswith(".fbx") and len(e["sha256"]) == 64 for e in res["exported"])
    assert "rename_map.json" in d["files"] and "manifest.json" in d["files"] and sum(1 for f in d["files"] if f.endswith(".fbx")) == 3
    assert d["undo"]["ok"] and d["names_after_undo"] == ["Cube.001", "Cube.002", "Cube.003"]


def test_each_format_exports_and_reimports_to_the_same_size(tmp_path):
    d = one(go(tmp_path, '''
obs = three()
out = {}
for fmt in ("glb", "obj"):
    res = call("batch_export", objects=["Cube.001"], convention=dict(CONV, set="X" + fmt), format=fmt, out_dir="export_" + fmt, plan_only=False)
    out[fmt] = {"ok": res["ok"], "verified": [e["verified"] for e in res["exported"]], "err": res.get("error"), "bbox_error": [e.get("bbox_error") for e in res["exported"]]}
    obs = three()
print("RESULT", json.dumps(out))
'''))
    for fmt in ("glb", "obj"):
        assert d[fmt]["ok"] and d[fmt]["verified"] == [True] and max(d[fmt]["bbox_error"]) < 1e-4, d[fmt]


def test_refusals_collision_unknown_preset_outside_root_usd_no_convention_and_a_changed_project_convention(tmp_path):
    d = one(go(tmp_path, '''
obs = three()
a = call("batch_export", objects=["Cube.001", "Cube.002"], convention=dict(CONV, pattern="{prefix}{set}_Piece"), plan_only=True)
b = call("batch_export", objects=["Cube.001"], convention=CONV, preset="quake")
c = call("batch_export", objects=["Cube.001"], convention=CONV, out_dir="/etc/lampway_nope")
e = call("batch_export", objects=["Cube.001"], convention=CONV, format="usd")
f = call("batch_export", objects=["Cube.001"])
call("batch_export", objects=["Cube.001"], convention=CONV, format="glb", out_dir="export", plan_only=False)
g = call("batch_export", objects=["Cube.002"], convention=dict(CONV, set="Other", unit_scale=0.01), format="fbx", out_dir="export", plan_only=False)
print("RESULT", json.dumps({"a": a, "b": b, "c": c, "e": e, "f": f, "g": g, "rec": json.load(open(root + "/export_convention.json"))}))
'''))
    assert d["a"]["ok"] is False and "name collision" in d["a"]["error"]
    assert d["b"]["ok"] is False and "unreal" in d["b"]["error"] and "unity" in d["b"]["error"]
    assert d["c"]["ok"] is False and "outside the project root" in d["c"]["error"]
    assert d["e"]["ok"] is False and "usd" in d["e"]["error"]
    assert d["f"]["ok"] is False and "cannot invent your" in d["f"]["error"]
    assert d["g"]["ok"] is False and "differs from the project's recorded convention" in d["g"]["error"]
    assert d["rec"]["unit_scale"] == 1.0 and d["rec"]["forward"] == "-Y"


def test_the_re_import_check_can_fail_a_file_that_is_not_the_object(tmp_path):
    d = one(go(tmp_path, '''
from mixar.modules.lampway_tools.features import batch_export as BX
a, b, _c = three()
bpy.context.view_layer.update()
path = root + "/probe.fbx"
BX._export_one(a, path, "fbx", "-Y", "Z", 1.0)
same = BX._verify(a, path, "fbx", "-Y", "Z", 1.0)
other = BX._verify(b, path, "fbx", "-Y", "Z", 1.0)                                             # the file holds `a`, claimed to be `b`
wrong_unit = BX._verify(a, path, "fbx", "-Y", "Z", 0.01)
print("RESULT", json.dumps({"same": same, "other": other, "wrong_unit": wrong_unit}))
'''))
    assert d["same"] < 1e-4 and d["other"] > 1e-3 and d["wrong_unit"] > 1e-3


def test_readback_cleans_all_ids_on_success_and_failure(tmp_path):
    from issue2_native import run_issue_case
    run_issue_case(tmp_path, '''
from mixar.modules.lampway_tools.features import batch_export as B
from pathlib import Path
bpy.ops.wm.read_factory_settings(use_empty=True);ob=sphere('Source');mat=bpy.data.materials.new('Authored');mat.use_nodes=True;ob.data.materials.append(mat)
p=Path(root)/'model.glb';bpy.ops.export_scene.gltf(filepath=str(p),export_format='GLB')
before=ids();B._verify(ob,p,'glb','-Y','Z',1);assert ids()==before,(ids(),before)
original=B._dims
calls=[0]
def fail(obs):
    calls[0]+=1
    if calls[0]==2:raise RuntimeError('planted readback failure')
    return original(obs)
B._dims=fail
try:
    try:B._verify(ob,p,'glb','-Y','Z',1)
    except RuntimeError:pass
    else:raise AssertionError('failure not raised')
    assert ids()==before,(ids(),before)
finally:B._dims=original
''')
