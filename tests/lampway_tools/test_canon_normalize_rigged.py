# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""N5 (specs/canon/normalization contracts/normalize_rig.md): lampway_normalize_rigged - canon R1 inspect + R3 normalize behind the
ingress door, then a canonical `skeleton` document on the armature (bones with `along` = head -> the next joint, never the tail;
frames; the roster; the naming) and a `rigged_mesh` document on each mesh skinned to it. Refused: a mixed convention (canon 17), an
incomplete roster (the missing bones named), a unit ratio no known factor explains (canon 18). REAL binary."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402

RIG = r'''
import json
from mathutils import Vector
from mixar.modules.lampway_tools import canon_asset as CA
prof = json.load(open(api.__file__.replace("api.py", "rig_convert/recipes/anim-profile-manny.json")))
zs = [b["bind"]["translation"][2] for b in prof["bones"]]
H = (max(zs) - min(zs)) / 100.0                        # the reference's joint height (m): the fixture stands that tall
J = {"pelvis": (0, 0, 0.55), "spine_01": (0, 0, 0.60), "spine_02": (0, 0, 0.66), "spine_03": (0, 0, 0.72), "spine_04": (0, 0, 0.78),
     "spine_05": (0, 0, 0.84), "neck_01": (0, 0, 0.90), "head": (0, 0, 0.96)}
for s, x in (("l", 1), ("r", -1)):
    J.update({f"clavicle_{s}": (0.03 * x, 0, 0.86), f"upperarm_{s}": (0.12 * x, 0, 0.86), f"lowerarm_{s}": (0.28 * x, 0, 0.72),
              f"hand_{s}": (0.40 * x, 0, 0.60), f"thigh_{s}": (0.06 * x, 0, 0.53), f"calf_{s}": (0.07 * x, 0, 0.28), f"foot_{s}": (0.07 * x, 0, 0.04),
              f"ball_{s}": (0.07 * x, -0.07, 0.0)})
P = {"pelvis": None, "spine_01": "pelvis", "spine_02": "spine_01", "spine_03": "spine_02", "spine_04": "spine_03", "spine_05": "spine_04",
     "neck_01": "spine_05", "head": "neck_01"}
for s in "lr":
    P.update({f"clavicle_{s}": "spine_05", f"upperarm_{s}": f"clavicle_{s}", f"lowerarm_{s}": f"upperarm_{s}", f"hand_{s}": f"lowerarm_{s}",
              f"thigh_{s}": "pelvis", f"calf_{s}": f"thigh_{s}", f"foot_{s}": f"calf_{s}", f"ball_{s}": f"foot_{s}"})
NEXT = {"pelvis": "spine_01", "spine_05": "neck_01"}
def build(name="body_rig", k=1.0, drop=(), off_limb=()):
    s_ = H / 0.96 * k
    arm = bpy.data.armatures.new(name); ob = bpy.data.objects.new(name, arm); bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode="EDIT")
    kids = {}
    for b, p in P.items():
        if p: kids.setdefault(p, []).append(b)
    for b, h in J.items():
        if b in drop: continue
        eb = arm.edit_bones.new(b); eb.head = Vector(h) * s_
        c = NEXT.get(b) or (kids.get(b, [None])[0] if len(kids.get(b, [])) == 1 else None)
        d = (Vector(J[c]) - Vector(h)) if c else Vector((0, 0, 0.05))
        if b in off_limb: d = d.cross(Vector((0, 1, 0))) if d.cross(Vector((0, 1, 0))).length > 1e-6 else Vector((1, 0, 0)) * d.length
        eb.tail = eb.head + d * s_
    for b, p in P.items():
        if p and b not in drop and p not in drop: arm.edit_bones[b].parent = arm.edit_bones[p]
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob
def skinned(arm, name="body"):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=0.2)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    mob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(mob)
    g = mob.vertex_groups.new(name="spine_01"); g.add(list(range(len(me.vertices))), 1.0, "REPLACE")
    m = mob.modifiers.new("Armature", "ARMATURE"); m.object = arm
    return mob
'''


def test_n5_a_clean_rig_and_its_skinned_mesh_are_stamped_canonical_and_open_their_doors():
    r = run_script(PRE + RIG + '''
arm = build(); body = skinned(arm)
r = api.normalize_rigged(armature="body_rig", dry_run=False)
doc = json.loads(arm["lw_canon"]) if "lw_canon" in arm.keys() else None
mdoc = json.loads(body["lw_canon"]) if "lw_canon" in body.keys() else None
probe = api.tool(consumes={"armature": api.Need(kind=("skeleton",), scale=CA.ANY_SCALE), "mesh": api.Need(kind=("rigged_mesh",), scale=CA.ANY_SCALE)})(lambda armature, mesh: {"ran": 1})
b = {x["name"]: x for x in (doc or {}).get("body", {}).get("bones", [])}
res({"ok": r.get("ok"), "error": r.get("error"), "errs": CA.validate(doc) if doc else "no doc", "merrs": CA.validate(mdoc) if mdoc else "no doc",
     "kind": doc and doc["kind"], "mkind": mdoc and mdoc["kind"], "conv": doc and doc["body"]["convention"], "roster": doc and doc["body"]["roster"],
     "along": b.get("upperarm_l", {}).get("along"), "src": b.get("upperarm_l", {}).get("along_source"),
     "hand": b.get("hand_l", {}).get("along"), "hsrc": b.get("hand_l", {}).get("along_source"), "ref": mdoc and mdoc["body"]["skeleton"],
     "csha": doc and doc["canonical_sha256"], "door": probe(armature="body_rig", mesh="body")})
''', timeout=300)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["ok"], d["error"]
    assert d["errs"] == [] and d["merrs"] == [] and d["kind"] == "skeleton" and d["mkind"] == "rigged_mesh", d
    assert d["conv"] == "blender" and d["roster"] == {"complete": True, "missing": []}
    a = d["along"]
    assert d["src"] == "child_head" and abs(a[0] - 0.16 / (0.16 ** 2 + 0.14 ** 2) ** 0.5) < 1e-5 and abs(a[2] + 0.14 / (0.16 ** 2 + 0.14 ** 2) ** 0.5) < 1e-5, a
    h = d["hand"]                                                       # a leaf: its tail points +Z, its along continues the forearm
    assert d["hsrc"] == "leaf_parent_line" and abs(h[0] - 0.12 / (0.12 ** 2 + 0.12 ** 2) ** 0.5) < 1e-5 and abs(h[2] + 0.12 / (0.12 ** 2 + 0.12 ** 2) ** 0.5) < 1e-5, h
    assert d["ref"]["canonical_sha256"] == d["csha"] and d["door"] == {"ok": True, "ran": 1}, d


def test_n5_refusals_mixed_convention_incomplete_roster():
    r = run_script(PRE + RIG + '''
build("mixed", off_limb=("upperarm_l", "lowerarm_l", "thigh_l", "calf_l", "spine_02", "spine_03"))
build("short", drop=("hand_l",))
res({"mixed": api.normalize_rigged(armature="mixed", dry_run=False), "short": api.normalize_rigged(armature="short", dry_run=False),
     "stamped": ["lw_canon" in bpy.data.objects[n].keys() for n in ("mixed", "short")]})
''', timeout=300)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["mixed"]["ok"] is False and "canon 17 refuses a mixed armature" in d["mixed"]["error"], d["mixed"]     # the refusal itself, not a schema failure
    assert d["short"]["ok"] is False and "hand_l" in d["short"]["error"] and "roster" in d["short"]["error"], d["short"]
    assert d["stamped"] == [False, False]


def test_n5_a_centimetre_rig_is_planned_then_normalized_to_real_scale_with_its_measured_ratio():
    r = run_script(PRE + RIG + '''
arm = build("cm_rig", k=100.0)
plan = api.normalize_rigged(armature="cm_rig")                          # dry run (the default): nothing changes
stamped_after_plan = "lw_canon" in arm.keys()
done = api.normalize_rigged(armature="cm_rig", dry_run=False)
doc = json.loads(arm["lw_canon"]) if "lw_canon" in arm.keys() else {}
res({"plan": {k: plan.get(k) for k in ("ok", "error", "dry_run", "unit")}, "stamped_after_plan": stamped_after_plan,
     "done": {k: done.get(k) for k in ("ok", "error")}, "scale": doc.get("scale"), "head_z": [x["head_m"][2] for x in doc.get("body", {}).get("bones", []) if x["name"] == "head"]})
''', timeout=300)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["plan"]["ok"] and d["plan"]["dry_run"] is True and d["plan"]["unit"] == "cm" and d["stamped_after_plan"] is False, d
    assert d["done"]["ok"], d["done"]
    s = d["scale"]
    assert s["state"] == "real" and s["decision"] == "measured" and s["evidence"]["method"] == "reference_height_ratio", s
    assert 0.9 < d["head_z"][0] / 1.0 < 2.0, d["head_z"]               # metres now, not 100x


def test_rig_inspect_reads_a_ue_named_rig_as_the_ue_family_with_its_roster_complete():
    """canon 16: UE bone names ARE the canonical slot names. rig_inspect knew only the mixamo and rigify tables, so a UE-named rig came
    back family None with every required slot missing; the shipped `ue` table maps each slot to itself."""
    r = run_script(PRE + RIG + '''
build("ue_rig")
i = api.rig_inspect(armature="ue_rig")
res({"family": i["family"]["name"], "missing": i["slots"]["missing_required"], "mapped": len(i["slots"]["mapped"])})
''', timeout=300)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["family"] == "ue" and d["missing"] == [] and d["mapped"] >= 17, d


def test_metahuman_corrective_root_with_multiple_children_keeps_authored_frame_on_apply():
    r = run_script(PRE + RIG + '''
for side, sign in (("l", 1), ("r", -1)):
    for i, finger in enumerate(("thumb", "index", "middle", "ring", "pinky")):
        for joint in (1, 2, 3):
            name = f"{finger}_{joint:02d}_{side}"
            J[name] = (sign * (0.40 + 0.025 * joint), 0.015 * (i - 2), 0.60)
            P[name] = f"{finger}_{joint - 1:02d}_{side}" if joint > 1 else f"hand_{side}"
J["upperarm_correctiveRoot_l"] = J["upperarm_l"]
P["upperarm_correctiveRoot_l"] = "upperarm_l"
for tag, dy in (("front", -0.02), ("back", 0.02)):
    name = "upperarm_corrective_" + tag + "_l"
    J[name] = (0.13, dy, 0.86); P[name] = "upperarm_correctiveRoot_l"
arm = build("mh_rig")
bpy.context.view_layer.objects.active = arm; bpy.ops.object.mode_set(mode="EDIT")
arm.data.edit_bones["upperarm_correctiveRoot_l"].roll = math.radians(120)
bpy.ops.object.mode_set(mode="OBJECT")
frame = [list(row) for row in arm.data.bones["upperarm_correctiveRoot_l"].matrix_local.to_3x3()]
r = api.normalize_rigged(armature="mh_rig", profile="metahuman", dry_run=False)
doc = json.loads(arm["lw_canon"]) if "lw_canon" in arm.keys() else {}
bones = {b["name"]: b for b in doc.get("body", {}).get("bones", [])}
res({"result": r, "corrective": bones.get("upperarm_correctiveRoot_l"), "frame": frame,
     "errors": CA.validate(doc) if doc else ["no document"]})
''', timeout=300)
    assert r.rc == 0, r.out[-2500:]
    d = r.results[-1]
    assert d["result"]["ok"], d["result"]
    assert d["errors"] == []
    assert d["corrective"]["along_source"] == "authored_helper_frame"
    import numpy as np
    assert np.allclose(d["corrective"]["frame"], d["frame"], atol=1e-9)
