"""The orphan tools' definitions (STATUS.md ORPHANS): Defs like every other Lampway tool, kept in their own file. ``lampway_tools`` appends ORPHAN_DEFS to
its DEFS before it builds BY_NAME and SPECS, so they reach the agent's registry, the MCP endpoint and the generated tool pages the same way."""

from .lampway_tools import Def, P, _PATHS  # noqa: F401  (lampway_tools is mid-import here: these names are already bound)

ORPHAN_DEFS = [
    Def("lampway_side_label_check", "Is a piece labelled left/right on the FIGURE's left/right, not the camera's, and is it not a mirrored copy of its pair? Read-only. "
        "The lateral axis is world X: the figure's left is +X while it faces -Y (default) and -X while it faces +Y. The side is the sign of the piece's area-weighted "
        "surface centroid against the body midline (body_midline_x, or the mean of the armature's paired _l/_r bone heads); a piece whose lateral extent holds the midline "
        "and whose centroid lies within a quarter of it is center; paired = one mesh holding both sides. declared_side defaults to the name's suffix (_l/_r, Left/Right). "
        "Returns measured_side, centroid_offset_m, mirror_asymmetry (mean surface distance to its own mirror, fraction of the diagonal), pair {is_mirror_of, "
        "chamfer_to_mirrored_pair} when `pair` names the other piece, pass and reasons. asym_threshold (default 0.02) is UNVERIFIED. Thumb side, palm side and finger "
        "count are not measured from a mesh (the vision slot's). Refused: left/right with neither body_midline_x nor an armature, an unapplied rotation or scale "
        "(apply transform first), an unknown side or facing.",
        [P("object", required=True, desc="the mesh"), P("declared_side", desc="left | right | center | paired (default: from the name)"), P("facing", desc="-Y (default) | +Y"),
         P("armature", desc="an armature with paired _l/_r bones: its midline"), P("body_midline_x", "number", "the body's midline x in metres"),
         P("pair", desc="the other piece of the pair"), P("asym_threshold", "number", "fraction of the diagonal, default 0.02 [UNVERIFIED]")], api="side_label_check"),
    Def("lampway_mirror_pair", "Make the opposite-side piece by a mirror across a stated plane, on a COPY (the source is untouched), ONLY after the typed decision "
        "design_symmetric=true: the user says the design is symmetric; this tool never assumes it, and wearer-left/right asymmetry must survive. The copy's mesh is mirrored in "
        "world space, its normals flipped back outward, its transform identity; its name and its sided vertex groups swap sides (rename {from, to}, default _l -> _r, either "
        "way round; weights drop removes the groups); mirror_uv flips U (default off). origin: 'bounds_centre' (default: mirror in place), 'body_midline' (body_midline_x or "
        "the armature's paired bones; plane x) or 'x,y,z'. The piece's own measured asymmetry (mean surface distance to its mirror, fraction of the diagonal) above "
        "asym_threshold (0.02) is refused unless force=true. Every mirror appends a decision row (question design_symmetric, decider captain when by=captain, else model) to "
        "<root>/<piece>/decisions.jsonl. Refused: no design_symmetric, design_symmetric false, an unknown plane, origin or weights mode.",
        [P("object", required=True), P("design_symmetric", "boolean", "the user's typed decision that the design is symmetric (required)"), P("plane", desc="x (default) | y | z"),
         P("origin", desc="bounds_centre (default) | body_midline | 'x,y,z'"), P("rename", "object", "{from, to}, default {from: _l, to: _r}"), P("mirror_uv", "boolean", "flip U, default false"),
         P("weights", desc="swap (default) | drop"), P("force", "boolean", "mirror despite a measured asymmetry (the user confirmed)"), P("body_midline_x", "number"),
         P("armature", desc="for origin body_midline"), P("asym_threshold", "number", "default 0.02 [UNVERIFIED]"), P("piece", desc="the decision folder, default the object name"),
         P("by", desc="agent (default) | captain: who decided"), P("captain_words", desc="the user's words, quoted into the decision row")], api="mirror_pair"),
    Def("lampway_scale_to_measure", "Put an object at its measured real size: ONE uniform factor that makes its dimension on target.axis (x | y | z | max) equal target.length_m "
        "(metres, 0.001..1000) or the same dimension of reference_object, in scene units of unit_scale metres (1.0; 0.01 for a centimetre FBX). apply (default true) then "
        "moves the scale into the mesh; it is REFUSED on a skinned mesh (an Armature modifier or an armature parent), on an armature, on a mesh with shape keys and on a "
        "mesh shared by other objects: scale the armature object only, or pass apply=false. children include (default: they follow) | skip (they keep their world "
        "placement). The transform before the change is kept as the object's lw_prev_scale; rollback=true restores it. Returns dimensions_before/after, factor, applied, "
        "unit_scale. The named object is changed (that is the point).",
        [P("object", required=True), P("target", "object", "{axis: x|y|z|max, length_m}"), P("reference_object", desc="match this object's dimension on target.axis"),
         P("apply", "boolean", "default true"), P("unit_scale", "number", "metres per scene unit, default 1.0"), P("children", desc="include (default) | skip"),
         P("rollback", "boolean", "restore the transform recorded in lw_prev_scale")], api="scale_to_measure"),
    Def("lampway_uv_check", "UV checks per island on the object's ACTIVE UV layer (island ids are uv_score's). measure: faces, UV and 3D area, texel density in px/m at "
        "texture_size, UV bbox and the UDIM tiles each island touches, the tiles used and the islands CROSSING a tile border, density mean and CV. select_by_density: "
        "selects the faces of the islands off target_density_px_m (default the mean) by more than tolerance (0.15). overlaps: rasterised per tile at res (512): the "
        "overlapping fraction and the overlapping island pairs split into stacked (the two share their UV outline: deliberate) and accidental. space_usage: coverage "
        "of tile 1001 and every used tile, and the empty cells of a 16 x 16 grid. orientation: flipped islands (winding against the majority) and mirrored pairs "
        "(3D geometry mirrored across mirror_axis within match_tolerance metres: the stack candidates). Edits, DRY RUNS unless dry_run=false, one undo step: udim_move "
        "(islands to tile_to by whole tiles; tile_from filters; 1001..1099 [UNVERIFIED limit]) and stack (each mirrored twin takes its partner's UVs vertex by vertex; "
        "named islands pairs that are not mirror twins are refused by name). Refused: no UV layer (unwrap first), Edit Mode, over 1M triangles, an edit on a "
        "textured object (texturing comes last: discard_texture=true overrides).",
        [P("object", required=True), P("action", desc="measure (default) | select_by_density | overlaps | space_usage | orientation | udim_move | stack"),
         P("target_density_px_m", "number", "select_by_density: px per metre (default the mean)"), P("texture_size", "integer", "default 2048"),
         P("tolerance", "number", "fraction, default 0.15"), P("tile_from", "integer", "udim_move: only islands in this tile"), P("tile_to", "integer", "udim_move: 1001..1099"),
         P("islands", "array", "island ids (udim_move), or id pairs a, b, c, d (stack)"), P("dry_run", "boolean", "edits: default true"), P("mirror_axis", desc="x (default) | y | z"),
         P("match_tolerance", "number", "metres, 0.0005..0.05, default 0.003"), P("res", "integer", "raster size 64..4096, default 512"),
         P("discard_texture", "boolean", "allow an edit on a textured object")], api="uv_check"),
    Def("lampway_render_condition_passes", "Render a blockout to the conditioning images an image or video model needs, all from ONE camera in a throw-away scene "
        "(your scene, frame and the objects' colours are restored): id = a flat colour per object (Workbench, anti-aliasing off, every pixel snapped to its "
        "object's palette colour; the palette is returned so a prompt can name regions), depth = a ray cast per pixel, 1 - (d - near)/(far - near) with near/far "
        "from the objects' bounds (nearer is brighter, background 0), edge = 1-pixel lines where the id changes or the depth jumps, clay = studio-lit grey. "
        "camera: a scene camera's name or auto (50 mm, 15 degrees above the -Y front, framing the objects). size is the long edge (64..2048; the aspect is your "
        "scene's). Light engines only: workbench (default) or eevee for clay; Cycles is refused. Control-image inputs on the image APIs are [UNVERIFIED]: use "
        "the passes as plain reference images. Nothing is spent." + _PATHS,
        [P("objects", "array", "the mesh objects of the blockout", required=True), P("camera", desc="a camera name | auto (default)"),
         P("passes", "array", "subset of id, depth, edge, clay; default clay, depth, id"), P("size", "integer", "long edge 64..2048, default 1024"),
         P("out_dir", desc="under the project root, default condition"), P("engine", desc="workbench (default) | eevee")], api="render_condition_passes"),
    Def("lampway_image_material_id", "A flat material-ID map (which region is metal, cloth, leather, gold ...) for masks and material assignment, written to "
        "<out_dir>/<piece>/<View>_matid.png. source parts (default; the FACT, free and exact): each polygon takes its part's material (the recipe's class, or "
        "part_materials {part: material}; the part per polygon from owner .npy or the int face attribute 'part'), rendered from the SAME camera as the clay "
        "render in flat Workbench colour with anti-aliasing off, every pixel snapped to the palette; regions report pixels and fractions. source model (a DRAFT, "
        "only when the mesh has no parts): the design_plate goes to the image slot with purpose mask (about $0.10 an image, measured) and the palette in the "
        "prompt; the black line art is filled, the rest quantised to the palette, and the draft is REJECTED under 0.99 conformance; it is named *_draft and never "
        "auto-accepted. live=false (default) is a dry run that sends nothing. palette {material: '#rrggbb'} 2..16 entries is the user's; two colours closer "
        "than dE 60 are refused as indistinguishable. Refused: parts on an unsegmented piece, model without design_plate." + _PATHS,
        [P("piece", required=True), P("object", desc="source parts: the mesh"), P("view", desc="Front (default) | Back | Left | Right | all"),
         P("palette", "object", "{material: '#rrggbb'}", required=True), P("source", desc="parts (default) | model"), P("recipe", desc="parts json (class per part)"),
         P("owner", desc="owner .npy, one part index per polygon"), P("part_materials", "object", "{part: material} overriding the recipe's classes"),
         P("design_plate", desc="source model: the plate image"), P("live", "boolean", "source model: really send (default false: a dry run)"),
         P("size", "integer", "render size, default 768"), P("out_dir", desc="default material_id")], api="image_material_id"),
    Def("lampway_parts_material_slots", "Make the parts of a piece its material SLOTS (the piece pipeline's one-material-per-piece gap): on a COPY <object>_slots "
        "the piece's one material becomes one slot per recipe part (by part, default) or per material class (by class, the recipe's class), each slot a copy "
        "of the material named <material>_<part|class> that SHARES its images (no re-bake, the texels stay), and every face takes its part's slot from owner "
        "(.npy, one part index per polygon) or the int face attribute 'part'. The source keeps its single material. Refused: no part per face, owner indices "
        "outside the recipe, no material." + _PATHS,
        [P("object", required=True), P("recipe", required=True, desc="the parts json"), P("owner", desc="owner .npy (default the face attribute 'part')"),
         P("by", desc="part (default) | class"), P("name", desc="the copy's name, default <object>_slots")], api="parts_material_slots"),
    Def("lampway_zone_sheet", "Show the user which zone is which, as ONE image: every zone of an object (by material_slot, part = the int face attribute 'part' "
        "(names from recipe), segment = the int face attribute 'segment', or vertex_group = faces whose vertices all belong) in a flat colour with its NUMBER "
        "written on it, from the clay camera's views side by side (Workbench, anti-aliasing off, pixels snapped to the zone colours), plus <out>_legend.json "
        "{number, name, faces, rgb}. Ask the user for a zone number; mesh_region_extract and mesh_local_edit take {zone, by}. Refused: fewer than two zones, "
        "by segment with no segment attribute (run segment_mesh first), size outside 256..2048." + _PATHS,
        [P("object", required=True), P("by", desc="material_slot (default) | part | segment | vertex_group"), P("views", "array", "default Front, Back, Left, Right"),
         P("size", "integer", "256..2048, default 768"), P("out", desc="sheet PNG under the project root, default zones/sheet.png"),
         P("recipe", desc="by part: the parts json for the names")], api="zone_sheet"),
    Def("lampway_mesh_region_extract", "Separate a chosen region of a mesh into its own object, from COPIES (the source is never changed): region {bbox: [x0, y0, z0, x1, "
        "y1, z1]} (face centres, world) | {polygon_2d: [[h, v], ...], view} (an X-ray lasso in a cardinal view: Front h=x, Back h=-x, Left h=-y, Right h=y, v=z) "
        "| {vertex_group} | {material_slot: index or name} | {zone, by} (a zone_sheet number). cap fill_holes (default; one face per open loop) | fan (filled "
        "then poked into triangles) | flat (refused on a non-planar loop: use fan) | none. keep_in_source=false also makes <object>_remainder, the rest with "
        "the hole left open for a later join. Returns extracted, remainder, faces, open_loops_before_cap, capped; each new object records the source's "
        "geometry hash and the region (identity anchors are the user's: asset_lineage). Refused: an empty region, a region over 90 % of the faces (that is "
        "the whole mesh), an unknown region kind or cap.",
        [P("object", required=True), P("region", "object", "{bbox} | {polygon_2d, view} | {vertex_group} | {material_slot} | {zone, by}", required=True),
         P("cap", desc="fill_holes (default) | fan | flat | none"), P("keep_in_source", "boolean", "default true: false also writes the remainder"),
         P("name", desc="the extracted object's name, default <object>_region"), P("recipe", desc="zone by part: the parts json")], api="mesh_region_extract"),
    Def("lampway_mesh_local_edit", "Change ONE bounded region of a derivative, on a COPY <object>_edit (the source is untouched); the object must have a lineage "
        "(asset_lineage record) first. engine deform (default): the region (bbox [x0, y0, z0, x1, y1, z1] in object space | vertex_group | face_ids) moves "
        "(delta metres), rotates (delta degrees about the region centre) or scales (delta factors), the rest follows by a smooth falloff of its distance to "
        "the region (falloff_m 0..0.2, default 0.01); no topology change, so counts and UVs survive; edit_locality_check then runs on the region grown by "
        "the falloff and the lineage anchors are verified. engine studio:tripo: the exact-box Edit Mesh retry (Studio action tripo.regen.region, free, the "
        "user's confirm in the Studios panel is its approval flag) answered as a plan with its studio_plan arguments; nothing is clicked; needs side and "
        "the three lineage anchors, plus an instruction. Rodin and Modddif have no driver. Refused: no lineage, an empty region, a region and falloff over "
        "60 % of the vertices (a regeneration: use the smallest region).",
        [P("object", required=True), P("region", "object", "{bbox} | {vertex_group} | {face_ids}", required=True), P("engine", desc="deform (default) | studio:tripo"),
         P("op", desc="move (default) | rotate | scale"), P("delta", "array", "[x, y, z]: metres, degrees or factors"), P("falloff_m", "number", "0..0.2, default 0.01"),
         P("instruction", desc="studio: the region-edit instruction"), P("side", desc="studio: left | right | center"), P("anchors", "array", "studio: the three lineage anchor names")],
        api="mesh_local_edit"),
    Def("lampway_edit_locality_check", "What a region edit changed OUTSIDE its region (read-only): moved vertices (by index on the same topology, else the "
        "distance to the other mesh's surface) beyond tolerance_m (0.0005), faces added or removed outside, open edges (all, and outside), UVs and UV "
        "islands, materials, dimensions and vertex-group weights; pass = nothing moved or changed outside and UVs, materials and weights unchanged, with "
        "reasons. region (a bbox in object space) is required, grown by margin_m (0.005) for the joining context. Refused: no region, different frames "
        "(align with the asset_lineage anchors), an after mesh that lost its UV layer.",
        [P("before", required=True), P("after", required=True), P("region", "array", "[x0, y0, z0, x1, y1, z1] object space", required=True),
         P("margin_m", "number", "0..0.1, default 0.005"), P("tolerance_m", "number", "1e-6..0.01, default 0.0005")], api="edit_locality_check"),
    Def("lampway_mesh_join_boolean", "Fuse, cut and connect parts, always on COPIES (the originals are kept). op join_remesh: the parts joined in world space then a "
        "voxel remesh (joining alone does not fuse surfaces); voxel_m 'coarse_first' (default) remeshes at 4x the fine voxel first (reported) then at the "
        "bounding diagonal / 100, or give a size; refused on a skinned mesh (remesh destroys weights; bind afterwards). op union: objects[0] + the rest, exact "
        "Boolean. op difference: objects[0] - the rest, each cutter first INFLATED so every face moves out by clearance_mm (required; 0 for an exact cut). op "
        "connector {kind plug_socket | pin, at [x, y, z] on the joint plane, size_mm diameter, axis default +Z}: a plug cylinder (2 x size long) united with "
        "objects[0] and the same cylinder grown by clearance_mm cut from objects[1]; the fit gap is MEASURED (gap_mm_measured; clearance_mm is required: it "
        "is the user's printer / paint tolerance). Returns faces, shells, manifold. Boolean inputs must be closed (the open-edge count is named).",
        [P("op", required=True, desc="join_remesh | union | difference | connector"), P("objects", "array", "two or more mesh objects", required=True),
         P("voxel_m", desc="join_remesh: 'coarse_first' (default) or a size in metres"), P("clearance_mm", "number", "0..2: difference and connector"),
         P("connector", "object", "{kind, at: [x, y, z], size_mm, axis}"), P("name", desc="the result's name")], api="mesh_join_boolean"),
    Def("lampway_multi_piece_material", "One material language across 2..8 separate pieces through ONE shared texturing pass. action merge: copies of the pieces "
        "joined in world space into <first>_proxy; each face keeps its piece (face attribute lw_piece) and its ORIGINAL UVs (layer lw_orig) and gets a shared "
        "non-overlapping atlas (layer lw_shared); the texel density each piece gets in the shared atlas (atlas_res) is compared with its own layout "
        "(individual_res, default atlas_res): ratio and pass against density_floor_ratio (0.7, UNVERIFIED). Texture the proxy on lw_shared with any texturing "
        "tool and never edit it. action transfer: the painted atlas returns to each piece's ORIGINAL UVs texel by texel (barycentric), giving <piece>_mpm (a "
        "copy) with <piece>_mpm_shared as its base colour; refused when the proxy changed after merge (re-merge); the proxy is removed unless keep_proxy. "
        "The originals are untouched. Refused: pieces whose world bounds overlap (move them apart for the proxy only), a piece without UVs." + _PATHS,
        [P("action", required=True, desc="merge | transfer"), P("pieces", "array", "merge: the mesh objects"), P("atlas_res", "integer", "merge: 2048 | 4096"),
         P("individual_res", "integer", "merge: the pieces' own texture size for the density comparison"), P("density_floor_ratio", "number", "0.3..1, default 0.7"),
         P("proxy", desc="transfer: the proxy"), P("atlas", desc="transfer: the painted atlas image"), P("out_dir", desc="transfer: default mpm"),
         P("res", "integer", "transfer: output size, default atlas_res"), P("keep_proxy", "boolean"), P("name", desc="merge: the proxy's name")], api="multi_piece_material"),
    Def("lampway_seamless_tile", "Make a seamless material tile BY RULES, never by repainting with a model (generated 'tileable' sheets are not seamless: measured "
        "wrap-edge error 20.5 vs interior 5.9), and gate it by measurement. mode motif (a true repeat: a crop searched at a whole number of periods, then a "
        "min-cut quilt only if needed), grain (no repeat: a variance-preserving cross-fade, narrowest passing band), fibre (as grain, named), motif_cell (one "
        "motif cell resampled to cell_px and repeated exactly). The gate (every check before 8-bit rounding): wrap ratio, line, chunk, signed step and structure "
        "z per RGB and chroma channel, wrap tone step, band and edge sharpness, band tone shift, low-frequency range, half-tile self-correlation, and the TONE "
        "SEAM (8 px bands across the wrap, <= 5 % of the mean luminance; derived from four bake-off tiles, UNVERIFIED beyond them). Writes <out>.png, "
        "<out>_mosaic.png (2N x 2N of the 3x3 tiling) and <out>.qa.json; passed=false is a gate verdict, not an error. prompt makes the sheet through the "
        "image slot (purpose tile) first: a dry run unless live=true. Refused: motif without a true repeat (use grain or fibre), grain/fibre on a periodic "
        "sheet (use motif), a sheet under twice the tile size, an existing output (never overwritten), size outside 256..4096." + _PATHS,
        [P("src", desc="the material sheet (or give prompt)"), P("out", required=True, desc="the tile path (no extension needed)"),
         P("mode", desc="grain (default) | motif | fibre | motif_cell"), P("size", "integer", "256..4096, default 1024"), P("flatten", "boolean", "remove very-low-frequency tone first"),
         P("cell_px", "integer", "motif_cell: the cell size; must divide size"), P("prompt", desc="make the sheet through the image slot (the MATERIAL, not a scene)"),
         P("live", "boolean", "prompt: really generate (default a dry run)")], api="seamless_tile"),
    Def("lampway_relief_tiles", "Multi-scale relief for mesh-paint projection (the second stage of relief_map): stage make tiles each 704 px plate view (v3_dir/<View>.png) "
        "into 200 px crops at stride 150 over its alpha box, each upscaled to 1024, boxes recorded in tile_dir/tiles.json; run the free Studio action "
        "tripo.relief (studio_plan: it uploads each image to tripo3d.ai and keeps the one 8-bit depth PNG) on the tiles into tile_dir as <tile>.relief.png; "
        "stage stitch keeps only each tile relief's FINE band (difference of gaussians, robust-normalised, clipped to +-3) and blends it into one fine frame per "
        "view (default 3072) with a raised-cosine window: <View>.fine.npy, a preview and fine.json (missing tile reliefs listed). The whole-view relief keeps "
        "the big form; the tiles add ornament detail. Free and local." + _PATHS,
        [P("stage", required=True, desc="make | stitch"), P("v3_dir", required=True, desc="the folder with <View>.png plates (704 px)"), P("tile_dir", required=True),
         P("out_dir", desc="stitch: the output folder"), P("views", "array", "default Front, Back, Left, Right"), P("fine", "integer", "stitch: the fine frame, default 3072")],
        api="relief_tiles"),
    Def("lampway_image_upscale", "Raise a plate or texture to 2048..4096 px (the long edge) WITHOUT changing its content; the original is never replaced and every output "
        "carries <file>.upscale.json. method lanczos (default): exact, free, the baseline. method model: the image slot as an edit with the source as the "
        "reference, at most 2880 x 2880 (GPT Image 2.5's 8.3 MP budget), a dry run unless live=true (the source goes to openrouter.ai); the result must pass the "
        "FAITHFULNESS gate or is kept as *_model_rejected: downscaled back, SSIM >= 0.95 on every RGB channel (a recolour fails), strong-edge IoU >= 0.90, and more "
        "fine detail than the Lanczos baseline (else it adds nothing) [thresholds UNVERIFIED]. method tripo: the Studio's free 4K image tool (studio_plan "
        "tripo.image with the returned plan_args; its price must read back 0): a plan, nothing clicked. Refused: a source under 512 px, a target outside "
        "2048..4096, a model target over 2880, an existing output." + _PATHS,
        [P("image", required=True), P("target", "integer", "2048..4096, default 4096"), P("method", desc="lanczos (default) | model | tripo"),
         P("live", "boolean", "model: really send (default a dry run)"), P("prompt", desc="model: overrides the 'reproduce exactly' prompt"),
         P("suffix", desc="added to the output name")], api="image_upscale"),
    Def("lampway_reference_pack", "The four-stage reference method as a GATED sequence, written under <root>/<asset>/reference/. stage sheet: ONE technical sheet on white, "
        "neutral light, the whole asset in frame, pose T (default) or A, with the anatomical LEFT and RIGHT named (left_description, right_description: refused "
        "without them; camera-left is not anatomical left); sheet_views lists the views the sheet already shows. stage audit (image): view_verify's admit and verify "
        "plus the silhouette IoU against approved_reference (>= 0.85, UNVERIFIED); a passing sheet unlocks the rest, a failure STOPS ('identity failed: fix the "
        "reference or prompt, not the batch size'). stage extract (components): one part per prompt from the passing sheet. stage views (views): ONLY the missing "
        "views (a view already in the sheet is refused). stage run: where the sequence stands. Every stage is a dry run (prompt files, nothing sent) unless "
        "live=true; a live stage sends to the image slot (purpose plates | concept, count 1..4), writes a run record (seed not_exposed, selected = the user's) "
        "and one ledger row per call. Each candidate is audited; the user selects." + _PATHS,
        [P("stage", required=True, desc="sheet | audit | extract | views | run"), P("asset", required=True), P("approved_reference", required=True, desc="the approved source image"),
         P("components", "array", "sheet / extract: the parts"), P("pose", desc="T (default) | A"), P("views", "array", "views: the missing views"),
         P("left_description", desc="sheet: what is on the anatomical left"), P("right_description", desc="sheet: what is on the anatomical right"),
         P("model_purpose", desc="plates (default) | concept"), P("count", "integer", "1..4, default 4"), P("live", "boolean", "really send (default a dry run)"),
         P("image", desc="audit: the candidate"), P("sheet_views", "array", "sheet: the views the sheet shows, default Front")], api="reference_pack"),
    Def("lampway_workflow_reference_to_asset", "One piece from reference to finished asset through the existing tools IN ORDER, stopping at every gate. steps (default for "
        "route existing: prep, retopo, uv, texture, pbr, rig, preview, export; generate/algorithmic add image and mesh first): each step is the Lampway tool of "
        "that name on a COPY of the previous step's object, with its cost class: local steps run; a SPEND step (image, texture, a generated mesh) is never run "
        "here: it stays blocked with the plan to make, the user's click its only confirm (gates.spend has no 'auto'). The first blocked or failed step stops the "
        "chain. Every step appends a row to <root>/<piece>/decisions.jsonl ({id, at, step, kind, by, detail}); resume=true skips the steps already done; "
        "workflow_report.md is the plan as a table. run=false (default) returns the plan only. Refused: route existing without existing_object, a route without "
        "reference, an unknown step, two chains on one object at once.",
        [P("piece", required=True), P("reference", desc="the clean reference image (generate / algorithmic)"), P("route", desc="existing (default) | generate | algorithmic"),
         P("existing_object", desc="route existing: the mesh"), P("steps", "array", "the steps in order"), P("gates", "object", "{spend: stop}"),
         P("target", desc="unreal (default) | unity | godot"), P("run", "boolean", "run the local steps (default: plan only)"), P("resume", "boolean", "skip the steps done")],
        api="workflow_reference_to_asset"),
    Def("lampway_image_matte", "Deterministic chroma matting of generated plates (magenta or white backgrounds), no model, no spend. action remove: every PNG under "
        "src keyed to transparent RGBA in a NEW directory `out` with manifest.json (settings, source/output/pixel sha256 per file); the key colour and clear "
        "threshold are read from each image's border ring (key=border; key=ideal is the literal #FF00FF), edges unmixed against that key (despill), enclosed "
        "key-coloured holes keyed. A sheet recipe (JSON {schema: 1, images: {name: {split: 2x2|3x2, x_cuts, y_cuts, row_x_cuts, erase: [[x0,y0,x1,y1]], "
        "background, opaque, clear, sha256?, size?}}}) splits turnaround sheets into named views (Front/Left/Back/Right or Front/Right/Back/Left/Top/Bottom). "
        "action center: transparent PNGs shifted by whole pixels onto a canvas (canvas_size an integer, or `common` = the smallest square holding every plate); "
        "never resampled. action verify: re-decodes every output (CRC), checks file and pixel hashes against the manifest, sources unchanged, every non-key "
        "source pixel preserved (remove) or the foreground bytes preserved (center), names files whose border is not fully transparent, and writes a light/dark "
        "contact sheet to verify_out for the edge review. Refused: PNGs that are not 8-bit RGB/RGBA non-interlaced (never converted), more than 16 million "
        "pixels, a ring that is not mostly the background, an image the key empties, an existing output, nested or symlinked paths. Limit: genuine magenta "
        "foreground is keyed too.",
        [P("action", required=True, desc="remove | center | verify"), P("src", required=True, desc="a PNG or a folder of PNGs (verify: the run's source)"),
         P("out", required=True, desc="the NEW output folder (verify: the folder to check)"), P("background", desc="magenta (default) | white"),
         P("key", desc="border (default) | ideal"), P("opaque", "integer", "key score at or under which a pixel stays opaque"),
         P("clear", "integer", "key score at or over which a pixel is cleared (default: 220, or the ring's own score)"),
         P("despill", "boolean", "unmix the key from edge pixels (default true)"), P("split", desc="2x2 | 3x2 for every image (a recipe sets it per image)"),
         P("recipe", desc="the sheet recipe JSON"), P("canvas_size", desc="center: an integer side in px, or common"),
         P("verify_out", desc="verify: the folder for checks.json and contact_sheet.png (default <out>.verify)")],
        api="image_matte"),
    Def("lampway_scribble_read", "The Scribble marks in this scene, re-read from the Client's own mark records (they persist in the .blend, so a mark from three turns "
        "ago is still readable after the message that carried it is gone). Returns mode (point: marks say WHERE to work; sketch: the drawing is WHAT to build), "
        "marks [{id, kind (circle|arrow|point|strike|stroke), object (the object it resolved to, or null for empty space), region (frame bbox u0,v0,u1,v1, "
        "bottom-up 0..1), ndc (the anchor in -1..1, y up), state (DRAFT: new since the last turn | SENT)}] and summary (the Client's prose: object names, "
        "coverage, world points). include_image writes the frozen annotated frame to <root>/scribble/<name>.png and returns image_path; refused when this file "
        "holds no frozen frame for the marks. Read-only; no marks is an empty answer, not an error.",
        [P("include_image", "boolean", "write the frozen annotated frame (default false)"), P("include_sent", "boolean", "include marks already sent (default true)")],
        api="scribble_read"),
]
