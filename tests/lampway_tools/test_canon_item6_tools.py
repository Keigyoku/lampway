# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 6 onward (the rest of the main plan) at the TOOL level:
* clearance (canon 15): an OPEN body is refused unless its opening band is declared (golden C05 open sphere);
* the skeleton export check (canon 21 / 01 C.3): bone FRAMES are compared, not only positions;
* the bake (canon 14): the ray reaches 2x the cage by default (golden C10's sunk HP);
* retopology (canon 12): deviation is two-sided (G12.2: a dropped fin);
* silhouette comparison (canon 10): masks are compared at their true aspect (golden C11: IoU 0.5, never 1.0).
Each was observed failing on the tool as it stood before the change."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from canon_support import LOAD_OBJ, J, goldens  # noqa: E402,F401
from test_wave3_weights import PRE  # noqa: E402


def run(body, goldens=None):
    head = PRE + LOAD_OBJ + (f"GOLD = {str(goldens)!r}\n" if goldens else "")
    r = run_script(head + body, timeout=400)
    assert r.rc == 0, r.out[-1500:]
    return r.results[-1]


def test_g15_3_an_open_body_is_refused_unless_its_opening_band_is_declared(goldens):
    d = run('''
arm = armature(bones=(("root", (0, 0, 0.7), (0, 0, 1.3), None),))
body = load_obj(GOLD + "/C05_clearance/open_sphere.obj", "body"); weights(body, arm, lambda c: {"root": 1.0})
piece = tube("piece", r=0.25, z0=0.9, z1=1.1, seg=16, rings=4)
a = api.garment_clearance("piece", "body", "rig")
b = api.garment_clearance("piece", "body", "rig", body_open_band_m=0.05)
res({"a": a.get("error"), "b_ok": b.get("ok"), "b_err": b.get("error"), "open": b.get("body_open")})
''', goldens)
    assert d["a"] and "open" in d["a"] and "body_open_band_m" in d["a"], d
    assert d["b_ok"], d["b_err"]
    assert d["open"]["boundary_edges"] > 0 and d["open"]["band_m"] == 0.05


def test_the_skeleton_export_check_compares_bone_frames_not_only_positions():
    d = run('''
import math
def rig(name, roll):
    arm = armature(name=name, bones=(("root", (0, 0, 0), (0, 0, 0.2), None), ("spine", (0, 0, 0.2), (0, 0, 0.6), "root")))
    bpy.context.view_layer.objects.active = arm; arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT"); arm.data.edit_bones["spine"].roll = math.radians(roll); bpy.ops.object.mode_set(mode="OBJECT")
    arm.select_set(False)
    return arm
ref = rig("ref", 0.0)
for o in bpy.context.view_layer.objects: o.select_set(False)
ref.select_set(True); bpy.context.view_layer.objects.active = ref
bpy.ops.export_scene.fbx(filepath=os.path.join(root, "ref.fbx"), use_selection=True, add_leaf_bones=False, primary_bone_axis="Z", secondary_bone_axis="X")
bpy.data.objects.remove(ref)
turned = rig("turned", 90.0); same = rig("same", 0.0)
a = api.skeleton_export_check(armature="turned", target={"names_from": "ref.fbx"})
b = api.skeleton_export_check(armature="same", target={"names_from": "ref.fbx"})
res({"a": {k: a.get(k) for k in ("pass", "reasons", "frames", "error")}, "b": {k: b.get(k) for k in ("pass", "reasons", "frames", "error")}})
''')
    a, b = d["a"], d["b"]
    assert a["pass"] is False and any("frame" in r for r in a["reasons"]) and a["frames"]["worst_deg"] == pytest.approx(90.0, abs=0.5), a
    assert b["frames"]["worst_deg"] < 0.01 and not any("frame" in r for r in b["reasons"]), b


def test_g14_3_the_bake_ray_reaches_twice_the_cage_by_default():
    d = run('''
bpy.ops.mesh.primitive_plane_add(size=1.0); low = bpy.context.active_object; low.name = "low"
bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0, 0, -0.005)); high = bpy.context.active_object; high.name = "high"
from mixar.modules.lampway_tools.features import bake as BK
cfg = BK.plan("high", "low", ["normal"], 256, None, 0.02, None, 4, "+Y", False, "bake", False, root)     # an explicit cage (auto is measured: item 9)
res({"cage": cfg["cage_extrusion_m"], "ray": cfg["max_ray_m"]})
''')
    assert d["ray"] == pytest.approx(2.0 * d["cage"], rel=1e-9), d


def test_g12_2_retopo_deviation_is_two_sided_so_a_dropped_fin_shows():
    d = run('''
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=0.5); plain = bpy.context.active_object; plain.name = "plain"
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=0.5); src = bpy.context.active_object; src.name = "src"
bm = bmesh.new(); bm.from_mesh(src.data)
top = max(bm.verts, key=lambda v: v.co.z)
fin = bm.verts.new((top.co.x, top.co.y, top.co.z + 0.02))                           # a 2 cm fin on the source the remesh lost
for e in list(top.link_edges)[:2]:
    bm.faces.new((top, e.other_vert(top), fin))
bm.to_mesh(src.data); bm.free()
from mixar.modules.lampway_tools.features import common as CM
rep = CM.mesh_report(plain, ref=src)
res({k: rep.get(k) for k in ("max_deviation", "from_source_max", "to_source_max")})
''')
    assert d["from_source_max"] is not None and d["from_source_max"] >= 0.019, d
    assert d["to_source_max"] < 0.005, d


def test_g10_4_silhouette_masks_are_compared_at_their_true_aspect(goldens):
    e = J(goldens, "C11_proportion/expected.json")["silhouette_aspect"]
    d = run('''
import numpy as np
from mixar.modules.lampway_tools.features import silhouette as SI
A = np.zeros((300, 300), bool); A[100:200, 50:250] = True
B = np.zeros((300, 300), bool); B[100:200, 100:200] = True
fa, fb = SI._fit_pair(A, B, 128)
res({"iou": SI._iou(fa, fb), "self": SI._iou(*SI._fit_pair(A, A, 128))})
''')
    assert d["iou"] == pytest.approx(e["iou_aspect_preserved"], abs=0.02) and abs(d["self"] - 1.0) < 1e-9, d


def test_g10_4_the_pure_true_aspect_fit_and_its_falsifier(goldens):
    from mixar.modules.lampway_tools import canon_geom as G
    e = J(goldens, "C11_proportion/expected.json")["silhouette_aspect"]
    A = np.zeros((300, 300), bool)
    A[100:200, 50:250] = True
    B = np.zeros((300, 300), bool)
    B[100:200, 100:200] = True
    assert G.mask_iou(*G.fit_masks_true_aspect(A, B, 128)) == pytest.approx(e["iou_aspect_preserved"], abs=0.02)

    def crop_stretch(m, size=128):
        ys, xs = np.nonzero(m)
        c = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        return c[np.ix_((np.arange(size) * c.shape[0] / size).astype(int), (np.arange(size) * c.shape[1] / size).astype(int))]
    assert G.mask_iou(crop_stretch(A), crop_stretch(B)) == pytest.approx(e["iou_crop_and_stretch_to_square"], abs=1e-9)
