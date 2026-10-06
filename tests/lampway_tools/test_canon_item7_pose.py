# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 7 (canon 08): the closest-pose solver's engine on golden C07 - the sign check before any sweep, axes in
the joint-named grammar through the bone's joint (pose_cs), the penetration metric cast from the bone's axis out to each skin sample,
regions selected by BONES (never absolute heights), the selection rule, and a pose.json that replays exactly. Pure python."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from canon_support import J, goldens, obj, tris  # noqa: E402,F401
from mixar.modules.lampway_tools.pipeline import pose_solve as PS  # noqa: E402

FRAME = {"up": (0.0, 0.0, 1.0), "forward": (0.0, -1.0, 0.0)}


def _c07(goldens, negate=False):
    rig = J(goldens, "C07_pose_solve/rig.json")
    V, F, *_ = obj(goldens, "C07_pose_solve/sleeve.obj")
    V, T = np.asarray(V, float), tris(F)
    sh = np.array(rig["shoulder"])
    a = math.radians(-40.0)
    d = np.array([math.cos(a), 0.0, math.sin(a)])
    ref = {"upperarm_l": {"parent": None, "rot": (0.0, 0.0, 0.0, 1.0), "pos": tuple(sh)},
           "lowerarm_l": {"parent": "upperarm_l", "rot": (0.0, 0.0, 0.0, 1.0), "pos": tuple(sh + rig["upperarm_length_m"] * d)}}
    u = np.cross(d, [0, 1, 0])
    u /= np.linalg.norm(u)
    v = np.cross(d, u)
    samples = [(tuple(sh + s * d + rig["arm_radius_m"] * (math.cos(t) * u + math.sin(t) * v)), "upperarm_l")
               for s in np.linspace(0.06, 0.27, 12) for t in 2 * math.pi * np.arange(16) / 16]
    axis = [-x for x in rig["dof"]["axis_world"]] if negate else rig["dof"]["axis_world"]
    lo, hi = rig["dof"]["range"]
    dof = {"bone": "upperarm_l", "axis": axis, "range": [lo, hi], "step": rig["dof"]["step"],
           "expect": {"joint": "lowerarm_l", "along": "-up", "min_cm": 2.0}}
    regions = {"arm_l": {"bones": ["upperarm_l"], "threshold_m": 0.01}}
    return ref, samples, (V, T), dof, regions


def test_g08_1_the_sweep_picks_the_authored_arm_angle_and_the_a_pose_penetrates(goldens):
    exp = J(goldens, "C07_pose_solve/expected.json")
    ref, samples, piece, dof, regions = _c07(goldens)
    out = PS.solve(ref, FRAME, samples, piece, [dof], regions=regions)
    assert out["entries"] == [{"bone": "upperarm_l", "axis": [0.0, 1.0, 0.0], "deg": float(exp["best_lower_deg"])}]
    assert out["posed"]["arm_l"]["over"] == exp["penetrating_at_best"] and out["a_pose"]["arm_l"]["over"] >= exp["a_pose_penetrating_min"]
    assert out["pose_cost_deg"] == 30.0 and out["schema"] == "lampway.fit-pose/1" and len(out["sweeps"]) == 9


def test_g08_2_a_negated_axis_is_refused_by_the_sign_check_before_any_sweep(goldens):
    ref, samples, piece, dof, regions = _c07(goldens, negate=True)
    calls = []
    with pytest.raises(PS.PoseError, match="sign check"):
        PS.solve(ref, FRAME, samples, piece, [dof], regions=regions, hits=lambda *a: calls.append(1) or PS.numpy_hits(*a))
    assert calls == [], "the sweep must not run"


def test_g08_3_the_pose_replays_through_pose_cs_to_the_sweeps_joints(goldens):
    ref, samples, piece, dof, regions = _c07(goldens)
    out = PS.solve(ref, FRAME, samples, piece, [dof], regions=regions)
    from mixar.modules.lampway_tools import canon_geom as G
    posed = G.pose_cs(ref, out["entries"])
    worst = max(math.dist(posed[b]["pos"], out["joints_m"][b]) for b in ref) * 100
    assert worst < 0.01 and out["joints_m"]["lowerarm_l"][2] < ref["lowerarm_l"]["pos"][2] - 0.05


def test_the_selection_prefers_the_natural_pose_and_ranges_are_bounded(goldens):
    ref, samples, piece, dof, regions = _c07(goldens)
    far = dict(dof, range=[-60, 40])
    with pytest.raises(PS.PoseError, match="90"):
        PS.solve(ref, FRAME, samples, piece, [far], regions=regions)
    key = PS.selection_key({"arm_l": {"over": 0, "worst_m": 0.0}}, 35.0)
    assert key > PS.selection_key({"arm_l": {"over": 0, "worst_m": 0.0}}, 30.0) and key < PS.selection_key({"arm_l": {"over": 1, "worst_m": 0.0}}, 0.0)


def test_regions_are_selected_by_bone_never_by_height(goldens):
    ref, samples, piece, dof, regions = _c07(goldens)
    moved = {b: dict(t, pos=tuple(np.add(t["pos"], (0, 0, 0.7)))) for b, t in ref.items()}         # the same body, 70 cm higher
    Vm = piece[0] + (0, 0, 0.7)
    sm = [(tuple(np.add(p, (0, 0, 0.7))), b) for p, b in samples]
    a = PS.solve(ref, FRAME, samples, piece, [dof], regions=regions)
    b = PS.solve(moved, FRAME, sm, (Vm, piece[1]), [dof], regions=regions)
    assert a["entries"] == b["entries"] and a["a_pose"] == b["a_pose"]


def test_b3_rays_start_on_the_bone_axis_so_a_cap_across_the_limb_is_not_a_pose_penetration(goldens):
    """canon 08 B.3: each ray runs from the sample's projection onto its bone's segment out to the sample. A disk across the arm (a
    cap, canon 06 / INV-08.5: an openings defect, not a pose problem) is crossed by no such ray; rays cast from the bone's HEAD would
    cross it for every sample beyond it and call the cap a penetration."""
    ref, samples, _piece, dof, regions = _c07(goldens)
    sh, d = np.asarray(ref["upperarm_l"]["pos"]), np.asarray(ref["lowerarm_l"]["pos"]) - np.asarray(ref["upperarm_l"]["pos"])
    d /= np.linalg.norm(d)
    u = np.cross(d, [0, 1, 0])
    u /= np.linalg.norm(u)
    v = np.cross(d, u)
    c = sh + 0.15 * d
    ring = [c + 0.2 * (np.cos(t) * u + np.sin(t) * v) for t in 2 * np.pi * np.arange(24) / 24]
    V = np.array([c] + ring)
    T = np.array([(0, 1 + k, 1 + (k + 1) % 24) for k in range(24)])
    out = PS.solve(ref, FRAME, samples, (V, T), [dict(dof, range=[0, 0])], regions=regions)
    assert out["a_pose"]["arm_l"]["over"] == 0, out["a_pose"]


TOOL = r'''
import math
from mathutils import Vector, Matrix
rig = json.load(open(GOLD + "/C07_pose_solve/rig.json"))
sh = Vector(rig["shoulder"]); a = math.radians(-40.0); d = Vector((math.cos(a), 0, math.sin(a)))
arm = bpy.data.armatures.new("rig"); ob = bpy.data.objects.new("rig", arm); bpy.context.scene.collection.objects.link(ob)
bpy.context.view_layer.objects.active = ob; ob.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
up = arm.edit_bones.new("upperarm_l"); up.head = sh; up.tail = sh + 0.3 * d
lo = arm.edit_bones.new("lowerarm_l"); lo.head = sh + 0.3 * d; lo.tail = sh + 0.55 * d; lo.parent = up
bpy.ops.object.mode_set(mode="OBJECT")
u = d.cross(Vector((0, 1, 0))).normalized(); w = d.cross(u)                       # the golden's arm: 12 stations x 16 around, radius 5 cm
verts = [sh + s_ * d + 0.05 * (math.cos(t) * u + math.sin(t) * w) for s_ in [0.06 + k * 0.21 / 11 for k in range(12)]
         for t in [2 * math.pi * j / 16 for j in range(16)]]
faces = [(k * 16 + j, k * 16 + (j + 1) % 16, (k + 1) * 16 + (j + 1) % 16, (k + 1) * 16 + j) for k in range(11) for j in range(16)]
me = bpy.data.meshes.new("body"); me.from_pydata([tuple(v) for v in verts], [], faces); me.update()
body = bpy.data.objects.new("body", me); bpy.context.scene.collection.objects.link(body)
g = body.vertex_groups.new(name="upperarm_l"); g.add(list(range(len(body.data.vertices))), 1.0, "REPLACE")
body.parent = ob; m = body.modifiers.new("Armature", "ARMATURE"); m.object = ob
sleeve = load_obj(GOLD + "/C07_pose_solve/sleeve.obj", "sleeve")
dof = {"bone": "upperarm_l", "axis": rig["dof"]["axis_world"], "range": rig["dof"]["range"], "step": rig["dof"]["step"],
       "expect": {"joint": "lowerarm_l", "along": "-up", "min_cm": 2.0}}
r = api.fit_pose(kind="chest", piece="sleeve", body="body", armature="rig", dofs=[dof], regions={"arm_l": {"bones": ["upperarm_l"], "threshold_m": 0.01}},
                 out="fit/pose.json")
res({"ok": r.get("ok"), "error": r.get("error"), "entries": r.get("entries"), "a_pose": r.get("a_pose"), "posed": r.get("posed"),
     "file": os.path.exists(os.path.join(root, "fit/pose.json")), "samples": r.get("samples")})
'''


def test_the_tool_solves_c07_on_scene_objects_with_the_bvh_caster(goldens):
    from canon_support import LOAD_OBJ
    from test_wave3_weights import PRE
    from blender_run import run_script
    r = run_script(PRE + LOAD_OBJ + f"GOLD = {str(goldens)!r}\n" + TOOL, timeout=300)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["ok"], d["error"]
    assert d["entries"] == [{"bone": "upperarm_l", "axis": [0.0, 1.0, 0.0], "deg": 30.0}], d
    assert d["posed"]["arm_l"]["over"] == 0 and d["a_pose"]["arm_l"]["over"] >= 1 and d["file"], d


def test_a_mirrored_dof_drives_the_other_side_by_the_sagittal_reflection(goldens):
    """contract `mirror: true`: one DOF sweeps both arms; the right entry is the left one reflected across x = 0 - R(a, deg) becomes
    R(Ma, -deg) with M = diag(-1, 1, 1) - so a sleeve authored 30 deg lower on BOTH arms is found in one 9-point sweep."""
    ref, samples, (V, T), dof, regions = _c07(goldens)
    M = np.diag([-1.0, 1.0, 1.0])
    ref = dict(ref, upperarm_r={"parent": None, "rot": (0.0, 0.0, 0.0, 1.0), "pos": tuple(M @ np.array(ref["upperarm_l"]["pos"]))},
               lowerarm_r={"parent": "upperarm_r", "rot": (0.0, 0.0, 0.0, 1.0), "pos": tuple(M @ np.array(ref["lowerarm_l"]["pos"]))})
    samples = samples + [(tuple(M @ np.array(p)), "upperarm_r") for p, _b in samples]
    piece = (np.vstack([V, V @ M]), np.vstack([T, T + len(V)]))
    regions = dict(regions, arm_r={"bones": ["upperarm_r"], "threshold_m": 0.01})
    out = PS.solve(ref, FRAME, samples, piece, [dict(dof, mirror=True)], regions=regions)
    assert out["entries"] == [{"bone": "upperarm_l", "axis": [0.0, 1.0, 0.0], "deg": 30.0}, {"bone": "upperarm_r", "axis": [0.0, 1.0, 0.0], "deg": -30.0}]
    assert out["posed"]["arm_l"]["over"] == 0 and out["posed"]["arm_r"]["over"] == 0 and out["a_pose"]["arm_r"]["over"] >= 1
    assert len(out["sweeps"]) == 9


def _a_pose_skeleton():
    """A synthetic A-pose skeleton in the body frame (front -Y, the wearer's left +X): arms 40 deg below horizontal."""
    a = math.radians(-40.0)
    J = {"pelvis": (0, 0, 0.95), "spine_01": (0, 0, 1.00), "spine_02": (0, 0, 1.08), "spine_03": (0, 0, 1.16), "spine_04": (0, 0, 1.24),
         "spine_05": (0, 0, 1.32), "neck_01": (0, 0, 1.45), "neck_02": (0, 0, 1.50), "head": (0, 0, 1.56),
         "upperarm_l": (0.18, 0, 1.42), "lowerarm_l": (0.18 + 0.30 * math.cos(a), 0, 1.42 + 0.30 * math.sin(a)),
         "upperarm_r": (-0.18, 0, 1.42), "lowerarm_r": (-0.18 - 0.30 * math.cos(a), 0, 1.42 + 0.30 * math.sin(a))}
    P = {"pelvis": None, "spine_01": "pelvis", "spine_02": "spine_01", "spine_03": "spine_02", "spine_04": "spine_03", "spine_05": "spine_04",
         "neck_01": "spine_05", "neck_02": "neck_01", "head": "neck_02", "upperarm_l": "spine_05", "lowerarm_l": "upperarm_l",
         "upperarm_r": "spine_05", "lowerarm_r": "upperarm_r"}
    return {b: {"parent": P[b], "rot": (0.0, 0.0, 0.0, 1.0), "pos": tuple(float(x) for x in J[b])} for b in J}


def test_the_chest_table_is_the_canons_and_passes_its_own_sign_check():
    from mixar.modules.lampway_tools import posing as PO
    t = PO.CHEST
    assert [(d["bone"], d["range"], d["step"], d.get("mirror")) for d in t["dofs"]] == [("upperarm_l", [0, 40], 5, True), ("upperarm_l", [-10, 10], 5, True)]
    assert [(d["bone"], d["range"], d["step"]) for d in t["chain"]] == [("spine_01", [-8, 8], 4), ("spine_03", [-8, 8], 4), ("neck_01", [-8, 8], 4)]
    assert t["regions"]["arm_l"]["threshold_m"] == 0.010 and t["regions"]["neck"]["threshold_m"] == 0.002 and t["regions"]["torso"]["threshold_m"] == 0.002
    ref = _a_pose_skeleton()
    samples = [(tuple(np.add(ref[b]["pos"], (0.0, 0.0, -0.01))), b) for b in ("upperarm_l", "upperarm_r", "spine_02", "neck_01")]
    far = (np.array([[5.0, 5, 5], [5.1, 5, 5], [5, 5.1, 5]]), np.array([[0, 1, 2]]))            # nothing to avoid: the natural pose wins
    out = PS.solve(ref, FRAME, samples, far, t["dofs"], t["chain"], regions=t["regions"])
    assert out["entries"] == [] and out["sign_check"]["moved_cm"] > 2.0 and len(out["sweeps"]) == 9 * 5 + 3 * 5
    flipped = [dict(t["dofs"][0], axis="forward")] + t["dofs"][1:]
    with pytest.raises(PS.PoseError, match="sign check"):
        PS.solve(ref, FRAME, samples, far, flipped, t["chain"], regions=t["regions"])


def test_the_tool_takes_the_canon_chest_table_by_name():
    from test_wave3_weights import PRE
    from blender_run import run_script
    ref = _a_pose_skeleton()
    body = r'''
from mathutils import Vector
REF = ''' + repr(ref) + '''
arm = bpy.data.armatures.new("rig"); ob = bpy.data.objects.new("rig", arm); bpy.context.scene.collection.objects.link(ob)
bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode="EDIT")
kids = {}
for b, t in REF.items():
    if t["parent"]: kids.setdefault(t["parent"], []).append(b)
for b, t in REF.items():
    eb = arm.edit_bones.new(b); eb.head = t["pos"]
    k = [c for c in kids.get(b, []) if not c.startswith("upperarm")]
    eb.tail = REF[k[0]]["pos"] if k else (Vector(t["pos"]) + Vector((0, 0, 0.05)) if not b.startswith("lowerarm") else Vector(t["pos"]) + (Vector(t["pos"]) - Vector(REF[t["parent"]]["pos"])) * 0.5)
for b, t in REF.items():
    if t["parent"]: arm.edit_bones[b].parent = arm.edit_bones[t["parent"]]
bpy.ops.object.mode_set(mode="OBJECT")
verts = [tuple(Vector(t["pos"]) + Vector((0, 0.03, 0))) for t in REF.values()]
me = bpy.data.meshes.new("body"); me.from_pydata(verts, [], []); me.update()
body = bpy.data.objects.new("body", me); bpy.context.scene.collection.objects.link(body)
for i, b in enumerate(REF):
    body.vertex_groups.new(name=b).add([i], 1.0, "REPLACE")
me2 = bpy.data.meshes.new("piece"); me2.from_pydata([(5, 5, 5), (5.1, 5, 5), (5, 5.1, 5)], [], [(0, 1, 2)]); me2.update()
bpy.context.scene.collection.objects.link(bpy.data.objects.new("piece", me2))
r = api.fit_pose(kind="chest", piece="piece", body="body", armature="rig", dofs="chest")
res({"ok": r.get("ok"), "error": r.get("error"), "entries": r.get("entries"), "sweeps": len(r.get("sweeps") or []), "sign": r.get("sign_check")})
'''
    r = run_script(PRE + body, timeout=300)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["ok"], d["error"]
    assert d["entries"] == [] and d["sweeps"] == 60 and d["sign"]["moved_cm"] > 2.0, d
