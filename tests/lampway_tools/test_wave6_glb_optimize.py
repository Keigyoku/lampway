# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""glb_optimize (specs/wiki/glb_optimize.md) in the real binary: a lighter GLB for web preview (Draco, WebP, a smaller texture) and the proof that shape, texture
and animation survived: re-imported and compared. The user's scene is untouched; the source file is never overwritten."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

MAKE_GLB = '''
def make_glb(rel):
    sc = bpy.data.scenes.new("mk")
    ob = sphere("ball", 0.5, subdiv=5)
    bpy.context.scene.collection.objects.unlink(ob); sc.collection.objects.link(ob)
    img = bpy.data.images.new("albedo", 512, 512)
    yy, xx = np.mgrid[0:512, 0:512]
    px = np.zeros((512, 512, 4), dtype=np.float32)
    px[..., 0] = (xx // 64) % 2; px[..., 1] = (yy // 64) % 2; px[..., 2] = 0.5; px[..., 3] = 1
    img.pixels = px.ravel()
    img.file_format = "PNG"; img.filepath_raw = os.path.join(root, "albedo.png"); img.save(); img.pack()
    mat = bpy.data.materials.new("mat"); mat.use_nodes = True
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage"); tex.image = img
    mat.node_tree.links.new(tex.outputs["Color"], mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    ob.data.materials.append(mat)
    bm = bmesh.new(); bm.from_mesh(ob.data); uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for l in f.loops:
            n = l.vert.co.normalized(); l[uv].uv = (0.5 + math.atan2(n.y, n.x) / (2 * math.pi), 0.5 + math.asin(max(-1, min(1, n.z))) / math.pi)
    bm.to_mesh(ob.data); bm.free()
    ob.location = (0, 0, 0); ob.keyframe_insert("location", frame=1)
    ob.location = (2, 0, 0); ob.keyframe_insert("location", frame=24)
    sc.frame_start, sc.frame_end = 1, 24
    with bpy.context.temp_override(scene=sc, view_layer=sc.view_layers[0]):
        bpy.ops.export_scene.gltf(filepath=os.path.join(root, rel), export_format="GLB", use_active_scene=True, export_animations=True)
    bpy.data.scenes.remove(sc)
    bpy.data.objects.remove(ob)
make_glb("in.glb")
user = sphere("user_obj", 0.2)
'''


def test_size_shrinks_and_vertices_stay_within_tolerance_and_the_texture_survives(tmp_path):
    d = one(go(tmp_path, MAKE_GLB + '''
res = call("glb_optimize", glb="in.glb", out="web/out.glb", mesh_compression="draco", texture_px=128, webp_quality=80)
print("RESULT", json.dumps({"res": res, "objects": sorted(o.name for o in bpy.data.objects), "scenes": [s.name for s in bpy.data.scenes],
                            "out": os.path.getsize(os.path.join(root, "web/out.glb")) if os.path.exists(os.path.join(root, "web/out.glb")) else 0}))
'''))
    res = d["res"]
    assert res["ok"], res
    assert res["bytes_after"] < res["bytes_before"] and res["bytes_after"] == d["out"]
    assert res["checks"]["vertex_deviation_rel"] < 0.005 and res["checks"]["texture_ssim"] > 0.8 and res["checks"]["texture_px_after"] == 128
    assert d["objects"] == ["user_obj"] and len(d["scenes"]) == 1                     # nothing imported is left behind


def test_animation_frames_preserved_and_reported_when_dropped(tmp_path):
    d = one(go(tmp_path, MAKE_GLB + '''
kept = call("glb_optimize", glb="in.glb", out="web/a.glb", mesh_compression="none", texture_px=256, webp_quality=90)
dropped = call("glb_optimize", glb="in.glb", out="web/b.glb", mesh_compression="none", texture_px=256, webp_quality=90, keep_animation=False)
print("RESULT", json.dumps({"kept": kept, "dropped": dropped}))
'''))
    assert d["kept"]["checks"]["animation_frames_equal"] is True and d["kept"]["checks"]["animations"] == {"before": 1, "after": 1}
    assert d["dropped"]["checks"]["animation_frames_equal"] is False and d["dropped"]["checks"]["animations"] == {"before": 1, "after": 0}


def test_refuses_inplace_outside_the_root_and_meshopt(tmp_path):
    d = one(go(tmp_path, MAKE_GLB + '''
inplace = call("glb_optimize", glb="in.glb", out="in.glb")
outside = call("glb_optimize", glb="in.glb", out="../x.glb")
meshopt = call("glb_optimize", glb="in.glb", out="web/m.glb", mesh_compression="meshopt")
quality = call("glb_optimize", glb="in.glb", out="web/q.glb", webp_quality=0)
print("RESULT", json.dumps({"inplace": inplace, "outside": outside, "meshopt": meshopt, "quality": quality}))
'''))
    assert d["inplace"]["ok"] is False and "out equals the input" in d["inplace"]["error"]
    assert d["outside"]["ok"] is False and "outside the project root" in d["outside"]["error"]
    assert d["meshopt"]["ok"] is False and "glTF Transform" in d["meshopt"]["error"]
    assert d["quality"]["ok"] is False and "1..100" in d["quality"]["error"]


def test_default_cube_context_and_failed_import_leave_all_ids_unchanged(tmp_path):
    from issue2_native import run_issue_case
    run_issue_case(tmp_path, '''
from mixar.modules.lampway_tools.features import glb_optimize as G
if os.environ.get('LAMPWAY_REVERT_GLB_CONTEXT'):
    import inspect
    source_code=inspect.getsource(G._import)
    start=source_code.index('        with bpy.context.temp_override')
    end=source_code.index('        new =',start)
    exec(source_code[:start]+'        canon_io.import_raw(path)'+chr(10)+source_code[end:],G.__dict__)
if os.environ.get('LAMPWAY_REVERT_GLB_CLEANUP'):
    G._cleanup=lambda scene,new:None
    canon_io.remove_new_ids=lambda before:None
source=os.path.join(root,'default.glb')
cube=bpy.data.objects['Cube'];assert any(c.name=='Collection' for c in cube.users_collection)
bpy.ops.object.select_all(action='DESELECT');cube.select_set(True);bpy.context.view_layer.objects.active=cube
bpy.ops.export_scene.gltf(filepath=source,export_format='GLB')
assert bpy.context.view_layer.objects.active is cube
before=ids()
r=call('glb_optimize',glb='default.glb',out='optimized.glb',mesh_compression='none')
assert r.get('ok'),r
# A context regression can export an empty document while returning ok.
# Check actual source/output payloads before considering scene cleanup.
import struct
from pathlib import Path
def mesh_vertex_counts(path):
    raw=Path(path).read_bytes();size,kind=struct.unpack_from('<II',raw,12)
    assert kind==0x4e4f534a
    document=json.loads(raw[20:20+size].decode('utf8'))
    return [document['accessors'][primitive['attributes']['POSITION']]['count']
            for mesh in document.get('meshes',[]) for primitive in mesh['primitives']]
source_counts=mesh_vertex_counts(source)
assert source_counts and mesh_vertex_counts(os.path.join(root,'optimized.glb'))==source_counts
assert ids()==before,(ids(),before)
original=canon_io.import_raw
def partial_failure(*args,**kw):
    original(*args,**kw)
    raise RuntimeError('planted post-import failure')
canon_io.import_raw=partial_failure
try:
    r=call('glb_optimize',glb='default.glb',out='failure.glb',mesh_compression='none')
    assert r['ok'] is False and 'planted' in r['error'],r
    assert ids()==before,(ids(),before)
finally:canon_io.import_raw=original
''')


def test_public_helmet_optimizer_receipt_on_default_scene(tmp_path):
    import os
    import pytest
    from issue2_native import run_issue_case
    asset_root=os.environ.get('LAMPWAY_MCP_ACCEPTANCE_ASSETS')
    if not asset_root or not (Path(asset_root)/'DamagedHelmet.glb').is_file():
        pytest.skip('pinned DamagedHelmet.glb required; real Tripo remains a separate acceptance input')
    run_issue_case(tmp_path, '''
import shutil,hashlib
shutil.copy2(ASSET,root+'/helmet.glb');before=ids();source_hash=canon_io.file_sha256(root+'/helmet.glb')
a=call('glb_optimize',glb='helmet.glb',out='a.glb',mesh_compression='none',texture_px=256)
assert a.get('ok') and a['checks']['vertex_deviation_rel']<.01,a
assert ids()==before,(ids(),before)
b=call('glb_optimize',glb='helmet.glb',out='b.glb',mesh_compression='none',texture_px=256)
assert b.get('ok') and b['checks']==a['checks'],(a,b)
assert ids()==before and canon_io.file_sha256(root+'/helmet.glb')==source_hash
from mixar.modules.lampway_tools.features import glb_optimize as G
original=G._pixels
G._pixels=lambda image: (_ for _ in ()).throw(RuntimeError('planted image comparison failure'))
try:
    refused=call('glb_optimize',glb='helmet.glb',out='refused.glb',mesh_compression='none',texture_px=256)
    assert not refused.get('ok') and 'planted image' in refused['error'],refused
    assert ids()==before,(ids(),before)
finally:G._pixels=original
print('GEOMETRY_RECEIPT '+json.dumps({'asset':'DamagedHelmet.glb','source_sha256':source_hash,'first':a,'second':b,'ids_unchanged':True}))
'''.replace('ASSET',repr(str(Path(asset_root)/'DamagedHelmet.glb'))))
