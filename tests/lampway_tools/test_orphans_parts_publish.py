# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Parts Library publishing (STATUS O33), ported from the owner's tool shelf as runner tools: export_parts (one GLB + part.json per part, versions never
overwritten, an unchanged part keeps its version), verify_set (no Blender: every part re-read and compared corner by corner with the source, every source face
covered once), render_final (the assembled set and each part, Workbench), judge_pack (two segmentations reconciled into candidates and decisions) and
gen_parts_table (the wiki entity's part table, from the exported files). REAL binary, a two-shell triangulated mesh."""

import json
from pathlib import Path

from features_support import run

BUILD = '''
import hashlib
v_ = []
ob = boxes("piece", [((0, 0, 0.5), (1, 0.4, 1)), ((1.5, 0, 0.5), (0.6, 0.3, 0.6))])
bm = bmesh.new(); bm.from_mesh(ob.data); bmesh.ops.triangulate(bm, faces=bm.faces[:]); bm.to_mesh(ob.data); bm.free()
me = ob.data
uv = me.uv_layers.new(name="UVMap")
co = np.array([v.co[:] for v in me.vertices]); vi = np.empty(len(me.loops), np.int64); me.loops.foreach_get("vertex_index", vi)
uv.data.foreach_set("uv", (co[vi][:, [0, 2]] / 2.0).ravel())
for o in bpy.context.scene.objects: o.select_set(o is ob)
bpy.context.view_layer.objects.active = ob
os.makedirs(os.path.join(root, "src"), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=os.path.join(root, "src", "source.glb"), export_format="GLB", use_selection=True, export_materials="NONE")
bpy.data.objects.remove(ob)
bpy.ops.import_scene.gltf(filepath=os.path.join(root, "src", "source.glb"))
ob = next(o for o in bpy.context.scene.objects if o.type == "MESH"); name = ob.name; me = ob.data
cx = np.array([p.center.x for p in me.polygons])
owner = (cx > 0.0).astype(np.int64) if abs(cx.min()) > 0 else None
lo, hi = cx.min(), cx.max(); owner = (cx > (lo + hi) / 2).astype(np.int64)
np.save(os.path.join(root, "owner.npy"), owner)
a = me.attributes.new("vote_a", "INT", "FACE"); a.data.foreach_set("value", owner.astype(np.int32))
b_ = owner.copy(); cz = np.array([p.center.z for p in me.polygons]); b_[(owner == 0) & (cz > 0.5)] = 5
b = me.attributes.new("vote_b", "INT", "FACE"); b.data.foreach_set("value", b_.astype(np.int32))
json.dump({"smartmesh": "source.glb", "parts": {"plate": {"class": "metal", "bind": "rigid:spine_03"}, "strap": {"class": "leather", "bind": "weights"}},
           "held": [{"note": "strap: buckle side unproven", "parts": ["strap"]}]}, open(os.path.join(root, "recipe.json"), "w"))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(root, "votes.blend"))
sha = hashlib.sha256(open(os.path.join(root, "src", "source.glb"), "rb").read()).hexdigest()
'''


def test_export_verify_render_and_table_through_the_runner(tmp_path):
    r = run(tmp_path, BUILD + '''
setdir = "out/Parts Library/Candidates/Cuirass/source"
e1 = api.run_tool("export_parts", ["votes.blend", name, "owner.npy", "recipe.json", "out", "Cuirass", sha, "v0001"])
v1 = api.run_tool("verify_set", ["src/source.glb", setdir, "v0001"])
again = api.run_tool("export_parts", ["votes.blend", name, "owner.npy", "recipe.json", "out", "Cuirass", sha, "v0001"])
e2 = api.run_tool("export_parts", ["votes.blend", name, "owner.npy", "recipe.json", "out", "Cuirass", sha, "v0002"])
rf = api.run_tool("render_final", ["votes.blend", name, "owner.npy", "recipe.json", "renders"])
json.dump({"name": "Mesh Library", "drive_path": "Lib", "entities": [{"slug": "cuirass", "title": "Cuirass", "tags": [], "raw": ["x"], "oneline": "o",
           "summary": "s", "related": []}]}, open(os.path.join(root, "spec.json"), "w"))
gt = api.run_tool("gen_parts_table", ["spec.json", "cuirass", setdir, "v0001"])
print("RESULT", json.dumps({"e1": e1, "v1": v1, "again": again, "e2": e2, "rf": rf, "gt": gt}))
''', timeout=900)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    setdir = tmp_path / "out/Parts Library/Candidates/Cuirass/source"
    assert o["e1"]["rc"] == 0, o["e1"]["output"][-2000:]
    pj = json.loads((setdir / "plate/v0001/part.json").read_text())
    assert pj["part"] == "plate" and pj["faces"] == 12 and pj["motion_class"] == "metal" and (setdir / "plate/v0001/plate.glb").exists(), pj
    assert json.loads((setdir / "strap/v0001/part.json").read_text())["held_notes"] == ["strap: buckle side unproven"]
    assert o["v1"]["rc"] == 0, o["v1"]["output"][-2000:]
    ver = json.loads((setdir / "evidence/VERIFY.v0001.json").read_text())
    assert ver["all_ok"] and ver["coverage"]["covered_once"] == ver["coverage"]["faces_total"] == 24, ver
    assert o["again"]["rc"] != 0 and "never overwritten" in o["again"]["output"], o["again"]["output"][-800:]
    s2 = json.loads((setdir / "SET.v0002.json").read_text())
    assert o["e2"]["rc"] == 0 and all(p["version"] == "v0001" and not p["changed"] for p in s2["parts"]), s2
    assert o["rf"]["rc"] == 0 and (tmp_path / "renders/assembly/assembled.png").exists() and (tmp_path / "renders/part/plate.png").exists(), o["rf"]["output"][-1500:]
    spec = json.loads((tmp_path / "spec.json").read_text())
    assert o["gt"]["rc"] == 0 and len([x for x in spec["entities"][0]["table"] if x.startswith("| `")]) == 2, spec


def test_judge_pack_reconciles_two_segmentations_into_candidates_and_decisions(tmp_path):
    r = run(tmp_path, BUILD + '''
jp = api.run_tool("judge_pack", ["votes.blend", name, "pack", "vote_a", "vote_b"])
print("RESULT", json.dumps({"jp": jp}))
''', timeout=900)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["jp"]["rc"] == 0, o["jp"]["output"][-2000:]
    pack = json.loads((tmp_path / "pack/pack.json").read_text())
    kinds = {d["kind"] for d in pack["decisions"]}
    assert "split" in kinds and "agreed" in kinds, pack["decisions"]
    assert (tmp_path / "pack/cand/P00.png").exists() and any((tmp_path / "pack/dec").iterdir())
