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


def run(tmp_path, gold, body, scene=C03_SCENE):
    r = run_script(FIT_PRE + LOAD_OBJ + f"GOLD = {str(gold)!r}\n" + scene + body, env={"LW_KEEP_ROOT": str(tmp_path)}, timeout=600)
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


C07_SCENE = r'''
rig = json.load(open(GOLD + "/C07_pose_solve/rig.json"))
sh = rig["shoulder"]; L = rig["upperarm_length_m"]; ra = rig["arm_radius_m"]
a = math.radians(-40.0)                                              # the A-pose arm: 40 deg below horizontal (canon 08 C07)
elbow = (sh[0] + L * math.cos(a), sh[1], sh[2] + L * math.sin(a))
arm = armature("rig", (("upperarm_l", tuple(sh), elbow, None),))
src = load_obj(GOLD + "/C07_pose_solve/sleeve.obj", "sleeve")
def bound_copy(name, P):
    me = src.data.copy(); ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    for v, p in zip(me.vertices, P): v.co = p
    g = ob.vertex_groups.new(name="upperarm_l"); g.add(list(range(len(me.vertices))), 1.0, "REPLACE")
    s = ob.vertex_groups.new(name="sleeve"); s.add(list(range(len(me.vertices))), 1.0, "REPLACE")
    m = ob.modifiers.new("Armature", "ARMATURE"); m.object = arm
    return ob
d = Vector(elbow) - Vector(sh); d.normalize()
P0 = [tuple(v.co) for v in src.data.vertices]
# the posed solution: the sweep found the arm lowered 30 deg (C07); the sleeve, bound there, RETURNS to rest by that rotation
# undone (+deg about +Y lowers the arm), unchanged in shape - a similarity of its source
from mathutils import Matrix
back = Matrix.Translation(sh) @ Matrix.Rotation(math.radians(-30.0), 4, Vector((0, 1, 0))) @ Matrix.Translation(Vector(sh) * -1)
posed = bound_copy("posed", [tuple(back @ Vector(p)) for p in P0])
# the body: the A-pose arm, a closed capped cylinder skinned to upperarm_l
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=24, radius1=ra, radius2=ra, depth=L,
                      matrix=Matrix.Translation((Vector(sh) + Vector(elbow)) / 2) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4())
me = bpy.data.meshes.new("armbody"); bm.to_mesh(me); bm.free()
armbody = bpy.data.objects.new("armbody", me); bpy.context.scene.collection.objects.link(armbody)
weights(armbody, arm, lambda co: {"upperarm_l": 1.0})
# the trap (canon 03 G03.4): instead of the pose sweep, push the sleeve's vertices outward from the A-pose arm (along the arm's
# surface normal at the nearest point) until no vertex penetrates, in 5 mm steps (bounded): what a penetration-only judge counts
from mathutils.bvhtree import BVHTree
armbody.data.calc_loop_triangles()
tree = BVHTree.FromPolygons([tuple(v.co) for v in armbody.data.vertices], [tuple(t.vertices) for t in armbody.data.loop_triangles])
E = [tuple(e.vertices) for e in src.data.edges]
P = [Vector(p) for p in P0]
def inside():
    out_ = set()
    for i, p in enumerate(P):
        loc, nor, _f, _dist = tree.find_nearest(p)
        if (p - loc).dot(nor) < 0:
            out_.add(i)
    return out_
def outward(i, step):
    loc, nor, _f, _dist = tree.find_nearest(P[i])
    P[i] = P[i] + nor.normalized() * step
steps = 0
for steps in range(1, 101):
    bad = inside()
    if not bad:
        break
    for i in bad:
        outward(i, 0.005)
PUSH_STEPS, PUSH_CLEAR = steps, not inside()
pushed = bound_copy("pushed", [tuple(p) for p in P])
# a second trap with no crossing at all: the returned sleeve bulged 8 % across its own axis (a non-uniform "fit" of a metal part)
ax = (back.to_3x3() @ Matrix.Rotation(math.radians(30.0), 3, Vector((0, 1, 0))) @ d).normalized()
def bulge(p):
    v = p - Vector(sh); t = v.dot(ax); return Vector(sh) + t * ax + (v - t * ax) * 1.08
bulged = bound_copy("bulged", [tuple(bulge(back @ Vector(p))) for p in P0])
'''


def test_g03_4_the_push_trap_fails_its_judge_and_the_posed_solution_does_not(tmp_path, goldens):
    d = run(tmp_path, goldens, '''
out = {"moved": sum(1 for a_, b_ in zip(P0, pushed.data.vertices) if (Vector(a_) - b_.co).length > 1e-9), "push_steps": PUSH_STEPS, "push_clear": PUSH_CLEAR}
for name in ("pushed", "posed", "bulged"):
    out[name] = api.fit_validate("measure", piece="sleeve", bound=name, original="sleeve", poses=[{"name": "rest"}], roles={"sleeve": "metal"},
                                 body="armbody")
res(out)
''', scene=C07_SCENE)
    m = {}
    for name in ("pushed", "posed", "bulged"):
        v = d[name]
        assert v["ok"], v
        m[name] = {"rest_fidelity_max_mm": v["rest_fidelity"]["per_part"]["sleeve"]["max_mm"],
                   "rest_fidelity_verdict": (v["rest_fidelity"].get("judge") or {}).get("sleeve", {}).get("verdict"), "summary_counts": v["summary"]["counts"],
                   "summary_ok": v["summary"]["ok"], "crossings": v["poses"][0]["pieces"]["sleeve"]["surface_crossings"],
                   "inside_vertices": v["poses"][0]["pieces"]["sleeve"]["inside_vertices"],
                   "pose_rigid_mm": v["poses"][0]["pieces"]["sleeve"]["rigid_residual_mm"], "control": v["crossing_control"]["ok"]}
    m["moved_vertices"], m["push_steps"] = d["moved"], d["push_steps"]
    assert d["push_clear"], d
    (tmp_path / "g03_4.json").write_text(json.dumps(m, indent=1))
    print("G03.4", json.dumps(m))
    assert d["moved"] > 0
    assert m["pushed"]["rest_fidelity_max_mm"] > 10.0 and m["posed"]["rest_fidelity_max_mm"] < 1e-3, m
    assert m["pushed"]["inside_vertices"] == 0 and m["pushed"]["pose_rigid_mm"] < 1e-3, m    # what a penetration-only judge sees: nothing wrong
    assert m["pushed"]["rest_fidelity_verdict"] == "FAIL" and m["pushed"]["summary_ok"] is False, m
    # the bulge crosses nothing and is rigid through every pose: only the rest fidelity against the source can fail it
    assert m["bulged"]["crossings"] == 0 and m["bulged"]["inside_vertices"] == 0 and m["bulged"]["rest_fidelity_max_mm"] > 0.5, m
    assert m["bulged"]["rest_fidelity_verdict"] == "FAIL" and m["bulged"]["summary_ok"] is False, m
    assert m["posed"]["rest_fidelity_verdict"] == "PASS" and m["posed"]["crossings"] == 0 and m["posed"]["summary_ok"] is True, m
