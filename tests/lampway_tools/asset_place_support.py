# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared fixtures for the asset_place tests (REAL binary): a library record shaped like ``AssetLibrary.get`` returns, and builders for the files
a placement reads (a GLB, a .blend holding a material / node group / action / armature, an image, a video)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE_AP = '''
import hashlib
SHA = "ab" * 32
def rec(kind, path, role="main", name="Greaves", subtype=None, stats=None, aid="asset-1", version=1, extra_files=(), license_id=None, attribution=None):
    files = [{"role": role, "ord": 0, "sha256": SHA, "bytes": os.path.getsize(path) if os.path.exists(path) else 0,
              "locations": [{"path": path, "storage": "external", "missing": 0}]}]
    for r, p in extra_files:
        files.append({"role": r, "ord": 0, "sha256": hashlib.sha256(r.encode()).hexdigest(), "bytes": 1, "locations": [{"path": p, "storage": "external", "missing": 0}]})
    return {"id": aid, "kind": kind, "subtype": subtype, "name": name, "version": version, "files": files, "stats": stats or {}, "license_id": license_id, "attribution": attribution}

def place(**kw):
    return call("asset_place", **kw)

def make_glb(path, name="Greaves", size=(0.3, 0.3, 1.0), scale=1.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (size[0] * scale, size[1] * scale, size[2] * scale)
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.select_all(action="DESELECT"); ob.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True)
    bpy.data.objects.remove(ob)
    for m in list(bpy.data.meshes):
        if m.users == 0:
            bpy.data.meshes.remove(m)

def world_box(ob):
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]

def write_blend(path, ids):
    bpy.data.libraries.write(path, set(ids), fake_user=True)
    for i in ids:
        coll = {bpy.types.Material: bpy.data.materials, bpy.types.ShaderNodeTree: bpy.data.node_groups, bpy.types.Action: bpy.data.actions,
                bpy.types.Object: bpy.data.objects}.get(type(i))
        if coll is not None:
            coll.remove(i)

def material(name, rgb=(0.8, 0.5, 0.2)):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*rgb, 1.0)
    return m

def node_group(name):
    g = bpy.data.node_groups.new(name, "ShaderNodeTree")
    g.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    out = g.nodes.new("NodeGroupOutput")
    bsdf = g.nodes.new("ShaderNodeBsdfDiffuse")
    g.links.new(bsdf.outputs[0], out.inputs[0])
    return g

def png(path, w=8, h=8, rgba=(0.5, 0.5, 1.0, 1.0), noncolor=False):
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=True, float_buffer=False)
    if noncolor:
        img.colorspace_settings.name = "Non-Color"
    img.pixels = list(rgba) * (w * h)
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)

def map_rec(subtype, path, aid=None, name=None):
    return rec("map", path, subtype=subtype, aid=aid or ("map-" + subtype), name=name or subtype)

def armature(name, bones=("hip", "spine")):
    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    for i, b in enumerate(bones):
        eb = arm.edit_bones.new(b)
        eb.head = (0, 0, i * 0.5); eb.tail = (0, 0, i * 0.5 + 0.4)
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob

def keyed_action(name, bones=("hip", "spine")):
    ob = armature("tmp_" + name, bones)
    for f in (1, 10):
        for b in bones:
            pb = ob.pose.bones[b]
            pb.rotation_mode = "XYZ"
            pb.rotation_euler = (0.1 * f, 0, 0)
            pb.keyframe_insert("rotation_euler", frame=f)
    act = ob.animation_data.action
    act.name = name
    ob.animation_data.action = None
    bpy.data.objects.remove(ob)
    return act

def video(path, frames=12):
    import subprocess
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=64x48:rate=24:duration={frames / 24}", "-pix_fmt", "yuv420p", path], check=True)
'''


def go(tmp_path, body, **kw):
    return run(tmp_path, PRE_AP + body, **kw)


def one(r):
    assert r.rc == 0, r.out[-3000:]
    return r.results[0]
