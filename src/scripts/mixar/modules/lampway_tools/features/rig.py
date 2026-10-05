# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Auto-rig, binding and pose tests. Proven code: a UE-named humanoid skeleton placed from LANDMARKS MEASURED on a T-pose mesh
(height, arm span at shoulder height, leg centres), Blender's heat-map weights with a proximity fallback for the vertices heat
cannot solve, the Data Transfer weight transfer for deforming pieces, ONE bone at full influence for rigid plates, and a pose
test that measures edge stretch and vertex displacement on the evaluated mesh (Stefan's rigging-existing-armor workflow).

Side naming: the mesh stands on Z and faces ``facing`` (default -Y, Blender's front); ``_l``/``_r`` are the FIGURE's own left
and right, so with the default facing ``_l`` is +X. A rig is not a claim of deformation quality: run pose_test."""

import math

import bpy
import numpy as np
from mathutils import Vector

from . import common as C

KINDS = ("humanoid",)
SPINE = ("spine_01", "spine_02", "spine_03")


def _world_points(ob):
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    m = np.array(ob.matrix_world)
    return (m[:3, :3] @ co.T).T + m[:3, 3]


def landmarks(pts, facing="-Y") -> dict:
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    h = float(hi[2] - lo[2])
    if h <= 0:
        raise C.FeatureError("the mesh has no height: a humanoid stands on Z")
    cx, cy = float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2)
    z = lambda f: float(lo[2] + f * h)                                           # noqa: E731
    band = pts[(pts[:, 2] > z(0.72) - 0.06 * h) & (pts[:, 2] < z(0.72) + 0.06 * h)]
    tip = float(np.abs(band[:, 0] - cx).max()) if len(band) else 0.45 * h
    low = pts[pts[:, 2] < z(0.3)]
    pos = low[low[:, 0] > cx]
    neg = low[low[:, 0] <= cx]
    leg = float(np.abs(np.concatenate([pos[:, 0], neg[:, 0]]) - cx).mean()) if len(low) and len(pos) and len(neg) else 0.06 * h
    sign = 1.0 if facing == "-Y" else -1.0                                        # the figure's LEFT side along +X when facing -Y
    return {"lo": lo, "hi": hi, "h": h, "cx": cx, "cy": cy, "z": z, "tip": tip, "leg": leg, "sign": sign}


def _bone_table(L) -> list:
    """(name, parent, head, tail) for the humanoid, in world coordinates."""
    cx, cy, z, h, s = L["cx"], L["cy"], L["z"], L["h"], L["sign"]
    arm_z = z(0.72)
    sx = 0.11 * h
    tip = max(L["tip"], sx + 0.1 * h)
    span = tip - sx
    rows = [("pelvis", None, (cx, cy, z(0.53)), (cx, cy, z(0.60))),
            ("spine_01", "pelvis", (cx, cy, z(0.60)), (cx, cy, z(0.66))),
            ("spine_02", "spine_01", (cx, cy, z(0.66)), (cx, cy, z(0.72))),
            ("spine_03", "spine_02", (cx, cy, z(0.72)), (cx, cy, z(0.80))),
            ("neck_01", "spine_03", (cx, cy, z(0.80)), (cx, cy, z(0.86))),
            ("head", "neck_01", (cx, cy, z(0.86)), (cx, cy, float(L["hi"][2])))]
    for side, k in (("l", s), ("r", -s)):
        x = lambda d: cx + k * d                                                  # noqa: E731
        rows += [(f"clavicle_{side}", "spine_03", (cx, cy, arm_z), (x(sx), cy, arm_z)),
                 (f"upperarm_{side}", f"clavicle_{side}", (x(sx), cy, arm_z), (x(sx + 0.45 * span), cy, arm_z)),
                 (f"lowerarm_{side}", f"upperarm_{side}", (x(sx + 0.45 * span), cy, arm_z), (x(sx + 0.88 * span), cy, arm_z)),
                 (f"hand_{side}", f"lowerarm_{side}", (x(sx + 0.88 * span), cy, arm_z), (x(tip), cy, arm_z))]
        lx = cx + k * L["leg"]
        rows += [(f"thigh_{side}", "pelvis", (lx, cy, z(0.53)), (lx, cy, z(0.28))),
                 (f"calf_{side}", f"thigh_{side}", (lx, cy, z(0.28)), (lx, cy, z(0.05))),
                 (f"foot_{side}", f"calf_{side}", (lx, cy, z(0.05)), (lx, cy - 0.07 * h, z(0.02)))]
    return rows


def _build_armature(ob, name, rows):
    arm = bpy.data.armatures.new(name)
    arm_ob = bpy.data.objects.new(name, arm)
    bpy.context.scene.collection.objects.link(arm_ob)
    C.activate(arm_ob)
    bpy.ops.object.mode_set(mode="EDIT")
    made = {}
    for bone, parent, head, tail in rows:
        eb = arm.edit_bones.new(bone)
        eb.head, eb.tail = Vector(head), Vector(tail)
        if parent:
            eb.parent = made[parent]
            eb.use_connect = (eb.parent.tail - eb.head).length < 1e-6
        made[bone] = eb
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm_ob


def _unweighted(ob) -> list:
    return [v.index for v in ob.data.vertices if sum(g.weight for g in v.groups) < 1e-4]


def _proximity_weights(ob, arm_ob, only=None, power=3.0, nearest=3):
    """Weights ~ 1/distance^power to the ``nearest`` bone segments (envelope-style), for the vertices heat could not solve."""
    me = ob.data
    bones = [(b.name, arm_ob.matrix_world @ b.head_local, arm_ob.matrix_world @ b.tail_local) for b in arm_ob.data.bones]
    groups = {n: ob.vertex_groups.get(n) or ob.vertex_groups.new(name=n) for n, _h, _t in bones}
    for v in me.vertices:
        if only is not None and v.index not in only:
            continue
        p = ob.matrix_world @ v.co
        ds = []
        for n, h, t in bones:
            seg = t - h
            u = max(0.0, min(1.0, (p - h).dot(seg) / max(seg.length_squared, 1e-12)))
            ds.append(((p - (h + seg * u)).length, n))
        ds.sort()
        w = [1.0 / max(d, 1e-4) ** power for d, _n in ds[:nearest]]
        tot = sum(w)
        for wi, (_d, n) in zip(w, ds[:nearest]):
            groups[n].add([v.index], wi / tot, "REPLACE")


def _parent(ob, arm_ob, auto):
    ob.parent = None
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    arm_ob.select_set(True)
    bpy.context.view_layer.objects.active = arm_ob
    bpy.ops.object.parent_set(type="ARMATURE_AUTO" if auto else "ARMATURE_NAME")


def auto_rig(object, kind="humanoid", engine="algorithmic", weights="auto", facing="-Y", copy=True):
    if engine != "algorithmic":
        return C.studio_slot("rig", engine)
    if kind not in KINDS:
        raise C.FeatureError(f"unknown kind {kind!r}; the kinds are {', '.join(KINDS)} (a creature needs the studio slot)")
    if weights not in ("auto", "proximity"):
        raise C.FeatureError(f"unknown weights {weights!r}; auto (heat map, proximity fallback) | proximity")
    src = C.need_object(object)
    ob = C.duplicate(src, "_rigged") if copy else src                              # parenting and weighting mutate: the source is never touched by default
    L = landmarks(_world_points(ob), facing)
    arm_ob = _build_armature(ob, f"{src.name}_rig", _bone_table(L))
    used = "proximity"
    if weights == "auto":
        _parent(ob, arm_ob, auto=True)
        used = "heat"
    else:
        _parent(ob, arm_ob, auto=False)
        _proximity_weights(ob, arm_ob)
    missing = _unweighted(ob)
    if missing:
        _proximity_weights(ob, arm_ob, only=set(missing))
        used = "heat+proximity" if used == "heat" else used
    final_missing = _unweighted(ob)
    return {"armature": arm_ob.name, "source": src.name, "mesh": ob.name, "kind": kind,
            "report": {"bones": len(arm_ob.data.bones), "weights": used if used == "proximity" else "heat",
                       "weights_detail": used, "heat_failed_vertices": len(missing), "unweighted_vertices": len(final_missing),
                       "height": round(L["h"], 4), "facing": facing}}


def bind_to_armature(object, armature, mode="rigid", bone="", source=""):
    ob = C.need_object(object)
    arm_ob = C.need_object(armature, "ARMATURE")
    if mode not in ("rigid", "transfer", "auto"):
        raise C.FeatureError(f"unknown mode {mode!r}; rigid (one bone, full weight) | transfer (from a body) | auto (heat map)")
    for g in list(ob.vertex_groups):
        ob.vertex_groups.remove(g)
    if mode == "rigid":
        if bone not in arm_ob.data.bones:
            raise C.FeatureError(f"no bone {bone!r} in {armature!r}; the bones are: {sorted(b.name for b in arm_ob.data.bones)[:30]}")
        ob.parent = arm_ob
        ob.parent_type = "OBJECT"
        for m in [m for m in ob.modifiers if m.type == "ARMATURE"]:
            ob.modifiers.remove(m)
        vg = ob.vertex_groups.new(name=bone)
        vg.add([v.index for v in ob.data.vertices], 1.0, "REPLACE")
        mod = ob.modifiers.new("Armature", "ARMATURE")
        mod.object = arm_ob
        ob.matrix_parent_inverse = arm_ob.matrix_world.inverted()
        return {"object": ob.name, "armature": arm_ob.name, "mode": mode, "bone": bone, "vertices": len(ob.data.vertices)}
    if mode == "auto":
        _parent(ob, arm_ob, auto=True)
        missing = _unweighted(ob)
        if missing:
            _proximity_weights(ob, arm_ob, only=set(missing))
        return {"object": ob.name, "armature": arm_ob.name, "mode": mode, "heat_failed_vertices": len(missing)}
    body = C.need_object(source)
    _parent(ob, arm_ob, auto=False)                                              # the armature modifier, no weights yet
    for g in list(ob.vertex_groups):
        ob.vertex_groups.remove(g)
    for g in body.vertex_groups:
        ob.vertex_groups.new(name=g.name)
    mod = ob.modifiers.new("lw_transfer", "DATA_TRANSFER")
    mod.object = body
    mod.use_vert_data = True
    mod.data_types_verts = {"VGROUP_WEIGHTS"}
    mod.vert_mapping = "POLYINTERP_NEAREST"
    C.activate(ob)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    # a vertex the transfer left bare (no neighbour weights) gets proximity weights
    bare = _unweighted(ob)
    if bare:
        _proximity_weights(ob, arm_ob, only=set(bare))
    return {"object": ob.name, "armature": arm_ob.name, "mode": mode, "source": body.name, "proximity_filled_vertices": len(bare)}


def _pose_bones(pose) -> list:
    """[(bone, euler degrees)] of one pose: ``bones`` (several) or the single ``bone`` + ``rotate``; neither = the rest pose."""
    if pose.get("bones"):
        return [(b["bone"], b.get("rotate", [0, 0, 0])) for b in pose["bones"]]
    if pose.get("bone"):
        return [(pose["bone"], pose.get("rotate", [0, 0, 0]))]
    return []


def _shell_labels(n_verts, edges) -> np.ndarray:
    parent = list(range(n_verts))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b in edges:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[ra] = rb
    return np.array([find(i) for i in range(n_verts)])


MAX_SEAM_PAIRS = 50000


def _seam_pairs(rest, edges, radius):
    """Vertex pairs of DIFFERENT shells closer than ``radius`` at rest: the seams between plates. Edge stretch is per mesh edge and never sees them."""
    from mathutils import kdtree
    labels = _shell_labels(len(rest), edges)
    tree = kdtree.KDTree(len(rest))
    for i, p in enumerate(rest):
        tree.insert(p, i)
    tree.balance()
    pairs = []
    for i, p in enumerate(rest):
        for _co, j, _d in tree.find_range(p, radius):
            if j > i and labels[i] != labels[j]:
                pairs.append((i, j))
                if len(pairs) >= MAX_SEAM_PAIRS:
                    return np.array(pairs, dtype=np.int64)
    return np.array(pairs, dtype=np.int64).reshape(-1, 2)


def _body_tree(body):
    from mathutils.bvhtree import BVHTree
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    m = ev.matrix_world
    tree = BVHTree.FromPolygons([m @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    ev.to_mesh_clear()
    return tree


def _clearance(points, body) -> dict:
    """Signed distance of the piece's vertices to the (posed) body: positive outside it, negative inside."""
    tree = _body_tree(body)
    signed = []
    for p in points:
        v = Vector(p)
        loc, nrm, _i, dist = tree.find_nearest(v)
        signed.append(dist if (v - loc).dot(nrm) >= 0 else -dist)
    signed = np.array(signed)
    return {"min_m": round(float(signed.min()), 6) if len(signed) else 0.0, "penetrating_vertices": int((signed < -1e-6).sum())}


def pose_test(armature, object, poses, clearance_body="", seam_radius_m=0.02):
    """Rotate bones (Euler degrees on the pose bone; a pose may move several bones), evaluate the mesh and measure per pose: the maximum edge
    stretch (current / rest length), the largest vertex displacement, the SEAM GAP growth (vertex pairs of different shells within
    ``seam_radius_m`` at rest: how far apart they end up) and, with ``clearance_body``, the distance to that body posed by the same
    armature. Every pose is reset afterwards."""
    arm_ob = C.need_object(armature, "ARMATURE")
    ob = C.need_object(object)
    body = C.need_object(clearance_body) if clearance_body else None
    rest = _evaluated(ob)
    me = ob.data
    edges = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", edges)
    edges = edges.reshape(-1, 2)
    rest_len = np.linalg.norm(rest[edges[:, 0]] - rest[edges[:, 1]], axis=1)
    keep = rest_len > 1e-9
    pairs = _seam_pairs(rest, edges, seam_radius_m)
    rest_gap = np.linalg.norm(rest[pairs[:, 0]] - rest[pairs[:, 1]], axis=1) if len(pairs) else np.zeros(0)
    out = []
    for pose in poses:
        moved = []
        for bone, rotate in _pose_bones(pose):
            pb = arm_ob.pose.bones.get(bone)
            if pb is None:
                raise C.FeatureError(f"no bone {bone!r} in {armature!r}; the bones are: {sorted(b.name for b in arm_ob.data.bones)[:30]}")
            pb.rotation_mode = "XYZ"
            moved.append((pb, tuple(pb.rotation_euler)))
            pb.rotation_euler = [math.radians(float(a)) for a in rotate]
        bpy.context.view_layer.update()
        cur = _evaluated(ob)
        cur_len = np.linalg.norm(cur[edges[:, 0]] - cur[edges[:, 1]], axis=1)
        gap = float((np.linalg.norm(cur[pairs[:, 0]] - cur[pairs[:, 1]], axis=1) - rest_gap).max()) if len(pairs) else 0.0
        names = [pb.name for pb, _b in moved]
        row = {"name": pose.get("name") or (names[0] if names else "rest"), "bone": names[0] if names else "", "bones": names,
               "max_edge_stretch": round(float((cur_len[keep] / rest_len[keep]).max()), 6) if keep.any() else 1.0,
               "min_edge_stretch": round(float((cur_len[keep] / rest_len[keep]).min()), 6) if keep.any() else 1.0,
               "max_vertex_displacement": round(float(np.linalg.norm(cur - rest, axis=1).max()), 6),
               "seam_gap_m": round(max(gap, 0.0), 6), "seam_pairs": int(len(pairs))}
        if body is not None:
            row["clearance"] = _clearance(cur, body)
        out.append(row)
        for pb, before in moved:
            pb.rotation_euler = before
        bpy.context.view_layer.update()
    return {"armature": arm_ob.name, "object": ob.name, "poses": out}


def _evaluated(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    m = np.array(ev.matrix_world)
    out = (m[:3, :3] @ co.T).T + m[:3, 3]
    ev.to_mesh_clear()
    return out
