# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_openings / opening_gasket: every cap a seed put across a limb, neck or waist opening gets a typed decision, keep | gasket | delete, logged append-only
(``<piece>/fit/decisions.jsonl``, question ``opening_decision``). A GASKET cuts the posed limb's cross-section plus the wear clearance into the cap plane, deletes the inside and forms a
COLLAR: a tubular flange running into the piece whose free edge ROLLS outward into a lip - the user's "manifold it" read as an engine exhaust / intake MANIFOLD PORT (a formed
collar with a rolled edge, not a raw cut hole). The collar depth (the flange length) is his number and unruled, so applying a gasket without one answers ``needs_decision``, and ``variants``
builds and renders three depths for him to pick. Metal is cut, never blended (no weights, no blend). Runs on the POSED body only: no pose, no gasket. The source object is never edited;
the result is ``<object>_openings``. A geometry step: it discards a studio texture on the changed faces (``texture_discard_ack``)."""

import hashlib
import json
import math
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector

from . import common as C

STAGES = ("detect", "propose", "rule", "apply", "variants", "check")
VERDICTS = ("keep", "gasket", "delete")
SUGGESTED_MM = [10, 20, 35]
CAP_NORMAL_DEG = 35.0


def _basis(n):
    n = Vector(n).normalized()
    a = Vector((1, 0, 0)) if abs(n.x) < 0.9 else Vector((0, 1, 0))
    u = n.cross(a).normalized()
    return u, n.cross(u).normalized()


def _bm(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    bm.faces.ensure_lookup_table()
    return bm


def _sig(ob) -> str:
    h = hashlib.sha256()
    for v in ob.data.vertices:
        h.update(np.array(v.co, dtype=np.float32).tobytes())
    for p in ob.data.polygons:
        h.update(np.array(p.vertices, dtype=np.int32).tobytes())
    return h.hexdigest()


# ------------------------------------------------------------------------------------------------ detect
def _cap_clusters(bm, axis, tol=1e-4):
    cos = math.cos(math.radians(CAP_NORMAL_DEG))
    n = Vector(axis).normalized()
    cand = [f for f in bm.faces if abs(f.normal.dot(n)) >= cos]
    pool, out = set(cand), []
    while pool:
        seed = pool.pop()
        d0 = seed.calc_center_median().dot(n)
        comp, stack = [seed], [seed]
        while stack:
            f = stack.pop()
            for e in f.edges:
                for nb in e.link_faces:
                    if nb in pool and abs(nb.calc_center_median().dot(n) - d0) < max(tol, 1e-3):
                        pool.discard(nb)
                        comp.append(nb)
                        stack.append(nb)
        out.append(comp)
    return out


def detect(ob, axis, min_area_frac=0.01):
    bm = _bm(ob)
    total = sum(f.calc_area() for f in bm.faces)
    n = Vector(axis).normalized()
    lo, hi = min(v.co.dot(n) for v in bm.verts), max(v.co.dot(n) for v in bm.verts)
    out = []
    for comp in _cap_clusters(bm, axis):
        area = sum(f.calc_area() for f in comp)
        d = float(np.mean([f.calc_center_median().dot(n) for f in comp]))
        if area < min_area_frac * total or not (abs(d - lo) < 0.02 * (hi - lo) or abs(d - hi) < 0.02 * (hi - lo)):
            continue
        cen = sum((f.calc_center_median() * f.calc_area() for f in comp), Vector()) / area
        rim = sum(e.calc_length() for f in comp for e in f.edges if any(nb not in comp for nb in e.link_faces))
        out.append({"id": "", "kind": "opening", "state": "capped", "axis": list(n), "plane_origin_m": [round(x, 6) for x in cen], "cap_faces": len(comp),
                    "cap_area_cm2": round(area * 1e4, 3), "rim_perimeter_cm": round(rim * 100, 3), "end": "low" if abs(d - lo) < abs(d - hi) else "high"})
    out.sort(key=lambda c: (c["end"] != "low", c["plane_origin_m"][2]))
    for i, c in enumerate(out):
        c["id"] = f"OP{i:03d}"
    bm.free()
    return out


def site_axis(armature, site):
    """(head, unit axis) of the POSED bone ``site``: its head and the line to the head of its next joint (canon 01 C.1 / 06 B.1)."""
    from ..canon_geom.bones import chain_ends, CONTINUATION
    from .normalize_rigged import canonical_helper_ends
    rig = C.need_object(armature, "ARMATURE")
    if site not in rig.pose.bones:
        raise C.FeatureError(f"no bone {site!r} in {armature!r}: the site is a bone of the posed body (upperarm_l, neck_01, calf_l, ...)")
    bpy.context.view_layer.update()
    W = rig.matrix_world
    heads = {pb.name: tuple(W @ pb.head) for pb in rig.pose.bones}
    parents = {pb.name: pb.parent.name if pb.parent else None for pb in rig.pose.bones}
    # Validate the rest stamp before transporting authored driver endpoints into
    # the pose. Drivers do not become anatomical directions at any pose.
    rest_helpers = canonical_helper_ends(rig)
    helpers = {}
    for name, end in rest_helpers.items():
        local = W.inverted() @ Vector(end)
        helpers[name] = tuple(W @ rig.pose.bones[name].matrix @ rig.data.bones[name].matrix_local.inverted() @ local)
    end = chain_ends(heads, parents, main_child=CONTINUATION, helper_ends=helpers)[site]
    h = Vector(heads[site])
    d = Vector(end) - h
    if d.length < 1e-9:
        raise C.FeatureError(f"bone {site!r} has no length to its next joint")
    return h, d.normalized()


def detect_site(ob, head, axis, min_area_frac=0.01):
    """canon 06 B.1: the caps of one SITE - clusters within CAP_NORMAL_DEG of the posed bone line that the line runs into (as the limb
    would push through them), wherever they sit on the piece, extreme or not."""
    from mathutils.bvhtree import BVHTree
    bm = _bm(ob)
    total = sum(f.calc_area() for f in bm.faces)
    n = Vector(axis).normalized()
    out = []
    for comp in _cap_clusters(bm, n):
        area = sum(f.calc_area() for f in comp)
        if area < min_area_frac * total:
            continue
        verts = sorted({v for f in comp for v in f.verts}, key=lambda v: v.index)
        idx = {v: i for i, v in enumerate(verts)}
        tree = BVHTree.FromPolygons([tuple(v.co) for v in verts], [[idx[v] for v in f.verts] for f in comp])
        if tree.ray_cast(Vector(head), n)[0] is None:
            continue                                                  # the posed limb's line does not meet this cluster
        cen = sum((f.calc_center_median() * f.calc_area() for f in comp), Vector()) / area
        rim = sum(e.calc_length() for f in comp for e in f.edges if any(nb not in comp for nb in e.link_faces))
        out.append({"id": "", "kind": "opening", "state": "capped", "axis": [round(x, 12) for x in n], "plane_origin_m": [round(x, 6) for x in cen],
                    "cap_faces": len(comp), "cap_area_cm2": round(area * 1e4, 3), "rim_perimeter_cm": round(rim * 100, 3), "end": "site",
                    "distance_m": round((cen - Vector(head)).dot(n), 6)})
    out.sort(key=lambda c: c["distance_m"])
    out = out[:1]                                                     # the first cap along the limb is the opening; beyond it is the piece's far side
    for i, c in enumerate(out):
        c["id"] = f"OP{i:03d}"
    bm.free()
    return out


# ------------------------------------------------------------------------------------------------ the limb's section
def _section_outline(limb, origin, axis, n_samples=96):
    bm = _bm(limb)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=origin, plane_no=axis)
    edges = [g for g in res["geom_cut"] if isinstance(g, bmesh.types.BMEdge)]
    if not edges:
        bm.free()
        raise C.FeatureError("the limb does not cross the cap plane: no cross-section to cut")
    adj = {}
    for e in edges:
        a, b = e.verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    seen, loops = set(), []
    for v in adj:
        if v in seen:
            continue
        loop, cur, prev = [v], v, None
        seen.add(v)
        while True:
            nxt = [w for w in adj[cur] if w != prev and w not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            loop.append(cur)
        loops.append([x.co.copy() for x in loop])
    u, w = _basis(axis)
    best, best_area = None, math.inf
    for lp in loops:                                         # canon 06 B.2: the loop CONTAINING the axis point (the origin), never the largest
        pts = np.array([[(p - Vector(origin)).dot(u), (p - Vector(origin)).dot(w)] for p in lp])
        area = 0.5 * abs(np.dot(pts[:, 0], np.roll(pts[:, 1], -1)) - np.dot(pts[:, 1], np.roll(pts[:, 0], -1)))
        if len(pts) >= 3 and _contains(pts, (0.0, 0.0)) and area < best_area:
            best, best_area = pts, area                      # the innermost loop around the point
    bm.free()
    if best is None:
        raise C.FeatureError(f"no section of the limb contains the opening's axis point ({len(loops)} loop(s) at the cap plane): pose the body into the piece first")
    pts = best
    if np.dot(pts[:, 0], np.roll(pts[:, 1], -1)) - np.dot(pts[:, 1], np.roll(pts[:, 0], -1)) < 0:
        pts = pts[::-1]                                                              # counter-clockwise about the axis
    return pts


def _contains(poly, p) -> bool:
    """Even-odd point-in-polygon in the plane."""
    x, y = p
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, np.roll(poly, -1, axis=0)):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _textures(ob) -> list:
    """The images the object's materials sample (canon 06 F.5: a texture is detected from the material, not only the studio flag)."""
    out = []
    for slot in ob.material_slots:
        m = slot.material
        if m is not None and m.use_nodes and m.node_tree is not None:
            out += [n.image.name for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image is not None]
    return sorted(set(out))


def _offset(pts, d):
    """The polygon pushed outward by ``d`` (mitred, limited to 2x); refuses a self-intersecting result."""
    n = len(pts)
    out = np.zeros_like(pts)
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        e0, e1 = p1 - p0, p2 - p1
        n0 = np.array([e0[1], -e0[0]]) / max(np.linalg.norm(e0), 1e-12)
        n1 = np.array([e1[1], -e1[0]]) / max(np.linalg.norm(e1), 1e-12)
        m = n0 + n1
        m = m / max(np.linalg.norm(m), 1e-12)
        cos_half = max(float(m @ n0), 0.5)
        out[i] = p1 + m * (d / cos_half)
    return out


def _simple(pts) -> bool:
    n = len(pts)

    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        for j in range(i + 2, n):
            if (j + 1) % n == i:
                continue
            c, d = pts[j], pts[(j + 1) % n]
            if ccw(a, c, d) != ccw(b, c, d) and ccw(a, b, c) != ccw(a, b, d):
                return False
    return True


def _ray_hit(poly, ang):
    """Distance from the origin to the polygon along the direction ang (star-shaped about the origin)."""
    d = np.array([math.cos(ang), math.sin(ang)])
    best = None
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        e = b - a
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-12:
            continue
        t = (a[0] * e[1] - a[1] * e[0]) / den
        s = (a[0] * d[1] - a[1] * d[0]) / den
        if t > 0 and -1e-9 <= s <= 1 + 1e-9 and (best is None or t < best):
            best = t
    return best


# ------------------------------------------------------------------------------------------------ the collar
def _strip(bm, X, Y, flip):
    faces = []
    n = len(X)
    for i in range(n):
        j = (i + 1) % n
        vs = (X[i], X[j], Y[j], Y[i])
        faces.append(bm.faces.new(vs[::-1] if flip else vs))
    return faces


def _boundary_loop(bm, cap_faces):
    """The ordered boundary loop of the hole left by deleting ``cap_faces`` (call before the delete: returns the cap's outer vertices in order)."""
    edges = [e for f in cap_faces for e in f.edges if any(nb not in cap_faces for nb in e.link_faces)]
    adj = {}
    for e in edges:
        a, b = e.verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    start = edges[0].verts[0]
    loop, prev, cur = [start], None, start
    while True:
        nxt = [w for w in adj[cur] if w != prev and w not in loop]
        if not nxt:
            break
        prev, cur = cur, nxt[0]
        loop.append(cur)
    return loop


def _gasket(bm, cap, origin, axis, outline, clearance_m, flange_m, lip_m, lip_rings):
    n = Vector(axis).normalized()
    u, w = _basis(n)
    O = Vector(origin)
    loop = _boundary_loop(bm, cap)
    # direction of the existing faces along each boundary edge, to wind the new strip against it
    e0 = bm.edges.get((loop[0], loop[1]))
    ex = [f for f in e0.link_faces if f not in cap][0]
    forward = any(l.vert == loop[0] and l.link_loop_next.vert == loop[1] for l in ex.loops)
    flip = forward                                                                  # the new quad must run the shared edge the opposite way
    cutter = _offset(outline, clearance_m)
    if not _simple(cutter):
        raise C.FeatureError("outline simplification failed at the opening: the clearance offset self-intersects")
    B2 = np.array([[(v.co - O).dot(u), (v.co - O).dot(w)] for v in loop])
    cen = B2.mean(axis=0)
    cutter_c = cutter - cen
    angs = [math.atan2(*(b - cen)[::-1]) for b in B2]
    C2d = []
    for a in angs:
        t = _ray_hit(cutter_c, a)
        if t is None:
            raise C.FeatureError("the body's section does not fit inside this opening: the piece is too small here; ask for a reroll")
        C2d.append(cen + t * np.array([math.cos(a), math.sin(a)]))
    for c2, b2 in zip(C2d, B2):
        if np.linalg.norm(c2 - cen) >= np.linalg.norm(b2 - cen):
            raise C.FeatureError("the body's section does not fit inside this opening: the piece is too small here; ask for a reroll")
    ring = lambda pts2, depth, rad_out=0.0: [bm.verts.new(O + u * p[0] + w * p[1] - n * depth + (u * (p[0] - cen[0]) + w * (p[1] - cen[1])).normalized() * rad_out)  # noqa: E731
                                              for p in pts2]
    Cr = ring(C2d, 0.0)
    rings = [loop, Cr]
    made = []
    made += _strip(bm, loop, Cr, flip)
    last = Cr
    wall = ring(C2d, flange_m)                                                       # the collar wall: straight down into the piece
    made += _strip(bm, last, wall, flip)
    last = wall
    for k in range(1, lip_rings + 1):                                               # the rolled lip: a half circle curling outward and back toward the cap
        th = math.pi * k / lip_rings
        r = lip_m
        nxt = ring(C2d, flange_m + r * math.sin(th), rad_out=r * (1 - math.cos(th)))
        made += _strip(bm, last, nxt, flip)
        last = nxt
    return made, last


def apply_one(ob, op, limb, clearance_mm, flange_mm, lip_mm, lip_rings=6):
    """One gasket on a copy of ``ob``'s mesh: returns (bmesh, report)."""
    bm = _bm(ob)
    axis, origin = op["axis"], op["plane_origin_m"]
    clusters = [c for c in _cap_clusters(bm, axis) if abs(np.mean([f.calc_center_median().dot(Vector(axis)) for f in c]) - Vector(origin).dot(Vector(axis))) < 1e-3]
    if not clusters:
        bm.free()
        raise C.FeatureError("no cap faces at that plane: detect the openings first")
    cap = max(clusters, key=lambda c: sum(f.calc_area() for f in c))
    outline = _section_outline(limb, origin, axis)
    area_removed = sum(f.calc_area() for f in cap)
    loop_cap = list(cap)
    # build while the cap still exists (its boundary loop is read from it), then delete it
    made, rim = _gasket(bm, loop_cap, origin, axis, outline, clearance_mm / 1000.0, flange_mm / 1000.0, lip_mm / 1000.0, lip_rings)
    bmesh.ops.delete(bm, geom=cap, context="FACES")
    return bm, {"area_removed_m2": round(area_removed, 6), "collar_depth_mm": flange_mm, "lip_mm": lip_mm, "lip_rings": lip_rings, "flange_faces": len(made)}


def manifold_stats(bm) -> dict:
    nm = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    bad = 0
    for e in bm.edges:
        if len(e.link_faces) == 2:
            dirs = []
            for f in e.link_faces:
                for l in f.loops:
                    if l.edge == e:
                        dirs.append((l.vert.index, l.link_loop_next.vert.index))
            bad += dirs[0] == dirs[1]
    bnd = [e for e in bm.edges if len(e.link_faces) == 1]
    seen, loops = set(), 0
    for e in bnd:
        if e in seen:
            continue
        loops += 1
        st = [e]
        seen.add(e)
        while st:
            cur = st.pop()
            for v in cur.verts:
                for nb in v.link_edges:
                    if len(nb.link_faces) == 1 and nb not in seen:
                        seen.add(nb)
                        st.append(nb)
    return {"non_manifold_edges": nm, "bad_winding_edges": bad, "boundary_loops": loops, "zero_area_faces": sum(1 for f in bm.faces if f.calc_area() < 1e-12)}


# ------------------------------------------------------------------------------------------------ decisions
def _decisions(root, piece):
    return Path(root) / piece / "fit" / "decisions.jsonl"


def _latest(path):
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                r = json.loads(line)
                out[r["descriptor"]["id"]] = r["answer"]
            except (ValueError, KeyError):
                continue
    return out


def _log(root, piece, op, answer, words, by="captain"):
    path = _decisions(root, piece)
    if _latest(path).get(op["id"]) == answer:
        return False                                                                   # a repeated identical answer appends nothing
    path.parent.mkdir(parents=True, exist_ok=True)
    desc = {k: op[k] for k in ("id", "kind", "state", "axis", "plane_origin_m", "cap_area_cm2")}
    with path.open("a") as fh:
        fh.write(json.dumps({"kind": "decision", "t": time.time(), "question": "opening_decision", "options": list(VERDICTS), "answer": answer, "decider": by,
                             "how": "typed", "captain_words": words or "", "descriptor": desc, "descriptor_sha256": hashlib.sha256(json.dumps(desc, sort_keys=True).encode()).hexdigest()}) + "\n")
    return True


def _need_pose(pose):
    if not pose:
        raise C.FeatureError("fit_openings runs on the posed body, never the rest pose (PIECE_PIPELINE): run lampway_fit_pose first and pass its pose")


def run(stage, object, root, axis=None, plane_origin=None, limb="", pose=None, answers=None, flange_mm=None, lip_mm=4.0, clearance_mm=15.0, piece="",
        captain_words="", texture_discard_ack=False, depths_mm=None, size=384, armature="", site=""):
    if stage not in STAGES:
        raise C.FeatureError(f"stage is one of {', '.join(STAGES)}")
    ob = C.need_object(object)
    piece = piece or ob.name
    if site:
        if not armature:
            raise C.FeatureError("a site is a bone of the posed body: pass armature=<the body's armature> with site=<bone>")
        _need_pose(pose)
        head, axis = site_axis(armature, site)
        ops = detect_site(ob, head, axis)
        for o in ops:
            o["site"] = site
        axis = list(axis)
    elif axis is None:
        raise C.FeatureError("axis is needed (the opening's axis, pointing out of the piece, e.g. [0, 0, 1]), or armature + site (a bone of the posed body)")
    else:
        ops = detect(ob, axis)
    if plane_origin is not None:                                                         # a typed site: only the cap at that plane
        n = Vector(axis).normalized()
        ops = [o for o in ops if abs(Vector(o["plane_origin_m"]).dot(n) - Vector(plane_origin).dot(n)) < 1e-3] or ops
    if stage == "detect":
        return {"object": ob.name, "candidates": ops}
    if stage == "propose":
        return {"object": ob.name, "proposals": [{"id": o["id"], "proposal": "ambiguous", "rule": "visibility and body penetration are not measured here (mesh_defect_scan and fit_pose supply them): the user rules each opening"} for o in ops]}
    if stage == "check":
        bm = _bm(ob)
        out = manifold_stats(bm)
        bm.free()
        return {"object": ob.name, "manifold": out["non_manifold_edges"] == 0 and out["bad_winding_edges"] == 0, **out}
    answers = answers or {}
    ids = {o["id"] for o in ops}
    if stage == "variants":
        _need_pose(pose)
        if not limb:
            raise C.FeatureError("variants need the posed limb (limb=<object>)")
        from . import silhouette as SIL
        out, depths = [], list(depths_mm or SUGGESTED_MM)
        op = ops[0]
        for mm in depths:
            bm, rep = apply_one(ob, op, C.need_object(limb), float(clearance_mm), float(mm), float(lip_mm))
            me = bpy.data.meshes.new("lw_collar_variant")
            bm.to_mesh(me)
            st = manifold_stats(bm)
            bm.free()
            vo = bpy.data.objects.new("lw_collar_variant", me)
            bpy.context.scene.collection.objects.link(vo)
            img = Path(root) / piece / "fit" / "openings" / f"collar_{int(mm)}mm.png"
            img.parent.mkdir(parents=True, exist_ok=True)
            try:
                from . import render as R
                R.render_view(vo, "Left", int(size), str(img))
            finally:
                bpy.data.objects.remove(vo)
                bpy.data.meshes.remove(me)
            out.append({"collar_depth_mm": mm, "image": str(img), "manifold": st["non_manifold_edges"] == 0 and st["bad_winding_edges"] == 0, **rep})
        return {"object": ob.name, "variants": out, "note": "nothing is applied: the collar depth is the user's number"}
    # apply / rule
    for k, v in answers.items():
        if v not in VERDICTS:
            raise C.FeatureError(f"an answer is one of: keep | gasket | delete (got {v!r} for {k})")
        if k not in ids:
            raise C.FeatureError(f"no opening {k!r}; the openings are: {sorted(ids)}")
    if not answers:
        raise C.FeatureError("decide every opening: keep, gasket or delete (answers {'OP000': 'keep'})")
    missing = ids - set(answers) if plane_origin is None else set()
    if missing:
        raise C.FeatureError(f"decide every opening: keep, gasket or delete; undecided: {sorted(missing)}")
    gaskets = [k for k, v in answers.items() if v == "gasket"]
    deletes = [k for k, v in answers.items() if v == "delete"]
    if gaskets or deletes:
        _need_pose(pose)
    tex = _textures(ob)
    if (gaskets or deletes) and ((ob.get("lw_studio_textured") or tex) and not texture_discard_ack):
        raise C.FeatureError("this is a geometry step: it discards the studio texture for the changed faces" + (f" (the material samples {', '.join(tex)})" if tex else "")
                             + "; run before the studio texture or pass texture_discard_ack=true and re-run it")
    if gaskets:
        if flange_mm is None:
            return {"needs_decision": {"what": "collar depth (flange length)", "question": "how deep is the gasket collar, in millimetres? (a formed tubular collar with a rolled lip, 'manifold it')",
                                       "suggested_mm": SUGGESTED_MM, "how": "stage variants builds and renders three depths for him to pick; then pass flange_mm"},
                    "object": ob.name}
        if not 2 <= float(flange_mm) <= 60:
            raise C.FeatureError("flange_mm is 2 to 60")
        if not limb:
            raise C.FeatureError("a gasket needs the posed limb (limb=<object>): run lampway_fit_pose first")
        if not 5 <= float(clearance_mm) <= 40:
            raise C.FeatureError("clearance_mm is 5 to 40 (the pipeline's wear clearance)")
    results, written = [], []
    bm = None
    work = None
    for op in ops:
        a = answers.get(op["id"])
        if a is None:
            continue
        if _log(root, piece, op, a, captain_words):
            written.append(op["id"])
        if a == "keep":
            results.append({"id": op["id"], "verdict": "keep", "manifold": True})
        elif a == "gasket":
            src = work or ob
            bm, rep = apply_one(src, op, C.need_object(limb), float(clearance_mm), float(flange_mm), float(lip_mm))
            work = _commit(ob, bm, work)
            results.append({"id": op["id"], "verdict": "gasket", "manifold": True, **rep})
        else:
            src = work or ob
            bm = _bm(src)
            cap = max([c for c in _cap_clusters(bm, op["axis"]) if abs(np.mean([f.calc_center_median().dot(Vector(op["axis"])) for f in c]) - Vector(op["plane_origin_m"]).dot(Vector(op["axis"]))) < 1e-3],
                      key=lambda c: sum(f.calc_area() for f in c))
            area = sum(f.calc_area() for f in cap)
            bmesh.ops.delete(bm, geom=cap, context="FACES")
            work = _commit(ob, bm, work)
            results.append({"id": op["id"], "verdict": "delete", "manifold": True, "area_removed_m2": round(area, 6)})
    out = {"object": (work.name if work else ob.name), "source": ob.name, "openings": results, "decisions_written": written, "texture_stale": bool(gaskets or deletes)}
    if work is not None:
        chk = _bm(work)
        st = manifold_stats(chk)
        chk.free()
        out["check"] = st
        for r in results:
            if r["verdict"] == "gasket":
                r["manifold"] = st["non_manifold_edges"] == 0 and st["bad_winding_edges"] == 0
    return out


def _commit(src, bm, work):
    """Write ``bm`` (world space) into the working copy ``<src>_openings`` (created on first use)."""
    if work is None:
        work = C.duplicate(src, "_openings")
        work.hide_set(False)
    bm.transform(src.matrix_world.inverted())
    bm.to_mesh(work.data)
    bm.free()
    work.data.update()
    return work
