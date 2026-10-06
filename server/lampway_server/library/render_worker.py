"""The headless Blender side of asset_render (specs/asset_library/asset_render.md section 6, engines 2 and 3). Run ONLY as

    nice -n 15 <blender> -b --factory-startup --python render_worker.py -- <job.json>

by ``render.blender_command``: a separate process with a throw-away user config and the bridge port 0, so it can never be, or talk to, the user's live session.
It imports the input into an empty scene, frames it with the same recipe as the software path (front three-quarter view, 35 mm, the projected surface's bounding box
plus the margin, a neutral grey background), and writes PNG frames into the job's ``out_dir``. Workbench for meshes, EEVEE for material balls; never Cycles."""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def empty_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    return sc


def import_input(path: Path):
    before = set(bpy.data.objects)
    ext = path.suffix.lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif ext == ".blend":
        with bpy.data.libraries.load(str(path), link=False) as (src, dst):
            dst.objects = list(src.objects)
        for ob in dst.objects:
            if ob is not None:
                bpy.context.scene.collection.objects.link(ob)
    else:
        raise SystemExit(f"cannot import {ext}: glb, gltf, fbx, obj or blend")
    meshes =[ob for ob in set(bpy.data.objects) - before if ob.type == "MESH"]
    if not meshes:
        raise SystemExit(f"the importer made no mesh object from {path.name}: nothing to render (a glTF with no nodes shows nothing in Blender; the software path reads it)")
    return meshes


def decimate(meshes, target):
    tris = sum(sum(len(p.vertices) - 2 for p in ob.data.polygons) for ob in meshes)
    if target and tris > target:
        for ob in meshes:
            m = ob.modifiers.new("lw_preview_decimate", "DECIMATE")       # a preview-only modifier on a throw-away scene: never saved
            m.ratio = target / tris


def world_points(meshes, limit=30000):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for ob in meshes:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ob.matrix_world
        step = max(1, len(me.vertices) // max(1, limit // max(1, len(meshes))))
        pts += [mw @ me.vertices[i].co for i in range(0, len(me.vertices), step)]
        ev.to_mesh_clear()
    return pts


def camera_for(recipe, pts, yaws, size):
    """A perspective camera whose lens and shift frame the projected points of every yaw, like ``raster.frame_views``. glTF +Y up / +Z front is Blender +Z up / -Y front."""
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    centre, radius = (lo + hi) / 2, max((hi - lo).length / 2, 1e-6)
    az, el = math.radians(recipe["azimuth_deg"]), math.radians(recipe["elevation_deg"])
    d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    half = math.atan(recipe["sensor_mm"] / 2 / recipe["focal_mm"])
    eye = centre + d * (radius / math.sin(half))
    f = -d
    right = f.cross(Vector((0, 0, 1))).normalized()
    up = right.cross(f)
    us, vs = [], []
    for a in yaws:
        rot = Matrix.Rotation(a, 3, "Z")
        for p in pts:
            q = rot @ (p - centre) + centre - eye
            z = q.dot(f)
            us.append(q.dot(right) / z)
            vs.append(q.dot(up) / z)
    span = max(max(us) - min(us), max(vs) - min(vs), 1e-9)
    cam_data = bpy.data.cameras.new("lw_preview_cam")
    cam_data.sensor_fit, cam_data.sensor_width = "HORIZONTAL", recipe["sensor_mm"]
    cam_data.lens = recipe["sensor_mm"] * (1 - 2 * recipe["margin"]) / span
    cam_data.shift_x = (max(us) + min(us)) / 2 * cam_data.lens / recipe["sensor_mm"]
    cam_data.shift_y = (max(vs) + min(vs)) / 2 * cam_data.lens / recipe["sensor_mm"]
    cam_data.clip_start, cam_data.clip_end = radius * 0.01, radius * 100
    cam = bpy.data.objects.new("lw_preview_cam", cam_data)
    cam.matrix_world = Matrix.Translation(eye) @ f.to_track_quat("-Z", "Y").to_matrix().to_4x4()
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    return centre


def setup_render(sc, recipe, size, engine):
    r = sc.render
    r.engine = "BLENDER_EEVEE" if engine == "eevee" else "BLENDER_WORKBENCH"
    r.resolution_x = r.resolution_y = int(size)
    r.resolution_percentage = 100
    r.film_transparent = False
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    sc.view_settings.view_transform = "Standard"
    if sc.world is None:
        sc.world = bpy.data.worlds.new("lw_preview_world")
    grey = srgb_to_linear(recipe["background"][0] / 255.0)
    sc.world.color = (grey, grey, grey)                            # Workbench reads this
    bg = next((n for n in (sc.world.node_tree.nodes if sc.world.node_tree else ()) if n.type == "BACKGROUND"), None)
    if bg is not None:                                             # EEVEE reads the world's node tree
        bg.inputs["Color"].default_value = (grey, grey, grey, 1.0)
        bg.inputs["Strength"].default_value = 1.0
    if engine != "eevee":
        sh = sc.display.shading
        sh.light, sh.color_type = "STUDIO", "TEXTURE"
        sh.show_cavity = False


def turntable(job, meshes):
    sc = bpy.context.scene
    n = 1 if job["product"] == "thumb" else int(job["frames"])
    yaws = [2 * math.pi * i / n for i in range(n)]
    pivot = bpy.data.objects.new("lw_preview_pivot", None)
    sc.collection.objects.link(pivot)
    centre = camera_for(job["recipe"], world_points(meshes), yaws, job["size"])
    pivot.location = centre
    for ob in meshes:
        if ob.parent is None or ob.parent not in meshes:
            mw = ob.matrix_world.copy()
            ob.parent = pivot
            ob.matrix_world = mw
    setup_render(sc, job["recipe"], job["size"], job["engine"])
    for i, a in enumerate(yaws):
        pivot.rotation_euler = (0, 0, a)
        sc.render.filepath = str(Path(job["out_dir"]) / f"frame_{i:03d}.png")
        bpy.ops.render.render(write_still=True)


def ball(job):
    """A UV sphere with the job's material (from a .blend), a three-point rig, EEVEE, 64 samples."""
    sc = empty_scene()
    path = Path(job["input"])
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        want = job.get("material")
        dst.materials = [m for m in src.materials if want is None or m == want][:1]
    if not dst.materials or dst.materials[0] is None:
        raise SystemExit(f"no material {job.get('material') or ''} in {path.name}")
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1.0)
    sph = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    sph.data.materials.append(dst.materials[0])
    for name, loc, energy in (("key", (4, -4, 5), 800), ("fill", (-5, -3, 2), 250), ("rim", (0, 5, 4), 400)):
        ld = bpy.data.lights.new(f"lw_{name}", "AREA")
        ld.energy, ld.size = energy, 3
        lo = bpy.data.objects.new(f"lw_{name}", ld)
        lo.location = loc
        lo.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(lo)
    camera_for(job["recipe"], [Vector((x, y, z)) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], [0.0], job["size"])
    setup_render(sc, job["recipe"], job["size"], "eevee")
    sc.eevee.taa_render_samples = 64
    sc.render.filepath = str(Path(job["out_dir"]) / "frame_000.png")
    bpy.ops.render.render(write_still=True)


def main():
    job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text())
    if job["engine"] not in ("workbench", "eevee"):
        raise SystemExit("the worker renders workbench or eevee only (never Cycles)")
    if job["product"] == "ball":
        ball(job)
        return
    empty_scene()
    meshes = import_input(Path(job["input"]))
    decimate(meshes, job.get("decimate_to"))
    turntable(job, meshes)


main()
