# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The standard parity scenes (specs/ue_parity/contracts/ue_parity.md §4), built from ONE JSON description so both sides build
the same thing: ``describe`` returns the description (objects, lights, world, the camera per view with its UE field of view,
and the pixel regions each class is measured in); ``build`` makes it in a THROW-AWAY scene of the open file and ``discard``
removes every datablock it made. Never by hand, never in the captain's scene.

  chart    emissive patches: a 13-step grey ramp 0.005..16 and the 8 colour patches of the audit's tone probe; no lights (COL)
  furnace  dielectric and metal spheres at roughness 0.1 / 0.25 / 0.5 / 0.75 / 1.0 under a uniform sky of 1 (SHD, LGT-07)
  normals  a plane with DirectX dome bumps under one grazing sun from +Y (NRM)
  lights   a white Lambert plane and a grey sphere under one sun, one point and one spot (LGT)

Frames: the description is in lampway.body/1 (metres, +Z up); the camera looks along +Y from -Y. Region rectangles are
[x0, y0, x1, y1] pixels, row 0 at the top."""

import hashlib
import math

import bpy
import numpy as np

from . import parity_metrics as PM
from . import profile as PR

SCHEMA = "lampway.ue-parity-scene/1"
SCENES = ("chart", "furnace", "normals", "lights")
LENS_MM, SENSOR_MM, DIST_M = 50.0, 36.0, 4.0
VIEWS = {"front": 0.0, "three_quarter": 45.0, "grazing": 75.0}             # camera yaw about Z, degrees
GREYS = [float(round(v, 6)) for v in np.geomspace(0.005, 16.0, 13)]
PATCHES = [(0.8, 0.05, 0.05), (3.2, 0.2, 0.2), (0.05, 0.6, 0.05), (0.05, 0.05, 0.6), (0.40, 0.22, 0.15), (0.9, 0.6, 0.2), (3.6, 2.4, 0.8), (0.30, 0.15, 0.06)]
ROUGH = (0.1, 0.25, 0.5, 0.75, 1.0)
_MADE = {}


def _camera(view):
    yaw = math.radians(VIEWS[view])
    loc = (DIST_M * math.sin(yaw), -DIST_M * math.cos(yaw), 0.0)
    return {"location": [round(c, 6) for c in loc], "rotation_euler": [math.pi / 2, 0.0, yaw], "lens_mm": LENS_MM, "sensor_mm": SENSOR_MM,
            "ue_hfov_deg": PM.ue_hfov_deg(LENS_MM, SENSOR_MM)}


def _to_cam(cam, p):
    """A world point in the camera frame of project_blender: +X right, +Y forward, +Z up."""
    yaw = cam["rotation_euler"][2]
    d = np.asarray(p, float) - np.asarray(cam["location"], float)
    right, fwd = np.array([math.cos(yaw), math.sin(yaw), 0.0]), np.array([-math.sin(yaw), math.cos(yaw), 0.0])
    return [float(d @ right), float(d @ fwd), float(d[2])]


def _rect(cam, size, centre, half_m):
    x, y = PM.project_blender([_to_cam(cam, centre)], LENS_MM, SENSOR_MM, size, size)[0]
    h = half_m * (LENS_MM / SENSOR_MM * size) / _to_cam(cam, centre)[1]
    return [int(round(x - h)), int(round(y - h)), int(round(x + h)), int(round(y + h))]


def describe(scene, size=768, views=("front",)):
    if scene not in SCENES:
        raise ValueError(f"scene is one of {', '.join(SCENES)} (or armour:<export dir>)")
    unknown = [v for v in views if v not in VIEWS]
    if unknown:
        raise ValueError(f"views are {', '.join(VIEWS)}: not {unknown}")
    objects, lights, world = {}, [], {"color": [0.0, 0.0, 0.0], "strength": 1.0}
    anchors = {}
    if scene == "chart":
        vals = [[g, g, g] for g in GREYS] + [list(p) for p in PATCHES]
        objects["patches"] = [{"location": [round((i % 7 - 3) * 0.4, 6), 0.0, round((1 - i // 7) * 0.4, 6)], "size_m": 0.3, "emission": v}
                              for i, v in enumerate(vals)]
        anchors["COL"] = [(p["location"], 0.1) for p in objects["patches"]]
    elif scene == "furnace":
        world = {"color": [1.0, 1.0, 1.0], "strength": 1.0}
        objects["spheres"] = [{"location": [round((i - 2) * 0.6, 6), 0.0, z], "radius_m": 0.25, "metallic": m, "roughness": r,
                               "base_color": [1.0, 1.0, 1.0] if m else [0.5, 0.5, 0.5]}
                              for m, z in ((1.0, 0.35), (0.0, -0.35)) for i, r in enumerate(ROUGH)]
        anchors["SHD"] = [(s["location"], 0.1) for s in objects["spheres"]]
    elif scene == "normals":
        objects["plane"] = {"location": [0.0, 0.0, 0.0], "size_m": 2.4, "rotation_euler": [math.pi / 2, 0.0, 0.0], "bumps": 3, "texture": "dome_dx"}
        lights.append({"type": "SUN", "energy": 3.0, "direction": [0.0, 0.35, -1.0], "angle_rad": 0.0})
        anchors["NRM"] = [([(i - 1) * 0.8, -0.001, 0.0], 0.3) for i in range(3)]
    else:
        objects["plane"] = {"location": [0.0, 0.3, 0.0], "size_m": 2.6, "rotation_euler": [math.pi / 2, 0.0, 0.0], "base_color": [1.0, 1.0, 1.0]}
        objects["sphere"] = {"location": [0.0, -0.3, -0.6], "radius_m": 0.25, "base_color": [0.5, 0.5, 0.5]}
        lights += [{"type": "SUN", "energy": 1.0, "direction": [0.2, 1.0, -0.4], "angle_rad": 0.0},
                   {"type": "POINT", "energy": 100.0, "location": [-0.8, -0.6, 0.6], "radius_m": 0.0},
                   {"type": "SPOT", "energy": 200.0, "location": [0.8, -1.5, 0.8], "radius_m": 0.0, "spot_size_rad": math.radians(45.0), "spot_blend": 0.15,
                    "direction": [-0.4, 1.0, -0.4]}]
        anchors["LGT"] = [([x, 0.29, z], 0.0) for x in (-0.8, 0.0, 0.8) for z in (0.5, 0.1, -0.2)]
    cams = {v: _camera(v) for v in views}
    regions = {}
    for v, cam in cams.items():
        r = {}
        for cls, pts in anchors.items():
            if cls == "LGT":
                r[cls] = [[(a[0] + a[2]) // 2, (a[1] + a[3]) // 2] for a in (_rect(cam, size, p, 0.0) for p, _h in pts)]
            elif cls == "NRM":
                r[cls] = [{"rect": _rect(cam, size, p, h), "axis": "y"} for p, h in pts]
            else:
                r[cls] = [_rect(cam, size, p, h) for p, h in pts]
        regions[v] = r
    return {"schema": SCHEMA, "scene": scene, "size": size, "frame": "lampway.body/1", "objects": objects, "lights": lights, "world": world,
            "cameras": cams, "regions": regions}


def scene_sha256(desc) -> str:
    return hashlib.sha256(PR.canonical_json(desc).encode("utf-8")).hexdigest()


def _mat(name, **inputs):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    for k, v in inputs.items():
        b.inputs[k].default_value = v
    return m


def _emissive(name, rgb):
    peak = max(rgb) or 1.0
    m = _mat(name, **{"Base Color": (0, 0, 0, 1), "Specular IOR Level": 0.0, "Roughness": 1.0, "Emission Color": (*[c / peak for c in rgb], 1.0),
                      "Emission Strength": peak})
    return m


def _dome_dx(n=256, bumps=3):
    """A DirectX normal map of `bumps` domes in a row (green holds -y), generated, packed into the file."""
    v, u = (np.mgrid[0:n, 0:n] + 0.5) / n
    nx = np.zeros((n, n))
    ny = np.zeros((n, n))
    for i in range(bumps):
        cx = (i + 0.5) / bumps
        x, y = (u - cx) * bumps * 2.2, (v - 0.5) * bumps * 2.2
        inside = x * x + y * y < 1
        nx, ny = np.where(inside, x * 0.7, nx), np.where(inside, y * 0.7, ny)
    ln = np.sqrt(nx * nx + ny * ny + 1.0)
    img = bpy.data.images.new("LW_parity_dome_dx", n, n, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    rgba = np.dstack([nx / ln * 0.5 + 0.5, -ny / ln * 0.5 + 0.5, 1.0 / ln * 0.5 + 0.5, np.ones((n, n))])
    img.pixels.foreach_set(rgba.astype(np.float32).ravel())
    img.pack()
    return img


def build(desc, view):
    """Make the description in a new scene (EEVEE, float output, transparent film) and return it."""
    before = {k: set(getattr(bpy.data, k)) for k in ("objects", "meshes", "materials", "lights", "cameras", "worlds", "images")}
    sc = bpy.data.scenes.new(f"LW_UE_parity_{desc['scene']}_{view}")
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = sc.render.resolution_y = desc["size"]
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "Standard"
    sc.eevee.taa_render_samples = 16
    w = bpy.data.worlds.new(sc.name)
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*desc["world"]["color"], 1.0)
    bg.inputs["Strength"].default_value = desc["world"]["strength"]
    sc.world = w

    def link(ob):
        sc.collection.objects.link(ob)
        return ob

    def plane(name, size, loc, rot, mat):
        me = bpy.data.meshes.new(name)
        h = size / 2
        me.from_pydata([(-h, -h, 0), (h, -h, 0), (h, h, 0), (-h, h, 0)], [], [(0, 1, 2, 3)])
        uv = me.uv_layers.new(name="UVMap")
        for i, c in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
            uv.data[i].uv = c
        me.materials.append(mat)
        ob = link(bpy.data.objects.new(name, me))
        ob.location, ob.rotation_euler = loc, rot
        return ob

    def sphere(name, loc, r, mat):
        me = bpy.data.meshes.new(name)
        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=r)
        bm.to_mesh(me)
        bm.free()
        for p in me.polygons:
            p.use_smooth = True
        me.materials.append(mat)
        ob = link(bpy.data.objects.new(name, me))
        ob.location = loc
        return ob

    o = desc["objects"]
    for i, p in enumerate(o.get("patches", [])):
        plane(f"patch_{i:02d}", p["size_m"], p["location"], (math.pi / 2, 0, 0), _emissive(f"patch_{i:02d}", p["emission"]))
    for i, s in enumerate(o.get("spheres", [])):
        sphere(f"sphere_{i:02d}", s["location"], s["radius_m"], _mat(f"sphere_{i:02d}", **{"Base Color": (*s["base_color"], 1.0), "Metallic": s["metallic"],
                                                                                            "Roughness": s["roughness"]}))
    if "plane" in o:
        pl = o["plane"]
        m = _mat("parity_plane", **{"Base Color": (*pl.get("base_color", [0.8, 0.8, 0.8]), 1.0), "Roughness": 1.0, "Specular IOR Level": 0.0})
        if pl.get("texture") == "dome_dx":
            nt = m.node_tree
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = _dome_dx(bumps=pl["bumps"])
            nm = nt.nodes.new("ShaderNodeNormalMap")
            nm.convention = "DIRECTX"
            nt.links.new(tex.outputs["Color"], nm.inputs["Color"])
            nt.links.new(nm.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
        plane("parity_plane", pl["size_m"], pl["location"], pl["rotation_euler"], m)
    if "sphere" in o:
        s = o["sphere"]
        sphere("parity_sphere", s["location"], s["radius_m"], _mat("parity_sphere", **{"Base Color": (*s["base_color"], 1.0), "Roughness": 1.0, "Specular IOR Level": 0.0}))
    from mathutils import Vector
    for i, li in enumerate(desc["lights"]):
        ld = bpy.data.lights.new(f"parity_{li['type'].lower()}_{i}", li["type"])
        ld.energy = li["energy"]
        if li["type"] == "SUN":
            ld.angle = li["angle_rad"]
        else:
            ld.shadow_soft_size = li["radius_m"]
        if li["type"] == "SPOT":
            ld.spot_size, ld.spot_blend = li["spot_size_rad"], li["spot_blend"]
        ob = link(bpy.data.objects.new(ld.name, ld))
        ob.location = li.get("location", (0.0, 0.0, 0.0))
        if "direction" in li:
            ob.rotation_euler = Vector(li["direction"]).to_track_quat("-Z", "Y").to_euler()
    cam = desc["cameras"][view]
    cd = bpy.data.cameras.new(sc.name)
    cd.lens, cd.sensor_width, cd.sensor_fit = cam["lens_mm"], cam["sensor_mm"], "HORIZONTAL"
    co = link(bpy.data.objects.new(sc.name + "_camera", cd))
    co.location, co.rotation_euler = cam["location"], cam["rotation_euler"]
    sc.camera = co
    sc.view_layers[0].update()                                            # world matrices are stale until the scene is evaluated
    _MADE[sc.name] = {k: [x for x in getattr(bpy.data, k) if x not in before[k]] for k in before}
    return sc


def discard(sc):
    """Remove the throw-away scene and every datablock ``build`` made for it."""
    made = _MADE.pop(sc.name, {})
    bpy.data.scenes.remove(sc)
    for kind in ("objects", "meshes", "materials", "lights", "cameras", "worlds", "images"):
        coll = getattr(bpy.data, kind)
        for x in made.get(kind, []):
            try:
                coll.remove(x)
            except ReferenceError:
                pass
