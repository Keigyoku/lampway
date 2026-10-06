# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Headless Blender work for a rented box (the Blender-offload job type of the compute wrapper): thumbnail, silhouette and ambient-occlusion bake. Run as `python offload.py <in> <out>` where `bpy` is the
PyPI module, or inside Blender after `--`. Reads <in>/params.json and the first model in <in>; writes images and result.json into <out>. Workbench for the images (no GPU, no Cycles, deterministic);
Cycles on the CPU only for the bake. Refuses what it cannot do: an unknown op or a missing model exits with a message, never a silent default."""
import json
import math
import os
import sys

import bpy

MODELS = (".glb", ".gltf", ".blend", ".obj")
# The normalization door's one-importer rule (canon_io) holds inside Lampway's own Blender. This script runs on a rented box under the
# PyPI bpy, where canon_io is not shipped; what it imports never lands in a Lampway scene (it returns images and numbers only).
CANON_FOREIGN_BLENDER = "runs on a rented box under the PyPI bpy; returns images and numbers, never datablocks"


def _args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if len(a) < 2:
        raise SystemExit("usage: offload.py <in> <out>")
    return a[0], a[1]


def _load(inp):
    path = next((os.path.join(inp, f) for f in sorted(os.listdir(inp)) if f.lower().endswith(MODELS)), None)
    if path is None:
        raise SystemExit(f"no model in {inp}: put a .glb, .gltf, .blend or .obj there")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        bpy.ops.wm.open_mainfile(filepath=path)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise SystemExit("no model: the file holds no mesh")
    return path, meshes


def _frame(meshes, yaw_deg=0.0, margin=1.15):
    pts = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]
    r = max(hi[i] - lo[i] for i in range(3)) / 2 * margin
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 2 * r
    bpy.context.scene.collection.objects.link(cam)
    yaw = math.radians(yaw_deg)
    cam.location = (c[0] + 10 * r * math.sin(yaw), c[1] - 10 * r * math.cos(yaw), c[2])
    cam.rotation_euler = (math.radians(90), 0, yaw)
    bpy.context.scene.camera = cam
    return len(pts)


def _render(path, size, transparent):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x = sc.render.resolution_y = int(size)
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = bool(transparent)
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "OBJECT"
    sc.view_settings.view_transform = "Standard"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def _alpha_coverage(path):
    img = bpy.data.images.load(path)
    px = list(img.pixels)
    a = px[3::4]
    cov = sum(1 for v in a if v > 0.5) / max(1, len(a))
    bpy.data.images.remove(img)
    return cov


def _bake_ao(meshes, out, size, samples):
    sc = bpy.context.scene
    ob = meshes[0]
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    img = bpy.data.images.new("ao", size, size, alpha=False)
    mat = bpy.data.materials.new("bake")
    mat.use_nodes = True
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = img
    mat.node_tree.nodes.active = node
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = int(samples)
    bpy.ops.object.bake(type="AO", margin=4)
    img.filepath_raw = os.path.join(out, "ao.png")
    img.file_format = "PNG"
    img.save()
    px = list(img.pixels)
    return sum(px[0::4]) / max(1, len(px[0::4]))


def main():
    inp, out = _args()
    os.makedirs(out, exist_ok=True)
    try:
        params = json.load(open(os.path.join(inp, "params.json")))
    except OSError:
        params = {}
    op, size = params.get("op", "thumbnail"), int(params.get("size", 256))
    if op not in ("thumbnail", "silhouette", "bake_ao"):
        raise SystemExit(f"unknown op {op!r}: thumbnail, silhouette or bake_ao")
    model, meshes = _load(inp)
    res = {"op": op, "model": os.path.basename(model), "vertices": sum(len(o.data.vertices) for o in meshes), "faces": sum(len(o.data.polygons) for o in meshes), "size": size}
    if op == "bake_ao":
        res.update(image="ao.png", mean_ao=_bake_ao(meshes, out, size, int(params.get("samples", 16))))
    else:
        _frame(meshes, float(params.get("yaw_deg", 0.0)))
        name = "thumbnail.png" if op == "thumbnail" else "silhouette.png"
        _render(os.path.join(out, name), size, op == "silhouette")
        res["image"] = name
        if op == "silhouette":
            res["alpha_coverage"] = _alpha_coverage(os.path.join(out, name))
    json.dump(res, open(os.path.join(out, "result.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
