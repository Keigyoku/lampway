# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon 03 E, the pipeline-level goldens, through the REAL tools on the REAL binary.

G03.1 metal survives the whole chain: goldens/C03_seam_tube (one shell, two parts; the cut ring exists twice), the lower part
declared metal, the upper cloth, on a body package whose weights are its NATIVE SIDECAR (blended across the cut, so a cloth vertex
at the seam would follow the twist if nothing held it): fit_bind plan -> weights (from the package) -> return -> fit_validate in
the golden's twist (spine_03 40 deg about Z). Expected: the metal part's rest fidelity similarity residual < 1e-6 m, its rigid
residual in the twist < 1e-6 m, the seam gap 0 (canon 07 B.5: the cloth copies of the seam take the metal's bone)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from canon_fit_support import FIT_PRE  # noqa: E402
from canon_support import LOAD_OBJ, J, goldens  # noqa: E402,F401

C03_SCENE = r'''
rig = json.load(open(GOLD + "/C03_seam_tube/rig.json"))
arm = armature("rig", tuple((n, tuple(b["head"]), tuple(b["tail"]), b["parent"]) for n, b in rig["bones"].items()))
piece = load_obj(GOLD + "/C03_seam_tube/piece.obj", "piece")
n_lower = rig["seam_pairs_source_ledger"][0][1]                      # the upper part starts at the first copy of the cut ring
lo, up = piece.vertex_groups.new(name="lower"), piece.vertex_groups.new(name="upper")
lo.add(list(range(n_lower)), 1.0, "REPLACE"); up.add(list(range(n_lower, len(piece.data.vertices))), 1.0, "REPLACE")
# the body: a closed capped cylinder (r 0.10) under the tube, its weights blended across the cut (spine_01 below 1.15, spine_03 above 1.25)
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=32, radius1=0.10, radius2=0.10, depth=0.7,
                      matrix=__import__("mathutils").Matrix.Translation((0, 0, 1.25)))
bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 0.5], cuts=27, use_grid_fill=False)
me = bpy.data.meshes.new("body"); bm.to_mesh(me); bm.free()
body = bpy.data.objects.new("body", me); bpy.context.scene.collection.objects.link(body)
def blend(co):
    u = min(1.0, max(0.0, (co.z - 1.15) / 0.10))
    return {k: w for k, w in (("spine_01", 1.0 - u), ("spine_03", u)) if w > 0}
weights(body, arm, blend)
write_sidecar(body, arm, os.path.join(root, "ue", "sidecar.json"), root_bone="spine_01")
pkg = api.fit_body("build", armature="rig", mesh="body", sidecar="ue/sidecar.json", out="fit/body")
assert pkg.get("ok"), pkg
body_pkg = os.path.relpath(pkg["package"], root)
'''

TWIST = [{"name": "twist", "bones": [{"bone": "spine_03", "axis": [0, 0, 1], "deg": 40.0}]}]


def run(tmp_path, gold, body):
    r = run_script(FIT_PRE + LOAD_OBJ + f"GOLD = {str(gold)!r}\n" + C03_SCENE + body, env={"LW_KEEP_ROOT": str(tmp_path)}, timeout=600)
    assert r.rc == 0, r.out[-2500:]
    return r.results[-1]


def test_g03_1_metal_survives_the_chain_on_the_native_sidecar(tmp_path, goldens):
    d = run(tmp_path, goldens, f'''
out = {{}}
out["plan"] = api.fit_bind("plan", piece="piece", armature="rig", roles={{"lower": "metal", "upper": "cloth"}}, out_dir="fb")
out["weights"] = api.fit_bind("weights", piece="piece", armature="rig", out_dir="fb", body=body_pkg)
if out["weights"].get("ok"):
    out["return"] = api.fit_bind("return", piece="piece", armature="rig", out_dir="fb")
    if out["return"].get("ok"):
        out["validate"] = api.fit_validate("measure", piece="piece", bound=out["return"]["object"], original="piece",
                                           poses=[{{"name": "rest"}}] + {TWIST!r}, roles={{"lower": "metal", "upper": "cloth"}})
res(out)
''')
    assert d["plan"]["ok"] and d["plan"]["parts"]["lower"]["mode"] == "rigid" and d["plan"]["parts"]["lower"]["bones"] == ["spine_01"], d["plan"]
    assert d["weights"]["ok"], d["weights"]
    assert "native sidecar" in d["weights"]["weights_source"], d["weights"]
    assert d["return"]["ok"], d["return"]
    v = d["validate"]
    assert v["ok"], v
    rest = v["rest_fidelity"]["per_part"]["lower"]
    twist = next(p for p in v["poses"] if p["name"] == "twist")
    m = {"rest_fidelity_max_mm": rest["max_mm"], "rest_fidelity_scale": rest["scale"], "twist_metal_rigid_mm": twist["pieces"]["lower"]["rigid_residual_mm"],
         "seam_max_cm": twist["pieces"]["lower"]["seam"]["max_cm"], "seam_open_over_2mm": twist["pieces"]["lower"]["seam"]["open_over_2mm"],
         "seam_pairs": twist["pieces"]["lower"]["seam"]["pairs"], "cloth_strain_p95": twist["pieces"]["upper"]["strain_p95"]}
    (tmp_path / "g03_1.json").write_text(json.dumps(m, indent=1))
    print("G03.1", json.dumps(m))
    assert rest["max_mm"] < 1e-3, m                                                       # < 1e-6 m
    assert twist["pieces"]["lower"]["rigid_residual_mm"] < 1e-3, m                         # < 1e-6 m
    assert m["seam_pairs"] == 32 and m["seam_max_cm"] == 0 and m["seam_open_over_2mm"] == 0, m


def test_the_sidecar_is_sampled_at_the_fit_pose_not_at_rest(tmp_path, goldens):
    """canon 07 A: the native body AT THE SAME POSE as the piece. spine_03 bent 70 deg forward at the fit pose; a cloth patch authored
    2 cm outside the POSED upper body takes spine_03 - sampling the sidecar at rest would find no spine_03 surface there."""
    d = run(tmp_path, goldens, '''
from mathutils import Matrix
pb = arm.pose.bones["spine_03"]; pb.rotation_mode = "XYZ"; pb.rotation_euler = (math.radians(70), 0, 0)
bpy.context.view_layer.update()
M = arm.matrix_world @ pb.matrix @ arm.data.bones["spine_03"].matrix_local.inverted()
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=0.03, matrix=Matrix.Translation((0, -0.12, 1.42)) @ Matrix.Rotation(math.radians(90), 4, "X"))
me = bpy.data.meshes.new("patch"); bm.to_mesh(me); bm.free()
patch = bpy.data.objects.new("patch", me); bpy.context.scene.collection.objects.link(patch)
patch.matrix_world = M; bpy.context.view_layer.update()
patch.data.transform(patch.matrix_world); patch.matrix_world = Matrix.Identity(4)
g = patch.vertex_groups.new(name="cloth"); g.add(list(range(len(patch.data.vertices))), 1.0, "REPLACE")
api.fit_bind("plan", piece="patch", armature="rig", roles={"cloth": "cloth"}, bind_overrides={"cloth": {"bones": ["spine_01", "spine_03"]}}, out_dir="fp")
w = api.fit_bind("weights", piece="patch", armature="rig", out_dir="fp", body=body_pkg)
out = {"w": w}
if w.get("ok"):
    fit = bpy.data.objects[w["object"]]
    gi = {g.index: g.name for g in fit.vertex_groups}
    out["spine_03"] = [sum(x.weight for x in v.groups if gi[x.group] == "spine_03") for v in fit.data.vertices]
res(out)
''')
    assert d["w"]["ok"], d["w"]
    assert min(d["spine_03"]) > 0.99, d["spine_03"]
