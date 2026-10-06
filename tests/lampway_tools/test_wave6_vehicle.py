# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""vehicle_wheel_rig (specs/wiki/vehicle_wheel_rig.md) in the real binary: each wheel's centre found by a least-squares circle fit to its rim ring, its origin
moved there on a COPY, a bone per wheel named for the template, and the four axles checked parallel. Handling and physics stay engine-side."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

CAR = '''
def wheel(name, centre, r=0.35, w=0.22, tilt=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=r, radius2=r, depth=w)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(90 + tilt), 3, "Y"))   # axle along X
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(centre) - Vector((0.1, 0.05, -0.2)))                       # the mesh sits off its origin
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.location = (0.1, 0.05, -0.2)
    return link(ob)
body = boxes("car", [((0, 0, 0.7), (1.8, 4.2, 0.9))])
CENTRES = {"wheel_fl": (-0.9, 1.4, 0.35), "wheel_fr": (0.9, 1.4, 0.35), "wheel_rl": (-0.9, -1.4, 0.35), "wheel_rr": (0.9, -1.4, 0.35)}
WHEELS = [{"object": n + "_mesh", "name": n} for n in CENTRES]
'''


def test_origin_moves_to_the_wheel_centre_on_a_copy_with_one_bone_per_wheel(tmp_path):
    d = one(go(tmp_path, CAR + '''
for n, c in CENTRES.items():
    wheel(n + "_mesh", c)
before = {w["object"]: list(bpy.data.objects[w["object"]].location) for w in WHEELS}
res = call("vehicle_wheel_rig", body="car", wheels=WHEELS, axis="x")
arm = bpy.data.objects[res["armature"]]
out = {}
for w in res["wheels"]:
    ob = bpy.data.objects[w["object"]]
    src = bpy.data.objects[w["source"]]
    shift = max((ob.matrix_world @ a.co - src.matrix_world @ b.co).length for a, b in zip(ob.data.vertices, src.data.vertices))
    out[w["name"]] = {"loc": [round(x, 4) for x in ob.matrix_world.translation], "parent": ob.parent_bone, "bone_head": [round(x, 4) for x in arm.matrix_world @ arm.data.bones[w["name"]].head_local],
                      "shift": shift}
print("RESULT", json.dumps({"res": res, "out": out, "before_same": before == {w["object"]: list(bpy.data.objects[w["object"]].location) for w in WHEELS}}))
'''))
    res, out = d["res"], d["out"]
    assert res["ok"], res
    assert d["before_same"] and res["axle_alignment_pass"] is True
    for w in res["wheels"]:
        c = {"wheel_fl": [-0.9, 1.4, 0.35], "wheel_fr": [0.9, 1.4, 0.35], "wheel_rl": [-0.9, -1.4, 0.35], "wheel_rr": [0.9, -1.4, 0.35]}[w["name"]]
        assert all(abs(a - b) < 1e-3 for a, b in zip(w["centre"], c)) and abs(w["radius_m"] - 0.35) < 0.005
        assert all(abs(a - b) < 1e-3 for a, b in zip(out[w["name"]]["loc"], c)) and out[w["name"]]["parent"] == w["name"]
        assert all(abs(a - b) < 1e-3 for a, b in zip(out[w["name"]]["bone_head"], c))
        assert abs(abs(w["axle_dir"][0]) - 1) < 1e-3 and w["origin_error_m"] > 0.2 and out[w["name"]]["shift"] < 1e-5      # the geometry did not move, only its origin


def test_non_circular_object_refused(tmp_path):
    d = one(go(tmp_path, CAR + '''
for n, c in list(CENTRES.items())[:3]:
    wheel(n + "_mesh", c)
boxes("wheel_rr_mesh", [((0.9, -1.4, 0.35), (0.22, 0.7, 0.5))])
res = call("vehicle_wheel_rig", body="car", wheels=WHEELS, axis="x")
print("RESULT", json.dumps(res))
'''))
    assert d["ok"] is False and "this does not look like a wheel" in d["error"] and "wheel_rr" in d["error"]


def test_axles_parallel_report_and_the_refusals(tmp_path):
    d = one(go(tmp_path, CAR + '''
for n, c in CENTRES.items():
    wheel(n + "_mesh", c, tilt=12.0 if n == "wheel_rr" else 0.0)
tilted = call("vehicle_wheel_rig", body="car", wheels=WHEELS, axis="x")
three = call("vehicle_wheel_rig", body="car", wheels=WHEELS[:3], axis="x")
bpy.data.objects["wheel_fl_mesh"].scale = (2, 2, 2)
scaled = call("vehicle_wheel_rig", body="car", wheels=WHEELS, axis="x")
print("RESULT", json.dumps({"tilted": tilted, "three": three, "scaled": scaled}))
'''))
    t = d["tilted"]
    assert t["ok"] and t["axle_alignment_pass"] is False and t["axle_worst_deg"] > 10
    assert d["three"]["ok"] is False and "wheel_fl, wheel_fr, wheel_rl, wheel_rr" in d["three"]["error"]
    assert d["scaled"]["ok"] is False and "apply" in d["scaled"]["error"]


def test_an_oval_rim_is_refused_by_its_fit_residual(tmp_path):
    d = one(go(tmp_path, CAR + '''
for n, c in CENTRES.items():
    w = wheel(n + "_mesh", c)
    if n == "wheel_fl":
        for v in w.data.vertices:                                            # a 1.2 x oval: the rim still goes all the way round
            v.co.z = c[2] - w.location.z + (v.co.z - (c[2] - w.location.z)) * 1.2
res = call("vehicle_wheel_rig", body="car", wheels=WHEELS, axis="x")
print("RESULT", json.dumps(res))
'''))
    assert d["ok"] is False and "this does not look like a wheel" in d["error"] and "wheel_fl" in d["error"] and "residual" in d["error"]
