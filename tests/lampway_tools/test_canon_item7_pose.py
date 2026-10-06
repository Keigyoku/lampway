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
