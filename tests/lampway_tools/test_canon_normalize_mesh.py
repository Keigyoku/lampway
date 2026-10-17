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


def test_an_empty_plate_is_refused_with_the_adopted_facing_margin_and_no_import_leaks():
    d = run('''
from mixar.modules.lampway_tools import canon_asset as CA
src = nosed(); export_glb(src, "box.glb"); bpy.data.objects.remove(src)
im = bpy.data.images.new("plate", 8, 8); im.filepath_raw = os.path.join(root, "front.png"); im.file_format = "PNG"; im.save()
before = canon_io.snapshot_ids()
out = api.normalize_mesh(input="box.glb", plate="front.png")
res({"ok": out.get("ok"), "err": out.get("error"), "margin": CA.SETTINGS["facing_margin"]["value"],
     "unchanged": canon_io.snapshot_ids() == before})
''')
    assert d["margin"] == .05
    assert not d["ok"] and "Front plate has no silhouette" in d["err"]
    assert d["unchanged"]


def test_an_approved_plate_uses_the_adopted_margin_without_an_override():
    from test_canon_normalize_facing import FACING

    r = run_script(PRE + FACING + '''
result = api.normalize_mesh(input="raw", plate=plate, generator="captain_authored", weld="never")
assert result.get("ok"), result
doc = json.loads(raw["lw_canon"])
res({"turn": doc["conventions"]["turn_deg"], "decision": doc["conventions"]["frame_decision"]})
''', timeout=300)
    assert r.rc == 0, r.out[-2500:]
    d = r.results[-1]
    assert d["turn"] == -90.0
    assert d["decision"]["kind"] == "measured"
    evidence = d["decision"]["evidence"]
    assert evidence["margin"] == .05
    assert evidence["value"] > .99
    assert evidence["value"] - evidence["second_best"] >= evidence["margin"]


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
    # it used to pin the opposite (the refused import left behind raw, `lw_raw`): audit F5 rules a refusal leaves the scene as it was
    assert not d["ok"] and "16 of 24" in d["err"] and d["left_raw"] == []


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


SCENE_PRINT = r'''
def scene_print():
    """every ID datablock the file holds, by kind and name: a refusal must leave this exactly as it was (audit F5)"""
    kinds = ("objects", "meshes", "materials", "images", "textures", "node_groups", "collections", "armatures", "actions", "cameras", "lights", "curves")
    return {k: sorted(x.name for x in getattr(bpy.data, k)) for k in kinds}
def textured(ob):
    m = bpy.data.materials.new("boxmat"); m.use_nodes = True
    im = bpy.data.images.new("boxtex", 8, 8); im.filepath_raw = os.path.join(root, "boxtex.png"); im.file_format = "PNG"; im.save()
    t = m.node_tree.nodes.new("ShaderNodeTexImage"); t.image = im
    m.node_tree.links.new(t.outputs["Color"], m.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    ob.data.materials.append(m)
    return ob
'''


def test_a_refused_import_leaves_the_scene_exactly_as_it_was_and_a_retry_gets_the_plain_names():
    """Audit F5 (specs/bugs/2026-10-06-cloud-audit-wave5.md): six refused file normalizations took a scene from 3 to 14 objects and the
    retries then made `.001` copies. A refused import removes EVERYTHING it brought in - objects, meshes, materials, images - and the
    scene's datablocks are exactly what they were; the accepted retry then lands under the file's own names."""
    d = run(SCENE_PRINT + '''
src = textured(nosed()); export_glb(src, "box.glb")
for x in (src, ): bpy.data.objects.remove(x)
for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
    for x in list(coll):
        if x.users == 0: coll.remove(x)
keep = nosed("bystander")                                   # something of the user's that must survive untouched
before = scene_print()
refusals = [api.normalize_mesh(input="box.glb") for _ in range(3)]
after = scene_print()
ok = api.normalize_mesh(input="box.glb", turn_deg=-90, generator="tripo_studio")
res({"refused": [r.get("ok") for r in refusals], "errors": [r.get("error") for r in refusals], "before": before, "after": after,
     "ok": ok.get("ok"), "names": ok.get("objects")})
''')
    assert d["refused"] == [False, False, False] and all("frame undecided" in e for e in d["errors"]), d["errors"]
    diff = {k: (d["before"][k], d["after"][k]) for k in d["before"] if d["before"][k] != d["after"][k]}
    assert not diff, diff
    assert d["ok"] and not any(".0" in n for n in d["names"]), d["names"]


def test_a_refused_scene_object_is_left_exactly_as_it_was():
    """The object form of the same rule: a refusal (here the frame undecided, and a weld over the 5 % guard) changes nothing."""
    d = run(SCENE_PRINT + '''
import hashlib
def sig(o):
    co = [round(c, 9) for v in o.data.vertices for c in v.co]
    return {"n": len(o.data.vertices), "co": hashlib.sha256(json.dumps(co).encode()).hexdigest(), "mw": [round(x, 9) for r in o.matrix_world for x in r],
            "props": sorted(o.keys())}
ob = nosed("mine"); ob.location = (1.0, 2.0, 0.5); bpy.context.view_layer.update()
before, prints = sig(ob), scene_print()
a = api.normalize_mesh(input="mine")
b = api.normalize_mesh(input="mine", turn_deg=-90, generator="tripo_studio", weld_distance_m=0.5)
res({"a": a.get("ok"), "b": b.get("ok"), "b_err": b.get("error"), "same": sig(ob) == before, "prints": scene_print() == prints})
''')
    assert d["a"] is False and d["b"] is False, d
    assert d["same"] and d["prints"], d


def test_a_canonical_object_placed_by_a_pure_translation_stays_canonical_and_a_turn_or_scale_does_not():
    """Audit F11: at x = 2.2 m uv_check refused a normalized object ("object matrix is not the identity"). The stamp describes the
    asset's DATA (its frame, metres, geometry); a pure translation is a PLACEMENT of that asset in the scene and the door accepts it,
    reporting where it stands. A rotation or a scale changes the frame or the scale the stamp claims and is still refused, saying
    so plainly; an edit of the data is refused as before, placed or not (SCHEMA.md transform, DOOR.md the check)."""
    d = run('''
from mathutils import Matrix
from mixar.modules.lampway_tools import canon_door as CD, canon_io as CIO
src = nosed(); export_glb(src, "box.glb"); bpy.data.objects.remove(src)
name = api.normalize_mesh(input="box.glb", turn_deg=-90, generator="tripo_studio")["objects"][0]
ob = bpy.data.objects[name]
probe = api.tool(consumes={"object": api.Need(kind=("mesh",), scale=("real", "generator_normalised", "unknown"))})(lambda object: {"ran": object})
out = {}
ob.location = (2.2, -0.4, 0.3); bpy.context.view_layer.update()
out["moved"] = probe(object=name); out["placed_m"] = CIO.facts(ob).get("placement_m")
out["again"] = api.normalize_mesh(input=name, turn_deg=-90, generator="tripo_studio")
out["still_there"] = list(ob.location)
placed = ob.matrix_world.copy()          # the glTF importer leaves rotation_mode QUATERNION: set the matrix, never one channel
ob.matrix_world = placed @ Matrix.Rotation(math.radians(30), 4, "Z"); bpy.context.view_layer.update()
out["turned"] = probe(object=name)
ob.matrix_world = placed @ Matrix.Scale(1.1, 4); bpy.context.view_layer.update()
out["scaled"] = probe(object=name)
ob.matrix_world = placed; bpy.context.view_layer.update()
out["back"] = probe(object=name)
ob.data.vertices[0].co.z += 0.01; ob.data.update()
out["edited"] = probe(object=name)
res(out)
''')
    assert d["moved"]["ok"] and d["moved"]["ran"], d["moved"]
    assert d["placed_m"] == [2.2, -0.4, 0.3] or max(abs(a - b) for a, b in zip(d["placed_m"], [2.2, -0.4, 0.3])) < 1e-6, d["placed_m"]
    assert d["again"]["ok"] and d["again"]["unchanged"] is True and max(abs(a - b) for a, b in zip(d["still_there"], [2.2, -0.4, 0.3])) < 1e-6, d
    for k in ("turned", "scaled"):
        e = d[k]["error"].lower()
        assert d[k]["ok"] is False and "rotat" in e and "scale" in e and "undo" in e and "placement" in e, (k, d[k])
        assert not any("scale_to_measure" in h for h in d[k]["help"]), ("a scaled OBJECT is not a scale-STATE refusal", d[k]["help"])
    assert d["back"]["ok"], d["back"]
    assert d["edited"]["ok"] is False and "geometry_sha256 differs" in d["edited"]["error"], d["edited"]


def test_a_multipart_import_preserves_assembly_placement_under_one_turn_and_pivot():
    d = run('''
from pathlib import Path
from mixar.modules.lampway_tools import canon_asset as CA
parts = [nosed("lower"), nosed("upper")]
parts[0].location = (0.2, -0.4, 0.3)
parts[1].parent = parts[0]
parts[1].location = (0.5, 0.7, 1.2)
bpy.context.view_layer.update()
for o in bpy.context.view_layer.objects: o.select_set(o in parts)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.export_scene.gltf(filepath=os.path.join(root, "assembly.glb"), use_selection=True)
for o in parts: bpy.data.objects.remove(o, do_unlink=True)
imp = canon_io.import_raw(os.path.join(root, "assembly.glb"))
raw = [bpy.data.objects[n] for n in imp["objects"] if bpy.data.objects[n].type == "MESH"]
P0 = [np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in raw]
for o in raw: bpy.data.objects.remove(o, do_unlink=True)
out = api.normalize_mesh(input="assembly.glb", turn_deg=-90, generator="tripo_studio", weld="never")
assert out.get("ok"), out
objs = [bpy.data.objects[n] for n in out["objects"]]
P1 = [np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in objs]
A = np.array([[0., 1., 0.], [-1., 0., 0.], [0., 0., 1.]])
turned = np.concatenate(P0) @ A.T
lo, hi = turned.min(0), turned.max(0)
off = np.array([-(lo[0]+hi[0])/2, -(lo[1]+hi[1])/2, -lo[2]])
# Match intrinsic piece sizes; returned order need not follow importer order.
errors = [min(float(np.abs(p - (q @ A.T + off)).max()) for q in P0) for p in P1]
receipts = [json.loads((Path(root)/p).read_text()) for p in out["receipts"]]
res({"error": max(errors), "height": float((np.concatenate(P1).max(0)-np.concatenate(P1).min(0))[2]),
     "expected_height": float((turned.max(0)-turned.min(0))[2]), "receipts": receipts,
     "valid": all(not CA.check(json.loads(o["lw_canon"]), canon_io.facts(o)) for o in objs)})
''')
    assert d["error"] < 1e-6, d
    assert abs(d["height"] - d["expected_height"]) < 1e-6, d
    assert d["valid"]
    assert all(r["assembly"]["members"] == 2 for r in d["receipts"])


def test_a_multipart_plate_only_import_refuses_without_leaving_scene_ids():
    d = run(SCENE_PRINT + r'''
parts = [nosed("lower"), nosed("upper")]
parts[1].location = (0.0, 0.0, 0.8)
bpy.context.view_layer.update()
for o in bpy.context.view_layer.objects: o.select_set(o in parts)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.export_scene.gltf(filepath=os.path.join(root, "assembly.glb"), use_selection=True)
for o in parts: bpy.data.objects.remove(o, do_unlink=True)
before = scene_print()
out = api.normalize_mesh(input="assembly.glb", plate="front.png", generator="tripo_studio", weld="never")
res({"ok": out.get("ok"), "error": out.get("error"), "unchanged": before == scene_print()})
''')
    assert not d["ok"] and "shared turn_deg" in d["error"], d
    assert d["unchanged"], d


def test_an_animated_assembly_ancestor_refuses_before_mesh_mutation():
    d = run('''
from mixar.modules.lampway_tools.features import normalize as N
anchor = bpy.data.objects.new("moving_parent", None)
bpy.context.scene.collection.objects.link(anchor)
anchor.keyframe_insert(data_path="location", frame=1)
parts = [nosed("lower"), nosed("upper")]
for o in parts: o.parent = anchor
bpy.context.view_layer.update()
before = [canon_io.geometry_sha256(o) for o in parts]
try:
    N._normalize_all(parts, None, None, 0, "", "", "tripo_studio", "any", None, "never", None, root)
    error = ""
except N.C.FeatureError as exc:
    error = str(exc)
res({"error": error, "unchanged": before == [canon_io.geometry_sha256(o) for o in parts],
     "unstamped": all("lw_canon" not in o for o in parts)})
''')
    assert "static copy" in d["error"], d
    assert d["unchanged"] and d["unstamped"], d
