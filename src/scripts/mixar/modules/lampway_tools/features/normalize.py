# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""lampway_normalize_mesh: a raw mesh into a canonical `mesh` (lampway.canonical-asset/1) with its receipt, or a refusal naming what
could not be decided (specs/canon/normalization contracts/normalize_mesh.md, DOOR.md 3).

Steps, each recorded in the receipt: import (canon_io.import_raw, settings pinned per container) -> frame (a DECLARED turn about Z
from the caller or the recipe; otherwise four cardinal silhouettes against the approved plate with an explicit facing margin; never a guess) ->
transform applied into the data (winding reversed under a mirror) -> scale STATE (real only with evidence; Tripo/Hi3D
generator_normalised; else unknown) -> weld by position for a generated mesh (1e-5 m, refused above 5 % merged; never an authored
mesh) -> lw_source_face (the raw face ids) -> measure -> pivot (the bounding box's bottom centre for an unplaced asset) -> stamp
``lw_canon`` and write the receipt. The same raw bytes and decisions give byte-identical documents."""

import hashlib
import json
import math
import re
import tempfile
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

from .. import canon_asset as CA
from .. import canon_io
from ..canon_geom import conventions_block, uv_island_ids, uv_metrics
from . import common as C

TOOL, TOOL_VERSION = "lampway_normalize_mesh", "1.0.0"
GENERATED = ("tripo_studio", "tripo_api", "meshy", "hi3d", "hyper3d", "hunyuan", "trellis", "fal", "higgsfield", "metatailor")
NORMALISING = ("tripo_studio", "tripo_api", "hi3d")            # canon 01 B: ~0.98 m on the longest side, never real size
GENERATORS = GENERATED + ("lampway_tool", "captain_authored", "cc0_ambientcg", "cc0_polyhaven", "ue_native", "blender_import", "unknown")
PINNED = {"glb": {"guess_original_bind_pose": False}, "gltf": {"guess_original_bind_pose": False}, "fbx": {"axis_forward": "-Z", "axis_up": "Y"}}
EVIDENCE_DECISION = {"scale_to_measure": "measured", "reference_height_ratio": "measured", "unit_metadata": "measured", "captain_length": "declared",
                     "fit_place_enclosure": "derived_from_body", "studio_auto_size": "source_real_world", "bbox_condition": "source_real_world",
                     "api_dimensions_m": "source_real_world"}
TOKENS = {(1, 0, 0): "+X", (-1, 0, 0): "-X", (0, 1, 0): "+Y", (0, -1, 0): "-Y", (0, 0, 1): "+Z", (0, 0, -1): "-Z"}


def _rz(deg):
    a = math.radians(deg)
    return np.array([[math.cos(a), -math.sin(a), 0.0], [math.sin(a), math.cos(a), 0.0], [0.0, 0.0, 1.0]])


def _token(v):
    k = int(np.argmax(np.abs(v)))
    t = [0, 0, 0]
    t[k] = int(np.sign(v[k]))
    return TOKENS[tuple(t)]


def _r9(x):
    return [[round(float(c), 9) + 0.0 for c in row] for row in x] if np.ndim(x) == 2 else [round(float(c), 9) + 0.0 for c in x]


def _decide_frame(turn_deg, recipe, plate, generator, root, ob=None, facing_margin=None):
    if turn_deg is not None:
        if not -180 <= float(turn_deg) <= 360:
            raise C.FeatureError("turn_deg is -180..360 (the piece's facing: -90 for a +X-facing import)")
        return float(turn_deg), {"kind": "declared", "evidence": {"method": "caller_turn", "value": float(turn_deg)}}
    if recipe:
        r = json.loads((Path(root) / recipe).read_text())
        if isinstance(r.get("turn_deg"), (int, float)):
            return float(r["turn_deg"]), {"kind": "declared", "evidence": {"method": "recipe_turn", "value": float(r["turn_deg"]), "reference": str(recipe)}}
    if plate:
        margin = facing_margin if facing_margin is not None else CA.SETTINGS["facing_margin"]["value"]
        if margin is None:
            raise C.FeatureError("plate registration needs the facing margin (setting facing_margin, decision D6: no number has been ruled): "
                                 "pass turn_deg (the piece's facing) instead")
        return _register_frame(ob, plate, margin, root)
    if generator == "lampway_tool":
        return 0.0, {"kind": "source_convention", "evidence": {"method": "source_spec", "reference": "a Lampway tool writes the body frame"}}
    raise C.FeatureError("frame undecided: pass turn_deg (the piece's facing: -90 for a +X-facing import) or plate=<approved Front plate>")


def _register_frame(ob, plate, margin, root):
    """Canon normalize_mesh §6: four cardinal yaws, shared silhouette masks, true-aspect IoU."""
    if isinstance(margin, bool) or not isinstance(margin, (int, float)) or not math.isfinite(margin) or not 0 <= margin <= 1:
        raise C.FeatureError("facing_margin is an explicit IoU difference in 0..1; pass turn_deg instead if it is unruled")
    report = measure_frame(ob, plate, root)
    rows, path = report["ranking"], Path(root) / report["plate"]
    best, second = rows[:2]
    gap = report["gap"]
    if gap <= 0 or gap < margin:
        raise C.FeatureError(f"facing ambiguous: yaw {best['yaw']:g} IoU {best['iou']:.6f}, yaw {second['yaw']:g} IoU {second['iou']:.6f}; "
                             f"difference {gap:.6f} needs margin {margin:g}; pass turn_deg")
    evidence = {"method": "plate_silhouette_registration", "value": best["iou"], "second_best": second["iou"],
                "margin": float(margin), "reference": report["plate"],
                "receipt_sha256": hashlib.sha256(json.dumps({"plate_sha256": canon_io.file_sha256(path), "ranking": rows}, sort_keys=True).encode()).hexdigest()}
    return best["yaw"], {"kind": "measured", "evidence": evidence}


def measure_frame(ob, plate, root):
    """Measure all cardinal candidates without accepting a facing margin or mutating input."""
    from . import silhouette
    from ..canon_geom import mask_iou, fit_masks_true_aspect
    if ob is None:
        raise C.FeatureError("plate registration needs the input mesh to render; pass turn_deg")
    path = (Path(root) / plate).resolve()
    if not path.is_relative_to(Path(root).resolve()) or not path.is_file():
        raise C.FeatureError("plate must be an approved Front image under the project root")
    target = silhouette._image_mask(path)
    if not target.any():
        raise C.FeatureError("the approved Front plate has no silhouette: provide alpha or its flat border background")
    before = canon_io.snapshot_ids()
    rows = []
    try:
        probe = ob.copy()
        with tempfile.TemporaryDirectory(prefix="lw_facing_") as temp:
            for yaw in (0.0, -90.0, 90.0, 180.0):
                probe.matrix_world = Matrix.Rotation(math.radians(yaw), 4, "Z") @ ob.matrix_world
                rendered = silhouette._render_mask(probe, probe, "Front", 512, Path(temp) / "mask.png")
                a, b = fit_masks_true_aspect(rendered, target, 512)
                rows.append({"yaw": yaw, "iou": mask_iou(a, b)})
    finally:
        canon_io.remove_new_ids(before)
    rows.sort(key=lambda row: (-row["iou"], row["yaw"]))
    return {"ranking": rows, "gap": rows[0]["iou"]-rows[1]["iou"],
            "plate": str(path.relative_to(Path(root).resolve())), "plate_sha256": canon_io.file_sha256(path)}


def _skinned(ob):
    return any(m.type == "ARMATURE" for m in ob.modifiers) or (ob.parent is not None and ob.parent.type == "ARMATURE")


def _weld(me, dist, guard):
    """(vertices merged, refused reason or None) - on a bmesh copy first, so a refused weld leaves the mesh as it was."""
    bm = bmesh.new()
    bm.from_mesh(me)
    n0 = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=dist)
    merged = n0 - len(bm.verts)
    if n0 and merged > guard * n0:
        bm.free()
        return merged, f"the weld at {dist:g} m would merge {merged} of {n0} vertices (> {guard:.0%}): the weld distance is wrong for this mesh: pass weld_distance_m"
    bm.to_mesh(me)
    bm.free()
    me.update()
    return merged, None


def _topology(me, welded, weld_rec, split):
    bm = bmesh.new()
    bm.from_mesh(me)
    faces = bm.faces
    non_manifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    boundary = [e for e in bm.edges if len(e.link_faces) == 1]
    seen, loops = set(), 0
    for e in boundary:                                          # boundary loops: connected chains of boundary edges
        if e.index in seen:
            continue
        loops += 1
        stack = [e]
        while stack:
            x = stack.pop()
            if x.index in seen:
                continue
            seen.add(x.index)
            stack.extend(y for v in x.verts for y in v.link_edges if len(y.link_faces) == 1 and y.index not in seen)
    consistent = all(len(e.link_faces) != 2 or e.link_loops[0].vert != e.link_loops[1].vert for e in bm.edges)
    shells, done = 0, set()
    for f in faces:
        if f.index in done:
            continue
        shells += 1
        stack = [f]
        while stack:
            g = stack.pop()
            if g.index in done:
                continue
            done.add(g.index)
            stack.extend(h for e in g.edges for h in e.link_faces if h.index not in done)
    out = {"verts": len(bm.verts), "faces": len(faces), "tris": sum(1 for f in faces if len(f.verts) == 3), "quads": sum(1 for f in faces if len(f.verts) == 4),
           "welded": bool(welded), "weld": weld_rec, "split_by_uv_seam_in_raw": bool(split), "manifold": non_manifold == 0,
           "non_manifold_edges": non_manifold, "boundary_loops": loops, "shells": shells, "winding_consistent": bool(consistent),
           "degenerate_faces": sum(1 for f in faces if f.calc_area() < 1e-14)}
    out["ngons"] = out["faces"] - out["tris"] - out["quads"]
    bm.free()
    return out


def _uv_sets(me, V):
    F = [list(p.vertices) for p in me.polygons]
    out = []
    for layer in me.uv_layers:
        uv = np.empty(len(me.loops) * 2)
        layer.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        FUV = [list(p.loop_indices) for p in me.polygons]
        m = uv_metrics(V, F, uv, FUV, res=256) if F else {"overlap": 0.0, "flipped": 0.0}
        out.append({"name": layer.name, "origin": "bottom_left", "v_up": True, "range": "udim" if len(uv) and uv.max() > 1.0 + 1e-6 else "unit",
                    "islands": int(uv_island_ids(F, FUV, uv).max() + 1) if F else 0, "island_rule": "vertex_index_and_uv",
                    "overlap": round(min(1.0, m["overlap"]), 6), "flipped_fraction": round(m["flipped"], 6),
                    "layout_sha256": hashlib.sha256(uv.astype("<f4").tobytes()).hexdigest()})
    return out


def normalize_object(ob, *, turn_deg=None, generator="unknown", raw=None, path_hint=None, want_scale="any", scale_evidence=None, weld="auto",
                     weld_distance_m=None, pivot="bbox_bottom_centre", pivot_offset=None, recipe="", plate="", root=".", facing_margin=None, assembly=None):
    """Normalize one scene mesh object in place; returns (document, receipt)."""
    if ob.type != "MESH":
        raise C.FeatureError(f"{ob.name} is a {ob.type}, not a mesh: normalize it with its own kind's tool")
    if _skinned(ob):
        raise C.FeatureError(f"{ob.name} is skinned: a skinned mesh is normalized with lampway_normalize_rigged")
    if generator not in GENERATORS:
        raise C.FeatureError(f"generator {generator!r} is not one of {', '.join(GENERATORS)}")
    if want_scale not in ("any", "real"):
        raise C.FeatureError("want_scale is any | real")
    if weld not in ("auto", "never"):
        raise C.FeatureError("weld is auto | never")
    if want_scale == "real" and not scale_evidence:
        raise C.FeatureError("scale unknown: real scale comes from fit_place (armour) or scale_to_measure (a measured length); "
                             "normalize with want_scale=any to keep generator scale")
    dist = float(weld_distance_m if weld_distance_m is not None else CA.SETTINGS["weld_m"]["value"])
    if not 1e-7 <= dist <= 1e-3:
        raise C.FeatureError("weld_distance_m is 1e-7..1e-3")
    if "lw_canon" in ob.keys():
        doc = json.loads(ob["lw_canon"])
        if not CA.validate(doc) and not CA.check(doc, canon_io.facts(ob)):
            return doc, None
    turn, decision = _decide_frame(turn_deg, recipe, plate, generator, root, ob, facing_margin)
    unit = float(bpy.context.scene.unit_settings.scale_length)
    if abs(unit - 1.0) > 1e-9:
        raise C.FeatureError(f"the scene's unit scale_length is {unit}, not 1: a canonical asset is in metres (set it to 1 first)")
    backup, W0 = ob.data, ob.matrix_world.copy()
    ob.data = ob.data.copy()                                       # work on a copy: a refusal below leaves the object as it was
    try:
        doc, rbytes = _normalize(ob, turn, decision, generator, raw, path_hint, want_scale, scale_evidence, weld, dist, pivot, pivot_offset, unit, assembly)
    except Exception:
        work = ob.data
        ob.data, ob.matrix_world = backup, W0
        bpy.data.meshes.remove(work)
        raise
    name = backup.name
    if backup.users == 0:
        bpy.data.meshes.remove(backup)
        ob.data.name = name
    bpy.context.view_layer.update()                                # the next reader of ob.dimensions / matrix_world sees the applied transform
    return doc, rbytes


def _normalize(ob, turn, decision, generator, raw, path_hint, want_scale, scale_evidence, weld, dist, pivot, pivot_offset, unit, assembly=None):
    me = ob.data
    raw = dict(raw or (json.loads(ob["lw_raw"]) if "lw_raw" in ob.keys() else {}))
    raw_sha = raw.get("sha256") or canon_io.geometry_sha256(ob)
    steps = [{"op": "import", "importer": raw.get("importer", "scene object"), "settings": raw.get("settings", {})}]
    if "lw_source_face" not in me.attributes:                    # the raw face ids, before anything renumbers faces
        a = me.attributes.new("lw_source_face", "INT", "FACE")
        a.data.foreach_set("value", np.arange(len(me.polygons), dtype=np.int32))
    W = np.array(ob.matrix_world)
    mirror = bool(np.linalg.det(W[:3, :3]) < 0)
    A = _rz(turn)
    A4 = np.eye(4)
    A4[:3, :3] = A
    me.transform(Matrix((A4 @ W).tolist()), shape_keys=True)        # every shape key rides with the basis
    if mirror:
        me.flip_normals()
    ob.matrix_world = Matrix.Identity(4)
    steps += [{"op": "axis_map", "matrix": _r9(A), "turn_deg": turn, "decision": decision["kind"], "evidence": decision["evidence"]},
              {"op": "apply_transform", "matrix": _r9(W), "winding_reversed": mirror}]
    steps.append({"op": "unit", "scene_scale_length": unit, "factor": 1.0})
    generated = generator in GENERATED
    if weld == "auto" and generated and not me.shape_keys:
        merged, refused = _weld(me, dist, CA.SETTINGS["weld_guard_fraction"]["value"])
        if refused:
            raise C.FeatureError(refused)
        weld_rec, welded = {"rule": "position", "distance_m": dist, "vertices_merged": int(merged)}, True
    else:
        why = "shape_keys" if me.shape_keys else ("captain_rule" if weld == "never" else ("authored_rig" if generator == "captain_authored" else None))
        weld_rec, welded, merged = ({"rule": "none", "refused_reason": why} if why else {"rule": "none"}), False, 0
    steps.append({"op": "weld", **weld_rec})
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    V = co.reshape(-1, 3)
    if pivot == "bbox_bottom_centre":
        lo, hi = V.min(0), V.max(0)
        off = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    else:
        off = np.asarray(pivot_offset if pivot_offset is not None else (0.0, 0.0, 0.0), float)
    me.transform(Matrix.Translation(off.tolist()), shape_keys=True)
    me.update()
    V = V + off
    steps.append({"op": "pivot", "rule": pivot, "offset_m": _r9(off)})
    longest = float((V.max(0) - V.min(0)).max()) if len(V) else 0.0
    if want_scale == "real":
        ev = dict(scale_evidence)
        if ev.get("method") not in EVIDENCE_DECISION:
            raise C.FeatureError(f"scale_evidence.method is one of {', '.join(EVIDENCE_DECISION)}")
        scale = {"state": "real", "decision": EVIDENCE_DECISION[ev["method"]], "factor_applied": 1, "uniform": True, "evidence": ev}
    elif generator in NORMALISING:
        scale = {"state": "generator_normalised", "decision": "none", "factor_applied": 1, "uniform": True,
                 "generator_norm": {"longest_side_m": round(longest, 6), "source": "canon 01 B"}}
    else:
        scale = {"state": "unknown", "decision": "none", "factor_applied": 1, "uniform": True}
    steps.append({"op": "scale", "state": scale["state"], "longest_side_m": round(longest, 6)})
    smooth = {bool(p.use_smooth) for p in me.polygons}
    geometry = canon_io.geometry_sha256(ob)
    uvs = _uv_sets(me, V)
    mats = [{"slot": i, **({"name": re.sub(r"\.\d{3}$", "", s.material.name)} if s.material else {})} for i, s in enumerate(ob.material_slots)]
    body = {"bbox_min_m": _r9(V.min(0)) if len(V) else [0, 0, 0], "bbox_max_m": _r9(V.max(0)) if len(V) else [0, 0, 0],
            "topology": _topology(me, welded, weld_rec, merged > 0), "uv_sets": uvs, "material_slots": mats,
            "normals": {"custom_split": bool(getattr(me, "has_custom_normals", False)), "shading": "mixed" if len(smooth) > 1 else ("smooth" if True in smooth else "flat")},
            "geometry_sha256": geometry}
    front = A.T @ np.array([0.0, -1.0, 0.0])
    conv = {"frame": CA.FRAME, "up": "+Z", "front": "-Y", "wearer_left": "+X", "handedness": "right", "units": "m",
            "source_frame": {"name": "lampway_body" if decision["kind"] == "source_convention" else "blender_import", "up": "+Z", "front": _token(front)},
            "axis_map": _r9(A), "axis_map_det": 1, "turn_deg": turn, "winding_reversed": mirror, "frame_decision": decision}
    raw_doc = {"sha256": raw_sha, "container": raw.get("container", "none"), "bytes": int(raw.get("bytes", 0)), "generator": {"source": generator}}
    if path_hint:
        raw_doc["path_hint"] = path_hint
    canonical = CA.digest(json.dumps({"geometry": geometry, "uv": [u["layout_sha256"] for u in uvs], "materials": mats}, sort_keys=True).encode())
    receipt = {"schema": "lampway.normalize-receipt/1", "tool": TOOL, "tool_version": TOOL_VERSION, "blender_version": bpy.app.version_string,
               "input": {"sha256": raw_sha, "container": raw_doc["container"], **({"path_hint": path_hint} if path_hint else {})},
               "output": {"canonical_sha256": canonical, "asset_id": f"raw-{raw_sha[:12]}"}, "steps": steps,
               "conventions": conventions_block(turn_deg=turn, weld_m=dist if welded else "n/a", source_frame=conv["source_frame"]["name"]),
               "settings": {k: CA.SETTINGS[k] for k in ("weld_m", "weld_guard_fraction", "pivot_rule", "facing_margin", "pair_scale_group")}, "refused": []}
    if assembly is not None:
        receipt["assembly"] = assembly
    rbytes = json.dumps(receipt, sort_keys=True, indent=1).encode()
    doc = {"schema": "lampway.canonical-asset", "schema_version": 1, "kind": "mesh", "asset_id": f"raw-{raw_sha[:12]}", "raw": raw_doc,
           "conventions": conv, "transform": {"applied": True, "object_matrix": _r9(np.eye(4))}, "scale": scale,
           "pivot": {"rule": pivot, "offset_m": _r9(off)}, "normalized_by": {"tool": TOOL, "tool_version": TOOL_VERSION, "blender_version": bpy.app.version_string},
           "canonical_sha256": canonical, "receipt_sha256": hashlib.sha256(rbytes).hexdigest(), "body": body}
    errs = CA.validate(doc)
    if errs:
        raise C.FeatureError(f"the canonical document does not validate (a normalizer bug): {errs[:3]}")
    ob["lw_canon"] = json.dumps(doc, sort_keys=True)
    for db in (ob, me):
        if "lw_raw" in db.keys():
            del db["lw_raw"]
    return doc, rbytes


_ID_KINDS = ("objects", "meshes", "materials", "images", "textures", "node_groups", "collections", "armatures", "actions", "cameras", "lights",
             "curves", "shape_keys", "worlds")


def _ids():
    return {(k, x.as_pointer()) for k in _ID_KINDS for x in getattr(bpy.data, k)}


def _remove_new(before):
    """Remove every datablock that did not exist in ``before`` (audit F5): a refused import leaves the file exactly as it was."""
    new = [x for k in _ID_KINDS for x in getattr(bpy.data, k) if (k, x.as_pointer()) not in before and k != "shape_keys"]
    if new:
        bpy.data.batch_remove(new)


def run(input, turn_deg=None, plate="", recipe="", generator="", want_scale="any", scale_evidence=None, weld="auto", weld_distance_m=None, root=".", facing_margin=None):
    """The tool: a path (imported raw through canon_io, settings pinned per container) or a scene object, normalized in place. A
    refused FILE leaves nothing behind: every datablock its import brought in (objects, meshes, materials, images, ...) is removed,
    so a retry lands under the file's own names (audit F5)."""
    ob = bpy.data.objects.get(input) if isinstance(input, str) else None
    if ob is not None:
        return _normalize_all([ob], None, None, turn_deg, plate, recipe, generator, want_scale, scale_evidence, weld, weld_distance_m, root, facing_margin)
    p = Path(root) / input
    if not p.exists():
        raise C.FeatureError(f"{input} is neither an object nor a file under the project root")
    ext = p.suffix.lower().lstrip(".")
    before = _ids()
    try:
        imp = canon_io.import_raw(str(p), **PINNED.get(ext, {}))
        objs = [bpy.data.objects[n] for n in imp["objects"] if bpy.data.objects[n].type == "MESH"]
        if not objs:
            raise C.FeatureError(f"{input} holds no mesh")
        raw = {k: imp[k] for k in ("sha256", "container", "importer", "settings")}
        raw["bytes"] = p.stat().st_size
        try:
            hint = str(p.resolve().relative_to(Path(root).resolve()))
        except ValueError:
            hint = p.name
        return _normalize_all(objs, raw, hint, turn_deg, plate, recipe, generator, want_scale, scale_evidence, weld, weld_distance_m, root, facing_margin)
    except Exception:
        _remove_new(before)
        raise


def _normalize_all(objs, raw, hint, turn_deg, plate, recipe, generator, want_scale, scale_evidence, weld, weld_distance_m, root, facing_margin=None):
    out, receipts, unchanged = [], [], True
    assembly, worlds, pivot_args = None, {}, {}
    if len(objs) > 1:
        # A file's meshes share one source frame. Capture it before baking any
        # ancestor, and choose one origin for the whole imported assembly.
        if plate and turn_deg is None and not recipe and generator != "lampway_tool":
            raise C.FeatureError("assembly facing needs one shared turn_deg or a recipe turn; per-piece plate registration would change assembly placement")
        turn, _ = _decide_frame(turn_deg, recipe, "", generator, root)
        worlds = {o.as_pointer(): o.matrix_world.copy() for o in objs}
        lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
        A = _rz(turn)
        for o in objs:
            node = o
            while node is not None:
                if node.constraints or node.animation_data:
                    raise C.FeatureError("animated or constrained assembly transforms need an explicit static copy before mesh normalization")
                node = node.parent
            co = np.empty(len(o.data.vertices) * 3)
            o.data.vertices.foreach_get("co", co)
            if not len(co):
                raise C.FeatureError(f"assembly member {o.name} has no vertices")
            W = np.asarray(worlds[o.as_pointer()])
            V = (co.reshape(-1, 3) @ W[:3, :3].T + W[:3, 3]) @ A.T
            lo, hi = np.minimum(lo, V.min(0)), np.maximum(hi, V.max(0))
        off = np.array([-(lo[0]+hi[0])/2, -(lo[1]+hi[1])/2, -lo[2]])
        assembly = {"members": len(objs), "pivot_rule": "bbox_bottom_centre", "offset_m": _r9(off),
                    "turned_bbox_min_m": _r9(lo), "turned_bbox_max_m": _r9(hi), "turn_deg": turn}
        pivot_args = {"pivot": "source_origin", "pivot_offset": off, "assembly": assembly}
        def depth(o):
            n = 0
            while o.parent is not None:
                n += 1
                o = o.parent
            return n
        objs = sorted(objs, key=depth)  # parents finish before child world matrices are restored
        plate = ""
    for o in objs:
        if assembly is not None:
            o.matrix_world = worlds[o.as_pointer()]
            bpy.context.view_layer.update()
        before = o.get("lw_canon")
        doc, rbytes = normalize_object(o, turn_deg=turn_deg, generator=generator or "unknown", raw=raw, path_hint=hint, want_scale=want_scale,
                                       scale_evidence=scale_evidence, weld=weld, weld_distance_m=weld_distance_m, recipe=recipe, plate=plate, root=root, facing_margin=facing_margin, **pivot_args)
        out.append(o.name)
        if rbytes is not None:
            unchanged = False
            rel = Path("canon") / "receipts" / f"{doc['canonical_sha256'][:12]}.json"
            (Path(root) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(root) / rel).write_bytes(rbytes)
            receipts.append(str(rel))
        elif before is None:
            unchanged = False
    return {"objects": out, "receipt_path": receipts[0] if receipts else None, "receipts": receipts, "unchanged": unchanged}
