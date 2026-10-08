# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""ue_export: one canonical export path per asset type, with receipts (specs/ue_parity/contracts/ue_export.md).

The input is CANONICAL only (specs/canon/normalization/SCHEMA.md, lampway.body/1: metres, right-handed, +Z up, front -Y,
transforms applied): an object whose transform is not applied, a negative scale or a scene that is not in metres is refused,
never fixed here. The UE interchange frame (centimetres, left-handed) is reached only through the adapter, which is the FBX
exporter with the settings below and measured skeletal convention recipes plus UE Interchange's scene conversion; the receipt states that map as expected until a
live UE run proves it (M-GEO-01). Texture colour spaces and the normal convention come from the declared roles (pbr_pack's
merge.json), never guessed.

Each mesh is triangulated ONCE, on a temporary copy, by ``triangulate`` (fixed quad method), so the bake and the export can share
triangles: ``triangles_sha256`` hashes that list, a bake receipt naming other triangles is refused. ``content_sha256`` is the
FBX with its CreationTimeStamp zeroed (fbx_bytes)."""

import hashlib
import json
import shutil
from pathlib import Path

import bmesh
import bpy

from ..features import common as C
from ..features import fit_export as FE
from . import cube as CB
from . import fbx_bytes as FX
from . import material_group as MG
from . import material_map as MM
from . import profile as PR

SCHEMA = "lampway.ue-export/1"
TYPES = ("skinned_piece", "static_prop", "animation", "texture_set")
QUAD_METHOD, NGON_METHOD = "FIXED", "EAR_CLIP"
UV_EPS = 1e-6
MORPH_MIN_M = 0.00015                          # UE drops morph deltas under 0.015 cm
_MESH = dict(use_selection=True, apply_unit_scale=True, global_scale=1.0, apply_scale_options="FBX_SCALE_NONE", primary_bone_axis="Z",
             secondary_bone_axis="X", axis_forward="-Z", axis_up="Y", add_leaf_bones=False, mesh_smooth_type="FACE", use_tspace=True, use_triangles=True, bake_anim=False,
             path_mode="COPY", embed_textures=False)
SETTINGS = {
    "skinned_piece": dict(_MESH, object_types={"ARMATURE", "MESH"}),
    "static_prop": dict(_MESH, object_types={"MESH"}),
    "animation": dict(object_types={"ARMATURE"}, use_selection=True, apply_unit_scale=True, global_scale=1.0, apply_scale_options="FBX_SCALE_NONE",
                      primary_bone_axis="Z", secondary_bone_axis="X", add_leaf_bones=False, bake_anim=True, bake_anim_step=1.0,
                      bake_anim_simplify_factor=0.0, bake_anim_use_all_actions=False, bake_anim_force_startend_keying=True,
                      bake_anim_use_nla_strips=False, path_mode="COPY", embed_textures=False),   # NLA strips on (the default) exports no keys without strips: measured
    "texture_set": {},
}
UE_TEXTURES = {"BaseColor.png": "TC_Default", "ORM.png": "TC_Masks", "Normal_DX.png": "TC_Normalmap"}
AXES = {"blender_to_ue": [[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], "scale_to_cm": 100, "input_frame": "lampway.body/1",
        "status": "expected (FBX exporter + Interchange convert_scene); proven by M-GEO-01"}


class ExportError(ValueError):
    pass


def _sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _json_settings(s):
    return {k: sorted(v) if isinstance(v, set) else v for k, v in s.items()}


def triangulate(me, quad_method=QUAD_METHOD):
    """Triangulate mesh data in place with the one fixed method the bake and the export share."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method=quad_method, ngon_method=NGON_METHOD)
    bm.to_mesh(me)
    bm.free()
    me.update()


def triangles_sha256(ob, quad_method=QUAD_METHOD) -> str:
    """sha256 of the triangle vertex-index list ``ob`` exports as (int32 LE, polygon order); the object is not changed."""
    me = ob.data.copy()
    try:
        triangulate(me, quad_method)
        return FX.triangles_sha256([v for p in me.polygons for v in p.vertices])
    finally:
        bpy.data.meshes.remove(me)


def _canonical(ob, scene):
    """Refuse what is not canonical input (SCHEMA.md 3: transform applied, metres); nothing is changed here."""
    bpy.context.view_layer.update()                                       # matrix_world is stale until the depsgraph runs
    m = ob.matrix_world
    if m.determinant() < 0:
        raise ExportError(f"{ob.name} has a negative scale: mirrored transforms invert tangent handedness in UE (NRM-08); apply a positive transform first")
    ident = all(abs(m[i][j] - (1.0 if i == j else 0.0)) <= 1e-6 for i in range(4) for j in range(4))
    if not ident:
        raise ExportError(f"{ob.name} is not canonical: its transform is not applied (canonical input is metres, +Z up, transforms applied: "
                          "specs/canon/normalization/SCHEMA.md); apply it, or normalize the asset first")
    us = scene.unit_settings
    if us.system not in ("METRIC", "NONE") or abs(us.scale_length - 1.0) > 1e-9:
        raise ExportError(f"the scene is not in metres (unit system {us.system}, scale {us.scale_length}): canonical input is metres")


def _uv_and_morphs(ob, hero):
    losses = []
    for uv in ob.data.uv_layers:
        co = [c for d in uv.data for c in d.uv]
        if co and (min(co) < -UV_EPS or max(co) > 1 + UV_EPS) and not hero:
            raise ExportError(f"{ob.name}: UV layer {uv.name} leaves [0,1] (min {min(co):.4f}, max {max(co):.4f}): 16-bit UVs lose about 4 texels "
                              "at 4096 outside [0,1]: keep UVs in range or set hero")
    keys = ob.data.shape_keys
    if keys:
        basis = keys.reference_key
        for kb in keys.key_blocks:
            if kb == basis:
                continue
            d = max(((a.co - b.co).length for a, b in zip(kb.data, basis.data)), default=0.0)
            if 0.0 < d < MORPH_MIN_M:
                losses.append({"kind": "shape_key_below_ue_threshold", "shape_key": kb.name, "max_delta_cm": round(d * 100, 6),
                               "why": "UE drops morph deltas under 0.015 cm"})
    return losses


def _declared_textures(tex_dir):
    """The UE texture set of a pbr_pack directory with each file's DECLARED colour space (merge.json); undeclared is refused."""
    d = Path(tex_dir)
    mj = d / "merge.json"
    if not mj.is_file():
        raise ExportError(f"{d} has no merge.json: the texture colour spaces are declared by pbr_pack, never guessed")
    merge = json.loads(mj.read_text(encoding="utf-8"))
    cs = merge.get("colorspace") or {}
    files = {}
    for name, comp in UE_TEXTURES.items():
        p = d / name
        if not p.is_file():
            if name == "Normal_DX.png" and (d / "Normal_GL.png").is_file():
                raise ExportError("the set has Normal_GL only: UE reads DirectX normals; pack with convention dx (pbr_pack)")
            continue
        stem = name[:-4]
        if stem not in cs:
            raise ExportError(f"{name} has no colour space in merge.json: declare the colour space: pbr_pack writes it")
        row = {"sha256": _sha(p), "colorspace": cs[stem], "compression": comp}
        if stem == "Normal_DX":
            row["convention"] = "DirectX"
        if stem == "ORM":
            row["channels"] = merge.get("orm")
        files[name] = (p, row)
    if not files:
        raise ExportError(f"{d} holds none of {sorted(UE_TEXTURES)}")
    return merge, files


def _ue_import(type_, hero, frame_rate, textures):
    return {"recompute_normals": False, "recompute_tangents": False, "use_mikktspace": True, "high_precision_tangents": hero,
            "full_precision_uvs": hero, "high_precision_weights": hero, "flip_normal_green": False,
            "textures": {n[:-4]: {"srgb": r["colorspace"] == "sRGB", "compression": r["compression"]} for n, r in textures.items()},
            "frame_rate": frame_rate, "import_morph_targets": type_ in ("skinned_piece", "static_prop"), "convert_scene": True,
            "force_front_x": False, "convert_scene_unit": True, "combine_skeletal": False}


def _write_fbx(path, settings, select, active):
    vl = bpy.context.view_layer
    sel = [o for o in vl.objects if o.select_get()]
    act = vl.objects.active
    try:
        for o in vl.objects:
            o.select_set(False)
        for o in select:
            o.select_set(True)
        vl.objects.active = active
        bpy.ops.export_scene.fbx(filepath=str(path), **settings)
    finally:
        for o in vl.objects:
            o.select_set(o in sel)
        vl.objects.active = act


def _mesh_export(ob, extra, settings, fbx):
    """Export a triangulated temporary copy under the object's own name; the original is renamed for the moment and restored."""
    name = ob.name
    copy = ob.copy()
    copy.data = ob.data.copy()
    for coll in ob.users_collection:
        coll.objects.link(copy)
    try:
        triangulate(copy.data)
        tri = FX.triangles_sha256([v for p in copy.data.polygons for v in p.vertices])
        ob.name = name + "__lw_ue_src"
        copy.name = name
        _write_fbx(fbx, settings, [copy] + extra, extra[0] if extra else copy)
        return tri
    finally:
        me = copy.data
        bpy.data.objects.remove(copy, do_unlink=True)
        bpy.data.meshes.remove(me)
        ob.name = name


def _material(ob, profile, merge, files):
    mat = next((s.material for s in ob.material_slots if s.material), None) if ob else None
    if mat is None:
        return None
    try:
        return MM.translate(MG.read_spec(mat), profile, mode="export" if merge else "report", merge=merge, files=sorted(files) if merge else None)
    except MM.TranslationError as exc:
        return {"material": mat.name, "error": str(exc)}


def _animation_skeleton_readback(path, arm, container_name):
    """Raw units and topology only: skeleton-only clips cannot prove skin binds."""
    from ..features import rig_export as RE, export_checks as EC
    from ..rig_tools import core as RC
    unit = RE.unit_scale_factor(path)
    carriers = EC.fbx_container_scale_failures(path)
    scales = EC.fbx_bone_scale(path)
    scale_failures = {name: scale for name, scale in scales.items()
                      if any(abs(value - 1.0) > RC.BARS["scale"] for value in scale)}
    _version, nodes = FX.parse(path.read_bytes())
    objects = FX._top(nodes, "Objects") or {"children": []}
    from io_scene_fbx.fbx_utils import FBX_KTIME
    import numpy as np
    scene = bpy.context.scene
    # Pinned writer fbx_animations_do: scene-frame keys, start_zero=False,
    # integral ktime conversion. Counts alone cannot prove keys at each frame.
    expected_times = (np.arange(scene.frame_start, scene.frame_end + 1, dtype=float)
                      / (scene.render.fps / scene.render.fps_base) * FBX_KTIME).astype(np.int64).tolist()
    curves = [FX._child(node, "KeyTime") for node in objects["children"] if node["name"] == "AnimationCurve"]
    times_match = bool(curves) and all(curve and curve["props"][0]["value"] == expected_times for curve in curves)
    models, parents = {}, {}
    for model in objects["children"]:
        if model["name"] != "Model":
            continue
        ident, name, kind = [p["value"] for p in model["props"][:3]]
        if ident in models:
            raise ExportError("duplicate animation skeleton model identity")
        models[ident] = {"name": name.split(b"\x00")[0].decode(), "kind": kind}
    connections = FX._top(nodes, "Connections") or {"children": []}
    for edge in connections["children"]:
        if edge["name"] != "C" or len(edge["props"]) < 3:
            continue
        kind, child, parent = [p["value"] for p in edge["props"][:3]]
        if kind == b"OO" and child in models and (parent in models or parent == 0):
            if child in parents:
                raise ExportError("ambiguous animation skeleton parent")
            parents[child] = parent
    bones = {ident: model for ident, model in models.items() if model["kind"] == b"LimbNode"}
    hierarchy, invalid_containers = {}, []
    for ident, bone in bones.items():
        parent = parents.get(ident)
        if parent in bones:
            hierarchy[bone["name"]] = bones[parent]["name"]
        else:
            hierarchy[bone["name"]] = None
            model = models.get(parent)
            if not (model and model["kind"] == b"Null" and model["name"] == container_name
                    and parents.get(parent) == 0):
                invalid_containers.append(bone["name"])
    expected = {bone.name: bone.parent.name if bone.parent else None for bone in arm.data.bones}
    same = (bool(expected) and hierarchy == expected and len(hierarchy) == len(bones)
            and set(scales) == set(expected) and not invalid_containers)
    return {"ok": unit == 1.0 and not carriers and not scale_failures and same and times_match,
            "scope": "raw_skeleton_units_topology_and_key_times", "unit_scale_factor": unit,
            "container_scale_failures": carriers, "bone_scale_failures": scale_failures,
            "hierarchy_matches": same, "bones_compared": len(bones),
            "key_times_match": times_match, "frame_range": [scene.frame_start, scene.frame_end],
            "invalid_containers": invalid_containers,
            "bind_acceptance": "unverified; skeleton-only animation has no independent skin cluster binds",
            "engine_acceptance": "unverified; requires actual native Unreal animation capture"}


def run(type_, object_, armature, action, out_dir, textures, body, frame_rate, hero, fmt, validation, bind_check, bake_receipt, profile_path,
        root, bone_axis=None, allow_unverified=False):
    if type_ not in TYPES:
        raise ExportError(f"type {type_!r}: one canonical path per type: {', '.join(TYPES)}")
    if fmt != "fbx":
        if type_ == "skinned_piece" and fmt in ("gltf", "glb"):
            raise ExportError("UE 5.8 reads only 4 influences from glTF: FBX is the path")
        raise ExportError(f"format {fmt!r}: the canonical path for {type_} is fbx")
    profile = PR.load(profile_path or PR.DEFAULT_PROFILE)
    hero = (profile["export"]["precision"] == "hero") if hero is None else bool(hero)
    out = Path(root) / out_dir
    if out.exists():
        raise ExportError(f"{out_dir} exists: a tag directory is never reused (pick a new one)")
    scene = bpy.context.scene
    settings = dict(SETTINGS[type_])
    merge, files, losses, gate, ob, arm, tri = None, {}, [], None, None, None, None
    convention, recipe, export_space = None, None, None
    if textures:
        merge, files = _declared_textures(Path(root) / textures if not Path(textures).is_absolute() else textures)
    if type_ in ("skinned_piece", "static_prop"):
        ob = C.need_object(object_)
        _canonical(ob, scene)
        if type_ == "skinned_piece":
            arm = C.need_object(armature, "ARMATURE")
            _canonical(arm, scene)
            gate = FE.gates(ob, body, None, validation, bind_check, allow_unverified, root)
            settings, convention, recipe = FE.export_settings(arm, settings, bone_axis)
        losses = _uv_and_morphs(ob, hero)
        if bake_receipt:
            want = json.loads((Path(root) / bake_receipt).read_text(encoding="utf-8")).get("triangles_sha256")
            if want != triangles_sha256(ob):
                raise ExportError("the normal map was baked on other triangles: re-bake after triangulation (the bake receipt's triangles_sha256 differs)")
    elif type_ == "animation":
        arm = C.need_object(armature, "ARMATURE")
        _canonical(arm, scene)
        fps = scene.render.fps / scene.render.fps_base
        if frame_rate is None:
            raise ExportError("an animation export needs frame_rate")
        if abs(fps - float(frame_rate)) > 1e-6:
            raise ExportError(f"frame_rate {frame_rate} differs from the scene's {fps:g} fps: set the scene rate (no resampling here)")
        if action and bpy.data.actions.get(action) is None:
            raise ExportError(f"no action named {action!r}")
        clip = bpy.data.actions.get(action) if action else (arm.animation_data.action if arm.animation_data else None)
        if clip is None:
            raise ExportError("animation export needs one baked action: run lampway_rig_bake first")
        settings, convention, recipe = FE.export_settings(arm, settings, bone_axis)

    out.mkdir(parents=True)
    rb, fbx = {}, None
    if type_ != "texture_set":
        fbx = out / f"{(ob or arm).name}.fbx"
        if ob is not None:
            if arm is not None:
                from ..features import rig_export_space as ES
                with ES.centimetre_copies(arm, [ob], None, settings, container_name=recipe["ue_armature_container"]) as prepared:
                    export_space = prepared["receipt"]
                    settings = prepared["exporter"]
                    tri = _mesh_export(prepared["meshes"][0], [prepared["armature"]], settings, fbx)
            else:
                tri = _mesh_export(ob, [], settings, fbx)
        else:
            from ..features import rig_export_space as ES
            with ES.centimetre_copies(arm, [], clip, settings, container_name=recipe["ue_armature_container"]) as prepared:
                export_space = prepared["receipt"]
                settings = prepared["exporter"]
                _write_fbx(fbx, settings, [prepared["armature"]], prepared["armature"])
        data = fbx.read_bytes()
        f = FX.facts(data)
        if ob is not None:
            g = f["geometries"][0] if f["geometries"] else {"layers": []}
            rb = {"tangents_present": "LayerElementTangent" in g["layers"], "binormals_present": "LayerElementBinormal" in g["layers"],
                  "smoothing_present": "LayerElementSmoothing" in g["layers"], "all_triangles": bool(g.get("all_triangles")),
                  "triangles_match": g.get("triangles_sha256") == tri}
            if gate:
                rb["joints"] = FE._readback(fbx, gate["joints"], convention, settings)
        else:
            rb = {"frames": scene.frame_end - scene.frame_start + 1, "animated_curves": len(f["curve_key_counts"]),
                  "keys_per_curve": sorted(set(f["curve_key_counts"])),
                  "skeleton": _animation_skeleton_readback(fbx, arm, recipe["ue_armature_container"])}
    if files:
        (out / "Textures").mkdir()
        for name, (p, _row) in files.items():
            shutil.copyfile(p, out / "Textures" / name)
        shutil.copyfile(Path(p).parent / "merge.json", out / "Textures" / "merge.json")
    tex_rows = {n: r for n, (_p, r) in files.items()}
    mat = _material(ob, profile, merge, files)
    import io_scene_fbx
    rec = {"schema": SCHEMA, "type": type_, "blender": {"version": bpy.app.version_string, "fbx_io": ".".join(map(str, io_scene_fbx.bl_info["version"]))},
           "settings": _json_settings(settings), "recipe_selection": recipe, "export_space": export_space, "axes": AXES, "hero": hero, "readback": rb, "textures": tex_rows, "material": mat,
           "profile_sha256": PR.sha256(profile), "ue_look_cube": CB.receipt(CB.validate(profile)), "losses": losses + ([{"kind": "material", **{k: v for k, v in mat.items() if k in ("dropped", "clamped")}}] if mat and mat.get("dropped") else []),
           "gates": {"validation_counts": gate["counts"], "unverified_roles": gate["roles"], "mesh_sha256": gate["mesh_sha256"]} if gate else None}
    if fbx:
        rec.update(file_sha256=_sha(fbx), content_sha256=FX.content_sha256(fbx.read_bytes()), triangles_sha256=tri)
    imp = _ue_import(type_, hero, frame_rate, tex_rows)
    (out / "export.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    (out / "ue_import.json").write_text(json.dumps(imp, indent=1), encoding="utf-8")
    lines = [f"# {(ob or arm).name if (ob or arm) else Path(out_dir).name} ({type_})", "", "Exported by lampway_ue_export; import it in UE with ue_import.json and nothing else.", "",
             "## Files (sha256)"] + ([f"- {fbx.name}: {rec['file_sha256']} (content, timestamp zeroed: {rec['content_sha256']})"] if fbx else []) + [
             f"- Textures/{n}: {r['sha256']} ({r['colorspace']}{', ' + r['convention'] if 'convention' in r else ''})" for n, r in tex_rows.items()] + [
             "", "## Settings", json.dumps(rec["settings"], sort_keys=True), "", "## Frame",
             "Input: lampway.body/1 (metres, +Z up, front -Y, transforms applied). UE: expected (x, -y, z) x 100 through the FBX exporter and Interchange; unproven until M-GEO-01."]
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = {"out_dir": str(out), "readback": rb, "losses": rec["losses"], **{k: rec[k] for k in ("file_sha256", "content_sha256", "triangles_sha256") if k in rec}}
    failed = [k for k in ("tangents_present", "binormals_present", "all_triangles", "triangles_match") if k in rb and not rb[k]]
    if rb.get("joints") and not rb["joints"].get("ok"):
        failed.append("joints")
    if type_ == "animation" and rb.get("keys_per_curve") != [rb.get("frames")]:
        failed.append("keys_per_curve")
    if type_ == "animation" and not rb["skeleton"]["ok"]:
        failed.append("animation_skeleton")
    if failed:
        return dict(result, ok=False, error=f"read-back failed ({', '.join(failed)}): the written file is not what this path promises; see readback")
    return dict(result, ok=True)
