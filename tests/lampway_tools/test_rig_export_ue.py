# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_export_ue, the write half (specs/canon/rig_tools/rig_export_ue.md; canon 21), REAL binary: the export is accepted only when a read-back
of the written file matches the reference bone by bone (0.01 cm, 0.01 deg, 1e-4 scale); the recipe states every exporter argument; the file's
own UnitScaleFactor is read from the FBX, because Blender's importer compensates it and cannot show the x100 a default-scaled file gives UE.

G21.1: a mixed convention is refused before anything is written. G21.2 on a synthetic 5-bone chain: the measured pair for each canon-17
convention reads back to 0.01 deg; the falsifier (the other pair) reads 90 deg off while every head matches. G21.3: FBX_SCALE_NONE writes
UnitScaleFactor 1 (centimetre-native), FBX_SCALE_UNITS writes 100."""

import json

from features_support import run

CHAIN = '''
J = [(0.2, 0.0, 1.4), (0.45, -0.02, 1.2), (0.68, -0.05, 1.02), (0.76, -0.06, 0.96), (0.80, -0.06, 0.93), (0.83, -0.06, 0.91)]
def chain(name, along="y", skin=True, mixed=False):
    """R02's arm extended to 5 bones, frames from the joints and +Z (canon 17) in one convention (mixed: alternating), with a skinned strip."""
    arm = bpy.data.armatures.new(name); ob = link(bpy.data.objects.new(name, arm))
    bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode="EDIT"); prev = None
    for i in range(5):
        a = Vector(J[i + 1]) - Vector(J[i]); a.normalize(); u = Vector((0, 0, 1)); u = (u - u.dot(a) * a).normalized()
        conv = ("x" if i % 2 else "y") if mixed else along
        cols = (a.cross(u), a, u) if conv == "y" else (a, u.cross(a), u)
        M = Matrix([[cols[0][r], cols[1][r], cols[2][r], J[i][r]] for r in range(3)] + [[0, 0, 0, 1]])
        e = arm.edit_bones.new(f"b{i}"); e.head = J[i]; e.tail = J[i + 1]; e.matrix = M; e.length = 0.05
        if prev: e.parent = prev
        prev = e
    bpy.ops.object.mode_set(mode="OBJECT")
    if skin:
        me = bpy.data.meshes.new(name + "_skin"); vs = []
        for i in range(5):
            for t in (0.3, 0.7):
                p = Vector(J[i]).lerp(Vector(J[i + 1]), t); vs += [p + Vector((0, 0.02, 0)), p + Vector((0, -0.02, 0)), p + Vector((0, 0, 0.02))]
        me.from_pydata(vs, [], [(k, k + 1, k + 2) for k in range(0, len(vs), 3)]); m = link(bpy.data.objects.new(name + "_skin", me))
        for i in range(5):
            g = m.vertex_groups.new(name=f"b{i}"); g.add(list(range(6 * i, 6 * i + 6)), 1.0, "REPLACE")
        mod = m.modifiers.new("Armature", "ARMATURE"); mod.object = ob; m.parent = ob
    return ob
def recipe(path, pa, sa, scale="FBX_SCALE_NONE", usf=1.0):
    base = json.loads(open(os.path.join(RECIPES, "titan_cm_native.json")).read())
    base["exporter"].update(primary_bone_axis=pa, secondary_bone_axis=sa, apply_scale_options=scale)
    base["expect"] = {"unit_scale_factor": usf}
    os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "w").write(json.dumps(base))
    return path
from mixar.modules.lampway_tools.rig_tools import core as _RC
RECIPES = os.path.join(os.path.dirname(_RC.__file__), "recipes")
'''


def test_the_measured_pair_reads_back_and_the_other_pair_is_rejected_90_degrees_off(tmp_path):
    r = run(tmp_path, CHAIN + '''
b = chain("cb", "y"); x = chain("cx", "x")
call("rig_inspect", armature="cb"); call("rig_inspect", armature="cx")
ok_b = call("rig_export_ue", armature="cb", out="export/cb.fbx", recipe=os.path.join(RECIPES, "cm_native_blender_convention.json"))
ok_x = call("rig_export_ue", armature="cx", out="export/cx.fbx", recipe=os.path.join(RECIPES, "cm_native_ue_axes.json"))
bad = call("rig_export_ue", armature="cb", out="export/cb_yx.fbx", recipe=os.path.join(RECIPES, "cm_native_ue_axes.json"))
again = call("rig_export_ue", armature="cb", out="export/cb.fbx", recipe=os.path.join(RECIPES, "cm_native_blender_convention.json"))
left = sorted(o.name for o in bpy.data.objects)
print("RESULT", json.dumps({"ok_b": ok_b, "ok_x": ok_x, "bad": bad, "again": again, "left": left,
                            "files": sorted(os.path.relpath(os.path.join(d, f), root) for d, _s, fs in os.walk(os.path.join(root, "export")) for f in fs)}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    for k in ("ok_b", "ok_x"):
        d = o[k]
        assert d["ok"] and d["verdict"] == "PASS", d
        rb = d["readback"]
        assert rb["bones_compared"] == 5 and rb["worst_rotation_deg"] < 0.01 and rb["worst_position_cm"] < 0.01 and rb["worst_scale"] < 1e-4, rb
        assert d["unit_scale_factor"] == 1.0 and d["sha256"]["fbx"] and d["sha256"]["armature_rest"] and d["normals"]["corner_max_deg"] < 0.1, d
    assert o["ok_b"]["convention"] == "blender" and o["ok_x"]["convention"] == "ue_axes"
    bad = o["bad"]
    assert bad["ok"] is False and "read-back" in bad["error"] and "export/rejected/cb_yx.fbx" in bad["error"], bad
    assert "b0" in bad["error"], "the rows over tolerance are named"
    assert o["again"]["ok"] is False and "exists" in o["again"]["error"], o["again"]
    assert "export/cb.fbx" in o["files"] and "export/rejected/cb_yx.fbx" in o["files"] and "export/cb_yx.fbx" not in o["files"], o["files"]
    assert o["left"] == ["cb", "cb_skin", "cx", "cx_skin"], "the read-back's imports are removed"


def test_the_file_unit_scale_is_read_from_the_fbx_and_the_recipe_expectation_gates_it(tmp_path):
    r = run(tmp_path, CHAIN + '''
x = chain("cx", "x"); call("rig_inspect", armature="cx")
units = call("rig_export_ue", armature="cx", out="export/u.fbx", recipe=recipe(os.path.join(root, "r/units.json"), "Y", "X", "FBX_SCALE_UNITS", 100.0))
wrong = call("rig_export_ue", armature="cx", out="export/w.fbx", recipe=recipe(os.path.join(root, "r/wrong.json"), "Y", "X", "FBX_SCALE_UNITS", 1.0))
open(os.path.join(root, "r/short.json"), "w").write(json.dumps({"name": "short", "exporter": {"primary_bone_axis": "Y"}, "expect": {}}))
short = call("rig_export_ue", armature="cx", out="export/s.fbx", recipe="r/short.json")
print("RESULT", json.dumps({"units": units, "wrong": wrong, "short": short}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["units"]["ok"] and o["units"]["unit_scale_factor"] == 100.0 and o["units"]["verdict"] == "PASS", o["units"]
    # G21.3's falsifier: Blender's importer compensates the 100 (the bones read scale 1), so only the file says it
    assert o["units"]["readback"]["worst_scale"] < 1e-4
    assert o["wrong"]["ok"] is False and "UnitScaleFactor 100" in o["wrong"]["error"], o["wrong"]
    assert o["short"]["ok"] is False and "secondary_bone_axis" in o["short"]["error"], o["short"]


def test_export_refuses_mixed_leaf_constrained_unknown_groups_and_the_uninspected_before_writing(tmp_path):
    r = run(tmp_path, CHAIN + '''
B = os.path.join(RECIPES, "cm_native_blender_convention.json")
m = chain("cm", mixed=True); call("rig_inspect", armature="cm")
mixed = call("rig_export_ue", armature="cm", out="export/m.fbx", recipe=B)
c = chain("cc"); cold = call("rig_export_ue", armature="cc", out="export/c.fbx", recipe=B)
cn = chain("cn"); cn.pose.bones["b2"].constraints.new("COPY_ROTATION"); call("rig_inspect", armature="cn")
constrained = call("rig_export_ue", armature="cn", out="export/n.fbx", recipe=B)
lf = chain("cl"); bpy.context.view_layer.objects.active = lf; bpy.ops.object.mode_set(mode="EDIT")
e = lf.data.edit_bones.new("b4_end"); e.head = J[5]; e.tail = (J[5][0], J[5][1], J[5][2] + 0.03); e.parent = lf.data.edit_bones["b4"]
bpy.ops.object.mode_set(mode="OBJECT"); call("rig_inspect", armature="cl")
leaf = call("rig_export_ue", armature="cl", out="export/l.fbx", recipe=B)
ref = chain("ref", "x", skin=False); bpy.context.view_layer.objects.active = ref; bpy.ops.object.mode_set(mode="EDIT")
ref.data.edit_bones.remove(ref.data.edit_bones["b4"]); bpy.ops.object.mode_set(mode="OBJECT")
g = chain("cg"); call("rig_inspect", armature="cg")
groups = call("rig_export_ue", armature="cg", out="export/g.fbx", recipe=B, reference="ref")
print("RESULT", json.dumps({"mixed": mixed, "cold": cold, "constrained": constrained, "leaf": leaf, "groups": groups,
                            "files": sorted(os.listdir(os.path.join(root, "export"))) if os.path.isdir(os.path.join(root, "export")) else []}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["mixed"]["ok"] is False and "mixed" in o["mixed"]["error"], o["mixed"]
    assert o["cold"]["ok"] is False and "rig_inspect" in o["cold"]["error"], o["cold"]
    assert o["constrained"]["ok"] is False and "b2" in o["constrained"]["error"] and "constraint" in o["constrained"]["error"], o["constrained"]
    assert o["leaf"]["ok"] is False and "b4_end" in o["leaf"]["error"], o["leaf"]
    assert o["groups"]["ok"] is False and "b4" in o["groups"]["error"] and "reference" in o["groups"]["error"], o["groups"]
    assert o["files"] == [], "every refusal happens before anything is written"


def test_titan_cm_native_is_the_default_and_is_refused_by_the_read_back_on_both_canon17_conventions(tmp_path):
    """A measured fact recorded as a test (2026-10-06): TITAN's pair (primary Z / secondary X), right in Unreal for the native MetaHuman as its
    Blender import laid it, is refused by the raw-frame read-back on a canon-17 rig of either convention (120 deg off on a 'blender' rig,
    90 deg on a 'ue_axes' one). The gate refuses; nothing is
    published. If this test starts passing, the read-back changed: re-measure before trusting either recipe."""
    r = run(tmp_path, CHAIN + '''
b = chain("cb", "y"); x = chain("cx", "x"); call("rig_inspect", armature="cb"); call("rig_inspect", armature="cx")
rb = call("rig_export_ue", armature="cb", out="export/b.fbx"); rx = call("rig_export_ue", armature="cx", out="export/x.fbx")
print("RESULT", json.dumps({"rb": rb, "rx": rx}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    for k, deg in (("rb", " 120 deg"), ("rx", " 90 deg")):
        e = r.results[0][k]
        assert e["ok"] is False and "export/rejected/" in e["error"] and deg in e["error"], e
