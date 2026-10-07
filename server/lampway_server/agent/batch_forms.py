"""Typed definitions for the batch tools that had none (facelift contract 07: the Way draws a form from a tool's definition, so a
tool without one had no form). Each is written from its script's own usage line and argparse (scripts/<path> in
mixar.modules.lampway_tools), positional arguments in order, flags as the script names them; descriptions are the scripts' own
home lines. Four of the thirteen already had a typed in-app definition, which the Way now offers instead (uv_score, bake_maps,
material_bake_export, asset_catalog_export: scripts/lampway/facelift/tool_specs.py FEATURES). render_textured's first field is
its .blend, which the runner opens before the script (runner.Tool.opens_blend)."""

from .tool_defs import Def, P

_PATHS = " Paths are relative to the project root."

BATCH_FORM_DEFS = [
    # the captain's ruling 6 (2026-10-06): the last three runner tools without a form
    Def("lampway_rtmw_detect", "RTMW whole-body 2D keypoints per frame (rtmlib and onnxruntime, the weights read from disk)." + _PATHS, [
        P("out", desc="The keypoints written (json)", required=True), P("onnx", desc="The RTMW model (onnx)", required=True),
        P("frames", "array", "The frames (png), in order", required=True),
        P("input", desc="The model's input size, WxH (for example 288x384)", flag="--input")], batch="rtmw_detect"),
    Def("lampway_proportion_fit", "Clearance-fit overlays of pieces on a body (fragile as a ranking: a look, not a verdict)." + _PATHS, [
        P("out_dir", desc="Where the overlays are written", required=True), P("body", desc="The body (glb)", required=True),
        P("pieces", "array", "piece:turn pairs, a mesh and its turn about Z in degrees (for example helmet.glb:-90)", required=True)],
        batch="proportion_fit"),
    Def("lampway_render_textured", "The textured look of a parts set on its shared atlas, rendered from the parts set's .blend." + _PATHS, [
        P("blend", desc="The parts set's .blend (Blender opens it before the script)", required=True),
        P("projection_dir", desc="The projection's output directory (the atlas)", required=True),
        P("out_dir", desc="Where the renders are written", required=True),
        P("object", desc="The object to render, default chest_smartmesh_r6")], batch="render_textured"),
    Def("lampway_clay_view", "Orthographic clay render of a mesh from a cardinal view (mesh-paint input), camera recorded." + _PATHS, [
        P("mesh", desc="The mesh (fbx)", required=True), P("out", desc="The PNG written", required=True),
        P("view", desc="Front | Back | Left | Right", required=True), P("res", "integer", "Image size in pixels", required=True, minimum=64, maximum=8192),
        P("turn", "number", "Turn about Z in degrees, default -90", flag="--turn", minimum=-360, maximum=360)], batch="clay_view"),
    Def("lampway_mesh_paint_set", "Projection plate set from mesh-paint results: picked painted views with their clay-render alpha." + _PATHS, [
        P("clay_dir", desc="The directory with clay_<View>.png", required=True), P("out", desc="The set's output directory", required=True),
        P("picks", "array", "View=image pairs, e.g. Front=a.png Back=b.png", required=True)], batch="mesh_paint_set"),
    Def("lampway_relief_project", "Project the view reliefs (relief_gen.py depth PNGs) onto a UV atlas as a detail height map." + _PATHS, [
        P("mesh_npz", desc="The piece's UV mesh (npz)", required=True), P("views_dir", desc="The relief views", required=True),
        P("v3_dir", desc="The V3 design plates", required=True), P("out_dir", desc="Where the height map is written", required=True),
        P("res", "integer", "Atlas size, default 2048", minimum=64, maximum=16384),
        P("strength_m", "number", "Relief height in metres", minimum=0, maximum=1),
        P("preblur_px", "number", "Blur before projecting, in pixels", minimum=0, maximum=256),
        P("fine_dir", desc="A second, finer relief set"), P("fine_w", "number", "The fine set's weight", minimum=0, maximum=1)], batch="relief_project"),
    Def("lampway_material_masks", "Material masks (gold, plate, red, linen, embroidery, leather) for a parts set's shared UV atlas from the "
        "projected V3 colour." + _PATHS, [
        P("projection_out_dir", desc="The projection's output directory", required=True), P("owner", desc="The owner map (npy)", required=True),
        P("recipe", desc="The parts recipe (json)", required=True),
        P("out_dir", desc="Where the masks are written, default the projection's directory"),
        P("mesh_npz", desc="The piece's mesh (npz): turns on the shell vote within metal parts")], batch="material_masks"),
    Def("lampway_uv_patches", "UV islands for patch faces, packed into the atlas free space with the original islands locked." + _PATHS, [
        P("mesh", desc="The patched mesh (fbx)", required=True), P("orig", desc="orig_poly.npy: source face per polygon, -1 = patch", required=True),
        P("out", desc="The fbx written", required=True), P("margin", "number", "Island margin, default 0.002", flag="--margin", minimum=0, maximum=0.1),
        P("angle", "number", "Smart UV angle in degrees, default 66", flag="--angle", minimum=1, maximum=89),
        P("max_flip", "number", "Largest flipped share, default 0.01", flag="--max-flip", minimum=0, maximum=1)],
        batch="uv_patches"),
    Def("lampway_patch_holes", "Apply the user's mesh QA rulings: delete ruled faces, patch ruled holes with curved fills; writes a new "
        "mesh and owner map." + _PATHS, [
        P("mesh", desc="The parts mesh (fbx)", required=True), P("owner", desc="owner_poly.npy", required=True),
        P("recipe", desc="The parts recipe (json)", required=True),
        P("cands", desc="The QA candidates.json", required=True), P("decisions", desc="The rulings (decisions.jsonl)", required=True),
        P("out", desc="Output prefix", required=True),
        P("deletions", desc='deletions.json: {"polys": [...]} faces ruled deleted (original indices), "refill" the ones to cover again',
          flag="--deletions"),
        P("session", desc="Read only this QA session's rulings", flag="--session"),
        P("turn", "number", "Turn about Z in degrees, default -90", flag="--turn", minimum=-360, maximum=360),
        P("edge_cm", "number", "Patch edge length in cm, default 1.5", flag="--edge-cm", minimum=0.01, maximum=100),
        P("relax", "integer", "Relax iterations, default 150", flag="--relax", minimum=0, maximum=10000),
        P("match_mm", "number", "Match distance in mm, default 2", flag="--match-mm", minimum=0, maximum=1000),
        P("owner_override", "array", "part overrides", flag="--owner-override", repeat=True),
        P("bridge_cm", "number", "Bridge length in cm, default 6", flag="--bridge-cm", minimum=0, maximum=1000),
        P("relabel_orig", desc='json {"relabels": [{"faces_orig": [...], "to": part, "why": ...}]}: ruled labels by source face id', flag="--relabel-orig"),
        P("relabel", "array", "FROM:TO:WITH: faces labelled FROM on small shells that also carry WITH faces become TO", flag="--relabel", repeat=True)],
        batch="patch_holes"),
    Def("lampway_robust_weight_transfer", "Fill the weights of unmatched vertices by a biharmonic solve over the robust Laplacian (robust "
        "skin-weight transfer, inpainting half)." + _PATHS, [
        P("in_npz", desc="V, F, matched, W", required=True), P("out_npz", desc="The weights written (npz)", required=True),
        P("mode", desc="point | surface, default point")], batch="robust_weight_transfer"),
    Def("lampway_mesh_qa_batch", "Mesh QA candidates (open loops, floating shells) with typed descriptors and review renders, as a batch "
        "run on files." + _PATHS, [
        P("mesh", desc="The parts mesh (fbx)", required=True), P("owner", desc="owner_poly.npy", required=True),
        P("recipe", desc="The parts recipe (json)", required=True), P("out", desc="Output directory", required=True),
        P("turn", "number", "Turn about Z in degrees, default 0", flag="--turn", minimum=-360, maximum=360),
        P("min_perimeter", "number", "Smallest loop perimeter in metres, default 0.15", flag="--min-perimeter", minimum=0, maximum=1000),
        P("max_shell_tris", "integer", "Largest floating shell in triangles, default 400", flag="--max-shell-tris", minimum=0, maximum=10000000),
        P("float_mm", "number", "Floating distance in mm, default 3", flag="--float-mm", minimum=0, maximum=1000),
        P("delete_polys", desc='deletions.json: {"polys": [...]} faces already ruled deleted, removed before the analysis', flag="--delete-polys"),
        P("no_render", "boolean", "Descriptors only, no EEVEE renders", flag="--no-render")], batch="mesh_qa"),
]
