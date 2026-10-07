# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Retopology. Proven code: Blender's QuadriFlow (all-quad, field-aligned), voxel remesh as the fallback; the result is a NEW
object ``<name>_retopo`` and the original is never touched (the docs: keep it until the replacement passes your checks)."""

import math
import os

import bpy
import bmesh

from . import common as C


def _surface_area(ob) -> float:
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    area = sum(f.calc_area() for f in bm.faces)
    bm.free()
    return area


def _voxel(new, target_faces):
    size = math.sqrt(max(_surface_area(new), 1e-12) / target_faces)
    new.data.remesh_voxel_size = size
    new.data.remesh_voxel_adaptivity = 0.0
    C.activate(new)
    bpy.ops.object.voxel_remesh()
    new.data.update()


def _write_obj(ob, path):
    """The object's evaluated mesh (modifiers applied), triangulated, in local coordinates."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    with open(path, "w") as f:
        for v in me.vertices:
            f.write("v %.9g %.9g %.9g\n" % tuple(v.co))
        for t in me.loop_triangles:
            f.write("f %d %d %d\n" % tuple(i + 1 for i in t.vertices))
    ev.to_mesh_clear()


def _read_obj(path):
    verts, faces = [], []
    with open(path) as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "v":
                verts.append(tuple(float(x) for x in parts[1:4]))
            elif parts[0] == "f":
                faces.append(tuple(int(x.split("/")[0]) - 1 for x in parts[1:]))
    return verts, faces


def _range(name, v, lo, hi):
    if not lo <= float(v) <= hi:
        raise C.FeatureError(f"{name} must be between {lo:g} and {hi:g}")
    return float(v)


def _autoremesher(src, new, target_faces, engine_bin, p, root, nice):
    from .. import runner
    if not engine_bin or not os.path.isfile(engine_bin):
        raise C.FeatureError("autoremesher is not configured: set settings autoremesher_bin to the lampway-quadremesh (or AppImage) path; the app never downloads it "
                             "(build it with native/quadremesh/build.sh)")
    out_dir = os.path.join(root, "retopo")
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, src.name)
    inp, outp, rep = base + ".obj", base + "_out.obj", base + ".report.txt"
    _write_obj(src, inp)
    cmd = [engine_bin, "--input", inp, "--output", outp, "--report", rep, "--target-quads", str(target_faces), "--edge-scaling", p["edge_scaling"], "--sharp-edge", p["sharp_edge"],
           "--smooth-normal", p["smooth_normal"], "--adaptivity", p["adaptivity"], "--anisotropy", p["anisotropy"]] + (["--hard-surface"] if p["hard_surface"] else [])
    version = runner.run_exe([engine_bin, "--version"], 10, root, nice)
    res = runner.run_exe(cmd, p["timeout"], root, nice)
    if res["timed_out"]:
        raise C.FeatureError(f"autoremesher timed out after {p['timeout']}s; lower target_faces or raise timeout")
    if res["rc"] != 0 or not os.path.isfile(outp):
        tail = "\n".join(res["log"][-20:])
        raise _EngineFailed(f"autoremesher exited with code {res['rc']}; the last 20 log lines:\n{tail}\nrun lampway_mesh_prep first (non-manifold or open input is the usual cause) or pass fallback=true for the voxel remesh")
    verts, faces = _read_obj(outp)
    if not faces:
        raise _EngineFailed("autoremesher wrote no faces; run lampway_mesh_prep first or pass fallback=true for the voxel remesh")
    me = bpy.data.meshes.new(new.name)
    me.from_pydata(verts, [], faces)
    me.update()
    old = new.data
    new.data = me
    bpy.data.meshes.remove(old)
    for poly in me.polygons:
        poly.use_smooth = True
    quads = sum(1 for f in faces if len(f) == 4)
    return {"engine_version": (version["log"][0] if version["rc"] == 0 and version["log"] else "unknown"),
            "engine_report": {"quads": quads, "non_quads": len(faces) - quads, "vertices": len(verts), "seconds": res["seconds"], "hard_surface": bool(p["hard_surface"])},
            "has_uv": False, "note": "the result has no UV layer; run lampway_uv_unwrap"}


class _EngineFailed(C.FeatureError):
    pass


WELD_M = 1e-5            # canon_geom.WELD_M: the parts are welded back along their shared boundary by position


def _per_part(src, target_faces, symmetry, preserve_sharp, attribute):
    """canon 12 B.1 / INV-12.3: each part (an INT face attribute) remeshed ALONE by QuadriFlow with its boundary preserved, the result
    labelled with its part, then the parts joined and welded by position: no face can span two parts."""
    me = src.data
    if attribute not in me.attributes or me.attributes[attribute].domain != "FACE" or me.attributes[attribute].data_type != "INT":
        raise C.FeatureError(f"per_part needs the part map: an INT face attribute {attribute!r} on {src.name} (segment_mesh writes one); "
                             f"a whole-shell remesh crosses the cuts between parts (canon 12 INV-12.3)")
    labels = [d.value for d in me.attributes[attribute].data]
    area = {}
    for poly, lab in zip(me.polygons, labels):
        area[lab] = area.get(lab, 0.0) + poly.area
    total = sum(area.values()) or 1.0
    pieces, report = [], {}
    try:
        for lab in sorted(area):
            c = src.copy()
            c.data = me.copy()
            bpy.context.scene.collection.objects.link(c)
            pieces.append(c)
            bm = bmesh.new()
            bm.from_mesh(c.data)
            lay = bm.faces.layers.int[attribute]
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[lay] != lab], context="FACES")
            bm.to_mesh(c.data)
            bm.free()
            n0 = len(c.data.polygons)
            C.activate(c)
            goal = max(50, int(round(target_faces * area[lab] / total)))
            try:
                ran = bpy.ops.object.quadriflow_remesh(mode="FACES", target_faces=goal, use_mesh_symmetry=bool(symmetry), use_preserve_sharp=bool(preserve_sharp),
                                                       use_preserve_boundary=True, seed=0)
            except RuntimeError as exc:
                raise C.FeatureError(f"part {lab}: QuadriFlow refused it ({str(exc).strip()[:160]}): fix the part (lampway_mesh_prep); per_part has no "
                                     f"voxel fallback (the voxel remesh closes a part's boundary)") from None
            if "FINISHED" not in ran or not any(len(q.vertices) == 4 for q in c.data.polygons):
                raise C.FeatureError(f"part {lab}: QuadriFlow returned {sorted(ran)} and left it as it was ({n0} faces); per_part has no voxel fallback")
            a = c.data.attributes.get(attribute) or c.data.attributes.new(attribute, "INT", "FACE")
            a.data.foreach_set("value", [lab] * len(c.data.polygons))
            report[str(lab)] = {"faces": len(c.data.polygons), "target": goal, "source_faces": n0}
        new = pieces[0]
        if len(pieces) > 1:
            C.activate(new)                                   # activate deselects everything: select the other parts after it
            for o in pieces[1:]:
                o.select_set(True)
            bpy.ops.object.join()
        pieces = [new]
    except Exception:
        for o in pieces:
            if o.name in bpy.data.objects:
                bpy.data.objects.remove(o)
        bpy.context.view_layer.objects.active = src
        raise
    new.name = src.name + "_retopo"
    bm = bmesh.new()
    bm.from_mesh(new.data)
    n0 = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=WELD_M)
    welded = n0 - len(bm.verts)
    bm.to_mesh(new.data)
    bm.free()
    new.data.update()
    return new, {"attribute": attribute, "parts": report, "welded_boundary_vertices": welded}


def retopo(object, target_faces=2000, method="quadriflow", engine="algorithmic", symmetry=False, keep_original_visible=True, adaptivity=1.0, anisotropy=1.0, sharp_edge=90.0,
           smooth_normal=0.0, edge_scaling=1.0, timeout=900, fallback=False, hard_surface=False, engine_bin="", root="", nice=15, preserve_sharp=True,
           per_part=False, part_attribute="part"):
    if engine != "algorithmic":
        return C.studio_slot("retopo", engine)
    if method not in ("quadriflow", "voxel", "autoremesher"):
        raise C.FeatureError(f"unknown method {method!r}; the methods are quadriflow, voxel and autoremesher")
    target_faces = int(target_faces)
    if method == "autoremesher":
        if symmetry:
            raise C.FeatureError("autoremesher has no symmetry option; use quadriflow with symmetry=true")
        if not 50 <= target_faces <= 2000000:
            raise C.FeatureError("target_faces must be between 50 and 2000000")
        p = {"adaptivity": _range("adaptivity", adaptivity, 0, 1), "anisotropy": _range("anisotropy", anisotropy, 0, 1), "sharp_edge": _range("sharp_edge", sharp_edge, 30, 180),
             "smooth_normal": _range("smooth_normal", smooth_normal, 0, 180), "edge_scaling": _range("edge_scaling", edge_scaling, 1, 4), "timeout": int(_range("timeout", timeout, 10, 3600)),
             "hard_surface": bool(hard_surface)}
    if target_faces < 50:
        raise C.FeatureError(f"target_faces {target_faces} is too small (at least 50)")
    src = C.need_object(object)
    if target_faces > 3 * len(src.data.polygons):                       # canon INV-12.5, every method
        raise C.FeatureError(f"target {target_faces} exceeds 3x the source ({len(src.data.polygons)}): a remesher cannot invent detail")
    if per_part:
        if method != "quadriflow":
            raise C.FeatureError("per_part remeshes with QuadriFlow (each part's boundary preserved); the voxel and AutoRemesher paths do not keep a boundary")
        new, pp = _per_part(src, target_faces, symmetry, preserve_sharp, part_attribute)
        bpy.context.view_layer.update()
        if not keep_original_visible:
            src.hide_set(True)
        return {"object": new.name, "source": src.name, "method": "quadriflow", "requested_method": method, "target_faces": target_faces,
                "preserve_sharp": bool(preserve_sharp), "per_part": pp, "report": C.mesh_report(new, ref=src), "source_faces": len(src.data.polygons)}
    new = C.duplicate(src, "_retopo")
    used = method
    extra = {}
    if method == "autoremesher":
        try:
            extra = _autoremesher(src, new, target_faces, engine_bin, p, root, nice)
        except _EngineFailed as exc:
            if not fallback:
                bpy.data.objects.remove(new)
                raise
            used = "voxel"
            extra = {"note": f"autoremesher failed and the voxel remesh was used (fallback=true): {str(exc).splitlines()[0]}"}
        except C.FeatureError:
            bpy.data.objects.remove(new)
            raise
    elif method == "quadriflow":
        C.activate(new)
        n0 = len(new.data.polygons)
        try:
            ran = bpy.ops.object.quadriflow_remesh(mode="FACES", target_faces=target_faces, use_mesh_symmetry=bool(symmetry),
                                                   use_preserve_sharp=bool(preserve_sharp), use_preserve_boundary=True, seed=0)
            why = None if ("FINISHED" in ran and any(len(p.vertices) == 4 for p in new.data.polygons)) else \
                f"QuadriFlow returned {sorted(ran)} and left the mesh as it was ({n0} faces, no quads)"
        except RuntimeError as exc:
            why = f"QuadriFlow refused the mesh: {str(exc).strip()[:200]}"
        if why:                                              # canon 12: never a silent fallback (QuadriFlow refuses a non-manifold input)
            if not fallback:
                bpy.data.objects.remove(new)
                bpy.context.view_layer.objects.active = src     # the removed copy was the active object
                raise C.FeatureError(f"{why}: fix the mesh (lampway_mesh_prep), or pass fallback=true to use the voxel remesh instead")
            used = "voxel"
            extra = {"note": f"{why}; the voxel remesh was used (fallback=true)"}
        extra["preserve_sharp"] = bool(preserve_sharp)          # canon 12 B.3: hard-surface edges kept (measured: 1 m box 3.98 -> 1.41 mm)
    if used == "voxel":
        _voxel(new, target_faces)
    bpy.context.view_layer.update()
    if not keep_original_visible:
        src.hide_set(True)
    return {"object": new.name, "source": src.name, "method": used, "requested_method": method, "target_faces": target_faces,
            "report": C.mesh_report(new, ref=src), "source_faces": len(src.data.polygons), **extra}
