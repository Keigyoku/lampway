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
