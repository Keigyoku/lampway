"""Typed definitions for the batch tools that had none (facelift contract 07: the Way draws a form from a tool's definition, so a
tool without one had no form). Each is written from its script's own usage line and argparse (scripts/<path> in
mixar.modules.lampway_tools), positional arguments in order, flags as the script names them; descriptions are the scripts' own
home lines. Four of the thirteen already had a typed in-app definition, which the Way now offers instead (uv_score, bake_maps,
material_bake_export, asset_catalog_export: scripts/lampway/facelift/tool_specs.py FEATURES). render_textured is not here: it
needs a .blend before -P, which api.run_tool does not pass."""

from .tool_defs import Def, P

_PATHS = " Paths are relative to the project root."

BATCH_FORM_DEFS = [
    Def("lampway_clay_view", "Orthographic clay render of a mesh from a cardinal view (mesh-paint input), camera recorded." + _PATHS, [
        P("mesh", desc="The mesh (fbx)", required=True), P("out", desc="The PNG written", required=True),
        P("view", desc="Front | Back | Left | Right", required=True), P("res", "integer", "Image size in pixels", required=True),
        P("turn", "number", "Turn about Z in degrees, default -90", flag="--turn")], batch="clay_view"),
    Def("lampway_mesh_paint_set", "Projection plate set from mesh-paint results: picked painted views with their clay-render alpha." + _PATHS, [
        P("clay_dir", desc="The directory with clay_<View>.png", required=True), P("out", desc="The set's output directory", required=True),
        P("picks", "array", "View=image pairs, e.g. Front=a.png Back=b.png", required=True)], batch="mesh_paint_set"),
    Def("lampway_relief_project", "Project the view reliefs (relief_gen.py depth PNGs) onto a UV atlas as a detail height map." + _PATHS, [
        P("mesh_npz", desc="The piece's UV mesh (npz)", required=True), P("views_dir", desc="The relief views", required=True),
        P("v3_dir", desc="The V3 design plates", required=True), P("out_dir", required=True),
        P("res", "integer", "Atlas size"), P("strength_m", "number", "Relief height in metres"), P("preblur_px", "number", "Blur before projecting"),
        P("fine_dir", desc="A second, finer relief set"), P("fine_w", "number", "The fine set's weight")], batch="relief_project"),
    Def("lampway_material_masks", "Material masks (gold, plate, red, linen, embroidery, leather) for a parts set's shared UV atlas from the "
        "projected V3 colour." + _PATHS, [
        P("projection_out_dir", desc="The projection's output directory", required=True), P("owner", desc="The owner map (npy)", required=True),
        P("recipe", desc="The parts recipe (json)", required=True), P("out_dir"), P("mesh_npz")], batch="material_masks"),
    Def("lampway_uv_patches", "UV islands for patch faces, packed into the atlas free space with the original islands locked." + _PATHS, [
        P("mesh", desc="The patched mesh (fbx)", required=True), P("orig", desc="orig_poly.npy: source face per polygon, -1 = patch", required=True),
        P("out", desc="The fbx written", required=True), P("margin", "number", "Island margin, default 0.002", flag="--margin"),
        P("angle", "number", "Smart UV angle, default 66", flag="--angle"), P("max_flip", "number", "Largest flipped share, default 0.01", flag="--max-flip")],
        batch="uv_patches"),
    Def("lampway_patch_holes", "Apply the user's mesh QA rulings: delete ruled faces, patch ruled holes with curved fills; writes a new "
        "mesh and owner map." + _PATHS, [
        P("mesh", required=True), P("owner", desc="owner_poly.npy", required=True), P("recipe", required=True),
        P("cands", desc="The QA candidates.json", required=True), P("decisions", desc="The rulings (decisions.jsonl)", required=True),
        P("out", desc="Output prefix", required=True), P("deletions", flag="--deletions"), P("session", flag="--session"),
        P("turn", "number", "Turn about Z, default -90", flag="--turn"), P("edge_cm", "number", "Patch edge length, default 1.5", flag="--edge-cm"),
        P("relax", "integer", "Relax iterations, default 150", flag="--relax"), P("match_mm", "number", "Match distance, default 2", flag="--match-mm"),
        P("owner_override", "array", "part overrides", flag="--owner-override", repeat=True),
        P("bridge_cm", "number", "Bridge length, default 6", flag="--bridge-cm"),
        P("relabel_orig", desc='json {"relabels": [{"faces_orig": [...], "to": part, "why": ...}]}: ruled labels by source face id', flag="--relabel-orig"),
        P("relabel", "array", "FROM:TO:WITH: faces labelled FROM on small shells that also carry WITH faces become TO", flag="--relabel", repeat=True)],
        batch="patch_holes"),
    Def("lampway_robust_weight_transfer", "Fill the weights of unmatched vertices by a biharmonic solve over the robust Laplacian (robust "
        "skin-weight transfer, inpainting half)." + _PATHS, [
        P("in_npz", desc="V, F, matched, W", required=True), P("out_npz", required=True),
        P("mode", desc="point | surface, default point")], batch="robust_weight_transfer"),
    Def("lampway_mesh_qa_batch", "Mesh QA candidates (open loops, floating shells) with typed descriptors and review renders, as a batch "
        "run on files." + _PATHS, [
        P("mesh", required=True), P("owner", desc="owner_poly.npy", required=True), P("recipe", required=True), P("out", desc="Output directory", required=True),
        P("turn", "number", "Turn about Z, default 0", flag="--turn"), P("min_perimeter", "number", "Smallest loop perimeter, default 0.15", flag="--min-perimeter"),
        P("max_shell_tris", "integer", "Largest floating shell, default 400", flag="--max-shell-tris"),
        P("float_mm", "number", "Floating distance, default 3", flag="--float-mm"), P("delete_polys", flag="--delete-polys"),
        P("no_render", "boolean", "Descriptors only, no EEVEE renders", flag="--no-render")], batch="mesh_qa"),
]
