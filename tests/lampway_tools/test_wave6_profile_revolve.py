# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""profile_revolve (specs/wiki/profile_revolve.md) in the real binary: a watertight lathe object from a 2D side profile (spin about Z, the seam merged, the poles
welded, the corners bevelled, normals outward)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

VOL = '''
def volume(ob):
    me = ob.data; me.calc_loop_triangles()
    v = 0.0
    for t in me.loop_triangles:
        a, b, c = (me.vertices[i].co for i in t.vertices)
        v += a.dot(b.cross(c)) / 6.0
    return v
'''


def test_cylinder_profile_volume_matches_pi_r2_h_and_is_manifold(tmp_path):
    d = one(go(tmp_path, VOL + '''
res = call("profile_revolve", profile=[[0, 0], [0.5, 0], [0.5, 1.0], [0, 1.0]], steps=256, name="post")
print("RESULT", json.dumps({"res": res, "vol": volume(bpy.data.objects["post"])}))
'''))
    res = d["res"]
    assert res["ok"] and res["object"] == "post" and res["manifold"] is True
    assert abs(d["vol"] - 3.141592653589793 * 0.25) / (3.141592653589793 * 0.25) < 0.005
    assert [round(x, 3) for x in res["bounds"]["size"]] == [1.0, 1.0, 1.0]


def test_normals_point_outward(tmp_path):
    d = one(go(tmp_path, VOL + '''
res = call("profile_revolve", profile=[[0, 0], [0.4, 0], [0.3, 0.5], [0.2, 0.8], [0, 0.9]], steps=48, name="pawn")
ob = bpy.data.objects["pawn"]
inward = 0
for p in ob.data.polygons:
    c = p.center
    radial = Vector((c.x, c.y, 0))
    if radial.length > 1e-3 and abs(p.normal.z) < 0.9 and p.normal.dot(radial) < 0:
        inward += 1
print("RESULT", json.dumps({"res": res, "vol": volume(ob), "inward": inward}))
'''))
    assert d["res"]["manifold"] is True and d["vol"] > 0 and d["inward"] == 0


def test_a_bevel_adds_faces_and_a_partial_angle_is_reported_open(tmp_path):
    d = one(go(tmp_path, '''
plain = call("profile_revolve", profile=[[0, 0], [0.5, 0], [0.5, 0.2], [0, 0.2]], steps=32, name="base")
bev = call("profile_revolve", profile=[[0, 0], [0.5, 0], [0.5, 0.2], [0, 0.2]], steps=32, bevel_m=0.02, name="base_bev")
half = call("profile_revolve", profile=[[0, 0], [0.5, 0], [0.5, 0.2], [0, 0.2]], steps=32, angle_deg=180, name="half")
print("RESULT", json.dumps({"plain": plain, "bev": bev, "half": half}))
'''))
    assert d["bev"]["faces"] > d["plain"]["faces"] and d["bev"]["manifold"] is True
    assert d["half"]["manifold"] is False and d["half"]["open_edges"] > 0


def test_negative_radius_too_few_points_and_bad_steps_are_refused(tmp_path):
    d = one(go(tmp_path, '''
neg = call("profile_revolve", profile=[[0, 0], [-0.2, 0.5], [0, 1]])
few = call("profile_revolve", profile=[[0.2, 0]])
steps = call("profile_revolve", profile=[[0, 0], [0.5, 0], [0, 1]], steps=4)
print("RESULT", json.dumps({"neg": neg, "few": few, "steps": steps, "objects": len(bpy.data.objects)}))
'''))
    assert d["neg"]["ok"] is False and "crosses the axis" in d["neg"]["error"]
    assert d["few"]["ok"] is False and "2..64" in d["few"]["error"]
    assert d["steps"]["ok"] is False and "8..256" in d["steps"]["error"] and d["objects"] == 0
