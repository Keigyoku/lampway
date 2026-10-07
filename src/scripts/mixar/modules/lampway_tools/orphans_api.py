# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The orphan tools' api functions (STATUS.md ORPHANS). They register through ``api.tool`` like every other tool, and ``api`` star-imports this module
just before it freezes TOOL_FUNCS, so ``api.call(name, ...)`` reaches them. Kept apart so api.py does not grow past reading."""

from .api import _p, _settings, tool  # noqa: F401  (api is mid-import here: these names are already bound)
from .canon_door import LEGACY, NONE, Need

# The door (specs/canon/normalization DOOR.md 2): every tool declares what it consumes; a mesh argument must be canonical. ALL = the three
# scale states (scale-free tools); REAL = absolute thresholds (metres, millimetres, px per metre). An optional texture or skeleton argument of a
# mesh tool is not declared yet: no texture or skeleton normalizer exists (it joins the declaration when one lands).
ALL = ("real", "generator_normalised", "unknown")
REAL = ("real",)
GEO = ("mesh", "part", "rigged_mesh")
_TEX = "pre-door lane merged: texture input awaits the texture normalizer"
_LIST = "pre-door lane merged: a list of objects awaits the list form of the door"
_GEOM, _MESH_PART = GEO, ("mesh", "part")      # the canon lane's names for the same kinds
_ANY = ALL

__all__ = []


def _generate_image(*a, **kw):
    """The image slot (the server's image_gen); tests replace this name."""
    from .features import jobs_client
    return jobs_client.generate_image(*a, **kw)


def _export(fn):
    __all__.append(fn.__name__)
    return fn


@_export
@tool(consumes={"object": Need(kind=GEO, scale=ALL)})
def side_label_check(object, declared_side=None, facing="-Y", armature="", body_midline_x=None, pair="", asym_threshold=0.02):
    """Is a piece labelled left/right on the FIGURE's left/right (not the camera's), and is it not a mirrored copy of its pair? Read-only."""
    from .features import handedness as _H
    return _H.side_label_check(object, declared_side, facing, armature, body_midline_x, pair, asym_threshold)


@_export
@tool(consumes={"object": Need(kind=GEO, scale=ALL)})
def mirror_pair(object, design_symmetric=None, plane="x", origin="bounds_centre", rename=None, mirror_uv=False, weights="swap", force=False, body_midline_x=None,
                armature="", asym_threshold=0.02, piece="", by="agent", captain_words=""):
    """The opposite piece by a mirror across a stated plane, on a COPY, only after the typed decision design_symmetric; a decision row in <root>/<piece>/decisions.jsonl."""
    from .features import handedness as _H
    return _H.mirror_pair(object, str(_settings().project_root), design_symmetric, plane, origin, rename, mirror_uv, weights, force, body_midline_x, armature,
                          asym_threshold, piece, by, captain_words)


@_export
@tool(consumes={"object": Need(kind=GEO, scale=ALL)})
def scale_to_measure(object, target=None, reference_object="", apply=True, unit_scale=1.0, children="include", rollback=False):
    """Put an object's dimension at a measured real size (target {axis, length_m} or a reference object's), applied safely; rollback restores lw_prev_scale."""
    from .features import scale_measure as _SM
    return _SM.scale_to_measure(object, target, reference_object, apply, unit_scale, children, rollback)


@_export
@tool(consumes={"object": Need(kind=("mesh", "part"), scale=REAL)})
def uv_check(object, action="measure", target_density_px_m=None, texture_size=2048, tolerance=0.15, tile_from=None, tile_to=None, islands=None, dry_run=True,
             mirror_axis="x", match_tolerance=0.003, res=512, discard_texture=False, limit=50, offset=0, full=False):
    """UV measurements per island (density, overlaps stacked vs accidental, space usage, orientation, UDIM tiles) and two dry-run-by-default edits (udim_move, stack).
    measure lists a page of islands (limit, default 50, from offset; island_count and next_offset); full=true lists them all."""
    from .features import uv_check as _UC
    return _UC.run(object, action, target_density_px_m, texture_size, tolerance, tile_from, tile_to, islands, dry_run, mirror_axis, match_tolerance, res, discard_texture,
                   limit, offset, full)


@_export
@tool(consumes={"objects": Need(kind=_GEOM, scale=_ANY)})
def render_condition_passes(objects, camera="auto", passes=None, size=1024, out_dir="condition", engine="workbench"):
    """The conditioning images from ONE camera: flat id colour per object (with its palette), depth (nearer brighter), edges and clay; light engines only."""
    from .features import condition_passes as _CP
    s_ = _settings()
    return _CP.run(objects, str(s_.project_root), camera, passes, size, _p(out_dir, s_.project_root), engine)


@_export
@tool(consumes={"object": Need(kind=("mesh", "part"), scale=ALL)})
def image_material_id(piece, object="", view="Front", palette=None, source="parts", recipe="", owner="", part_materials=None, design_plate="", live=False, size=768,
                      out_dir="material_id"):
    """A flat material-ID map: source parts renders each part in its material's palette colour from the clay camera (exact, free); source model is a gated DRAFT."""
    from .features import material_id as _MI
    s_ = _settings()
    return _MI.run(piece, str(s_.project_root), object, view, palette, source, _p(recipe, s_.project_root), _p(owner, s_.project_root), part_materials,
                   _p(design_plate, s_.project_root), live, size, _p(out_dir, s_.project_root))


@_export
@tool(consumes={"object": Need(kind=("mesh", "part"), scale=ALL)})
def parts_material_slots(object, recipe, owner="", by="part", name=""):
    """On a copy <object>_slots: the piece's one material becomes one slot per part (or per material class), each a copy sharing the images, faces by part."""
    from .features import parts_slots as _PS
    s_ = _settings()
    return _PS.run(object, _p(recipe, s_.project_root), _p(owner, s_.project_root), by, name)


@_export
@tool(consumes={"object": Need(kind=("mesh", "part"), scale=ALL)})
def zone_sheet(object, by="material_slot", views=None, size=768, out="zones/sheet.png", recipe=""):
    """One image where every material slot, part, segment or vertex group is a flat colour with a number, and its legend; answer with a zone number."""
    from .features import zones as _Z
    s_ = _settings()
    return _Z.zone_sheet(object, by, views, size, _p(out, s_.project_root), _p(recipe, s_.project_root))


@_export
@tool(consumes={"object": Need(kind=("mesh", "part"), scale=ALL, welded=True)})
def mesh_region_extract(object, region, cap="fill_holes", keep_in_source=True, name="", recipe=""):
    """A chosen region (bbox, a lasso in a view, vertex group, material slot or zone number) as its own object from copies, capped or filled; the source is unchanged."""
    from .features import region_extract as _RX
    return _RX.run(object, region, cap, keep_in_source, name, _p(recipe))


@_export
@tool(consumes={"object": Need(kind=("mesh", "part"), scale=REAL, welded=True)})
def mesh_local_edit(object, region, engine="deform", op="move", delta=None, falloff_m=0.01, instruction="", side="", anchors=None):
    """One bounded edit of a derivative with a lineage, on a copy <object>_edit (deform with falloff; studio:tripo = the exact-box Edit Mesh plan), then its locality."""
    from .features import local_edit as _LE
    return _LE.mesh_local_edit(object, region, str(_settings().project_root), engine, op, delta, falloff_m, instruction, side, anchors)


@_export
@tool(consumes=LEGACY("its after is another tool's output, and outputs are not re-stamped yet (produces=Inherit is not built): a Need would refuse every real use"))
def edit_locality_check(before, after, region=None, margin_m=0.005, tolerance_m=0.0005):
    """What a region edit changed OUTSIDE its region: moved vertices, faces, open edges, UVs, materials, dimensions, weights; read-only."""
    from .features import local_edit as _LE
    return _LE.edit_locality_check(before, after, region, margin_m, tolerance_m)


@_export
@tool(consumes={"objects": Need(kind=_MESH_PART, scale=("real",), welded=True)})
def mesh_join_boolean(op, objects, voxel_m="coarse_first", clearance_mm=None, connector=None, name=""):
    """Fuse (join + voxel remesh), union, difference with clearance, or plug/socket connectors with a measured gap; on copies, originals kept."""
    from .features import join_boolean as _JB
    return _JB.run(op, objects, voxel_m, clearance_mm, connector, name)


@_export
@tool(consumes={"pieces": Need(kind=_MESH_PART, scale=("real",))})
def multi_piece_material(action, pieces=None, atlas_res=4096, individual_res=None, density_floor_ratio=0.7, proxy="", atlas="", out_dir="mpm", res=None, keep_proxy=False,
                         name=""):
    """One material across pieces: merge copies into a proxy with a shared atlas, texture it once, transfer the atlas back to each piece's original UVs."""
    from .features import multi_piece as _MP
    s_ = _settings()
    return _MP.run(action, str(s_.project_root), pieces, atlas_res, individual_res, density_floor_ratio, proxy, _p(atlas, s_.project_root),
                   _p(out_dir, s_.project_root), res, keep_proxy, name)


@_export
@tool(consumes=LEGACY("image FILE paths: the door resolves datablocks and canon sidecars, not project-relative paths, and normalize_texture stamps the datablock only"))
def seamless_tile(src="", out="", mode="grain", size=1024, flatten=False, cell_px=None, prompt="", live=False):
    """A seamless tile BUILT by rules (motif crop, quilt, cross-fade, or an exact motif cell) from a sheet, never repainted by a model, and gated; prompt makes the
    sheet through the image slot (purpose tile) first, a dry run unless live."""
    from .pipeline import seamless_tile as _ST
    s_ = _settings()
    if not out:
        raise ValueError("out names the tile (a project path; .png, _mosaic.png and .qa.json are written beside it)")
    out_p = _p(out, s_.project_root)
    sheet = None
    if prompt:
        if not live:
            return {"dry_run": True, "prompt": prompt, "purpose": "tile", "cost_note": "one image on the server's tile purpose (gpt-image-2.5-flare measured $0.0238 at 1024 px)",
                    "how": "live=true makes the sheet (only when the user asked for it); the tile is then built and gated by rules"}
        import os as _os
        sheet = _os.path.splitext(out_p)[0] + "_sheet.png"
        if _os.path.exists(sheet):
            raise ValueError(f"{sheet} exists: never overwritten")
        _os.makedirs(_os.path.dirname(sheet), exist_ok=True)
        data = _generate_image(prompt, None, 1, params_extra={"purpose": "tile"})[0]
        with open(sheet, "wb") as fh:
            fh.write(data)
        src_p = sheet
    else:
        if not src:
            raise ValueError("give src (a sheet under the project root) or prompt (make one through the image slot)")
        src_p = _p(src, s_.project_root)
    try:
        res = _ST.build(src_p, out_p, mode, size, flatten, cell_px)
    except _ST.TileRefused as exc:
        raise ValueError(str(exc)) from None
    if sheet:
        res["sheet"] = sheet
    return res


@_export
@tool(consumes=LEGACY("directories of image files: the door checks one asset (or a list of them) per argument"))
def relief_tiles(stage, v3_dir="", tile_dir="", out_dir="", views=None, fine=3072):
    """Multi-scale relief: make = tile each plate view so the relief generator sees ornament at full scale; stitch = the tile reliefs' fine band per view."""
    from .pipeline import relief_tiles as _RT
    s_ = _settings()
    if stage == "make":
        rec = _RT.make(_p(v3_dir, s_.project_root), _p(tile_dir, s_.project_root), list(views or []) or None)
        rec["next"] = "run the Studio action tripo.relief (studio_plan) on the tile images, into the tile folder, then relief_tiles stage=stitch"
        return rec
    if stage == "stitch":
        return _RT.stitch(_p(v3_dir, s_.project_root), _p(tile_dir, s_.project_root), _p(out_dir, s_.project_root), fine)
    raise ValueError("stage is make | stitch")


@_export
@tool(consumes=LEGACY("image FILE paths: the door resolves datablocks and canon sidecars, not project-relative paths, and normalize_texture stamps the datablock only"))
def image_upscale(image, target=4096, method="lanczos", live=False, prompt="", suffix=""):
    """Raise a plate to 2048..4096 px without changing it: lanczos (exact baseline), model (gated for faithfulness, a dry run until live) or tripo (a plan)."""
    from .pipeline import upscale as _UP
    try:
        return _UP.upscale(_p(image), target, method, live, prompt, _generate_image, suffix)
    except _UP.UpscaleRefused as exc:
        raise ValueError(str(exc)) from None


def _record_ledger(row):
    """A ledger row through the server; a failure is returned in the result, never raised over images already made."""
    from .features import jobs_client
    try:
        return jobs_client.record_ledger(row)
    except Exception as exc:  # noqa: BLE001
        return {"recorded": False, "error": str(exc)}


@_export
@tool(consumes=LEGACY("image FILE paths: the door resolves datablocks and canon sidecars, not project-relative paths, and normalize_texture stamps the datablock only"))
def reference_pack(stage, asset, approved_reference, components=None, pose="T", views=None, left_description="", right_description="", model_purpose="plates",
                   count=4, live=False, image="", sheet_views=None):
    """The four-stage reference method, gated: sheet (left and right named) -> audit against the approved source -> extract parts -> only the missing views."""
    from .pipeline import reference_pack as _RP
    s_ = _settings()
    try:
        return _RP.run_stage(stage, str(s_.project_root), asset, _p(approved_reference, s_.project_root), components, pose, views, left_description, right_description,
                             model_purpose, count, live, _p(image, s_.project_root), sheet_views, _generate_image, _record_ledger)
    except _RP.ReferenceRefused as exc:
        raise ValueError(str(exc)) from None


@_export
@tool(consumes={"existing_object": Need(kind=("mesh", "part"), scale=ALL)})
def workflow_reference_to_asset(piece, reference="", route="existing", existing_object="", steps=None, gates=None, target="unreal", run=False, resume=False,
                                pieces=None, body_refs=None, example_sheet=""):
    """One piece through the existing tools in order (prep, retopo, uv, ... export), stopping at every gate; a spend step stays blocked for the user's click;
    every step is a row in <piece>/decisions.jsonl. route=moodboard defines the captain's moodboard chain as the workflow graph <piece> (reference = the armor
    design, body_refs = the MetaHuman turnarounds, pieces = the parts to carry through, example_sheet = a turnaround sheet to follow) and returns its plan;
    each generation is then confirmed one node at a time (workflow_graph action=confirm)."""
    import json
    from . import api as _API
    from .features import ref_to_asset as _RA
    s_ = _settings()
    if route == "moodboard":
        from . import workflow_graph as _WG
        from .features import moodboard_chain as _MC
        if not reference or not body_refs:
            raise ValueError("route moodboard needs reference (the armor design: Image B of the adaptation) and body_refs (the MetaHuman turnaround images)")
        g = _WG.Graphs(s_.project_root)
        inputs = {"armor_design": reference, "body_refs": list(body_refs) if isinstance(body_refs, (list, tuple)) else [body_refs]}
        if example_sheet:
            inputs["example_sheet"] = example_sheet
        g.define(piece, _MC.graph(pieces or [], name=piece, example_sheet=bool(example_sheet)), inputs)
        return {"route": "moodboard", "graph": piece, **g.plan(piece),
                "help": [f"workflow_graph action=confirm name={piece} from_node=anatomy generates the first image (one spend, on the user's word)",
                         f"workflow_graph action=run name={piece} shows what is confirmed and what waits"]}

    def _call(fn, args):
        return _API.call(fn, json.dumps(args))
    return _RA.run(str(s_.project_root), piece, _p(reference, s_.project_root) if reference else "", route, existing_object, steps, gates, target, run, resume, _call)


@_export
@tool(consumes=NONE("reads the Client's own mark records and frozen frames: no asset"))
def scribble_read(include_image=False, include_sent=True):
    """The Scribble marks in this scene: per mark its kind, the object it resolved to, its frame region and NDC anchor; the mode (point or sketch); the
    Client's own prose summary. include_image writes the frozen annotated frame under <root>/scribble/. Read-only."""
    from .features import scribble_read as _SR
    return _SR.read(str(_settings().project_root), bool(include_image), bool(include_sent))


@_export
@tool(consumes=LEGACY("image FILE paths: the door resolves datablocks and canon sidecars, not project-relative paths, and normalize_texture stamps the datablock only"))
def image_matte(action, src, out, background="magenta", key="border", opaque=None, clear=None, despill=True, split=None, recipe="", canvas_size=None,
                verify_out=""):
    """Deterministic chroma matting of generated plates: remove (key to transparent RGBA, the key read from each image's border ring; sheet split
    by recipe) | center (integer shifts onto one canvas; canvas_size int or "common") | verify (decode, CRC, hashes, preserved pixels, border, light/dark
    contact sheet). Writes NEW directories under the project root; sources are never touched."""
    from .pipeline import image_matte as _IM
    root = str(_settings().project_root)
    s, o = _p(src, root), _p(out, root)
    if action == "remove":
        return _IM.remove(s, o, opaque, clear, bool(despill), background=background, key=key, split=split, sheet_recipe=_p(recipe, root) or None)
    if action == "center":
        if isinstance(canvas_size, str) and canvas_size.isdigit():
            canvas_size = int(canvas_size)
        return _IM.center(s, o, canvas_size)
    if action == "verify":
        return _IM.verify(o, s, _p(verify_out, root) or o + ".verify")
    raise ValueError("action is remove | center | verify")


def _render_prompt(template, variables=None, model=""):
    """The server's prompt library renders the template (POST /app/prompts/render); tests replace this name."""
    from .features import jobs_client
    return jobs_client._request("POST", "/app/prompts/render", {"id": template, "variables": variables or {}, "model": model or None})


@_export
@tool(consumes=LEGACY("image FILE paths: the door resolves datablocks and canon sidecars, not project-relative paths, and normalize_texture stamps the datablock only"))
def prompt_image(template, variables=None, references=None, out_dir="prompt_images", count=1, live=False, model="", piece=""):
    """One image from a built-in or user prompt template: the server renders it, the references are sent in the template's own input order (references
    {role: path or [paths]}, e.g. character_body = Image A, design_plate = Image B). Dry run unless live (one generation = one spend: only on the user's word;
    in a workflow graph a spend node runs only through confirm). Saves under the project root and writes a ledger row."""
    import hashlib
    import os
    from pathlib import Path
    s_ = _settings()
    root = str(s_.project_root)
    r = _render_prompt(template, variables, model)
    roles = [i["role"] for i in r.get("inputs_required") or []]
    given = dict(references or {})
    unknown = sorted(set(given) - set(roles))
    if unknown:
        raise ValueError(f"{template} takes the references {roles}; not {unknown}")
    ordered = []
    for i in r.get("inputs_required") or []:
        v = given.get(i["role"])
        paths = [] if v in (None, "", []) else (list(v) if isinstance(v, (list, tuple)) else [v])
        if i.get("required") and not paths:
            raise ValueError(f"{template} needs {i['role']}: {i['description']}")
        ordered += [(i["role"], _p(p, root)) for p in paths]
    for _, p in ordered:
        if not os.path.isfile(p):
            raise ValueError(f"no reference image at {p}")
    plan = {"template": r.get("template", template), "prompt": r["prompt"], "references": [{"role": k, "file": p} for k, p in ordered], "count": int(count)}
    if not live:
        return {**plan, "live": False, "help": ["live=true generates it: one spend, only on the user's word"]}
    blobs = [Path(p).read_bytes() for _, p in ordered]
    imgs = _generate_image(r["prompt"], blobs[0] if blobs else None, int(count), extra_references=blobs[1:], params_extra=r.get("params") or None)
    d = Path(_p(out_dir, root))
    d.mkdir(parents=True, exist_ok=True)
    stem = str(r.get("template", template)).replace("@", "-")
    files = []
    for k, data in enumerate(imgs, 1):
        f = d / f"{stem}-{k}.png"
        f.write_bytes(data)
        files.append(str(f))
    led = _record_ledger({"piece": piece or stem, "stage": "image", "studio": "local", "seed": "not_exposed", "by": "agent", "model_version": None,
                          "settings": {"template": plan["template"], "variables": variables or {}, "count": int(count), "image_slot": "server image_gen"},
                          "prompt_hash": hashlib.sha256(r["prompt"].encode()).hexdigest(), "reference_hashes": [hashlib.sha256(b).hexdigest() for b in blobs],
                          "output_hashes": [hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in files], "cost": {},
                          "reason": "prompt_image: the image job carries its own price row"})
    return {**plan, "live": True, "image": files[0], "images": files, "ledger": led}


@_export
@tool(consumes={"object": Need(kind=GEO, scale=ALL)})
def recon_measure(object, plates, size=256):
    """A reconstruction measured against its approved plates: the best of the 24 axis orientations by mean silhouette IoU (front, left, top), the IoU of
    every given view (front, right, back, left, top, bottom: the wearer's axes), the cavity and shell ratios through the crown, the crest-fin width and
    length ratios from the top view, and the albedo's left/right luminance ratio. Read-only."""
    from .features import recon_measure as _RCM
    return _RCM.run(object, plates, str(_settings().project_root), size)


@_export
@tool(consumes=NONE("stages files byte for byte from a manifest that declares each one's role and colour space: it reads no asset"))
def texture_library_stage(manifest, staging_root, library_listing=""):
    """Stage an additive, versioned delta for a texture library from a manifest (JSON under the project root): immutable files with sha256, lineage inside
    the library, unknowns null, colour spaces declared, no inferred PBR, nothing under an approved folder; a catalog and the INDEX of the delta. Nothing is
    uploaded: the staging root is local."""
    import json
    from .pipeline import texlib_stage as _TS
    root = str(_settings().project_root)
    m = json.load(open(_p(manifest, root)))
    for f in m.get("files") or []:
        if isinstance(f, dict) and f.get("src"):
            f["src"] = _p(f["src"], root)
    listing = json.load(open(_p(library_listing, root))) if library_listing else None
    try:
        return _TS.stage(m, _p(staging_root, root), listing)
    except _TS.StageRefused as exc:
        raise ValueError(str(exc)) from None
