# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""profile_revolve: a watertight lathe object from a 2D side profile (specs/wiki/profile_revolve.md), deterministically, for studs, rims, crests and bases.

The profile [[r, z], ...] lies in the XZ plane (r along +X) and is spun about Z with ``bmesh.ops.spin``. A full turn merges the seam; points ON the axis
(r = 0) are welded into poles, so a profile that starts and ends on the axis closes into a solid. ``bevel_m`` bevels the profile's corner vertices (two
segments) before the spin. Normals are recalculated outward. A partial angle leaves the cut open and says so (manifold false, open_edges)."""

import math

import bmesh
import bpy
from mathutils import Vector

from . import common as C

AXIS_EPS = 1e-9


def profile_revolve(profile, steps=64, angle_deg=360.0, bevel_m=0.0, name="lw_revolve"):
    pts = profile if isinstance(profile, list) else []
    if not 2 <= len(pts) <= 64 or any(not isinstance(p, (list, tuple)) or len(p) != 2 for p in pts):
        raise C.FeatureError("profile is 2..64 points [r, z]")
    if any(float(p[0]) < 0 for p in pts):
        raise C.FeatureError("the profile crosses the axis (a negative radius): keep r >= 0, points on the axis close the solid")
    if not 8 <= int(steps) <= 256:
        raise C.FeatureError("steps is 8..256")
    if not 1 <= float(angle_deg) <= 360:
        raise C.FeatureError("angle_deg is 1..360")
    if not 0 <= float(bevel_m) <= 0.05:
        raise C.FeatureError("bevel_m is 0..0.05")
    if not str(name or "").strip():
        raise C.FeatureError("name the object")
    bm = bmesh.new()
    verts = [bm.verts.new((float(r), 0.0, float(z))) for r, z in pts]
    edges = [bm.edges.new((a, b)) for a, b in zip(verts, verts[1:])]
    if float(bevel_m) > 0:
        corners = [v for v in verts[1:-1] if v.co.x > AXIS_EPS]
        if corners:
            bmesh.ops.bevel(bm, geom=corners, offset=float(bevel_m), segments=2, affect="VERTICES", profile=0.5)
    full = float(angle_deg) >= 360.0 - 1e-9
    geom = list(bm.verts) + list(bm.edges)
    bmesh.ops.spin(bm, geom=geom, cent=(0, 0, 0), axis=(0, 0, 1), angle=math.radians(float(angle_deg)), steps=int(steps), use_merge=full, use_duplicate=False)
    on_axis = [v for v in bm.verts if math.hypot(v.co.x, v.co.y) <= 1e-7]
    if on_axis:
        bmesh.ops.remove_doubles(bm, verts=on_axis, dist=1e-6)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-9)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    non_manifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    co = [v.co for v in me.vertices]
    lo = Vector([min(c[i] for c in co) for i in range(3)])
    hi = Vector([max(c[i] for c in co) for i in range(3)])
    return {"object": ob.name, "faces": len(me.polygons), "manifold": boundary == 0 and non_manifold == 0, "open_edges": boundary,
            "bounds": {"min": [round(x, 6) for x in lo], "max": [round(x, 6) for x in hi], "size": [round(x, 6) for x in hi - lo]}}
