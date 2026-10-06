# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_fit_template on a real mesh (specs/canon/rig_tools/rig_fit_template.md; canon 20), REAL binary: the UE5 Manny template rigged at
joints MEASURED on an example (Manny's joints with longer legs and shorter arms, a mesh of boxes around its bones), every measured head
written exactly, the rest of the 161 bones placed by their measured segments, frames by canon 17, an inside check by six axis rays per joint,
the example's own weights from the fitted segments - and the refusals of the 2026-09-28 defect (joints copied from the template's body), a
joints file measured on another mesh, a missing required joint, joints outside the example, and joints from views."""

from features_support import run

EXAMPLE = '''
from mixar.modules.lampway_tools.features import rig_conform as _RF
from mixar.modules.lampway_tools.rig_tools import core as _RC
from mixar.modules.lampway_tools import canon_io as _IO
_probe = bpy.data.objects.new("probe", None)
TPL = _RF.reference_rig("", _probe)
bpy.data.objects.remove(_probe)
LEG = ("thigh", "calf", "foot", "ball")
def measured(legs=1.08, arms=0.95):
    """Manny's required joints, each limb chain stretched about its root joint (legs x1.08 about the thigh, arms x0.95 about the upperarm)."""
    out = {}
    for n in _RC.REQUIRED_JOINTS:
        h = Vector(TPL["heads"][n]); s = n.rsplit("_", 1)[-1]
        if n.startswith(LEG):
            o = Vector(TPL["heads"]["thigh_" + s]); h = o + (h - o) * legs
        elif n.split("_")[0] in ("upperarm", "lowerarm", "hand", "thumb", "index", "middle", "ring", "pinky"):
            o = Vector(TPL["heads"]["upperarm_" + s]); h = o + (h - o) * arms
        out[n] = [h.x, h.y, h.z]
    return out
def body(J, name="example"):
    """Boxes around every bone segment of the measured joints (each joint inside its box)."""
    parts = []
    for n, p in J.items():
        par = TPL["parents"].get(n)
        while par is not None and par not in J: par = TPL["parents"].get(par)
        a = Vector(p); b = Vector(J[par]) if par else a + Vector((0, 0, 0.05))
        r = 0.012 if n.split("_")[0] in ("thumb", "index", "middle", "ring", "pinky") else 0.05
        lo = Vector([min(x, y) - r for x, y in zip(a, b)]); hi = Vector([max(x, y) + r for x, y in zip(a, b)])
        parts.append(((lo + hi) / 2, hi - lo))
    ob = boxes(name, parts)
    canon(name)
    return ob
def joints_file(path, J, ob, **extra):
    doc = dict({"schema": "titan.rig-joints/1", "example_sha256": _IO.geometry_sha256(ob), "joints": J}, **extra)
    os.makedirs(os.path.dirname(os.path.join(root, path)), exist_ok=True); open(os.path.join(root, path), "w").write(json.dumps(doc))
    return path
'''


def test_the_template_is_rigged_at_the_measured_joints_with_its_own_weights(tmp_path):
    r = run(tmp_path, EXAMPLE + '''
J = measured(); ob = body(J)
jf = joints_file("rig/ex.joints.json", J, ob)
dry = call("rig_fit_template", example="example", joints=jf, out="rig/ex.rig.blend", dry_run=True)
done = call("rig_fit_template", example="example", joints=jf, out="rig/ex.rig.blend")
arm = bpy.data.objects.get("example_rig"); m = bpy.data.objects.get("example_rigged")
heads = {b.name: list(b.head_local) for b in arm.data.bones} if arm else {}
ins = call("rig_inspect", armature="example_rig") if arm else None
groups = sorted(g.name for g in m.vertex_groups) if m else []
print("RESULT", json.dumps({"dry": dry, "done": done, "heads": heads, "J": J, "ins": ins, "groups": groups,
                            "mod": m.modifiers["Armature"].object.name if m else None, "file": os.path.isfile(os.path.join(root, "rig/ex.rig.blend")),
                            "src_groups": len(ob.vertex_groups)}))
''', timeout=900)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["dry"]["ok"] and o["dry"]["dry_run"] is True, o["dry"]
    d = o["done"]
    assert d["ok"] and d["residual"]["max_m"] <= 1e-6 and d["outside"] == [] and d["weights"]["unweighted"] == 0, {k: d.get(k) for k in ("residual", "outside", "weights", "error")}
    assert abs(d["ratios"]["calf_l"] - 1.08) < 1e-6 and abs(d["ratios"]["lowerarm_l"] - 0.95) < 1e-6 and abs(d["ratios"]["spine_02"] - 1.0) < 1e-6, d["ratios"]
    assert "upperarm_twist_01_l" in d["synthesized"] and d["synthesized"]["upperarm_twist_01_l"]["rule"].startswith("segment upperarm_l"), d["synthesized"].get("upperarm_twist_01_l")
    assert d["hidden"] == ["pelvis", "thigh_l", "thigh_r"] and d["sha256"]["example"] and d["sha256"]["joints"] and d["sha256"]["out"], d
    for n, p in o["J"].items():                                       # the measured joints ARE the fit
        assert max(abs(a - b) for a, b in zip(o["heads"][n], p)) <= 1e-6, n
    assert len(o["heads"]) == 161 and o["ins"]["ok"] and o["ins"]["convention"]["class"] == "blender", o["ins"].get("convention")
    assert "hand_l" in o["groups"] and "upperarm_twist_01_l" not in o["groups"], "weights on the body grammar only"
    assert o["mod"] == "example_rig" and o["file"] and o["src_groups"] == 0, "the example itself is untouched; its rigged copy is written"


def test_fit_refuses_copied_joints_another_mesh_a_missing_joint_views_and_joints_outside(tmp_path):
    r = run(tmp_path, EXAMPLE + '''
J = measured(); ob = body(J)
copied = call("rig_fit_template", example="example", joints=joints_file("rig/c.json", {n: list(TPL["heads"][n]) for n in J}, ob), out="rig/c.blend")
other = call("rig_fit_template", example="example", joints=joints_file("rig/o.json", J, ob, example_sha256="0" * 64), out="rig/o.blend")
K = dict(J); del K["head"]
missing = call("rig_fit_template", example="example", joints=joints_file("rig/m.json", K, ob), out="rig/m.blend")
views = call("rig_fit_template", example="example", joints="views", out="rig/v.blend")
O = dict(J); O["pinky_03_l"] = [O["pinky_03_l"][0] + 0.3, O["pinky_03_l"][1], O["pinky_03_l"][2]]
outside = call("rig_fit_template", example="example", joints=joints_file("rig/x.json", O, ob), out="rig/x.blend")
allowed = call("rig_fit_template", example="example", joints=joints_file("rig/y.json", O, ob), out="rig/y.blend", allow_outside=["pinky_03_l"])
print("RESULT", json.dumps({"copied": copied, "other": other, "missing": missing, "views": views, "outside": outside, "allowed": allowed}))
''', timeout=900)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["copied"]["ok"] is False and "copied_not_fitted" in o["copied"]["error"], o["copied"]
    assert o["other"]["ok"] is False and "another mesh" in o["other"]["error"], o["other"]
    assert o["missing"]["ok"] is False and "head" in o["missing"]["error"], o["missing"]
    assert o["views"]["ok"] is False and "pose environment" in o["views"]["error"], o["views"]
    assert o["outside"]["ok"] is False and "pinky_03_l" in o["outside"]["error"] and "allow_outside" in o["outside"]["error"], o["outside"]
    assert o["allowed"]["ok"] and o["allowed"]["outside"] == ["pinky_03_l"], o["allowed"].get("error")
