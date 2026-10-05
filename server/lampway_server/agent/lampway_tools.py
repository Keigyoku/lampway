"""The Lampway tool definitions: what the model can call to work on a piece (mesh QA, the rebuild loop, the parts and
proportion tools). Each is a Python script the client runs in its sandbox via blender.execute_script; the script is one call
into ``mixar.modules.lampway_tools.api`` (inside the app) carrying its arguments as ONE JSON string literal, so no argument
value can change the code. The server never touches the user's files itself.

The studio drivers (Tripo) are not here: they spend credits and drive a browser, so they live in lampway_server/studios and
are called by the server directly, never through Blender.
"""

import json
from dataclasses import dataclass, field
from typing import Optional

from .providers.base import ToolSpec


class BadArguments(ValueError):
    pass


@dataclass
class P:
    name: str
    type: str = "string"                   # string | number | integer | boolean | array | object
    desc: str = ""
    required: bool = False
    flag: Optional[str] = None             # batch tools: None = positional, else the command-line flag
    repeat: bool = False                   # an array given as one flag per value


@dataclass
class Def:
    name: str
    description: str
    params: list = field(default_factory=list)
    api: Optional[str] = None              # an api.<fn> tool function, or
    batch: Optional[str] = None            # a ported batch tool run through api.run_tool

    def spec(self) -> ToolSpec:
        props, req = {}, []
        for p in self.params:
            prop = {"type": p.type, "description": p.desc}
            if p.type == "array":
                prop["items"] = {"type": "object"} if p.name in ("poses", "waypoints", "anchors", "landmarks", "axis", "plane_origin", "depths_mm") else {"type": "string"}
            props[p.name] = prop
            if p.required:
                req.append(p.name)
        return ToolSpec(name=self.name, description=self.description,
                        parameters={"type": "object", "properties": props, "required": req, "additionalProperties": False})


def _literal(payload: dict) -> str:
    return json.dumps(json.dumps(payload))


def _args_for(d: Def, arguments: dict) -> list:
    out = []
    for p in (q for q in d.params if q.flag is None):
        v = arguments.get(p.name)
        if v is None:
            continue
        out += [str(x) for x in v] if isinstance(v, list) else [str(v)]
    for p in (q for q in d.params if q.flag is not None):
        v = arguments.get(p.name)
        if v is None or v is False:
            continue
        if v is True:
            out.append(p.flag)
        elif isinstance(v, list):
            vals = [str(x) for x in v]
            out += [x for val in vals for x in (p.flag, val)] if p.repeat else [p.flag, ",".join(vals)]
        else:
            out += [p.flag, str(v)]
    return out


def build_script(d: Def, arguments: dict) -> str:
    arguments = arguments if isinstance(arguments, dict) else {}
    missing = [p.name for p in d.params if p.required and arguments.get(p.name) in (None, "")]
    if missing:
        raise BadArguments(f"{d.name} needs {', '.join(missing)}")
    known = {p.name for p in d.params}
    given = {k: v for k, v in arguments.items() if k in known}
    if d.batch:
        fn, payload = "run_tool", {"name": d.batch, "args": _args_for(d, given)}
    else:
        fn, payload = d.api, given
    return ("from mixar.modules.lampway_tools import api\n"
            f"__RESULT__ = api.call({json.dumps(fn)}, {_literal(payload)})\n")


_PATHS = " Paths are relative to the project root; a path outside it is refused."

DEFS = [
    Def("lampway_status", "Show Lampway's tool state: the project root, which interpreters exist, whether mesh QA is set up "
        "for this scene, running jobs, and the list of batch tools. Call this first when unsure what is configured.", api="status"),
    Def("lampway_qa_setup", "Point mesh QA at a mesh object. `recipe` is the parts json (parts and their motion classes); `owner` is "
        "a .npy of one part index per polygon (empty = the mesh's int face attribute 'part'); `offset` is the live frame minus the "
        "mesh's own frame (the lift). `orig_poly` is a rebuild's source-face map (-1 = patch). Call it once per PIECE: several pieces can be set up in one scene, each with its own config, and later tools take `piece` (the last one set up is the default). `turn` is the rotation about Z that brings the object to a -y front (a Tripo FBX facing +x: -90)." + _PATHS,
        [P("object", desc="Name of the mesh object", required=True), P("recipe", desc="Parts recipe json", required=True),
         P("owner", desc="Owner map .npy"), P("piece", desc="Piece name (rulings live in <root>/<piece>/rulings)"),
         P("session", desc="Decision-log session name"), P("offset", "array", "Live frame minus mesh frame, [x, y, z] as strings"),
         P("orig_poly", desc="Rebuild's orig_poly .npy"), P("turn", "number", "Turn about Z in degrees that brings the object to the -y front (Tripo FBX: -90)"),
         P("rulings_dir", desc="Rulings directory"), P("min_perimeter", "number", "Open loops shorter than this (m) are ignored; default 0.15"),
         P("max_shell_tris", "integer", "A floating shell has at most this many triangles; default 400"),
         P("float_mm", "number", "A shell floats when its nearest neighbour is further than this (mm); default 3")], api="qa_setup"),
    Def("lampway_qa_tag_layers", "Add the three annotation tag layers the user draws on: Red = Delete, Green = Mislabel, "
        "Yellow = Hole (placement Surface). Existing layers are kept.", api="qa_tag_layers"),
    Def("lampway_qa_candidates", "Find open loops (holes) and floating shells on the piece and write them as typed candidates "
        "(descriptor: size, bordering parts and their motion classes, side of the body, which views see it, what lies behind). "
        "Ruled deletions are applied first. `draw` also draws them into the scene (collection QA_<piece>, markers <piece>_L000).",
        [P("draw", "boolean", "Also draw them"), P("piece", desc="The piece (default: the last one set up)"),
         P("collection", desc="Collection to draw into, default QA_<piece>"), P("prefix", desc="Marker name prefix, default <piece>_")],
        api="qa_candidates"),
    Def("lampway_qa_draw", "Draw the candidates into the scene (collection QA_<piece>): tubes along open loops, rings around floating "
        "shells, each labelled with its id (and verdict, once proposed), so the user can review them and answer with the tag layers. "
        "A re-run replaces only this piece's collection.", [P("piece"), P("collection"), P("prefix")], api="qa_draw"),
    Def("lampway_qa_propose", "PROPOSE verdicts for a piece's candidates and recolour the markers (delete red, hole yellow, mislabel green, "
        "keep grey and hidden; label `<id> <VERDICT>`). RULES FIRST: called with no `proposals`, the proven rules decide every candidate "
        "their descriptors make clear (each reason names its rule) and the rest comes back as `ambiguous` - judge only those, in small "
        "batches, from lampway_qa_descriptors, then call this again with `proposals` {id: {verdict, reason}} (rules=false). A re-run of "
        "the rules never replaces your row. A proposal is NOT a ruling and never changes the mesh: only the user's tags or typed "
        "answers become rulings.",
        [P("proposals", "object", "{candidate id: {verdict: delete|hole|mislabel|keep, reason, target}}; omit to run the rules"),
         P("piece"), P("by", desc="Who proposes, default agent"), P("rules", "boolean", "Run the rules too (default: only when no proposals)")],
        api="qa_propose"),
    Def("lampway_qa_descriptors", "COMPACT descriptors of a piece's candidates (never segments, never the candidate files themselves) in small "
        "batches: `ids` picks some; `ambiguous_only` = those with no proposal yet; `limit` (max 20) and `offset` page. Read these, not the "
        "candidates JSON, to judge what the rules left ambiguous (large rims, backfacing hits, shells near the float threshold).",
        [P("piece"), P("ids", "array", "Candidate ids"), P("ambiguous_only", "boolean"), P("limit", "integer"), P("offset", "integer")],
        api="qa_descriptors"),
    Def("lampway_qa_proposals", "Read the proposals so far for a piece, with counts per verdict.", [P("piece")], api="qa_proposals"),
    Def("lampway_qa_read_tags", "Read the user's Red/Green/Yellow annotation strokes: faces and Smart UV islands per stroke, the "
        "candidate loops a Hole stroke circles or runs along (or an orphan the generator missed), and the floating shell a Delete "
        "stroke sits on. With apply (default) writes the decision log and the rulings (deletions, relabels, texel overrides). A Green "
        "stroke needs a target part in `mislabel_to` ({stroke index: part}); without one it is returned in "
        "relabels_needing_a_target - never guess it. `close_round` answers every candidate nobody named 'keep'.",
        [P("apply", "boolean", "Write decisions and rulings (default true); false = a dry run"),
         P("close_round", "boolean", "Everything not named is intentional"),
         P("mislabel_to", "object", "Target part per green stroke index, e.g. {\"0\": \"cuirass_back_plate\"}"), P("piece")],
        api="qa_read_tags"),
    Def("lampway_qa_rulings", "Summarise the rulings so far: deleted faces, relabels, texel overrides, decision rows, and the latest "
        "answer per candidate.", [P("piece")], api="qa_rulings"),
    Def("lampway_rebuild_setup", "Save what a rebuild needs besides the rulings: the SOURCE mesh and its owner map (rebuilds always "
        "start from the source), the relief views and plates, the live material to copy, where outputs go, the objects to hide."
        + _PATHS, [P("source_mesh", required=True), P("source_owner", required=True), P("relief_dir", required=True),
                   P("plates_dir", required=True), P("template_material", desc="Live textured material to copy", required=True),
                   P("out_root"), P("relabel_rules", "array", "FROM:TO:WITH relabel rules for patch_holes"),
                   P("turn", "number"), P("lift", "number"), P("previous", "array", "Object names to hide when the new one loads")],
        api="rebuild_setup"),
    Def("lampway_rebuild", "Read the user's tags, write the rulings, rebuild the piece (patch holes, patch UVs, project colour, "
        "material masks) and load the result beside the previous version. It runs as a BACKGROUND job (minutes) and returns its id "
        "at once; poll lampway_job_status. When it finishes the new mesh loads textured next to the old one, the old is hidden, and "
        "mesh QA points at the new object so the loop continues. A tag is never overwritten.",
        [P("tag", desc="A new name for this rebuild", required=True), P("res", "integer", "Atlas size: 2048 or 4096"),
         P("color_full", "boolean", "Sample the plates at full resolution"), P("ornament", desc="max_tris:reach_px:min_share, e.g. 600:24:0.25"),
         P("mesh_gold", "boolean"), P("read_tags", "boolean", "Read the tags first (default true)"), P("close_round", "boolean"),
         P("mislabel_to", "object"), P("resume", "boolean", "Finish an interrupted tag")], api="rebuild"),
    Def("lampway_job_status", "Status of background jobs (a rebuild): running, done or failed, with the steps and the loaded object. "
        "Without `job` lists them all.", [P("job", desc="A job id like rebuild-1")], api="job_status"),
    Def("lampway_run_tool", "Run any ported batch tool by name (see lampway_status) with raw arguments, in the background-safe runner: "
        "niced, output trimmed, full log kept." + _PATHS, [P("name", desc="Tool name", required=True),
        P("args", "array", "Arguments, in the tool's order"), P("timeout", "number", "Seconds; default 3600")], api="run_tool"),
    Def("lampway_meshpaint", "Mesh-paint texturing, the best texture source: a clay render of OUR mesh per view; the image backend paints V3's "
        "design over it as flat albedo (4 variants per view, studio_image_generate); pick 1 of 4 per view by silhouette IoU; plates with "
        "the clay alpha; projection at 4096 with no warp; masks; the projected albedo as a live-material toggle. `stage`: setup (once: "
        "piece, mesh, design_dir, tag, recipe, relief_dir, out_root, template_material, lift), clay, prompt (view: writes the prompt "
        "file and returns the references and out_dir to hand to studio_image_generate), image (view, count 1-4, live: generate that ONE view through the configured image backend, e.g. OpenRouter; costs money when live), pick (view, optional file; default the best by "
        "IoU), plates, project (background job), run (ALL of it as one background job; live=true to really generate: otherwise the "
        "image backend only dry-runs), albedo (material, on), status. Poll lampway_job_status for jobs." + _PATHS,
        [P("stage", desc="setup | clay | prompt | image | pick | plates | project | run | albedo | status", required=True),
         P("piece"), P("mesh"), P("design_dir"), P("tag"), P("recipe"), P("relief_dir"), P("out_root"), P("template_material"),
         P("lift", "number"), P("turn", "number"), P("clay_res", "integer"), P("res", "integer", "Clay render size for stage clay"),
         P("view", desc="Front | Back | Left | Right"), P("file", desc="A variant to pick instead of the best"),
         P("require_all", "boolean", "Plates: all four views must be picked (default true)"), P("material", desc="The _albedo material"),
         P("on", "boolean", "Albedo on or off"), P("live", "boolean", "Really generate (default a dry run)"),
         P("count", "integer", "Stage image: images to make, 1-4 (default 4)")], api="meshpaint"),
    Def("lampway_export_piece", "Export a finished piece for the engine: the object as FBX into out_dir, its texture maps copied "
        "under Textures/, and a README naming every file, what each map is (ORM order, normal convention) and its sha256. The scene "
        "is not changed." + _PATHS, [P("object", desc="The object to export", required=True), P("out_dir", required=True),
        P("textures", "array", "The maps to ship (e.g. the pbr_merge outputs)"), P("note", desc="A line for the README")],
        api="export_piece"),
    Def("lampway_retopo", "Retopology: a NEW all-quad mesh `<object>_retopo` near target_faces (QuadriFlow; voxel remesh as the fallback) "
        "with a measured report (faces, quads, non-manifold and open-boundary edges, surface deviation). The original is untouched; "
        "keep it until the replacement passes your checks. engine=studio:tripo answers with the studio action and its price for the "
        "owner's approval and clicks nothing.", [P("object", desc="Mesh object name", required=True),
        P("target_faces", "integer", "Default 2000"), P("method", desc="quadriflow (default) | voxel"),
        P("engine", desc="algorithmic (default) | studio:tripo"), P("symmetry", "boolean")], api="retopo"),
    Def("lampway_uv_unwrap", "UV unwrap: a NEW mesh `<object>_uv` with a packed layout (method smart | angle | conformal; seams at edges "
        "sharper than angle_limit) and a measured report (islands, coverage, overlap by rasterising, texel-density spread, the "
        "density achieved at texture_size). The original keeps its UVs; inspect the checker before texturing. engine=studio:tripo "
        "is the Smart UV slot: it answers with the action and price for the owner's approval.", [P("object", required=True),
        P("method", desc="smart (default) | angle | conformal"), P("angle_limit", "number", "Degrees, default 66"),
        P("margin", "number", "Island margin in UV units, default 0.005"), P("texel_density", "number", "Texels per metre wanted"),
        P("texture_size", "integer", "Default 2048"), P("engine", desc="algorithmic (default) | studio:tripo")], api="uv_unwrap"),
    Def("lampway_segment_mesh", "Mesh Segment: split a mesh into part objects in the collection `<object>_parts` (largest first, UVs and "
        "materials kept). method: shells (connected pieces) | sharp (regions bounded by edges sharper than `angle` degrees) | "
        "uv_islands (needs a UV layer). Regions smaller than min_faces merge into the neighbour they share the longest border with. "
        "The original is hidden, never deleted. engine=studio:tripo is the part-detection slot (answers with action and price).",
        [P("object", required=True), P("method", desc="shells (default) | sharp | uv_islands"), P("angle", "number", "Degrees, default 40"),
         P("min_faces", "integer", "Merge regions under this many faces, default 1 (no merge)"),
         P("engine", desc="algorithmic (default) | studio:tripo")], api="segment_mesh"),
    Def("lampway_mesh_prep", "Workflow, geometry preparation: a branch `<object>_prep` of a generated mesh with its source hash "
        "recorded, loose and doubled vertices removed and inverted normals fixed; returns before/after reports. The source is untouched.",
        [P("object", required=True), P("merge_distance", "number", "Weld distance, default 1e-5")], api="mesh_prep"),
    Def("lampway_asset_acceptance", "Workflow, engine acceptance: identity / orientation / geometry / materials gates for a candidate "
        "asset (optionally against a `reference` object), each with reasons, and an overall `accepted`. Lists what it did not check.",
        [P("object", required=True), P("reference", desc="An approved object to compare bounds against"),
         P("tolerance", "number", "Fraction of the reference diagonal, default 0.1"),
         P("source_hash", desc="sha256 of the approved source: identity fails unless the object records it (mesh_prep does) or is identical to it")],
        api="asset_acceptance"),
    Def("lampway_rig_armor", "Workflow, fit existing armor: fit a copy `<object>_fit` to an armature (bone = one bone at full weight for "
        "rigid plates; body = weights transferred from the aligned body; else heat map), then measure edge stretch over a pose set. "
        "The original is never bound.", [P("object", required=True), P("armature", required=True), P("bone"), P("body"),
        P("max_stretch", "number", "Accept limit; default 1.001 rigid, 1.35 deforming"),
        P("clearance_body", desc="The body rigged to the same armature: every pose is judged by the piece's distance to it (the only check that can fail a rigid plate)"),
        P("min_clearance_m", "number", "Smallest accepted clearance, default 0"),
        P("seam_limit_m", "number", "Widest accepted seam gap between plates, default 0.01 [unverified default]"),
        P("poses", "array", "Pose objects; default is the wiki's eight poses (idle ... weapon_grip)")], api="rig_armor"),
    Def("lampway_auto_rig", "Auto Rig: a UE-named humanoid armature `<object>_rig` placed from landmarks measured on a T-pose mesh "
        "(standing on Z, facing -Y by default; _l/_r are the FIGURE's own sides), the mesh parented with heat-map weights and a "
        "proximity fallback for vertices heat cannot solve. Test it with lampway_pose_test: a rig is not a claim of deformation "
        "quality. engine=studio:tripo is the Auto Rig slot (answers with action and price).", [P("object", required=True),
        P("kind", desc="humanoid"), P("weights", desc="auto | proximity"), P("facing", desc="-Y (default) | +Y"),
        P("engine", desc="algorithmic (default) | studio:tripo"),
        P("copy", "boolean", "Rig a copy `<object>_rigged` and leave the source untouched (default true); false rigs in place")], api="auto_rig"),
    Def("lampway_bind_to_armature", "Bind a piece (armor) to an armature: mode rigid = ONE bone at full weight (plates; give `bone`), "
        "transfer = weights copied from `source` (the aligned body; for deforming pieces), auto = heat-map weights.",
        [P("object", required=True), P("armature", required=True), P("mode", desc="rigid (default) | transfer | auto"),
         P("bone"), P("source", desc="The body whose weights are transferred (mode transfer)")], api="bind_to_armature"),
    Def("lampway_pose_test", "Rotate bones and MEASURE the evaluated mesh: max/min edge stretch and the largest vertex displacement per pose "
        "(a rigid plate on one bone must read stretch 1.0). `poses`: [{name, bone, rotate: [x, y, z] degrees}]; every pose is reset.",
        [P("armature", required=True), P("object", required=True), P("poses", "array", "Pose objects", required=True),
         P("clearance_body", desc="A body rigged to the same armature: reports the clearance of the piece to it in every pose"),
         P("seam_radius_m", "number", "Vertex pairs of different shells closer than this at rest are a seam, default 0.02")], api="pose_test"),
    Def("lampway_asset_lineage", "Lineage of a derivative so a repaired mesh cannot silently become an unrelated one. action record: store the source's geometry/UV/"
        "material hashes, the transformation and exactly THREE identity anchors (landmarks that must not move: [{name, point: [x, y, z]}] in object space; pick them "
        "with the user, never invent them); verify: each anchor's nearest-point distance to the derivative must stay within tolerance_m (default 0.01); show: the "
        "lineage and its parent chain. A second record on a derived object needs parent=<its lineage id>.",
        [P("action", required=True, desc="record | verify | show"), P("object", required=True), P("source", desc="The approved source object (record; default: the object)"),
         P("transform", desc="One line: what was done"), P("anchors", "array", "Exactly three {name, point} (record)"), P("tolerance_m", "number", "0.0001..0.05, default 0.01"),
         P("parent", desc="The lineage id this derives from (chain)"), P("piece", desc="The piece folder name, default the object name")], api="asset_lineage"),
    Def("lampway_workflow_graph", "A workflow as data: a typed DAG of Lampway tool calls with cached outputs. action define (graph {nodes: [{id, tool, args, after: [ids], "
        "spend, studio_action, credits}], outputs}, inputs; an arg string @node.key is that upstream node's output, {{name}} an input) | plan (order, cached, credits_planned: "
        "nothing runs) | run | rerun (from_node) | version / rollback (version) | template_save / template_use (template, description) | show. A spend node is only "
        "planned and priced: the user confirms spends in the Studios panel and what depends on it waits.",
        [P("action", required=True), P("name", desc="The graph's name"), P("graph", "object", "The graph (define)"), P("inputs", "object", "Values for {{name}} placeholders"),
         P("from_node", desc="rerun: the node to start from"), P("version", desc="version / rollback: the version name"), P("template"), P("description")], api="workflow_graph"),
    Def("lampway_plate_pick", "Plates stage: stage prompt (the plate-4k-crisper template + variables for a view; render it and generate 4 images per view), score (rank the 4 "
        "regenerations in variants_dir against the approved V3 plate v3_dir/<View>.png by silhouette IoU x structure x (1 - colour error)), cut (the pick's deterministic alpha), "
        "run (score + cut + margins/aspect/view-correspondence checks -> <piece>/plates_4k_alpha/<View>.png + alpha.json), status. `pick` 1-4 is the user's override. Paired "
        "pieces: Front and Back only. Free and local; never overwrites.",
        [P("stage", required=True, desc="prompt | score | cut | run | status"), P("piece", required=True), P("view", desc="Front | Back | Left | Right"), P("paired", "boolean", "Front and Back only"),
         P("v3_dir", desc="Folder with <View>.png (RGBA) of the approved plates"), P("variants_dir", desc="Folder with 1.jpg..4.jpg for the view"), P("design_words", desc="prompt: the design inventory"),
         P("palette", desc="prompt: the colours"), P("pick", "integer", "1-4: the user's choice"), P("bg_threshold", "number", "0.01..0.2, default 0.06"),
         P("opening_iters", "integer", "default 3"), P("min_px", "integer", "Refuse variants smaller than this, default 1024")], api="plate_pick"),
    Def("lampway_uv_score", "Score UV layouts on measurements, not by eye (the shelf's uv_score): utilization (rasterised at res 256..4096), overlap, UV islands, stretch p90/p10, the fraction "
        "of area off by 2x, flipped (mirrored) faces, seam length and a composite score; each row has gates {pass, failed}. objects: mesh objects in the scene; files: .fbx/.glb Smart UV "
        "attempts inside the project root (measured in a headless Blender, the live scene untouched). `best` is advice: the user picks (tripo.uv.pick, then save).",
        [P("objects", "array", "Mesh object names"), P("files", "array", "Project-relative .fbx/.glb paths"), P("res", "integer", "256..4096, default 1024"),
         P("out", desc="Report path under the project root, default uv_score.json"), P("gates", "object", "{max_overlap, max_flipped, max_off_density_2x}")], api="uv_score"),
    Def("lampway_uv_texel_density", "Set and equalise texel density per UV island on a NEW object `<object>_td` (the source keeps its UVs), repack, and report the density achieved "
        "(before/after density_cv, coverage, overlap, per-island scales, shortfall). target: px/metre, 'N px/cm' or 'auto' (the current mean); weights {material | vertex group | island:N: 0.1..4}; "
        "texture_size a power of two. Refuses a textured object (a UV change discards the texture) unless discard_texture.",
        [P("object", required=True), P("texture_size", "integer", "Power of two, default 2048"), P("target", desc="px/metre | 'N px/cm' | auto (default)"),
         P("weights", "object", "{material | vertex group | island:N: factor}"), P("mode", desc="island (default) | all"), P("repack", "boolean", "default true"),
         P("margin", "number", "UV units 0..0.05, default 0.005"), P("name", desc="Default <object>_td"), P("discard_texture", "boolean", "Allow a textured object")], api="uv_texel_density"),
    Def("lampway_mesh_defect_scan", "A read-only clay inspection: typed defect candidates for the user's decisions, NEVER an edit. kinds (default all): open_loop, floating_shell (a small shell "
        ">3 mm from the body), intersection (faces crossing faces, by BVH), thin (thinner than thin_threshold_m inward; default 0.002, unverified), flipped_shell (closed or open), degenerate, "
        "isolated_tri. Each candidate: id, kind, descriptor {faces, area_m2, centroid, bbox, normal, rim_length_m}, rule_verdict (keep|delete|hole|ambiguous), rule, severity. More than "
        "max_candidates: the first N plus truncated and total.", [P("object", required=True), P("piece"), P("kinds", "array", "Subset of the kinds"),
                                                          P("thin_threshold_m", "number", "0.0001..0.05"), P("max_candidates", "integer", "1..500, default 100")], api="mesh_defect_scan"),
    Def("lampway_silhouette_compare", "Did the piece drift? Render the approved source `a` and the candidate `b` (a mesh, or a plate image with an alpha or a flat background) from the SAME "
        "orthographic cameras (Front/Back/Left/Right, framed on a) and report per view the silhouette IoU, area ratio, centroid shift and, with landmarks [{name, point}] in world space, the "
        "drift to b's surface. `pass` = worst IoU >= min_iou (default 0.9, a placeholder). Side-by-side PNGs under <root>/<piece>/compare/. A mirrored candidate fails the view that sees it.",
        [P("a", required=True), P("b", required=True, desc="A mesh object name or a plate image path"), P("piece"), P("views", "array", "Subset of Front, Back, Left, Right"),
         P("size", "integer", "128..2048, default 512"), P("min_iou", "number", "0..1"), P("landmarks", "array", "[{name, point: [x, y, z]}] in world space")], api="silhouette_compare"),
    Def("lampway_seed_audit", "Rank a piece's seeds (the 4 generation variants, then the pick plus its rerolls). stage measure: per seed the dihedral fold counts (>120 and >90 degrees), boundary "
        "and non-manifold edges, components and closed bowls across the opening, ranked PROPORTIONS first (scores {seed: score_rms}; within 5 % is a tie), DEFECTS second, V3 fidelity third; "
        "lineup: front + side Workbench renders (420 px, never Cycles); judge: the packet (numbers + renders, at most 6 seeds) for you to propose verdicts from; record: audit.json from your "
        "proposals - a decision row is written only for by=captain (your verdict is a proposal, not a ruling). seeds are npz paths (mesh_to_npz output) inside the project root.",
        [P("stage", required=True, desc="measure | lineup | judge | record"), P("piece", required=True), P("seeds", "array", "npz paths"),
         P("scores", "object", "{seed id: score_rms} from the proportion tools"), P("proposals", "object", "{seed: {verdict: usable|fix|reject, defects, rank}} (record)"),
         P("by", desc="agent (default) | model | captain"), P("turn", "number", "lineup: degrees about Z, default -90 (Tripo FBX)"), P("engine", desc="lineup: WORKBENCH only")], api="seed_audit"),
    Def("lampway_parts_critique", "The auditor's critique of a transferred or segmented part set. stage flags: the rules first (weak-vote and far-transfer islands, parts with too few polygons or absent, a "
        "_L/_R part crossing the sagittal plane, left/right area asymmetry); render: the owner map in four views, flagged islands magenta (Workbench, headless); judge: the packet to propose fixes from "
        "(at most `limit` flags, biggest first); write_fixes: your proposals [{target_part, islands | bbox_fbx, only_from_parts, reason, evidence}] validated and written to <piece>/parts/fixes.json; check: "
        "a dry run per fix ({triangles, from}) without writing an owner map. A fix between a metal part and a cloth/leather part is refused (that class is the user's or the recipe's, never a render's). "
        "Proposals only: apply_part_fixes writes the owner map once the user approves.",
        [P("stage", required=True, desc="flags | render | judge | write_fixes | check"), P("piece", required=True), P("recipe", required=True, desc="recipe.json (parts + classes)"),
         P("transfer_dir", desc="the directory transfer_parts wrote"), P("piece_uv", desc="piece_uv.npz"), P("owner_poly", desc="owner_poly.npy (render)"), P("mesh", desc="fbx|glb (render)"),
         P("proposals", "array", "fix proposals (write_fixes, check)"), P("fixes", desc="a recorded fixes.json (check)"), P("weak", "number", "default 0.6"), P("far_mm", "number", "default 30"),
         P("min_faces", "integer", "default 50"), P("limit", "integer", "judge batch 1..20, default 12"), P("turn", "number", "render: degrees about Z, default -90"),
         P("by", desc="agent (default) | model | captain")], api="parts_critique"),
    Def("lampway_palette_fit", "Fit the per-class Hue/Saturation/Value of the studio colours to the mesh-paint albedo, nudge it live, then write the params pbr_merge reads. stage fit: per class the median "
        "HSV of the studio base under the class mask vs the albedo under the same mask -> hue_shift, sat_mul, val_mul, measured in sRGB by default (the recorded chest fit is the sRGB median), space=linear optional, plus a residual and a named reason for each skipped class; "
        "apply_live: a copy of `material` with a Hue/Saturation/Value node per class mixed by its mask (labelled PAL:, idempotent) for the user to nudge; read_live: read his sliders back (his nudge is law, "
        "the fit is advice); write_params: <piece>/pbr/live_material_params.json from source fit | live (refused while a cloth/leather class is not in metal_zero_on).",
        [P("stage", required=True, desc="fit | apply_live | read_live | write_params"), P("piece", required=True), P("studio_base", desc="BaseColor map (png)"), P("albedo", desc="v3_colour_atlas.png"),
         P("masks", desc="directory with mask_<class>.png"), P("classes", "array", "default gold, plate, red, linen, leather, embroidery"), P("material", desc="scene material (apply_live, read_live, live write_params)"),
         P("name", desc="the copy's name"), P("source", desc="write_params: fit (default) | live"), P("metal_zero_on", "array", "classes with metallic forced to 0"),
         P("statistic", desc="median (default) | mean"), P("space", desc="srgb (default) | linear"), P("min_texels", "integer", "default 1000")], api="palette_fit"),
    Def("lampway_bake_maps", "Bake a high-poly donor (`source`: a name or a list) into a UV-mapped low-poly `target`: normal (tangent), albedo (Cycles COLOR pass only: no lighting, by construction) and ao, "
        "in a niced HEADLESS Cycles worker, never the live scene. size a power of two 32..8192 (default 2048), margin_px default size/128 (>= 2), cage_extrusion_m 0..0.2 or auto, max_ray_m, samples 1..512. "
        "Refused before running, each with its fix: no UV (unwrap first), overlapping UVs, unapplied non-uniform scale, source == target, a pair not aligned (bbox centres > 2 % of the diagonal), an "
        "unsupported map (curvature, cavity, dust, bevel, position are not Cycles bake types), an existing map without overwrite. Returns the PNG paths, the black-texel fraction per map with a "
        "cage-too-small hint, the colour spaces, and (attach) a <target>_baked material wired with the maps.",
        [P("source", required=True, desc="donor object name, or a list"), P("target", required=True, desc="the UV-mapped low-poly object"), P("maps", "array", "normal | albedo | ao (default normal, albedo)"),
         P("size", "integer", "power of two, default 2048"), P("margin_px", "integer", "0..64"), P("cage_extrusion_m", desc="0..0.2 or auto"), P("max_ray_m", "number", "default half the extrusion"),
         P("samples", "integer", "1..512, default 16"), P("normal_green", desc="gl (default) | dx"), P("allow_overlap", "boolean", "bake despite overlapping UVs"),
         P("out_dir", desc="under the project root, default bake"), P("overwrite", "boolean", "replace existing maps"), P("attach", "boolean", "add the baked material, default true")], api="bake_maps"),
    Def("lampway_pbr_pack", "Engine-ready PBR maps. pack: maps {base, normal, rough, metal, ao|null} -> BaseColor (sRGB), ORM (R occlusion, 1 when no AO, G roughness, B metallic: Unreal order, linear), "
        "Normal_GL / Normal_DX (green flipped), Roughness, Metallic and merge.json; square power-of-two maps only; metal forced to 0 under metal_zero_masks (cloth/leather); a flat normal is flagged; a "
        "set is never overwritten. audit: an object's material - base colour sRGB, roughness/metallic/normal Non-Color, a Normal Map node, every channel reported linked or not. swap_base_color: replace "
        "only the base-colour image on a COPY of the material, keeping the other maps; refused unless uv_hash equals the mesh's (the colour map must share this mesh's UV layout).",
        [P("action", required=True, desc="pack | audit | swap_base_color"), P("maps", "object", "{base, normal, rough, metal, ao} project paths (pack)"), P("convention", desc="dx | gl | both (default)"),
         P("name", desc="output folder name (pack)"), P("metal_zero_masks", "array", "mask pngs of cloth/leather classes (pack)"), P("object", desc="mesh object (audit, swap_base_color)"),
         P("new_base", desc="the new colour map (swap_base_color)"), P("uv_hash", desc="the colour map producer's UV hash (swap_base_color)")], api="pbr_pack"),
    Def("lampway_armor_piece_pipeline", "One armour piece from V3 plates to an engine-ready export as 15 ordered, gated steps (the user's runbook mapped to Lampway's tools and Tripo Studio actions). mode plan: every "
        "step with tool, arguments, state (done | ready | waiting | needs_approval) and planned credits (mesh 100, Smart UV 20, texture 30, PBR 5: 155 for a piece); start: the same but refused when from_step > 1 "
        "has no run record; record: append one step's result (artefacts with sha256, mesh_hash) to <piece>/pipeline/run.json - a geometry step after the texture marks it stale. Laws: texturing last, Studio "
        "actions on a saved copy, pose before rig. It NEVER confirms a spend: needs_approval rows wait for the user's click.",
        [P("piece", required=True, desc="Helmet1 | Chest1 | Waist1 | Gauntlets1 | Boots1"), P("mode", desc="plan (default) | start | record"), P("from_step", "integer", "1..15"), P("to_step", "integer", "1..15"),
         P("paired", "boolean", "front and back views only (default true for Gauntlets1, Boots1)"), P("topology", desc="Quad | Triangle"), P("v3_dir", desc="the V3 plates folder"),
         P("record_step", "integer", "record: which step"), P("artefacts", "array", "record: files produced"), P("mesh_hash", desc="record: the mesh+UV hash at that step"), P("note")], api="armor_piece_pipeline"),
    Def("lampway_fit_pose", "The closest pose of the body to a piece. chest: routed to pose_clearance. helmet | waist | boots | gauntlets: needs_decision - the bones, axes and ranges to sweep are the user's to rule; "
        "the contract's proposals are included, marked unverified.", [P("kind", required=True, desc="chest | helmet | waist | boots | gauntlets")], api="fit_pose"),
    Def("lampway_weight_audit", "Read-only audit of a skinned mesh's weights, or a plan for how to bind it. audit: unweighted vertices, vertices over the influence cap, sums not 1, per-bone counts and mean weight, a "
        "rigid check (intended {rigid_bone}: vertices with any other influence), a side check (a *_l group on a right-side mesh), and competing-bone hotspots (two bones each >= 20 %). plan: rigid (>= 90 % of the "
        "vertices nearest one bone) or deforming (it spans bones that rotate against each other), with the bone(s) and the reason. An unbound object is told to bind first. Nothing is changed.",
        [P("action", required=True, desc="audit | plan"), P("object", required=True), P("armature", required=True), P("intended", "object", "{rigid_bone: name}"),
         P("max_influences", "integer", "1..8, default 4"), P("side", desc="left | right (default: inferred from the mesh)")], api="weight_audit"),
    Def("lampway_weight_cleanup", "Fix weights on a COPY named <object>_wclean. ops in order: {op: normalize}, {op: limit, max_influences}, {op: remove_influence, bone, region: {bbox} | {vertex_group}} (refused over "
        "40 % of the vertices: that is a rebind; never leaves a vertex unweighted), {op: smooth, iterations, factor, region}, {op: rigid, bone, region}. Returns the ops applied and the audit of the result.",
        [P("object", required=True), P("armature", required=True), P("ops", "array", "the ops", required=True), P("mirror_from", desc="not built")], api="weight_cleanup"),
    Def("lampway_weight_transfer", "Copy skin weights from a rigged body onto a piece by closest-surface matching (distance <= max_distance, default 0.05 m, and normal within max_normal_angle, default 30), then "
        "inpaint every unmatched vertex so armpits and gaps blend. engine algorithmic: a harmonic fill; robust: the SIGGRAPH Asia 2023 biharmonic method in the science python. Source needs vertex groups and "
        "exactly one Armature modifier. Result: a NEW object <object>_wt with the body's groups (capped at limit_groups, default 4). The original is untouched.",
        [P("object", required=True), P("source", required=True, desc="the rigged body"), P("max_distance", "number", "0..0.5, default 0.05"), P("max_normal_angle", "number", "degrees, default 30"),
         P("flip_normals", "boolean", "default true"), P("inpaint_mode", desc="point (default) | surface (robust)"), P("limit_groups", "integer", "default 4, 0 = no cap"),
         P("deform_only", "boolean", "default true"), P("name", desc="the new object's name"), P("engine", desc="algorithmic (default) | robust")], api="weight_transfer"),
    Def("lampway_garment_clearance", "How far a piece sits from the body in rest and named poses: the signed distance (positive outside, negative inside) of every piece vertex to the body posed by its armature. "
        "pose_set rest | wiki8 | a list [{name, bone, rotate: [x, y, z degrees]} | {name, bones: [...]}]; poses are reset afterwards. Per pose: min_clearance_m, penetrating_vertices, max_depth_m, worst_region, the "
        "blocking body triangles and pass (every vertex clears its target: clearance_target_m, default 0.015, or the target of the piece's vertex group named in `classes`). Also pass_pose_count and closest_pose. "
        "Refused: an unskinned body, a piece more than 0.5 m away (run place_piece first).",
        [P("piece", required=True), P("body", required=True), P("armature", required=True), P("pose_set", desc="rest (default) | wiki8 | a list of poses"),
         P("clearance_target_m", "number", "0..0.1, default 0.015"), P("classes", "object", "{vertex group: target metres}")], api="garment_clearance"),
    Def("lampway_fit_place", "Place a piece on the body by ENCLOSURE with ONE uniform scale (never registration, never a per-region push): kind helmet = the widest head level above neck_02; waist = "
        "the band at spine_01 + 3 cm; boots = shaft width | knee height | foot length by scale_anchor (REQUIRED: the user has not ruled which anchor); gauntlets = the bracer at 35 % of its length "
        "vs the forearm's middle (an axis >25 degrees off is refused); chest = the audits' placement unchanged. piece and body are npz files (mesh_to_npz; the body with joints); turn brings the piece "
        "to -Y front, +Z up. Writes placed.npz + .json (scale, translation, anchor_shift, turn) and returns the report. Run before mesh-paint and texture: a geometry step discards a texture.",
        [P("kind", required=True, desc="chest | helmet | waist | boots | gauntlets"), P("piece", required=True), P("body", required=True), P("turn", "number", "default 0"),
         P("clear_mm", "number", "wear clearance 0-40, default 15"), P("scale_anchor", desc="boots: width | height | foot"), P("sides", desc="both (default) | l | r"),
         P("out", desc="default placed.npz")], api="fit_place"),
    Def("lampway_fit_openings", "The openings decision at fit: every cap a seed put across a limb, neck or waist opening gets keep | gasket | delete, logged append-only in <piece>/fit/decisions.jsonl. "
        "stage detect: the capped sites along `axis` (pointing out of the piece); propose: proposals only (the user rules); apply: answers {'OP000': 'gasket'}; check: manifold report; variants: "
        "builds and renders three collar depths. A GASKET cuts the POSED limb's cross-section (`limb`, an object) plus clearance_mm (5..40, default 15) into the cap plane and forms a COLLAR: a tubular "
        "flange into the piece whose free edge rolls outward into a lip (an exhaust/intake manifold port, not a raw hole). Its depth `flange_mm` (2..60) is the user's number: without it apply answers "
        "needs_decision. Needs `pose` (the fit_pose result), never the rest pose. Result `<object>_openings`; the source is untouched; a studio texture is discarded (texture_discard_ack).",
        [P("stage", required=True, desc="detect | propose | apply | variants | check"), P("object", required=True), P("axis", "array", "The opening's axis [x, y, z], pointing out of the piece"),
         P("plane_origin", "array", "A point on the cap plane (selects one site)"), P("limb", desc="The posed limb object whose section is cut"), P("pose", "object", "The fit_pose result"),
         P("answers", "object", "{'OP000': 'keep'|'gasket'|'delete'}"), P("flange_mm", "number", "Collar depth, 2..60 (the user's number)"), P("lip_mm", "number", "Rolled lip radius, default 4"),
         P("clearance_mm", "number", "5..40, default 15"), P("piece"), P("captain_words", desc="Quoted into the decision row"), P("texture_discard_ack", "boolean"),
         P("depths_mm", "array", "variants: the depths, default 10, 20, 35"), P("size", "integer", "variants: image size")], api="fit_openings"),
    Def("lampway_detail_normals", "Micro depth for a textured_atlas material without the relief map: per-material tiling detail normals box-projected "
        "in object space (metals take their ambientCG NormalGL maps; cloth and leather a small bump from their colour), blended by the material's "
        "per-texel masks. Idempotent: its 'DN:' nodes are replaced on a re-run. strengths: {plate, gold, cloth, leather}.",
        [P("material", required=True), P("strengths", "object", "Per-layer strengths, defaults plate 0.6, gold 0.45, cloth 0.25, leather 0.3"),
         P("ambientcg_dir", desc="The ambientCG folder (default: the settings / LAMPWAY_AMBIENTCG_DIR)")], api="detail_normals"),
    Def("lampway_image_to_3d", "Image to 3D / multi-view WITHOUT a model: mode hull = the visual hull of two or more cardinal views "
        "(images = {\"Front\": path, \"Left\": path, ...}; Front u=+X, Left u=-Y; silhouettes from alpha or the corner colour), "
        "extrude = a rounded or slab extrusion of Front (+Back) for paired pieces (depth in metres), relief = a luminance relief of one "
        "image. The mesh is judged by re-projection IoU, volume and boundary edges. engine=studio:tripo is the Smart Mesh slot "
        "(100 credits): it answers with action and price for the owner's approval and clicks nothing." + _PATHS,
        [P("images", "object", "View name -> image path (project-relative)", required=True), P("size", "number", "Height in metres, default 1"),
         P("resolution", "integer", "Voxels along the height, 8-160, default 64"), P("mode", desc="hull (default) | extrude | relief"),
         P("depth", "number", "extrude/relief depth in metres"), P("profile", desc="extrude: round (default) | slab"), P("name"),
         P("engine", desc="algorithmic (default) | studio:tripo")], api="image_to_3d"),
    Def("lampway_splat_import", "Import a 3D Gaussian Splatting PLY (binary little endian with x y z f_dc_0..2 opacity scale_0..2) as ONE point "
        "object with colour, opacity and radius attributes and a geometry-nodes view. A splat has no faces and is never converted to "
        "a mesh; max_points subsamples deterministically. Generating a splat from an image or text needs a world model (not wired)."
        + _PATHS, [P("path", required=True), P("max_points", "integer", "Default 200000"), P("name")], api="splat_import"),
    Def("lampway_render_video", "Video: render a turntable or a keyframed camera path (waypoints [{frame, location}]) of an object to an H.264 mp4 "
        "under the project root, in a throw-away scene, with the light engines only (workbench | eevee; Cycles is refused). The file is "
        "read back (frames, size, bytes). engine=model:<name> is the generative video slot: not wired." + _PATHS,
        [P("object", required=True), P("out", desc="mp4 path under the project root", required=True), P("kind", desc="turntable (default) | camera_path"),
         P("frames", "integer", "Turntable frames, default 48 (max 1200)"), P("width", "integer"), P("height", "integer"), P("fps", "integer"),
         P("engine", desc="workbench (default) | eevee"), P("waypoints", "array", "camera_path waypoints")], api="render_video"),
    Def("lampway_project_views", "Project cardinal-view images ({\"Front\": path, ...}, each framed to the subject) into the UV atlas of a mesh by "
        "which way each texel faces (with an occlusion ray test) and apply it as the material `<object>_proj`; reports coverage and the share "
        "of texels each view painted. The object needs UVs." + _PATHS, [P("object", required=True), P("views", "object", "View -> image path", required=True),
        P("size", "integer", "Atlas size, default 1024"), P("out", desc="Atlas PNG path"), P("occlusion", "boolean", "Default true")], api="project_views"),
    Def("lampway_texture_gen", "Texture Gen: a clay render of each view goes to the image model with the prompt, the painted views are projected into the "
        "mesh's UV atlas and applied as a material. The object needs UVs; the image step costs money (about $0.07 an image on OpenRouter) and "
        "runs on the server's image slot. engine=studio:tripo is the Texture + PBR slot (30 + 5 credits): it answers with action and price "
        "for the owner's approval and clicks nothing." + _PATHS, [P("object", required=True), P("prompt", required=True), P("out_dir", desc="Folder for the clay, painted views and atlas"),
        P("views", "array", "Default Front, Back"), P("size", "integer"), P("engine", desc="algorithmic (default) | studio:tripo")], api="texture_gen"),
    Def("lampway_ai_render", "AI Render: a clay render of an object from a view goes to the image model with the prompt; the result is saved and loaded as a "
        "Blender image. Look development only: it changes nothing in the scene. Costs about $0.07 on OpenRouter." + _PATHS,
        [P("object", required=True), P("prompt", required=True), P("view", desc="Front | Back | Left | Right"), P("out", desc="Result PNG path"), P("size", "integer")],
        api="ai_render"),
    Def("lampway_repair_texture", "Local texture repair: blend a patch image through a mask (both framed like a clay render of the view) into an existing "
        "atlas, only where the surface faces that view; writes `out`, never overwrites the original." + _PATHS,
        [P("object", required=True), P("texture", required=True), P("view", required=True), P("patch", required=True), P("mask", required=True),
         P("out", required=True), P("feather", "number")], api="repair_texture"),
    Def("lampway_pbr_merge", "The engine-ready PBR set (BaseColor sRGB, Normal GL and DX, ORM = occlusion/roughness/metallic, Roughness, "
        "Metallic) for a patched mesh from a studio PBR set plus our projection: the studio texels are kept, the patch islands are "
        "filled from our albedo atlas and the class medians, the live palette is baked in linear space, metal is forced to 0 on "
        "non-metal classes. Writes merge.json beside the maps." + _PATHS, [
        P("out_dir", required=True), P("base", desc="Studio base colour map", flag="--base", required=True),
        P("normal", flag="--normal", required=True), P("rough", flag="--rough", required=True), P("metal", flag="--metal", required=True),
        P("masks", desc="Directory with mask_*.png and texel_face.npy (the projection's)", flag="--masks", required=True),
        P("albedo", desc="Our projected albedo atlas (v3_colour_atlas.png)", flag="--albedo", required=True),
        P("mesh_npz", desc="The piece_uv npz", flag="--mesh-npz", required=True), P("orig_poly", flag="--orig-poly", required=True),
        P("params", desc="live_material_params.json (palette per mask, metal_zero_on, normal strength)", flag="--params", required=True),
        P("res", "integer", "Map size, default 4096", flag="--res"), P("base_res", "integer", "Base colour size, default 8192", flag="--base-res"),
        P("ao", desc="An AO map for ORM.R", flag="--ao"), P("dilate", "integer", flag="--dilate")], batch="pbr_merge"),
    # ---- the parts tools
    Def("lampway_delete_caps", "Delete a cap that closes an opening that must stay open (neck bowl, waist fan, arm dome) by ray-casting "
        "through a rectangular footprint; UVs kept; writes a NEW file." + _PATHS, [
        P("input", required=True), P("output", required=True), P("axis", desc="z+ | z- | x+ | x- | y+ | y-", flag="--axis", required=True),
        P("footprint", desc="x0,x1,y0,y1 in metres", flag="--footprint", required=True),
        P("beyond", "number", "threshold coordinate: the cap is the first hit beyond it", flag="--beyond", required=True),
        P("step", "number", flag="--step"), P("grow", "integer", "rings of neighbouring polygons also deleted", flag="--grow")],
        batch="delete_caps"),
    Def("lampway_render_owner", "Render a mesh coloured by its part owner map: four orthographic views plus a legend; flagged "
        "polygons in magenta." + _PATHS, [P("mesh", required=True), P("owner", required=True), P("recipe", required=True),
        P("out_prefix", required=True), P("turn", "number", flag="--turn"), P("flag_poly", flag="--flag-poly")], batch="render_owner"),
    Def("lampway_split_relief", "Split a raised relief (the pauldron lion heads) out of its part as a material-only part, by the "
        "part's dense Smart UV islands." + _PATHS, [P("out_prefix", required=True), P("piece_uv", required=True),
        P("owner_tri", required=True), P("recipe", required=True),
        P("split", "array", "part:new_part pairs", flag="--split", repeat=True, required=True),
        P("max_face_mm2", "number", flag="--max-face-mm2"), P("min_share", "number", flag="--min-share")], batch="split_relief"),
    Def("lampway_transfer_parts", "Carry an APPROVED part set onto a new seed of the same design (body-frame nearest label, then a "
        "Smart UV island vote; weak islands are flagged, never silently relabelled)." + _PATHS, [
        P("out_dir", required=True), P("body", required=True), P("old", required=True), P("old_owner", required=True),
        P("recipe", required=True), P("new_piece_uv", required=True), P("old_turn", "number", flag="--old-turn"),
        P("new_turn", "number", flag="--new-turn"), P("weak", "number", flag="--weak"), P("far_mm", "number", flag="--far-mm")],
        batch="transfer_parts"),
    Def("lampway_apply_part_fixes", "Apply an auditor's part fixes (island or bbox relabels) to a transferred owner map; writes a new map."
        + _PATHS, [P("transfer_dir", required=True), P("piece_uv", required=True), P("recipe", required=True), P("fixes", required=True),
                   P("out_owner_poly", required=True)], batch="apply_part_fixes"),
    # ---- the proportion tools
    Def("lampway_mesh_to_npz", "Export a mesh (fbx/glb) or the MetaHuman body (with joints) to npz for the proportion tools."
        + _PATHS, [P("out", required=True), P("mode", desc="piece | piece_uv | body", required=True), P("file", required=True)],
        batch="mesh_to_npz"),
    Def("lampway_proportion_ratios", "The PRIMARY proportion score of torso pieces against the MetaHuman body: scale-free landmark "
        "ratios (lower is closer; 0 = the body's proportions)." + _PATHS, [P("out", required=True), P("body", required=True),
        P("pieces", "array", "name=piece.npz:turn_deg entries", required=True)], batch="proportion_ratios"),
    Def("lampway_piece_ratios", "Proportion scores of the NON-torso pieces (kind helmet | waist | boots | gauntlets) against the MetaHuman body: scale-free landmark ratios, "
        "piece vs body + a uniform wear clearance, score = RMS log deviation (0 = the body's proportions). The torso (chest) is lampway_proportion_ratios. NEW and UNVALIDATED "
        "(`validated: false` until an auditor's falsification is recorded): it ranks, it does not decide. Known biases: helmet depth includes a crest, the waist scores the design "
        "flare, boots score knee height and relief, gauntlets cannot see collapsed or slotted plates. A gauntlet that is not cuff-up is refused. body.npz needs joints (mesh_to_npz body)."
        + _PATHS, [P("kind", required=True, desc="helmet | waist | boots | gauntlets"), P("out", required=True), P("body", required=True),
                   P("pieces", "array", "name=piece.npz:turn_deg entries (Tripo FBX: -90)", required=True), P("clear_mm", "number", "Wear clearance in mm, 0-40, default 15", flag="--clear-mm")],
        batch="piece_ratios"),
    Def("lampway_place_piece", "Place a torso piece on the body the way the audits do (chest width + 40 mm, axilla aligned)." + _PATHS,
        [P("placed", required=True), P("body", required=True), P("piece", required=True), P("turn", "number", flag="--turn")],
        batch="place_piece"),
    Def("lampway_pose_clearance", "The MetaHuman's closest pose to a placed piece (arms, hips, chest, neck) and the residual blocking "
        "surfaces." + _PATHS, [P("out_dir", required=True), P("body", desc="Body glb", required=True), P("placed", required=True)],
        batch="pose_clearance"),
    Def("lampway_mesh_compare", "Compare candidate meshes with a reference: faces, open boundary loops, shells, matcap renders."
        + _PATHS, [P("out_dir", required=True), P("reference", required=True), P("candidates", "array", required=True)],
        batch="mesh_compare"),
    Def("lampway_pauldron_symmetry", "Is one pauldron sunken? Height maps of each shoulder against the mirrored other." + _PATHS,
        [P("compare_dir", required=True), P("labels", "array")], batch="pauldron_symmetry"),
]

BY_NAME = {d.name: d for d in DEFS}
SPECS = [d.spec() for d in DEFS]
