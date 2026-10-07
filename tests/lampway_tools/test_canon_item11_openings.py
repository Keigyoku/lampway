# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 11 (canon 06 F.2, F.5): the gasket cuts the body section that CONTAINS the opening's axis point (never the
largest loop: at an arm plane the torso's loop is larger), and a texture is detected from the material's image nodes, not only from
the studio flag. REAL binary."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_wave2_openings import SCENE, scene  # noqa: E402,F401

ARM = '''
def tube(bm, x, radius, depth, z, caps, segments):
    bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=segments, radius1=radius, radius2=radius, depth=depth, matrix=Matrix.Translation((x, 0, z)))
bm = bmesh.new(); tube(bm, 0.4, 0.12, 1.0, 0.5, True, 32)
me = bpy.data.meshes.new("sleeve"); bm.to_mesh(me); bm.free(); link(bpy.data.objects.new("sleeve", me))
bm = bmesh.new(); tube(bm, 0.4, 0.06, 2.0, 0.5, False, 24); tube(bm, 0.0, 0.25, 2.0, 0.5, False, 24)          # arm + torso, one body
me = bpy.data.meshes.new("body"); bm.to_mesh(me); bm.free(); link(bpy.data.objects.new("body", me))
'''


def test_c12_the_gasket_cuts_the_section_containing_the_arm_not_the_larger_torso(tmp_path):
    r = scene(tmp_path, ARM + '''
res = call("fit_openings", stage="apply", object="sleeve", limb="body", axis=[0, 0, 1], plane_origin=[0.4, 0, 1.0], pose=POSE, answers={"OP001": "gasket"},
           flange_mm=20, lip_mm=4, clearance_mm=15)
out = {"res": res}
if res.get("ok"):
    new = bpy.data.objects[res["object"]]
    ring = [v.co for v in new.data.vertices if abs(v.co.z - 1.0) < 1e-6 and 0.04 < math.hypot(v.co.x - 0.4, v.co.y) < 0.11]
    poly = [(0.4 + 0.06 * math.cos(2 * math.pi * k / 24), 0.06 * math.sin(2 * math.pi * k / 24)) for k in range(24)]
    def seg_dist(p, a, b):
        ax, ay = a; bx, by = b; dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))
    d = [min(seg_dist((v.x, v.y), poly[k], poly[(k + 1) % 24]) for k in range(24)) for v in ring]
    out.update(n=len(ring), lo=min(d) if d else None, hi=max(d) if d else None, after=stats(new))
print("RESULT", json.dumps(out))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["res"]["ok"] is True, o["res"]
    assert o["n"] >= 24 and o["lo"] == pytest.approx(0.015, abs=0.001) and o["hi"] == pytest.approx(0.015, abs=0.001), o
    assert o["after"]["non_manifold"] == 0 and o["after"]["bad_winding"] == 0


def test_c12_a_section_plane_that_misses_the_axis_point_is_refused(tmp_path):
    r = scene(tmp_path, ARM + '''
bpy.data.objects["body"].location.x = 1.5; bpy.context.view_layer.update()
bpy.ops.object.select_all(action="DESELECT"); bpy.data.objects["body"].select_set(True); bpy.context.view_layer.objects.active = bpy.data.objects["body"]
bpy.ops.object.transform_apply(location=True)
res = call("fit_openings", stage="apply", object="sleeve", limb="body", axis=[0, 0, 1], plane_origin=[0.4, 0, 1.0], pose=POSE, answers={"OP001": "gasket"},
           flange_mm=20, clearance_mm=15)
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["ok"] is False and "contains the opening's axis point" in res["error"], res


def test_f5_a_texture_in_the_material_needs_the_discard_ack(tmp_path):
    r = scene(tmp_path, '''
ob = capped_cylinder("piece")
img = bpy.data.images.new("albedo", 8, 8)
mat = bpy.data.materials.new("m"); mat.use_nodes = True
node = mat.node_tree.nodes.new("ShaderNodeTexImage"); node.image = img
ob.data.materials.append(mat)
a = call("fit_openings", stage="apply", object="piece", axis=[0, 0, 1], plane_origin=[0, 0, 1.0], pose=POSE, answers={"OP001": "delete"})
b = call("fit_openings", stage="apply", object="piece", axis=[0, 0, 1], plane_origin=[0, 0, 1.0], pose=POSE, answers={"OP001": "delete"}, texture_discard_ack=True)
print("RESULT", json.dumps({"a": a, "b": b}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["a"]["ok"] is False and "discards the studio texture" in o["a"]["error"] and "albedo" in o["a"]["error"], o["a"]
    assert o["b"]["ok"] is True, o["b"]


SITE = """
def box(name, lo, hi):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector([lo[i] + (hi[i] - lo[i]) * (v.co[i] + 0.5) for i in range(3)])
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return link(bpy.data.objects.new(name, me))
chest = box("chest", (-0.2, -0.12, 0.9), (0.2, 0.12, 1.5))
pad = box("pad", (0.2, -0.08, 1.42), (0.32, 0.08, 1.52))
bm = bmesh.new()
for o in (chest, pad): bm.from_mesh(o.data)
me = bpy.data.meshes.new("piece"); bm.to_mesh(me); bm.free()
piece = link(bpy.data.objects.new("piece", me))
for o in (chest, pad): bpy.data.objects.remove(o)
arm = bpy.data.armatures.new("rig"); rig = link(bpy.data.objects.new("rig", arm))
bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode="EDIT")
s = arm.edit_bones.new("spine_05"); s.head = (0, 0, 1.0); s.tail = (0, 0, 1.3)
u = arm.edit_bones.new("upperarm_l"); u.head = (0.1, 0, 1.3); u.tail = (0.4, 0, 1.3); u.parent = s
l = arm.edit_bones.new("lowerarm_l"); l.head = (0.4, 0, 1.3); l.tail = (0.65, 0, 1.3); l.parent = u
bpy.ops.object.mode_set(mode="OBJECT")
"""


def test_f1_the_site_axis_is_the_posed_bone_line_and_finds_a_cap_that_is_not_at_the_extreme(tmp_path):
    r = scene(tmp_path, SITE + '''
typed = call("fit_openings", stage="detect", object="piece", axis=[1, 0, 0])
site = call("fit_openings", stage="detect", object="piece", armature="rig", site="upperarm_l", pose=POSE)
pb = bpy.data.objects["rig"].pose.bones["upperarm_l"]; pb.rotation_mode = "XYZ"; pb.rotation_euler = (0, 0, 0.0)
print("RESULT", json.dumps({"typed": typed, "site": site}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    xs = sorted(round(c["plane_origin_m"][0], 3) for c in o["typed"]["candidates"])
    assert 0.2 not in xs, xs                                  # the falsifier: the extreme rule finds the pad's face (x 0.32), not the arm hole
    c = o["site"]["candidates"]
    assert o["site"]["ok"] and len(c) == 1 and abs(c[0]["plane_origin_m"][0] - 0.2) < 1e-6 and c[0]["site"] == "upperarm_l", o["site"]
    assert c[0]["axis"] == [1.0, 0.0, 0.0] and c[0]["end"] == "site", c[0]


def test_f1_the_site_follows_the_pose_not_the_rest(tmp_path):
    """The arm turned 90 deg in the horizontal plane: its POSED line now leaves the chest through its front or back face, and that is the
    cap found, on the posed axis (the rest axis +X would have found the flank)."""
    r = scene(tmp_path, SITE + '''
pb = bpy.data.objects["rig"].pose.bones["upperarm_l"]; pb.rotation_mode = "XYZ"; pb.rotation_euler = (0, 0, math.radians(-90))
bpy.context.view_layer.update()
rig = bpy.data.objects["rig"]
d = (rig.matrix_world @ rig.pose.bones["lowerarm_l"].head) - (rig.matrix_world @ rig.pose.bones["upperarm_l"].head)
site = call("fit_openings", stage="detect", object="piece", armature="rig", site="upperarm_l", pose=POSE)
print("RESULT", json.dumps({"site": site, "dir": list(d.normalized())}))
''')
    assert r.rc == 0, r.out[-2500:]
    s, d = r.results[0]["site"], r.results[0]["dir"]
    assert abs(abs(d[1]) - 1.0) < 1e-6, d                                   # the posed arm points along Y
    c = s["candidates"]
    assert s["ok"] and len(c) == 1 and max(abs(a - b) for a, b in zip(c[0]["axis"], d)) < 1e-6, s
    assert abs(abs(c[0]["plane_origin_m"][1]) - 0.12) < 1e-6 and c[0]["plane_origin_m"][1] * d[1] > 0, c[0]
