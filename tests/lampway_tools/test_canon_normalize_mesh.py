# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""N3 (specs/canon/normalization contracts/normalize_mesh.md): lampway_normalize_mesh and the landings that call it.

A raw mesh becomes a canonical `mesh` (metres, +Z up, front -Y, transform applied, the scale STATE recorded, a generated mesh
welded, source face ids written, the pivot at the bounding box's bottom centre, stamped `lw_canon`) with its receipt - or a refusal
naming what could not be decided. Fixtures are synthetic: a "nosed" box whose nose marks its front, exported by Blender itself."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402

# A 0.2 x 0.1 x 0.3 box with a 5 cm nose on its +X face (Tripo's front after Blender's glTF import, canon 01 B), exported as GLB.
FIXTURE = r'''
import json
from mixar.modules.lampway_tools import canon_io
def nosed(name="raw_box"):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= 0.2; v.co.y *= 0.1; v.co.z *= 0.3; v.co.z += 0.15
    nose = [v for v in bm.verts if v.co.x > 0.09]
    for v in nose:
        if v.co.z > 0.2:
            v.co.x += 0.05
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for poly in me.polygons:
        poly.use_smooth = True          # smooth, no UVs: the exporter splits no vertex (a flat box splits every corner three ways)
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob
def export_glb(ob, name):
    for o in bpy.context.view_layer.objects: o.select_set(False)
    ob.select_set(True); bpy.context.view_layer.objects.active = ob
    p = os.path.join(root, name); bpy.ops.export_scene.gltf(filepath=p, use_selection=True); return p
def nose_dir(ob):
    P = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
    top = P[P[:, 2] > P[:, 2].max() - 1e-6]
    c = P.mean(0); t = top.mean(0) - c; t[2] = 0
    return (t / np.linalg.norm(t)).round(3).tolist()
import numpy as np
'''


def run(body):
    r = run_script(PRE + FIXTURE + body, timeout=400)
    assert r.rc == 0, r.out[-2000:]
    return r.results[-1]


def test_a_declared_turn_lands_the_nosed_box_facing_minus_y_in_metres_with_a_valid_document():
    d = run('''
src = nosed(); p = export_glb(src, "box.glb"); bpy.data.objects.remove(src)
out = api.normalize_mesh(input="box.glb", turn_deg=-90, generator="tripo_studio")
ob = bpy.data.objects[out["objects"][0]]
from mixar.modules.lampway_tools import canon_asset as CA
doc = json.loads(ob["lw_canon"])
res({"ok": out.get("ok"), "err": out.get("error"), "nose": nose_dir(ob), "matrix": [list(r) for r in ob.matrix_world], "errors": CA.validate(doc),
     "check": CA.check(doc, canon_io.facts(ob)), "scale": doc["scale"], "pivot": doc["pivot"], "decision": doc["conventions"]["frame_decision"],
     "min_z": min((ob.matrix_world @ v.co).z for v in ob.data.vertices), "receipt": out.get("receipt_path"), "hint": doc["raw"].get("path_hint")})
''')
    assert d["ok"], d["err"]
    assert d["nose"] == [0.0, -1.0, 0.0] and np.allclose(d["matrix"], np.eye(4)) and d["errors"] == [] and d["check"] == []
    assert d["scale"]["state"] == "generator_normalised" and d["scale"]["generator_norm"]["longest_side_m"] > 0.2
    assert d["pivot"]["rule"] == "bbox_bottom_centre" and abs(d["min_z"]) < 1e-6
    assert d["decision"] == {"kind": "declared", "evidence": {"method": "caller_turn", "value": -90}}
    assert d["hint"] == "box.glb" and d["receipt"].startswith("canon/receipts/")


def test_the_frame_is_never_guessed_no_turn_and_no_plate_is_refused():
    d = run('''
src = nosed(); export_glb(src, "box.glb"); bpy.data.objects.remove(src)
out = api.normalize_mesh(input="box.glb")
res({"ok": out.get("ok"), "err": out.get("error")})
''')
    assert not d["ok"] and "frame undecided" in d["err"] and "turn_deg" in d["err"]


def test_a_plate_needs_the_facing_margin_nobody_has_set_yet():
    d = run('''
src = nosed(); export_glb(src, "box.glb"); bpy.data.objects.remove(src)
im = bpy.data.images.new("plate", 8, 8); im.filepath_raw = os.path.join(root, "front.png"); im.file_format = "PNG"; im.save()
out = api.normalize_mesh(input="box.glb", plate="front.png")
res({"ok": out.get("ok"), "err": out.get("error")})
''')
    assert not d["ok"] and "facing_margin" in d["err"]


def test_the_turn_is_recorded_and_reversible_to_the_raw_positions():
    d = run('''
src = nosed(); export_glb(src, "box.glb"); bpy.data.objects.remove(src)
r = canon_io.import_raw(os.path.join(root, "box.glb")); raw = bpy.data.objects[r["objects"][0]]
P0 = np.array([(raw.matrix_world @ v.co)[:] for v in raw.data.vertices])
out = api.normalize_mesh(input=raw.name, turn_deg=-90, generator="tripo_studio", weld="never")      # a weld would renumber vertices
ob = bpy.data.objects[out["objects"][0]]
doc = json.loads(ob["lw_canon"]); A = np.array(doc["conventions"]["axis_map"]); off = np.array(doc["pivot"]["offset_m"])
P1 = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
back = (P1 - off) @ np.linalg.inv(A).T
res({"err": float(np.abs(back - P0).max()), "same_object": ob.name == raw.name})
''')
    assert d["err"] < 1e-6 and d["same_object"]


def test_a_generated_mesh_is_welded_so_its_seam_split_islands_are_one_shell_and_its_uv_islands_stay():
    d = run('''
bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=0.3, calc_uvs=True)
seam = [e for e in bm.edges if abs(e.verts[0].co.x) < 1e-6 and abs(e.verts[1].co.x) < 1e-6]
bmesh.ops.split_edges(bm, edges=seam)
me = bpy.data.meshes.new("split"); bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("split", me); bpy.context.scene.collection.objects.link(ob); ob["lw_raw"] = json.dumps({"sha256": "0" * 64, "container": "glb"})
n0 = len(me.vertices)
out = api.normalize_mesh(input="split", turn_deg=0, generator="tripo_studio")
doc = json.loads(bpy.data.objects[out["objects"][0]]["lw_canon"])
res({"ok": out.get("ok"), "err": out.get("error"), "topo": doc["body"]["topology"], "uv": doc["body"]["uv_sets"], "n0": n0,
     "face_ids": sorted(set(a.value for a in bpy.data.objects[out["objects"][0]].data.attributes["lw_source_face"].data))[:3]})
''')
    assert d["ok"], d["err"]
    t = d["topo"]
    assert t["welded"] and t["weld"]["rule"] == "position" and t["weld"]["vertices_merged"] > 0 and t["shells"] == 1 and t["split_by_uv_seam_in_raw"]
    assert d["face_ids"] == [0, 1, 2]


def test_a_flat_shaded_box_exported_split_at_every_corner_is_refused_by_the_5_percent_guard():
    # the ruled guard (D5) refuses a low-poly hard-surface export: 16 of its 24 vertices are corner duplicates
    d = run('''
src = nosed()
for poly in src.data.polygons: poly.use_smooth = False
export_glb(src, "flat.glb"); bpy.data.objects.remove(src)
out = api.normalize_mesh(input="flat.glb", turn_deg=-90, generator="tripo_studio")
res({"ok": out.get("ok"), "err": out.get("error"), "left_raw": [("lw_raw" in o, "lw_canon" in o) for o in bpy.data.objects if o.type == "MESH"]})
''')
    assert not d["ok"] and "16 of 24" in d["err"] and d["left_raw"] == [[True, False]]


def test_a_weld_that_would_merge_more_than_5_percent_is_refused():
    d = run('''
bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=20, y_segments=20, size=0.001)
me = bpy.data.meshes.new("dense"); bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("dense", me); bpy.context.scene.collection.objects.link(ob)
out = api.normalize_mesh(input="dense", turn_deg=0, generator="tripo_studio", weld_distance_m=1e-3)
res({"ok": out.get("ok"), "err": out.get("error")})
''')
    assert not d["ok"] and "weld" in d["err"] and "weld_distance_m" in d["err"]


def test_real_scale_is_refused_without_evidence():
    d = run('''
src = nosed(); export_glb(src, "box.glb"); bpy.data.objects.remove(src)
a = api.normalize_mesh(input="box.glb", turn_deg=-90, generator="tripo_studio", want_scale="real")
res({"ok": a.get("ok"), "err": a.get("error")})
''')
    assert not d["ok"] and "scale unknown" in d["err"]


def test_normalizing_a_canonical_object_again_changes_nothing():
    d = run('''
src = nosed(); export_glb(src, "box.glb"); bpy.data.objects.remove(src)
a = api.normalize_mesh(input="box.glb", turn_deg=-90, generator="tripo_studio")
ob = a["objects"][0]; h = json.loads(bpy.data.objects[ob]["lw_canon"])["body"]["geometry_sha256"]
b = api.normalize_mesh(input=ob, turn_deg=-90, generator="tripo_studio")
res({"unchanged": b.get("unchanged"), "h2": json.loads(bpy.data.objects[ob]["lw_canon"])["body"]["geometry_sha256"], "h": h})
''')
    assert d["unchanged"] is True and d["h"] == d["h2"]


def test_the_same_raw_bytes_and_decisions_give_byte_identical_documents():
    d = run('''
src = nosed(); export_glb(src, "box.glb"); bpy.data.objects.remove(src)
a = api.normalize_mesh(input="box.glb", turn_deg=-90, generator="tripo_studio")
b = api.normalize_mesh(input="box.glb", turn_deg=-90, generator="tripo_studio")
res({"a": bpy.data.objects[a["objects"][0]]["lw_canon"], "b": bpy.data.objects[b["objects"][0]]["lw_canon"]})
''')
    assert d["a"] == d["b"]


def test_a_skinned_mesh_is_sent_to_the_rig_normalizer():
    d = run('''
arm = armature(); ob = tube("skinned"); weights(ob, arm, lambda c: {"spine_03": 1.0})
out = api.normalize_mesh(input="skinned", turn_deg=0)
res({"ok": out.get("ok"), "err": out.get("error")})
''')
    assert not d["ok"] and "normalize_rigged" in d["err"]


def test_the_studio_landing_normalizes_with_a_declared_turn_and_lands_raw_without_one():
    d = run('''
from mixar.modules.lampway_tools import studio_landing as SL
src = nosed(); p = export_glb(src, "box.glb"); bpy.data.objects.remove(src)
a = SL.import_file(p, prefix="job1_", turn_deg=-90, generator="tripo_studio")
oa = bpy.data.objects[a["objects"][0]]
b = SL.import_file(p, prefix="job2_")
ob = bpy.data.objects[b["objects"][0]]
res({"a_canon": "lw_canon" in oa, "a_nose": nose_dir(oa), "a_note": a.get("normalize"), "b_canon": "lw_canon" in ob, "b_raw": "lw_raw" in ob,
     "b_note": b.get("normalize"), "a_coll": a["collection"]})
''')
    assert d["a_canon"] and d["a_nose"] == [0.0, -1.0, 0.0] and d["a_coll"] == "Studio"
    assert not d["b_canon"] and d["b_raw"] and "frame undecided" in d["b_note"]


def test_shape_keys_ride_the_normalization_with_the_basis():
    """A mesh with shape keys, turned and moved: every key is transformed with the basis (Mesh.transform leaves keys behind unless asked),
    so a key's offset from the basis is the same vector turned, never a key stranded in the raw frame."""
    r = run_script(PRE + '''
import math
from mixar.modules.lampway_tools.features import normalize as N
bm = bmesh.new(); bmesh.ops.create_cube(bm, size=0.2)
me = bpy.data.meshes.new("head"); bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("head", me); bpy.context.scene.collection.objects.link(ob)
ob.location = (1.0, 2.0, 3.0)
ob.shape_key_add(name="Basis"); k = ob.shape_key_add(name="jawOpen")
for v in k.data: v.co.x += 0.05                                                   # the key moves every vertex 5 cm along raw +X
N.normalize_object(ob, turn_deg=-90, generator="captain_authored")
kb = ob.data.shape_keys.key_blocks
d = [(a.co - b.co)[:] for a, b in zip(kb["jawOpen"].data, kb["Basis"].data)]
dv = [(a.co - b.co).length for a, b in zip(kb["Basis"].data, ob.data.vertices)]
res({"delta": d[0], "basis_vs_mesh": max(dv)})
''', timeout=180)
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert d["basis_vs_mesh"] < 1e-6, d                                    # the basis key is where the mesh is
    assert abs(d["delta"][1] + 0.05) < 1e-6 and abs(d["delta"][0]) < 1e-6, d   # raw +X turned -90 deg about Z is -Y


def test_the_object_reads_its_new_dimensions_at_once():
    """Normalization leaves the scene evaluated: a tool reading ob.dimensions right after it sees the applied transform (it read the
    raw mesh's local size - a 2x-scaled 0.3 m box measured 0.3, so scale_to_measure scaled it to 0.64 m for a 0.32 m target)."""
    r = run_script(PRE + '''
from mixar.modules.lampway_tools.features import normalize as N
bm = bmesh.new(); bmesh.ops.create_cube(bm, size=0.3)
me = bpy.data.meshes.new("helm"); bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("helm", me); bpy.context.scene.collection.objects.link(ob)
ob.scale = (2.0, 2.0, 2.0); bpy.context.view_layer.update()
N.normalize_object(ob, turn_deg=0, generator="lampway_tool", pivot="source_origin")
res({"dims": list(ob.dimensions), "scale": list(ob.scale)})
''', timeout=180)
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert d["scale"] == [1.0, 1.0, 1.0] and max(abs(x - 0.6) for x in d["dims"]) < 1e-6, d
