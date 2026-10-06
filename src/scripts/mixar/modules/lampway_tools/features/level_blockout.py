# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""level_blockout: from a reference annotation to a primitive blockout at real gameplay scale in named sets, then traversal_check, before any art is imported
or generated (specs/wiki/level_blockout.md).

The layout's units become metres through the scale anchor (``{object: <a primitive's name>, length_m}``: that primitive's longest side is length_m), else
they are metres already. Primitives (box | ramp | stair; ``at`` is the centre of their bounding box, ``size`` its extent) go into the collections
``<name>_ground``, ``_route``, ``_obstacles``, ``_landmarks`` under ``<name>``; the route is also a polyline ``<name>_route_path`` (edges only: nothing
walkable). A stair's riser is the largest that fits under 0.9 x max_step_m. Three fixed cameras: a top orthographic view and the views from the start and
from the goal. Nothing is deleted; a blockout name already in use is refused. Reading a reference image and PCG rules are not here (the agent's vision
model proposes the annotation; PCG is an engine-side action)."""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import common as C
from . import traversal as TR

SETS = ("ground", "route", "obstacles", "landmarks")
KINDS = ("box", "ramp", "stair")


def _mesh(name, build):
    bm = bmesh.new()
    build(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def _box(bm, lo, hi):
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((lo + hi) / 2) @ Matrix.Diagonal((*(hi - lo), 1.0)))


def _ramp(bm, lo, hi):
    v = [bm.verts.new(p) for p in ((lo.x, lo.y, lo.z), (hi.x, lo.y, hi.z), (hi.x, hi.y, hi.z), (lo.x, hi.y, lo.z), (hi.x, lo.y, lo.z), (hi.x, hi.y, lo.z))]
    for f in ((0, 1, 2, 3), (0, 4, 1), (3, 2, 5), (1, 4, 5, 2), (0, 3, 5, 4)):
        bm.faces.new([v[i] for i in f])


def _stair(bm, lo, hi, riser):
    n = max(1, math.ceil((hi.z - lo.z) / riser))
    run = (hi.x - lo.x) / n
    for k in range(n):
        _box(bm, Vector((lo.x + k * run, lo.y, lo.z)), Vector((hi.x, hi.y, lo.z + (hi.z - lo.z) * (k + 1) / n)))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)


def _scale(layout, prims):
    anchor = layout.get("scale_anchor")
    if not anchor:
        return 1.0, "metres (no scale anchor)"
    named = {p.get("name"): p for p in prims if p.get("name")}
    if anchor.get("object") not in named or not isinstance(anchor.get("length_m"), (int, float)) or anchor["length_m"] <= 0:
        raise C.FeatureError(f"scale_anchor is {{object: <a primitive's name>, length_m}}; the named primitives are {sorted(named)}")
    units = max(float(x) for x in named[anchor["object"]]["size"])
    return round(float(anchor["length_m"]) / units, 9), f"{anchor['object']} is {anchor['length_m']} m ({units:g} layout units)"


def level_blockout(layout, player=None, primitives=None, views=3, name="blockout"):
    try:
        p = TR._player(player)
    except C.FeatureError:
        raise C.FeatureError("project dimensions are required: the capsule decides what is traversable (player: " + ", ".join(TR.KEYS) + ")") from None
    if abs(bpy.context.scene.unit_settings.scale_length - 1.0) > 1e-9 or bpy.context.scene.unit_settings.system not in ("METRIC", "NONE"):
        raise C.FeatureError("the scene is not in real-world metres (unit scale 1.0): set the units first (scale_to_measure), then build the blockout")
    if not isinstance(name, str) or not name.replace("_", "").isalnum():
        raise C.FeatureError("name is letters, digits and _")
    if bpy.data.collections.get(name) is not None:
        raise C.FeatureError(f"a blockout named {name!r} exists: pick another name (nothing is replaced)")
    lay = layout if isinstance(layout, dict) else {}
    if not (lay.get("start") and lay.get("goal")):
        raise C.FeatureError("layout needs start and goal ([x, y, z]); route is the points between them")
    prims = list(primitives or [])
    for q in prims:
        if q.get("set") not in SETS:
            raise C.FeatureError(f"a primitive's set is one of {', '.join(SETS)} (got {q.get('set')!r})")
        if q.get("kind") not in KINDS:
            raise C.FeatureError(f"a primitive's kind is box | ramp | stair (got {q.get('kind')!r})")
        if not (isinstance(q.get("size"), list) and len(q["size"]) == 3 and all(float(x) > 0 for x in q["size"]) and isinstance(q.get("at"), list) and len(q["at"]) == 3):
            raise C.FeatureError("a primitive has size [x, y, z] (positive) and at [x, y, z] (its centre)")
    if int(views) != 3:
        raise C.FeatureError("views is 3 (top, from the start, from the goal)")
    f, source = _scale(lay, prims)
    S = lambda v: Vector([float(x) * f for x in v])  # noqa: E731
    root = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(root)
    colls = {}
    for s in SETS:
        colls[s] = bpy.data.collections.new(f"{name}_{s}")
        root.children.link(colls[s])
    made = []
    for i, q in enumerate(prims):
        size, at = S(q["size"]), S(q["at"])
        lo, hi = at - size / 2, at + size / 2
        oname = f"{name}_{q['name']}" if q.get("name") else f"{name}_{q['set']}_{q['kind']}_{i:02d}"
        if q["kind"] == "box":
            ob = _mesh(oname, lambda bm: _box(bm, lo, hi))
        elif q["kind"] == "ramp":
            ob = _mesh(oname, lambda bm: _ramp(bm, lo, hi))
        else:
            ob = _mesh(oname, lambda bm: _stair(bm, lo, hi, 0.9 * p["max_step_m"]))
        colls[q["set"]].objects.link(ob)
        made.append(ob.name)
    pts = [S(lay["start"])] + [S(r) for r in lay.get("route") or []] + [S(lay["goal"])]
    me = bpy.data.meshes.new(f"{name}_route_path")
    me.from_pydata([tuple(v) for v in pts], [(k, k + 1) for k in range(len(pts) - 1)], [])
    path = bpy.data.objects.new(f"{name}_route_path", me)
    colls["route"].objects.link(path)
    cams = _cameras(name, root, pts)
    bpy.context.view_layer.update()
    trav = TR.traversal_check([list(v) for v in pts], name, player)
    return {"collections": {s: f"{name}_{s}" for s in SETS}, "objects": made, "cameras": cams, "scale": {"factor": f, "source": source},
            "traversal": trav, "note": "a composition and playability blockout: replace one family of props at a time, keeping generation and placement as separate receipts"}


def _cameras(name, root, pts):
    lo = Vector([min(v[i] for v in pts) for i in range(3)])
    hi = Vector([max(v[i] for v in pts) for i in range(3)])
    centre, span = (lo + hi) / 2, max((hi - lo).length, 1.0)
    out = []
    specs = [("ortho", centre + Vector((0, 0, span * 2)), centre),
             ("persp", pts[0] + (pts[0] - pts[-1]).normalized() * 3 + Vector((0, 0, 1.7)), pts[-1]),
             ("persp", pts[-1] + (pts[-1] - pts[0]).normalized() * 3 + Vector((0, 0, 1.7)), pts[0])]
    for k, (kind, loc, look) in enumerate(specs, start=1):
        data = bpy.data.cameras.new(f"{name}_cam{k}")
        if kind == "ortho":
            data.type, data.ortho_scale = "ORTHO", span * 1.3
        cam = bpy.data.objects.new(f"{name}_cam{k}", data)
        cam.location = loc
        d = (look - loc)
        cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler() if d.length > 1e-9 else (0, 0, 0)
        root.objects.link(cam)
        out.append(cam.name)
    return out
