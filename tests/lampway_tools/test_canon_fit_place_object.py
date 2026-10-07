# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon 03 B.4 -> B.6: the placement is applied to the SCENE piece the later stages work on. lampway_fit_place object=<name> moves
the object by the very similarity the placement found (fitted from piece.npz to placed.npz: it must BE one similarity), after
checking that piece.npz is that object's world mesh - a placement computed for another mesh is refused. REAL binary."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from canon_fit_support import FIT_PRE  # noqa: E402

SCENE = r'''
body, arm = figure()
pkg = api.fit_body("build", armature="rig", mesh="body", out="fit/body")
assert pkg.get("ok"), pkg
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=False, segments=32, radius1=0.2, radius2=0.2, depth=0.35, matrix=__import__("mathutils").Matrix.Translation((0.02, 0.01, 1.2)))
me = bpy.data.meshes.new("band"); bm.to_mesh(me); bm.free()
band = bpy.data.objects.new("band", me); bpy.context.scene.collection.objects.link(band)
band.data.transform(__import__("mathutils").Matrix.Translation((0, 0, -0.05)))          # an object with its own transform: the placement is a WORLD map
band.location = (0, 0, 0.05); band.rotation_euler = (0, 0, math.radians(30)); bpy.context.view_layer.update()
npz(band, os.path.join(root, "pieces", "band.npz"))
body_npz = os.path.relpath(os.path.join(pkg["package"], "body.npz"), root)
'''


def test_fit_place_applies_the_placement_to_the_scene_object_and_refuses_another_mesh(tmp_path):
    r = run_script(FIT_PRE + SCENE + '''
out = {"placed": api.fit_place("waist", piece="pieces/band.npz", body=body_npz, out="fit/placed.npz", object="band")}
if out["placed"].get("ok"):
    P = np.load(os.path.join(root, "fit", "placed.npz"))["V"]
    W = np.array([tuple(band.matrix_world @ v.co) for v in band.data.vertices])
    out["max_diff_m"] = float(np.abs(P - W).max())
other = band.copy(); other.data = band.data.copy(); other.name = "other"; bpy.context.scene.collection.objects.link(other)
for v in other.data.vertices: v.co.z += 0.1
out["other"] = api.fit_place("waist", piece="pieces/band.npz", body=body_npz, out="fit/placed2.npz", object="other")
res(out)
''', env={"LW_KEEP_ROOT": str(tmp_path)}, timeout=300)
    assert r.rc == 0, r.out[-2500:]
    d = r.results[-1]
    p = d["placed"]
    assert p["ok"], p
    assert abs(p["scale"] - 1.0) > 1e-3, "the band must actually be rescaled for this to test anything"
    assert d["max_diff_m"] < 1e-6, d
    assert p["object"]["name"] == "band" and p["object"]["similarity_residual_m"] < 1e-9, p["object"]
    assert d["other"]["ok"] is False and "piece.npz" in d["other"]["error"], d["other"]
