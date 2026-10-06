"""The Lampway tool definitions: what the model can call to work on a piece (mesh QA, the rebuild loop, the parts and
proportion tools). Each is a Python script the client runs in its sandbox via blender.execute_script; the script is one call
into ``mixar.modules.lampway_tools.api`` (inside the app) carrying its arguments as ONE JSON string literal, so no argument
value can change the code. The server never touches the user's files itself.

The studio drivers (Tripo) are not here: they spend credits and drive a browser, so they live in lampway_server/studios and
are called by the server directly, never through Blender.
"""

import json

from .tool_defs import Def, P, needs  # noqa: F401  (the records live in tool_defs.py; re-exported here)


class BadArguments(ValueError):
    pass


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


# 5.8 (HC14): each Def with an `engine` serves one Choices purpose; a local option is the Def's own method (or mode / weights)
ENGINE_PURPOSES = {"lampway_retopo": "3d.retopo", "lampway_uv_unwrap": "3d.uv", "lampway_segment_mesh": "3d.segment_mesh", "lampway_auto_rig": "3d.rig",
                   "lampway_image_to_3d": "3d.image_to_3d", "lampway_texture_gen": "3d.texture", "lampway_segment_image": "3d.segment_image"}
_LOCAL_ARG = {"lampway_retopo": ("method", {}), "lampway_uv_unwrap": ("method", {}), "lampway_segment_mesh": ("method", {}),
              "lampway_auto_rig": ("weights", {"heat_map": "auto", "proximity": "proximity"}),
              "lampway_image_to_3d": ("mode", {"visual_hull": "hull"}), "lampway_segment_image": ("method", {})}
_LEGACY_ENGINES = ("algorithmic", "studio:tripo")


def _engine_desc(name: str, legacy: str) -> str:
    from ..choices import registry as REG
    opts = ", ".join(REG.listed(REG.get(ENGINE_PURPOSES[name])))
    return f"{legacy}; or one of the purpose's options ({opts}); omit it to use the user's choice in Choices"


def _resolve_engine(name: str, given: dict) -> dict:
    """The engine an agent names is a job override (the purpose's policy decides: CH3); none named is the user's choice. A local option
    becomes ``algorithmic`` with the Def's method; a Studio option is passed as is (the client answers with that action for approval)."""
    from .. import choices as CH
    engine = given.get("engine")
    if engine in _LEGACY_ENGINES:
        return given
    pid = ENGINE_PURPOSES[name]
    try:
        r = CH.resolve(pid, CH.Job(override=engine or None, origin="agent"))
        oid = r.option
    except CH.NoChoice as exc:
        if engine and not exc.skipped:
            raise BadArguments(str(exc)) from None
        if not engine:
            return given                                    # nothing can serve now: the Def's own default runs, as before
        oid = engine
    out = dict(given)
    if oid.startswith(("local:", "deterministic:")):
        out["engine"] = "algorithmic"
        arg, names = _LOCAL_ARG.get(name, (None, {}))
        local = oid.split(":", 1)[1]
        if arg and not given.get(arg) and (local in names or arg == "method"):
            out[arg] = names.get(local, local)
    else:
        out["engine"] = oid
    return out


def ladder_models(category: str) -> dict:
    """HC17: the view_verify ladder's models - the purpose's resolution, and the fallback resolve(..., avoid=[the first])."""
    from .. import choices as CH
    pid = "image.reference_sheet" if category == "sheet" else "image.plates"
    out = {}
    try:
        first = CH.resolve(pid, CH.Job(needs={"runs_on": ["openrouter"]}))
        out["primary"] = first.model
        out["fallback"] = CH.resolve(pid, CH.Job(needs={"runs_on": ["openrouter"]}, avoid=(first.option,))).model
    except CH.NoChoice:
        pass
    return {k: v for k, v in out.items() if v}


def plate_template() -> str:
    """The Plates purpose's template param (Choices), else today's ``plate-4k-crisper`` (choices_migration.md 5.13)."""
    from .. import choices as CH
    try:
        return str(CH.resolve_params("image.plates").get("template") or "plate-4k-crisper")
    except Exception:  # noqa: BLE001 - an unreadable store keeps today's template
        return "plate-4k-crisper"


def build_script(d: Def, arguments: dict) -> str:
    arguments = arguments if isinstance(arguments, dict) else {}
    missing = [p.name for p in d.params if p.required and arguments.get(p.name) in (None, "")]
    if missing:
        raise BadArguments(needs(d.name, missing, d.spec().parameters))
    known = {p.name for p in d.params}
    given = {k: v for k, v in arguments.items() if k in known}
    if d.name in ENGINE_PURPOSES:
        given = _resolve_engine(d.name, given)
    if d.name == "lampway_view_verify" and given.get("action") == "ladder" and not given.get("models"):
        given["models"] = ladder_models(str(given.get("category") or "sheet"))
    if d.name == "lampway_plate_pick" and given.get("stage") == "prompt" and not given.get("template"):
        given["template"] = plate_template()                      # HC16: the Plates choice's template, not a literal
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
        "Yellow = Hole (placement Surface). Existing layers are kept. For a piece set up with lampway_qa_setup (piece, default the "
        "active one); refused when none is.", [P("piece", desc="The piece (default: the last one set up)")], api="qa_tag_layers"),
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
        "owner's approval and clicks nothing. method=autoremesher runs the Qt-free lampway-quadremesh configured by the settings key autoremesher_bin "
        "(never an argument), niced with a timeout; the result has no UV layer.", [P("object", desc="Mesh object name", required=True),
        P("target_faces", "integer", "Default 2000"), P("method", desc="quadriflow (default) | voxel | autoremesher"),
        P("engine", desc="algorithmic (default) | studio:tripo"), P("symmetry", "boolean"),
        P("adaptivity", "number", "autoremesher: 0..1"), P("anisotropy", "number", "autoremesher: 0..1"), P("sharp_edge", "number", "autoremesher: 30..180 degrees"),
        P("smooth_normal", "number", "autoremesher: 0..180 degrees"), P("edge_scaling", "number", "autoremesher: 1..4"), P("timeout", "integer", "autoremesher: 10..3600 s"),
        P("fallback", "boolean", "quadriflow / autoremesher: use the voxel remesh when the engine fails or leaves the mesh unchanged (else refused)"), P("hard_surface", "boolean", "autoremesher: hard-surface model type"),
        P("preserve_sharp", "boolean", "quadriflow: keep sharp (hard-surface) edges, default true")], api="retopo"),
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
        "The original is hidden, never deleted. engine=studio:tripo is the part-detection slot (answers with action and price). labels instead NAMES the "
        "UV islands as vertex groups <object>_<label> (nothing is split), with the Client's own island enumeration (Mesh Segment's island_labels): mode map "
        "takes island_labels {\"<island>\": label}; mode recipe gives each island the recipe part owning the majority of its faces in owner (a .npy per polygon, "
        "default the int face attribute 'part'), an island under min_share (0.6) unlabelled and named; labels outside the recipe's part names are refused, "
        "and more than max_unlabeled (0.3) of the faces unlabelled refuses to apply. Needs a UV map.",
        [P("object", required=True), P("method", desc="shells (default) | sharp | uv_islands"), P("angle", "number", "Degrees, default 40"),
         P("min_faces", "integer", "Merge regions under this many faces, default 1 (no merge)"),
         P("engine", desc="algorithmic (default) | studio:tripo"),
         P("labels", "object", "{mode: map | recipe, island_labels: {island: label}, recipe: parts json, owner: .npy, min_share, max_unlabeled}")], api="segment_mesh"),
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
        "quality. engine=studio:tripo is the Auto Rig slot (answers with action and price). Body plans beyond the humanoid, each from landmarks measured "
        "on the mesh standing on Z: quadruped | hexapod | octopod (feet clustered per side; upper, lower and foot per leg; spine, head, tail), avian (the "
        "humanoid with wing_* arms), serpentine | aquatic (a chain of chain_bones along the principal axis), auto (inferred, reported as kind_inferred). "
        "naming ue (default) | mixamo (mixamorig:*) | metahuman (the UE5 names; spine_04/05 and neck_02 are not made), humanoid and avian only; tripo is "
        "refused (its naming is not documented here). parts: more mesh objects rigged as ONE character with one armature.", [P("object", required=True),
        P("kind", desc="humanoid (default) | quadruped | hexapod | octopod | avian | serpentine | aquatic | auto"), P("weights", desc="auto | proximity"), P("facing", desc="-Y (default) | +Y"),
        P("naming", desc="ue (default) | mixamo | metahuman"), P("parts", "array", "more mesh objects of the same character"), P("chain_bones", "integer", "serpentine/aquatic: 3..64, default 10"),
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
        "nothing runs) | run | rerun (from_node) | confirm (from_node: ONE spend node runs once, on the user's word; its output is kept for exactly its inputs, "
        "and what depends on it can then run) | version / rollback (version) | template_save / template_use (template, description) | show. A spend node is only "
        "planned and priced by plan and run: the user confirms spends and what depends on it waits.",
        [P("action", required=True), P("name", desc="The graph's name"), P("graph", "object", "The graph (define)"), P("inputs", "object", "Values for {{name}} placeholders"),
         P("from_node", desc="rerun: the node to start from; confirm: the spend node"), P("version", desc="version / rollback: the version name"), P("template"), P("description")], api="workflow_graph"),
    Def("lampway_plate_pick", "Plates stage: stage prompt (the plate-4k-crisper template + variables for a view; render it and generate 4 images per view), score (rank the 4 "
        "regenerations in variants_dir against the approved V3 plate v3_dir/<View>.png by silhouette IoU x structure x (1 - colour error)), cut (the pick's deterministic alpha), "
        "run (score + cut + margins/aspect/view-correspondence checks -> <piece>/plates_4k_alpha/<View>.png + alpha.json), status. `pick` 1-4 is the user's override. Paired "
        "pieces: Front and Back only. Free and local; never overwrites.",
        [P("stage", required=True, desc="prompt | score | cut | run | status"), P("piece", required=True), P("view", desc="Front | Back | Left | Right"), P("paired", "boolean", "Front and Back only"),
         P("v3_dir", desc="Folder with <View>.png (RGBA) of the approved plates"), P("variants_dir", desc="Folder with 1.jpg..4.jpg for the view"), P("design_words", desc="prompt: the design inventory"),
         P("palette", desc="prompt: the colours"), P("pick", "integer", "1-4: the user's choice"), P("bg_threshold", "number", "0.01..0.2, default 0.06"),
         P("opening_iters", "integer", "default 3"), P("min_px", "integer", "Refuse variants smaller than this, default 1024"),
         P("template", desc="prompt: the library template (default: the Plates choice's template, plate-4k-crisper)")], api="plate_pick"),
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
        "in a niced HEADLESS Cycles worker, never the live scene. size a power of two 32..8192 (default 2048), margin_px default size/128 (>= 2), cage_extrusion_m 0..0.2 or auto (measured from the pair: the high-poly's height above the target; the ray reaches the cage plus its depth below), max_ray_m, samples 1..512; normals 16-bit, one GL bake, DX by flipping its green. "
        "Refused before running, each with its fix: no UV (unwrap first), overlapping UVs, unapplied non-uniform scale, source == target, a pair not aligned (bbox centres > 2 % of the diagonal), an "
        "unsupported map (curvature, cavity, dust, bevel, position are not Cycles bake types), an existing map without overwrite. Returns the PNG paths, the black-texel fraction per map with a "
        "cage-too-small hint, the colour spaces, and (attach) a <target>_baked material wired with the maps.",
        [P("source", required=True, desc="donor object name, or a list"), P("target", required=True, desc="the UV-mapped low-poly object"), P("maps", "array", "normal | albedo | ao (default normal, albedo)"),
         P("size", "integer", "power of two, default 2048"), P("margin_px", "integer", "0..64"), P("cage_extrusion_m", desc="0..0.2 or auto (measured, default)"), P("max_ray_m", "number", "auto: measured; with an explicit cage, twice it"),
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
    Def("lampway_fit_pose", "The closest pose of the body to a piece (canon 08). With dofs (bone, axis in the joint grammar, range <= 90 deg, step; the first with an expect for the "
        "sign check) and the scene's piece, skinned body and armature: a deterministic sweep, rays from each skin sample's bone axis to the piece, regions by bone; answers the pose in "
        "the replayable grammar with the A-pose and posed numbers and writes pose.json. Without dofs: chest is routed to pose_clearance; helmet | waist | boots | gauntlets: "
        "needs_decision - the bones, axes and ranges to sweep are the user's to rule; the contract's proposals are included, marked unverified.",
        [P("kind", required=True, desc="chest | helmet | waist | boots | gauntlets"), P("piece", desc="the placed piece"), P("body", desc="the skinned body"),
         P("armature", desc="the body's armature"), P("dofs", desc="[{bone, axis, range, step, expect, mirror}] or 'chest' (the canon's chest table)"), P("chain", "array", "[{bone, axis, range, step}] after the grid"),
         P("regions", "object", "{name: {bones, threshold_m}}"), P("out", desc="pose.json path under the project root")], api="fit_pose"),
    Def("lampway_weight_audit", "Read-only audit of a skinned mesh's weights, or a plan for how to bind it. audit: unweighted vertices, vertices over the influence cap, sums not 1, per-bone counts and mean weight, a "
        "rigid check (intended {rigid_bone}: vertices with any other influence), a side check (a *_l group on a right-side mesh), and competing-bone hotspots (two bones each >= 20 %). plan: rigid (>= 90 % of the "
        "vertices nearest one bone) or deforming (it spans bones that rotate against each other), with the bone(s) and the reason. An unbound object is told to bind first. Nothing is changed.",
        [P("action", required=True, desc="audit | plan"), P("object", required=True), P("armature", required=True), P("intended", "object", "{rigid_bone: name}"),
         P("max_influences", "integer", "1..8, default 4"), P("side", desc="left | right (default: inferred from the mesh)")], api="weight_audit"),
    Def("lampway_weight_cleanup", "Fix weights on a COPY named <object>_wclean. ops in order: {op: normalize}, {op: limit, max_influences}, {op: remove_influence, bone, region: {bbox} | {vertex_group}} (refused over "
        "40 % of the vertices: that is a rebind; never leaves a vertex unweighted), {op: smooth, iterations, factor, region}, {op: rigid, bone, region}. Returns the ops applied and the audit of the result.",
        [P("object", required=True), P("armature", required=True), P("ops", "array", "the ops", required=True), P("mirror_from", desc="not built")], api="weight_cleanup"),
    Def("lampway_joints_from_views", "Joints of a humanoid from orthographic views (canon 11): 2D keypoints made in known cameras are triangulated (exact for orthographic "
        "views; a view missing by more than max_px dropped; an ambiguous outlier refused), moved by a calibration measured on a body with known joints in the SAME cameras (a rig "
        "run needs it; known= writes one), and centred in the canonical mesh's limb cross-section. One view per joint, a calibration from another framing, or a 2D detector "
        "(a model slot pending the captain's decision) are refused. Writes {joints: {name: {pos_m, views_used, residual_px, calibrated, centred, centred_cm}}}.",
        [P("mesh", desc="the canonical example mesh (for centring)"), P("cameras", desc="project path {cameras: [{name, res, ortho, center, right, up, look}]}"),
         P("keypoints", desc="project path {keypoints_px: {joint: {view: [x, y, confidence?]}}}"), P("calibration", desc="calibration json from a known body in the same cameras"),
         P("known", desc="project path {joints_m}: calibrate instead, writing out"), P("detector", desc="keypoints_json (default) | rtmw_wholebody | rtmpose_hand (not installed)"),
         P("rig", "boolean", "default true: needs a calibration"), P("max_px", "number", "default 4"), P("centre", "boolean", "default true"),
         P("hidden", "array", "joints read off cloth: left out"), P("out", desc="default joints.json")], api="joints_from_views"),
    Def("lampway_normalize_rigged", "An armature and the meshes skinned to it into a canonical skeleton and canonical rigged meshes (canon: specs/canon/normalization): "
        "rig_inspect (convention, roster, units) then rig_normalize (unit and object scale, drift-checked), then the documents - bones with along = head -> the next joint "
        "(never the imported tail) and their frames; stamped lw_canon. Refused: a mixed convention, an incomplete roster (the missing bones named), units no known factor "
        "explains, a turn (the rig must face -Y). dry_run (default true) changes nothing and answers the plan.",
        [P("armature", required=True, desc="the armature object"), P("meshes", "array", "default: every mesh skinned to it"),
         P("profile", desc="ue5_body (default) | ue5_body_fingers | metahuman"), P("turn_deg", "number", "0 only (turning a rig is not built)"),
         P("dry_run", "boolean", "default true")], api="normalize_rigged"),
    Def("lampway_normalize_texture", "An image (a scene image, or a file under the project root, loaded raw) into a CANONICAL texture (canon: specs/canon/normalization): its role "
        "declared or from the declared source's naming (ambientcg | polyhaven | lampway; otherwise role=auto refuses), the colour space bound to the role and set on the image "
        "(sRGB basecolor/emission/reference, Linear Rec.709 hdri, Non-Color every data map), a normal map's GL/DX convention from the naming or declared (never assumed), "
        "ORM packed r=ao g=roughness b=metallic, size, bit depth, channels and the file's sha256 recorded; stamped lw_canon with a receipt. Tools that read images refuse a raw one "
        "with 'normalize first'.",
        [P("input", required=True, desc="image name or project path"), P("role", desc="auto (default: from source_naming) | basecolor | normal | roughness | metallic | ao | orm | height | "
         "displacement | emission | opacity | mask | material_id | curvature | hdri | reference"), P("normal_convention", desc="auto (default: from the naming) | gl | dx"),
         P("tiling_real_world_m", "array", "a tileable's physical size [w, h] in metres"), P("source_naming", desc="ambientcg | polyhaven | lampway | tripo | none (default)")],
        api="normalize_texture"),
    Def("lampway_normalize_mesh", "A raw mesh (a scene object, or a file under the project root, imported raw) into a CANONICAL mesh (canon: specs/canon/normalization): metres, +Z up, "
        "front -Y, transform applied, the scale state recorded (Tripo / Hi3D generator_normalised; real only with evidence), a generated mesh welded by position (1e-5 m, refused above 5 % merged), "
        "lw_source_face, pivot at the bounding box's bottom centre; stamped lw_canon with a receipt. The facing is DECLARED by turn_deg (-90 for a +X-facing import) or a recipe; never guessed "
        "('frame undecided'). A skinned mesh goes to the rig normalizer. Tools that read assets refuse a raw one with 'normalize first'.",
        [P("input", required=True, desc="object name or project path"), P("turn_deg", "number", "the piece's facing turn about Z"), P("plate", desc="approved Front plate (needs the facing margin)"),
         P("recipe", desc="a recipe json with turn_deg"), P("generator", desc="tripo_studio | tripo_api | meshy | hi3d | ... | lampway_tool | captain_authored | unknown"),
         P("want_scale", desc="any (default) | real"), P("scale_evidence", "object", "{method, value, reference} for real scale"), P("weld", desc="auto (default) | never"),
         P("weld_distance_m", "number", "1e-7..1e-3, default 1e-5")], api="normalize_mesh"),
    Def("lampway_weight_transfer", "Copy skin weights from a rigged body onto a piece (canon: specs/canon/07-skin-weights.md): the piece's vertices are WELDED by position first (weld_m, default 1e-5 m; 0 for an authored rig) so seam duplicates share one row, then closest-surface matching (distance <= max_distance, default 0.05 m, and normal within max_normal_angle, default 30), then "
        "inpaint every unmatched vertex so armpits and gaps blend. engine algorithmic: a harmonic fill; robust: the SIGGRAPH Asia 2023 biharmonic method in the science python. Source needs vertex groups and "
        "exactly one Armature modifier. Result: a NEW object <object>_wt with the body's groups (capped at limit_groups, default 4). The original is untouched.",
        [P("object", required=True), P("source", required=True, desc="the rigged body"), P("max_distance", "number", "0..0.5, default 0.05"), P("max_normal_angle", "number", "degrees, default 30"),
         P("flip_normals", "boolean", "default true"), P("inpaint_mode", desc="point (default) | surface (robust)"), P("limit_groups", "integer", "default 4, 0 = no cap"),
         P("deform_only", "boolean", "default true"), P("name", desc="the new object's name"), P("engine", desc="algorithmic (default) | robust"),
         P("weld_m", "number", "position weld before matching and inpainting, default 1e-5 m; 0 = no weld (an authored rig)")], api="weight_transfer"),
    Def("lampway_garment_clearance", "How far a piece sits from the body in rest and named poses: the signed distance (positive outside, negative inside) of every piece vertex to the body posed by its armature. "
        "pose_set rest | wiki8 | a list [{name, bone, rotate: [x, y, z degrees]} | {name, bones: [...]}]; poses are reset afterwards. Per pose: min_clearance_m, penetrating_vertices, max_depth_m, worst_region, the "
        "blocking body triangles and pass (every vertex clears its target: clearance_target_m, default 0.015, or the target of the piece's vertex group named in `classes`). Also pass_pose_count and closest_pose. "
        "Refused: an unskinned body, a piece more than 0.5 m away (run place_piece first), an open body without body_open_band_m (canon: specs/canon/15-clearance-penetration.md).",
        [P("piece", required=True), P("body", required=True), P("armature", required=True), P("pose_set", desc="rest (default) | wiki8 | a list of poses"),
         P("clearance_target_m", "number", "0..0.1, default 0.015"), P("classes", "object", "{vertex group: target metres}"),
         P("body_open_band_m", "number", "an OPEN body (boundary edges) is refused without it: vertices within this band of the opening stay unsigned (canon 15)")], api="garment_clearance"),
    Def("lampway_fit_validate", "Measure a bound piece through poses against its ORIGINAL shell and judge it (canon: specs/canon/05-fit-validation.md). measure: `bound` (an Armature-modified piece), `original` "
        "(the pre-fit source shell, REQUIRED: a baked rest hides the distortion; same vertex count), `poses` (named poses such as rest, wrist_r_plus30, elbow_r_70, curl_r_full, or [{name, bones: [{bone, axis: up | "
        "forward | lateral | {line: [a, b]} | {perp: [a, b], to}, deg}], expect: {joint, along | closer_to, min_cm}} | {name, curl: {side, fraction}} | {name, bone, rotate} (Euler stress set)]), `roles` {part: metal | "
        "leather | cloth | embroidery} (the user's or the recipe's, never a render's colour). The expect is measured on the posed JOINTS first: a wrong sign is REFUSED; an expect on the commanded angle is refused. "
        "Per pose and part: rigid residual with the scale FIXED, edge strain p95/max (fraction), the source seam ledger (open over 2 mm), SURFACE crossings both ways and inside vertices of `body`; rest fidelity per "
        "metal part; a capped crossing control (no crossing seen = UNPROVEN). Verdicts PASS | FAIL | UNVERIFIED (no limits for the role, or a metric not measured) | REFUSED | UNPROVEN; default limits are Titan's, "
        "adopted (metal rigid < 0.5 mm, strain p95 < 1 %, no body crossing). judge: re-judge a validation under new limits.",
        [P("stage", required=True, desc="measure | judge"), P("piece", desc="the piece's name"), P("bound", desc="the bound object"), P("original", desc="the pre-fit source shell"),
         P("poses", "array", "the poses"), P("roles", "object", "{part: role}"), P("limits", "object", "{status, body: {crossings}, metal: {rigid_max_mm, strain_p95}}"), P("body", desc="the posed body for crossings"),
         P("armature", desc="default: the piece's Armature modifier"), P("validation", desc="judge: a validation dict or file")], api="fit_validate"),
    Def("lampway_skeleton_export_check", "Check an armature in the scene or an FBX under the project root (exactly one) against a reference skeleton (target.names_from: a reference FBX). Reports leaf bones (`*_end`: "
        "export with add_leaf_bones off), missing and extra bones, parents that differ, the root, the unit scale (height ratio to the reference: a 100x export reads 100), the up axis and rest_vs_frame (bones posed with no "
        "animation: the bind pose was taken from a posed scene), with pass and reasons.",
        [P("armature", desc="armature object name"), P("fbx", desc="an FBX path (alternative)"), P("target", "object", "{names_from: a reference FBX}"), P("expect_unit_scale", "number", "default 1"),
         P("allow_extra_bones", "boolean", "default false")], api="skeleton_export_check"),
    Def("lampway_engine_import_check", "Static check of an exported package (a folder with an FBX and Textures/) against the engine's import rules: FBX header version (Unreal 7400+; FBX 2020.2 = 7700), mesh names and "
        "material slots, UCX_<Render>_NN collision meshes matching a render mesh, textures the materials name that are missing, textures nobody names, and an optional hand-run import receipt that is recorded, not judged.",
        [P("package_dir", required=True), P("engine", desc="unreal (default)"), P("collision", "array", "expected collision mesh names"), P("receipt", "object", "{engine_version, import_settings, wired_channels, notes}")], api="engine_import_check"),
    Def("lampway_fit_body", "The body for fitting as one hashed package. build: <out>/<sha8>/ with joints.json (parents before children; head, tail, rest axes in metres), body.npz when `mesh` is given, body.glb, the "
        "NATIVE weights sidecar.json when `sidecar` names a file the user's UE editor leg wrote, and receipt.json (sha256 of every file). verify: recompute the hashes ('the body asset changed: rebuild the package'). "
        "weights: refused unless a native sidecar is present. Only the project-native body is accepted; the UE editor leg itself is not run from here.",
        [P("verb", required=True, desc="build | verify | weights | show"), P("armature", desc="the body's armature object (build)"), P("mesh", desc="the body mesh object (build)"), P("glb", desc="a GLB to copy in"),
         P("native_asset", desc="must be under /Game/MetaHumans/"), P("uproject", desc="refused: the editor leg is the user's"), P("sidecar", desc="a native weights sidecar file"), P("out", desc="build: output folder; verify/weights/show: the package dir")], api="fit_body"),
    Def("lampway_fit_export", "The rigged export of a fitted piece, behind gates, with a read-back. Refuses: a missing validation or one with FAIL/UNPROVEN, roles with no declared limits (unless allow_unverified, then the README says "
        "so), a bind_check that is not ok, textures whose merge.json mesh_sha256 is another mesh (re-run steps 13-14), vertex groups naming a bone the body package lacks, an existing out_dir. Writes <object>.fbx (primary "
        "bone axis Z, secondary X, leaf bones off, units applied), Textures/, README.md and export.json, then reads the FBX back and compares every joint's position (0.1 mm) AND axes (0.5 degrees) with the body package.",
        [P("object", required=True), P("armature", required=True), P("out_dir", required=True), P("body", required=True, desc="the fit_body package dir"), P("textures", "array", "map paths (their merge.json names the mesh)"),
         P("validation", desc="validation.json"), P("bind_check", desc="bind_check.json"), P("note"), P("allow_unverified", "boolean", "default false")], api="fit_export"),
    Def("lampway_fit_bind", "Bind a finished piece to the body's skeleton by the user's weight laws. plan: per part (a vertex group of the piece) a role from `roles` {part: metal | leather | cloth | embroidery} (the user's or the "
        "recipe's, never a render's colour: a part without one is refused) and a mode - metal = rigid, ONE bone at full weight (blending it is refused: ask for a ruled cut), anything else = restrict (weighted by position from "
        "the body's weights, restricted to the bones its geometry spans); bind_overrides {part: {mode, bones, reason, fallback}}; two rigid parts of one shell on different bones open the seam (seam_opens). weights "
        "(canon: specs/canon/07-skin-weights.md): a copy <piece>_fit from `body_object` (a scene body: an approximation, the native sidecar sampler is not built); a restrict part is welded by position, matched only "
        "on the body's OWN region for its bones, a weight on another bone moves to its nearest allowed ancestor else the part's fallback (else refused by name), and a vertex left with no weight is refused. return: the metal rest residual vs the ORIGINAL shell. apply: refused while a seam opens unless accept_seam_gap_mm. report.",
        [P("stage", required=True, desc="plan | weights | return | apply | report"), P("piece"), P("armature"), P("roles", "object", "{part: role}"), P("bind_overrides", "object", "{part: {mode, bones, reason, fallback}}"),
         P("out_dir", desc="default fit/bind"), P("body_object", desc="weights: the skinned body object"), P("accept_seam_gap_mm", "number", "apply: accept an opened seam")], api="fit_bind"),
    Def("lampway_fit_glove", "The glove's plate labels as a typed decision. stage labels: `labels` {plate: bone} for EVERY plate (the piece's vertex groups; an unlabelled plate is named, never guessed), `roles` {plate: role}, "
        "the glove's own side's bones only, finger caps and the bracer metal = one rigid bone each, a cloth plate (the upper arm) never rigid. Writes <piece>/fit/glove_labels.json and one decision row per plate "
        "(decider by) and returns the bind_fragment for fit_bind. pose | bind | report need the hand-pose engine of the user's project: needs_decision.",
        [P("stage", required=True, desc="labels | pose | bind | report"), P("piece"), P("side", desc="r (default) | l"), P("labels", "object", "{plate: bone}"), P("roles", "object", "{plate: role}"),
         P("overrides", "object", "{plate: {mode}}"), P("by", desc="agent (default) | captain")], api="fit_glove"),
    Def("lampway_fit_state", "The descriptor / question / answer fit loop: NOT BUILT. Answers needs_decision: is the Laya / fit-model route still the direction now that fit_validate measures the fit?", [], api="fit_state"),
    Def("lampway_anim_reference_render", "The character at rest from a KNOWN orthographic camera on a plain grey background, front and side, with the camera recorded: the start images of the animation-from-video set. "
        "Writes ref_<view>.png, ref_<view>_mask.png and cameras.json (orthographic scale, px_per_m, centre, axes) in a throw-away Workbench scene, anti-aliasing off: the grey is exact and two renders are byte-identical. "
        "Refused: a perspective camera, a posed character, no skinned model, a figure whose feet or head leave the frame. Free.",
        [P("character", required=True, desc="object (its children are included) or collection"), P("views", "array", "front, side (default both)"), P("size", desc="WIDTHxHEIGHT, default 720x1280"),
         P("background", desc="#RRGGBB, default #808080"), P("camera", "object", "{ortho_scale, center, height_m}: default fit-to-height with a 6 % margin"), P("out_dir", desc="default anim/reference")], api="anim_reference_render"),
    Def("lampway_animation_retarget", "Bake an animation from one skeleton onto another: a NEW Action on the target, rest poses compensated (the target bone turns by the source bone's world rotation, whatever either "
        "rest is), the root following the source's travel scaled by the pelvis-height ratio, and measured (world-direction error of what was baked, foot slide, edge stretch of check_objects). source: an armature in "
        "the scene or a project-relative .fbx/.bvh/.glb; mapping 'auto' reads bone names (Mixamo, Rigify, UE, Bip01) to labels and sides; dry_run shows the mapping first. method 'constraints' is Copy Rotation + "
        "NLA bake and does NOT compensate a different rest pose. Refused: no action, humanoid set not covered (missing labels listed), scale outside 0.01..100, a file outside the project.",
        [P("source", required=True), P("target", required=True), P("action", desc="name, 'all', or the source's active"), P("mapping", desc="auto | preset name"), P("method", desc="matrix (default) | constraints"),
         P("root_motion", desc="keep | in_place"), P("scale", desc="auto or a number"), P("frame_range", "array", "[start, end]"), P("fps", "number"), P("check_objects", "array", "meshes bound to the target"),
         P("sample_frames", "integer", "2..64, default 8"), P("name", desc="default <action>_rt"), P("dry_run", "boolean"), P("keep_source", "boolean")], api="animation_retarget"),
    Def("lampway_anim_multiview_fit", "Motion from ONE split-screen clip (front + side), orthographic: per-panel 2D keypoints (JSON, 15 joints in the order of pipeline.anim_mv.JOINTS) triangulated to 3D, the side view's "
        "near/far leg labels corrected from the FRONT view, pelvis-relative, held frames listed, the grid clip's parallax giving the root speed. Refused: panels out of sync, no scale. single_view=true is the control "
        "that cannot tell legs apart (it says so). stage detect: the RTMW whole-body 2D detector on frames {front: [png] | folder, side: ...} with onnx = the RTMW "
        "weights the user put on disk (never downloaded; rtmlib + onnxruntime in the science python): COCO-WholeBody points mapped to the 15 joints, confidence "
        "kept, smoothed over time, written as front.json / side.json beside out. stage refine: the two-view SKINNED-silhouette analysis-by-synthesis: the "
        "character's own rig (armature, its skinned mesh) posed per frame, the evaluated mesh rasterised through the recorded cameras (cameras.json), and the "
        "bones' rotations (default thighs, calves, upper and lower arms; twist is not observable) moved by a coarse sweep then halving coordinate descent until "
        "both silhouettes match masks {front: dir, side: dir}; a receipt with IoU before/after per frame and the worst frames; key=true keys the rig. Free.",
        [P("front", desc="fit: front-panel keypoints JSON"), P("side", desc="fit: side-panel keypoints JSON"), P("calibration", "object", "{px_per_m}"), P("cameras", desc="cameras.json of anim_reference_render"),
         P("fps", "number"), P("single_view", "boolean"), P("grid_frames", "array", "PNGs of the side-track grid clip"), P("stage", desc="fit (default) | detect | refine"),
         P("out", desc="default anim/multiview/fit.json"), P("frames", "object", "detect: {front: [png] | folder, side: ...}"), P("onnx", desc="detect: the RTMW weights file"),
         P("armature", desc="refine: the character's armature"), P("mesh", desc="refine: its skinned mesh"), P("masks", "object", "refine: {front: dir, side: dir} of silhouette PNGs"),
         P("bones", "array", "refine: the bones to move"), P("step_deg", "number", "refine: default 8"), P("rounds", "integer", "refine: default 5"),
         P("key", "boolean", "refine: key the rig per frame")], api="anim_multiview_fit"),
    Def("lampway_anim_check", "Judge a tracked motion against BOTH views' masks and the ground, with numbers: G-OUT-front >= 0.80, G-OUT-side >= 0.85, G-LEGS >= 85 %, G-FOOT-SLIDE <= 1 cm, G-FOOT-PLANT <= 1 cm, G-TWIST "
        "<= 5 deg (unverified without twist), G-CLAIMS. Controls run on the same take (a fore-aft mirrored copy must fail G-LEGS, a dragged foot must fail the slide gate); a check whose controls cannot fail does not "
        "pass. A single view is refused. Thresholds are proposed; G-TOE is unverified.",
        [P("poses", required=True, desc="the anim_multiview_fit file"), P("masks", "object", "{front: dir, side: dir} of silhouette PNGs"), P("rendered", "object", "{front, side} dirs of posed silhouettes"),
         P("cameras", desc="cameras.json: a capsule stand-in silhouette is drawn when rendered is absent"), P("twist", "array", "[tracker yaws, refined yaws] in radians"), P("claims", "array", "[{text, measurement}]"),
         P("out", desc="default anim/check.json")], api="anim_check"),
    Def("lampway_anim_loop_export", "Turn a checked multi-stride take into one seamless loop (period found and refined, strides averaged by phase) with the export gates: G-LOOP <= 1 deg, G-LOOP-WRAP, G-SPEED "
        "within 5 %, G-STRIDES >= 4, G-SKEL against reference_bones. Refused: a take that failed anim_check, one stride, an export onto Manny. The AnimSequence, G-FIDELITY and G-ENGINE need the user's UE editor leg: "
        "reported not_run / unverified, never a pass.",
        [P("take", required=True, desc="JSON {quats, bones, root_y_m, fps, planted_foot_speed_mps}"), P("cycle", desc="auto | strides:N"), P("fps", "number", "30 default (24 the clips' native: the user's call)"),
         P("skeleton", desc="metahuman_base_skel"), P("check", desc="the anim_check file"), P("strides_note", desc="the user's note accepting 2-3 strides"), P("reference_bones", "array", "the reference bone names"),
         P("loop_tolerance_deg", "number"), P("out", desc="default anim/loop")], api="anim_loop_export"),
    Def("lampway_anim_clip", "Plan ONE character clip as a DRY RUN: the lampway_video_gen arguments (locked-camera prompt, Seedance 2.0, 720p 9:16 5 s), the list price (22.5 Higgsfield credits; $0.76 or $0.46 with the front "
        "clip as reference on OpenRouter, derived) and nothing spent. Run it with lampway_video_gen (the user confirms the cost), then gate the file with lampway_video_gate kind=clip; a failed gate is not retried.",
        [P("reference_image", required=True), P("view", desc="front | side"), P("motion", desc="walk | jog | run | idle | text"), P("driver_video", desc="the front clip, for the side view"),
         P("route", desc="higgsfield (default) | openrouter"), P("model"), P("duration", "integer", ">= 4"), P("resolution"), P("aspect_ratio", desc="9:16"), P("generate_audio", "boolean"),
         P("has_camera_record", "boolean")], api="anim_clip"),
    Def("lampway_anim_track", "Body tracking, video to the MetaHuman skeleton: the provider is the USER's decision, so this answers needs_decision with the question and the model slots (GEM-X, hosted SAM 3D Body, "
        "Uthana: all needs_approval) and names anim_multiview_fit as the primary tracker. Refused: gvhmr with shipping=true (research-only licence), no mask_dir, mha_markerless off Windows. stage coverage: >= 90 % of frames. "
        "Nothing is run or spent.",
        [P("provider"), P("shipping", "boolean"), P("clip"), P("mask_dir"), P("camera"), P("skeleton"), P("stage", desc="plan | coverage"), P("frames_with_pose", "array", "frame indices"), P("total_frames", "integer")], api="anim_track"),
    Def("lampway_anim_from_video", "The animation-from-video pipeline as ONE dry-run plan: reference render (free) -> clip (the only paid step, one spend card at list price) -> track (provider decision open) -> check -> loop "
        "export, with the decisions.jsonl path. stock_first refuses when a stock animation already has the move (retarget it). Nothing is run or spent; a failed gate stops the run and a clip is never re-drawn without the user.",
        [P("character", required=True), P("motion"), P("views", "array"), P("stock_first", "boolean"), P("provider_track"), P("route"), P("out_package"), P("stock_inventory", "array", "names of stock animations"),
         P("anim_dir")], api="anim_from_video"),
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
        "(100 credits): it answers with action and price for the owner's approval and clicks nothing. A turnaround SHEET is cut first: detect_views=<sheet> "
        "with views = the panel order left to right (never guessed) splits it into labelled views (a single image wider than 2:1 is refused: it would fuse "
        "the panels). paired=true (gauntlets, boots) takes front and back only. engine studio:tripo (tripo.mesh) | studio:meshy (meshy.multi_image_to_3d) | "
        "studio:hi3d (hi3d.image_to_3d) answer with the action and its plan_args for studio_plan after a plate check (a plate under 1024 px, without a "
        "subject or touching the border is named: fix the plate first; plate_check=false skips it)." + _PATHS,
        [P("images", "object", "View name -> image path (project-relative); or detect_views"), P("size", "number", "Height in metres, default 1"),
         P("resolution", "integer", "Voxels along the height, 8-160, default 64"), P("mode", desc="hull (default) | extrude | relief"),
         P("depth", "number", "extrude/relief depth in metres"), P("profile", desc="extrude: round (default) | slab"), P("name"),
         P("engine", desc="algorithmic (default) | studio:tripo | studio:meshy | studio:hi3d"), P("detect_views", desc="a turnaround sheet to cut into views"),
         P("views", "array", "detect_views: the panel order left to right, e.g. Front, Left, Back, Right"), P("paired", "boolean", "front and back only"),
         P("plate_check", "boolean", "studio engines: check the plates first, default true")], api="image_to_3d"),
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
        "mesh's UV atlas and applied as a material on a COPY <object>_tex (keep_original, default; the source keeps its materials). The object needs UVs; the "
        "image step costs money (about $0.07 an image on OpenRouter) and runs on the server's image slot. The views' coverage is measured on the clay renders "
        "FIRST: under min_coverage (0.6) the run is refused before anything is paid (add Back/Left/Right views). reference_image (a material reference) rides as "
        "the SECOND image; count 1..4 variants per view, the best silhouette IoU against the clay kept (picks lists every IoU); delight divides out baked "
        "low-frequency lighting before projection. Every run appends a ledger row (stage texture, hashes of the clay renders, reference, picked images and "
        "atlas; the image jobs carry their own price rows) unless record=false. engine=studio:tripo is the Texture + PBR slot (30 + 5 credits): it answers "
        "with action and price for the owner's approval and clicks nothing." + _PATHS, [P("object", required=True), P("prompt", required=True), P("out_dir", desc="Folder for the clay, painted views and atlas"),
        P("views", "array", "Default Front, Back"), P("size", "integer"), P("engine", desc="algorithmic (default) | studio:tripo"),
        P("reference_image", desc="a material reference image, passed second"), P("count", "integer", "variants per view 1..4, default 1"),
        P("keep_original", "boolean", "texture a copy <object>_tex, default true"), P("record", "boolean", "append a ledger row, default true"),
        P("piece", desc="the ledger piece, default the object name"), P("delight", "boolean", "flatten baked lighting, default false"),
        P("min_coverage", "number", "refuse under this surface coverage, default 0.6")], api="texture_gen"),
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
    Def("lampway_uv_rectify", "Straighten, rectify and gridify UV islands of strap-like geometry (straps, belts, bracers, skirt strips) on a NEW object ``<object>_rect``; the 3D mesh and the source's UVs are never changed. op auto: an island of quads forming a regular grid is gridified (quad-ring propagation; the spacing is the mean 3D edge length per column and row, `evenness` 0..1 blends it toward uniform, `geometry_ratio` 0..1 blends the aspect between the grid counts and the 3D lengths); a non-grid island with a bounding aspect over 3 is rectified; any other is SKIPPED with the reason, never dropped. op rectify: one simple boundary loop onto a rectangle from four corners (largest turns), the interior solved harmonically. op straighten: `edges` [[v, v], ...] an ordered chain goes onto an axis-aligned line at its cumulative 3D lengths (keep_length), the island's boundary stays, the rest relaxes. `islands` are ids from uv_score. Returns per island rectangularity (UV area / bounding box) and stretch p90/p10 before and after. Refused: no UV layer, a textured object (texturing comes last: discard_texture=true to override), a chain that is not one path inside one island.",
        [P("object", "string", required=True), P("op", "string"), P("islands", "array"), P("edges", "array"), P("evenness", "number"), P("geometry_ratio", "number"), P("keep_length", "boolean"), P("name", "string"), P("discard_texture", "boolean")], api="uv_rectify"),
    Def("lampway_uv_layout", 'Island layout operations the packer does not do, on a NEW object ``<object>_lay`` (the source keeps its UVs). ops (default [orient]): orient (each island to its minimal axis-aligned box), align_world (rotate so world_axis x|y|z|auto maps to UV +V, from the UV->3D Jacobian), stack_mirrored (islands whose geometry mirrors across mirror_axis, symmetric Chamfer <= match_tolerance metres: NOT a face-count rule, share one UV vertex by vertex; the mesh must be centred on the plane; stacking overlaps UVs so bake_maps refuses it unless stacked_ok), fix_flipped (the minority-winding islands are mirrored in U), sort (a shelf layout, padding). Returns oriented/aligned/flipped_fixed counts, the stacked pairs with their Chamfer distance, and a report (accidental overlap excluding stacked, the deliberate stacked overlap, flipped fraction, coverage). per_face is not built. Refused: unknown op, no UV layer, a textured object (discard_texture=true overrides), an off-plane mesh for stacking.',
        [P("object", "string", required=True), P("ops", "array"), P("world_axis", "string"), P("per_face", "boolean"), P("mirror_axis", "string"), P("match_tolerance", "number"), P("padding", "number"), P("repack", "boolean"), P("name", "string"), P("discard_texture", "boolean")], api="uv_layout"),
    Def("lampway_model_compare", "Put 2..4 models (GLB files under the project root, or scene objects) side by side with the numbers that decide. stats: read from the FILES without Blender: triangles, vertices, textures with their sizes and roles, which PBR channels were actually baked (a flat fallback is the finding), n-gon encoding, compression, generator. build: every model is normalised into the same 2-unit box in a scratch scene (yaw, scale the longest axis to 2, measure again, THEN centre), saved as compare.json under <root>/<piece>/compare/<id>/; blind=true replaces the names with aliases A..D assigned by file hash and seals the real labels until the user picks. numbers: per pair and view the silhouette IoU, area ratio, centroid shift AND the interior difference with ten height bands and the enclosed holes. reveal shows the labels (after the pick when require_pick). pick is the USER's: an agent is refused. close removes the scratch scene. Refused: fewer than 2 or more than 4 models, a file outside the root, not a glTF binary, a meshopt-only file for the 3D view. The live windowed viewer with synchronised cameras is not built (it needs the pop-out probe).",
        [P("action", "string"), P("set", "string"), P("views", "array"), P("size", "integer"), P("blind", "boolean"), P("require_pick", "boolean")], api="model_compare"),
    Def("lampway_clip_classify", "What kind of motion is each action on this armature, what should it be called, does it loop: all measured from six landmark bones (hip, head, hand.l, hand.r, foot.l, foot.r; the bone names default from the UE, MetaHuman and mannequin skeletons or are passed in `landmarks`), every length a fraction of the figure's height H (given, else the deform mesh's rest height, else head-bone to foot-bone; the source is reported). Returns per action the features (speed in H per SECOND: duration is (last - first) / fps), every class label that fits plus the primary one (null in a gap: a gap is a finding), the loop decision (true / false / null when not measurable; upstream's 0.5 deg + 0.01 H rule and what anim_loop_export's 1 deg limit would say, neither chosen), and a measured name with `inferred` true when its wording implies intent no number can prove. The default thresholds come from ONE subject on one rig (11 clips): single-subject, recalibrate before trusting a gap. A rig that scales joints is listed first. apply=props stores lw_clip_* on the Action; apply=rename is the USER's click (an agent is refused and may only propose names). The frame, action and pose are restored.",
        [P("armature", "string", required=True), P("action", "string"), P("samples", "integer"), P("fps", "number"), P("landmarks", "object"), P("figure_height_m", "number"), P("thresholds", "string"), P("apply", "string"), P("labels_for_naming", "object")], api="clip_classify"),
    Def("lampway_view_verify", "Is this generated image really the view that was asked for? admit: reject an empty, tiny, fragmented (largest piece under 0.60 of the figure) or duplicate (perceptual hash within 6 of a known_images plate) reference BEFORE any model is paid, with the reason. verify: measured checks on the silhouette (alpha, `mask`, or a flat background): shoulder-width ratio and mirror IoU about the figure's own axis, feet baseline, arm angle (A-pose is 30 to 60), framing margins, background flatness; verdict pass | soft_fail | hard_fail | uncertain with the signed estimated rotation, and every threshold (they are PLACEHOLDERS until calibrated on labelled images) in the result; asymmetric_ok (a weapon in one hand) skips the symmetry checks as not_applicable. A side view is `uncertain` (a profile cannot be read from a silhouette). A vision judge may rescue an uncertain and never override a measured hard failure; none is configured here (judge=vision is refused). ladder: the bounded retry decision over `attempts` [{verdict, reason, model, rotation_deg}]: accept | accept_with_warning | retry (the first on the same model, the second on the fallback, with the escalated prompt built from `original_prompt`) | stop at max_attempts (1..4, default 3, never bypassed) with the user's three options; it never generates. templates: the built-in prompt-library set.",
        [P("action", "string"), P("image", "string"), P("category", "string"), P("view", "string"), P("approved_front", "string"), P("mask", "string"), P("asymmetric_ok", "boolean"), P("judge", "string"), P("known_images", "array"), P("attempts", "array"), P("max_attempts", "integer"), P("original_prompt", "string"),
         P("models", "object", "ladder: {primary, fallback} (filled from Choices when omitted)")], api="view_verify"),
    Def("lampway_scene_cleanup", "Report first, then clean. plan_only (the default) reads the scene and changes nothing: per object the non-uniform scale, loose vertices, doubled vertices at the merge distance, non-manifold edges (wire, boundary, multi-face), flipped faces (found on closed shells with doubles welded, so a double cannot hide a flip), n-gons, material slots (unused, duplicates) and UV layers, plus the scene's orphan data blocks. plan_only=false runs the steps IN THE DOCUMENTED ORDER whatever order you list: apply_transforms, loose, merge_by_distance, non_manifold, normals (closed shells only), ngons (policy report | triangulate | keep), purge_orphans, naming (needs `convention`: prefix, suffix, lowercase, replace_spaces, strip_numeric_suffix: it will not invent one), materials_uvs (removes unused slots; duplicates are reported). merge_distance 'auto' = 1e-4 x the bounding diagonal (scale-aware); a merge that would remove more than 5 % of the vertices stops and says the threshold is wrong. Work happens on `<object>_clean` copies with the source hash recorded (copy=false edits in place and refuses shared mesh data). Refused: Edit Mode.",
        [P("objects", "array"), P("steps", "array"), P("merge_distance", "string"), P("ngon_policy", "string"), P("convention", "object"), P("plan_only", "boolean"), P("copy", "boolean")], api="scene_cleanup"),
    Def("lampway_batch_export", "Audit meshes against YOUR convention, fix it as one pass, and export each object to its own file. plan_only (the default) lists, per object, the violations (name, scale, origin, default material names, unused slots) and its new name, and changes and writes nothing. convention is required: {prefix, set, pattern ('{prefix}{set}_{piece}_{nn}'), origin base|center|keep, unit_scale, forward, up}: the tool will not invent one. A real run (plan_only=false) writes rename_map.json, renames, applies transforms and the base origin (apply: transforms, modifiers, merge_materials, drop_unused_slots), then exports each object from a temporary copy as fbx | glb | gltf | obj under out_dir (inside the project root), re-imports it and compares the bounding box (verified when within 1e-4), and writes manifest.json. The project's convention (unit scale and axes) is recorded on the first real run; a later differing call is refused. undo=<rename_map.json> restores the names (not transforms). Refused: a name collision, an unknown preset (unreal | unity | godot), usd (not built), glTF with a unit scale other than 1, a path outside the root, Edit Mode. The presets only default the axes and are unverified against each engine's importer.",
        [P("objects", "array"), P("collection", "string"), P("convention", "object"), P("format", "string"), P("preset", "string"), P("apply", "string"), P("out_dir", "string"), P("per", "string"), P("textures", "string"), P("plan_only", "boolean"), P("verify", "boolean"), P("undo", "string")], api="batch_export"),
    Def("lampway_camera_shot", "Cinema-mode shots from the agent. A shot is a camera tagged with its name; its keys are ordinary location, rotation and lens keyframes (editable in the scene). new: a camera framed on `target` (or the selected mesh) at lens_mm 18..135 and an aspect (16:9, 2.39:1, 9:16, 1:1, 4:3), key at `frame`. frame / key: re-frame or key the current pose. preset: the Client Director's moves from the camera's live pose, keys 12 frames apart: ORBIT_LEFT/RIGHT (an arc that keeps the subject framed), DOLLY_IN/OUT, DOLLY_ZOOM (widens the lens by 0.6 while dollying in), CRANE_UP/DOWN, PAN_LEFT/RIGHT; handheld adds a small deterministic jitter. render_guides: beauty, clay (Workbench, never Cycles) and depth (ray-cast, fixed near/far so frames compare; nearer is brighter) PNGs at every key under out_dir, the longest side `size`; refused with fewer than two keyed poses. delete removes a camera this tool made (or just the shot tag and keys from yours). list shows the shots. Your frame and render engine are restored.",
        [P("action", "string"), P("shot", "string"), P("camera", "string"), P("lens_mm", "string"), P("aspect", "string"), P("frame", "integer"), P("preset", "string"), P("target", "string"), P("passes", "string"), P("out_dir", "string"), P("handheld", "boolean"), P("size", "integer")], api="camera_shot"),
    Def("lampway_segment_image", "One image to per-part masks, no model: connected components (8-connected) on the alpha channel of a transparent plate (alpha_components) or on the foreground of an opaque sheet (color_regions: pixels that differ from the border's commonest colour). Writes mask_NN.png (8-bit, same size as the image, white = the part) and overlay.png (numbered tints) under out_dir inside the project root; masks are in reading order, left to right. expected_parts labels them only when the count matches. min_pixels (default 6000) drops specks and reports how many. Touching or overlapping parts are ONE component (the note says so). Refused: no transparency for alpha_components (use color_regions), more than 64 components (raise min_pixels), over 16 megapixels, a mask that already exists and differs (a record is never overwritten), a path outside the root, engine studio:* or model:* (no driver or provider exists for segmentation yet). Nothing lands in the scene.",
        [P("image", "string", required=True), P("method", "string"), P("min_pixels", "integer"), P("expected_parts", "array"), P("out_dir", "string"), P("engine", "string")], api="segment_image"),
    Def("lampway_procedural_library", "The procedural material library: 12 armour materials (bronze, gold, brass, steel, iron, two leathers, two cloths) built from parametric node-group templates and a preset table, registered in the Client's own material registry. Every material is one node group with a single Shader output and bounded inputs (Tint, Roughness Scale, Wear, Scale, Bump Strength, Seed, Mask: a mask input lets curvature drive edge wear), in Object space so no UVs are needed. list / find (query ranks by name; material_id for one; category metal|leather|cloth) return the materials with their inputs. seed registers them (idempotent; a changed manifest at the same library_version is refused unless upgrade). verify builds every group and reports shader outputs, input bounds and build time (bake_stats adds real Cycles bakes: base colour mean, hue, metallic and roughness means, and near-duplicate pairs). bake renders one material at size px with params to a PNG and its sha256 (compare_to another PNG for the mean difference). add_to_layer puts the material on `object` as a procedural layer of its paint stack (initialise one first if the refusal says so).",
        [P("action", "string"), P("category", "string"), P("query", "string"), P("material_id", "string"), P("object", "string"), P("layer_name", "string"), P("params", "object"), P("size", "integer"), P("bake_stats", "boolean"), P("compare_to", "string"), P("upgrade", "boolean")], api="procedural_library"),
    Def("lampway_layered_material", "The Client's layer-paint stack (an editable material built from layers and masks) from the agent. init puts a paint project on the mesh's material (a material that samples image maps is refused, naming them: init rebuilds the material and would drop them; params {discard_textures: true} starts anyway); inspect returns the stack ({index, name, type, enabled, blend, opacity, channels, mask}); add_layer {type: fill | paint | image | group, name, blend: MIX|ADD|MULTIPLY|SUBTRACT|SCREEN|OVERLAY, opacity 0..1, color [r,g,b] for fill, size for paint/image, mask: {type: edge_detect | color_id | vcol | image}, projection: uv | triplanar | planar | spherical | cylindrical | decal} (uv needs a UV map: otherwise use triplanar or unwrap first); add_procedural puts a library material (see procedural_library) on as a layer; set_params {opacity, enabled, name, blend_type, projection_type, translation, rotation, scale ...} edits layer_index (-1 = the active layer); apply_manifest builds a whole stack from a manifest (index 0 must be a PBR layer). mask {type, invert: true} inverts the new mask, and action mask_invert {params: {invert: true|false}} toggles the INVERT mask modifier on layer_index's first mask (the paint package's own modifier, added once). Refused: not a mesh, no paint project yet (the refusal names init), unknown blend / type / mask / projection (each lists the choices), mask_invert on a layer without a mask. One undo step per Blender operator the Client's package uses.",
        [P("action", "string"), P("object", "string"), P("material", "string"), P("layer", "object"), P("manifest", "object"), P("layer_index", "string"), P("params", "object")], api="layered_material"),
    Def("lampway_material_bake_export", "Bake the layer-stack material of `object` to the images a destination needs, in a niced HEADLESS Cycles worker (never your live scene). channels: base_color, roughness, metallic, normal, ao, emission (default base_color, roughness, metallic, normal); size a power of two 1024..8192; format png | exr | tiff | jpeg (jpeg with normal is refused: lossy normals); normal_green gl (OpenGL, Unity/Blender/Godot) | dx (DirectX, Unreal); pack=orm also writes <object>_orm (R occlusion, G roughness, B metallic; R is 1.0 with a warning when no ao was baked; roughness and metallic must be baked too). Base colour and emission are sRGB, everything else Non-Color. Writes the images and a README with every file's sha256 and the conventions under out_dir (inside the project root). The layer stack is untouched. Refused: no paint-stack material (build one with layered_material), no UV map, an unsaved project (allow_dirty=true to override), a bad size or channel, a path outside the root.",
        [P("object", "string", required=True), P("material", "string"), P("channels", "array"), P("size", "integer"), P("format", "string"), P("pack", "string"), P("normal_green", "string"), P("out_dir", "string"), P("samples", "integer"), P("allow_dirty", "boolean")], api="material_bake_export"),
    # ---- the Asset Vault, Blender side (the server-side lampway_vault_* tools are in vault_tools.py)
    Def("lampway_vault_place", "Put an Asset Vault asset (an id from lampway_vault_search) into the open scene in the way its kind needs, as ONE undo step, stamping lw_asset_id / lw_asset_version / lw_asset_sha256 on what it places. mode auto picks by kind: mesh -> import (glb/fbx/obj/usd) or append (.blend), link only for a .blend outside the managed store; image -> a reference empty; map -> assign_maps on a slot target; material -> assign_material (procedural, from its .blend) or assign_maps (a PBR set, wired by role: base colour sRGB, ORM split G roughness B metallic, a DX normal's green flipped); texture_set -> assign_maps; hdri -> set_world; video -> add_clip (a Movie Clip, or a strip at the current frame with target sequencer); animation -> apply_animation (a .blend action onto the target armature whose bones it names; a mismatch is refused: retarget with lampway_animation_retarget); rig -> attach_rig (the armature, bound to an object:<mesh> target); add_node_group drops a node group into node_tree:<material> (wired to the output only when the tree is empty). target {where: cursor | origin | object:<name> | slot:<object>:<index> | node_tree:<material> | sequencer}. options {collection, scale_to_unit (default true: the library's unit_scale), force (above 5M triangles), replace (over a layer-stack paint material), location [x, y] for a node, height (wire a height map to displacement), undo_step}. The response names every datablock and carries attribution text to keep when the licence asks for it. Refused: a UV layout, prompt, receipt or collection (not placeable), a moved file, a link of a managed file, a layer-stack paint slot without replace.",
        [P("asset_id", "string", required=True), P("version", "integer"), P("mode", "string"), P("target", "object"), P("options", "object")], api="asset_place"),
    Def("lampway_vault_catalog_export", "Publish Asset Vault assets as a Blender asset library under dest_library (inside the project root): a headless worker writes lampway_library.blend with every datablock (materials and node groups from their .blend, meshes, rigs, actions) marked as an asset in its catalogue (never your live file), and blender_assets.cats.txt from the taxonomy (<facet>/<label>; catalogue ids are UUID5 of the path, stable across exports). register=true adds the folder to Blender's asset libraries as library_name, so the Asset Browser and the island's library tab see it. Refused: a lampway_library.blend Lampway did not write, a kind that does not publish, a moved file." + _PATHS,
        [P("asset_ids", "array", required=True), P("dest_library", "string", required=True), P("register", "boolean"), P("library_name", "string")], api="asset_catalog_export"),
    Def("lampway_ue_material", "Translate a Principled material to Unreal's legacy Default Lit, deterministically: the UE material-instance parameters (BaseColor, Metallic, Roughness, Specular = clamp(2 x level x F0(ior) / 0.08), Emissive x k), blend mode Opaque | Masked (clip 0.3333) | Translucent, Two Sided = not backface culling, the textures' sRGB flags and compression, what is dropped (sheen, coat tint, anisotropy, thin film, diffuse roughness...) or clamped, and translation_sha256. mode report changes nothing; preview builds '<material> [UE]' with the UE Default Lit node group beside the untouched original; export reads the pbr_pack merge_json for colour spaces and the ORM order. on_loss refuse refuses any loss. Free, no model." + _PATHS,
        [P("material", "string", required=True), P("mode", "string"), P("merge_json", "string"), P("master", "string"), P("on_loss", "string"), P("profile", "string")], api="ue_material"),
    Def("lampway_ue_look", "The UE Look mode: predict what Unreal shows. apply switches the scene to one UE profile (exposure log2(k) + Bias - EV100, GI and reflections as the profile says, lights mapped by k, every material swapped to its UE Default Lit preview) and returns the receipt, the lights' UE values and the trust per difference class (measured | unmeasured | needs_decision); revert restores every value exactly; status says whether a look is on and which classes are still unmeasured (quote them before saying 'this is what UE will show'); generate writes the UE view's OCIO config; enable also writes the launcher's state (the next launch starts with the view), disable clears it. The tonemapper cube is generated on the UE side and named by the profile (tonemap_cube, tonemap_cube_meta) or by cube / cube_meta; a missing or mismatched cube is refused with the fix. parity=true is the parity-render rule set. Refused: Standard ACES, a non-sRGB working space, auto exposure or engine defaults with parity, area or temperature lights, a scene already in a look. Agents call it on headless copies; the captain's live scene changes only by his click. Free.",
        [P("action", "string", desc="apply | status | revert | enable | disable | generate"), P("profile", "string"), P("scope", "string", desc="scene | selected"), P("parity", "boolean"), P("receipt", "string"),
         P("cube", "string", desc="the UE-side .cube (read, never copied)"), P("cube_meta", "string", desc="its lampway.ue-cube-meta/1 sidecar")], api="ue_look"),
    Def("lampway_ue_export", "Export to Unreal by the ONE path the asset type allows, with receipts: skinned_piece (FBX, armature + mesh, bone axes Z/X, no leaf bones, tangents, triangles; fit_export's gates and the joint read-back: body package, validation, bind_check), static_prop, animation (every frame keyed at the scene rate; frame_rate must match) or texture_set (BaseColor / ORM / Normal_DX with their DECLARED colour spaces). Canonical input only: an unapplied transform, a negative scale or a non-metre scene is refused. Meshes are triangulated once on a temporary copy; a bake_receipt with other triangles is refused. Writes the FBX, Textures/, README.md, export.json (settings, content_sha256 with the FBX timestamp zeroed, read-back, losses) and ue_import.json (the only import settings the UE editor leg may use). glTF for a skinned asset is refused; an existing out_dir is refused. Free." + _PATHS,
        [P("type", "string", required=True, desc="skinned_piece | static_prop | animation | texture_set"), P("object", "string"), P("armature", "string"), P("action", "string"), P("out_dir", "string", required=True), P("textures", "string"), P("body", "string"), P("frame_rate", "integer"), P("hero", "boolean"), P("format", "string"), P("validation", "string"), P("bind_check", "string"), P("bake_receipt", "string"), P("profile", "string"), P("allow_unverified", "boolean")], api="ue_export"),
    Def("lampway_ue_parity", "The UE parity harness, Lampway half: build a standard scene (chart | furnace | normals | lights) from its one JSON description in a throw-away scene, render each view (front | three_quarter | grazing) headless in EEVEE under the UE look with parity rules to float EXR, and write report.json / report.md with versions, hashes and a verdict per difference class. The UE half needs box time (needs_box) until the UE editor leg captures ue_<view>.exr; with ue_captures the same report compares them (COL display <= 3 codes and linear < 1 %, SHD < 3 %, NRM sign 100 % and dE2000 <= 2, LGT < 2 %, GEO IoU >= 0.995). Refused: a profile with engine defaults, auto exposure, GI, reflections, SSAO, bloom, vignette or local exposure on; a mislabelled or .hdr capture; an existing out_dir. Free." + _PATHS,
        [P("scene", "string", required=True), P("profile", "string"), P("size", "integer"), P("views", "array"), P("out_dir", "string", required=True), P("ue_captures", "string"), P("ue_linear_scale", "number")], api="ue_parity"),
]

from .wave6_tools import DEFS as _WAVE6_DEFS  # noqa: E402  (after Def and P exist: wave6_tools imports them)

DEFS += _WAVE6_DEFS

from .orphan_tools import ORPHAN_DEFS  # noqa: E402  (the orphan tools, STATUS.md ORPHANS: their own file)
DEFS += ORPHAN_DEFS
from .rig_defs import RIG_DEFS  # noqa: E402  (the rig tools, specs/canon/rig_tools: their own file)
DEFS += RIG_DEFS

for _d in DEFS:                                                 # 5.8: every engine Def names its purpose's options
    if _d.name in ENGINE_PURPOSES:
        for _p in _d.params:
            if _p.name == "engine":
                _p.desc = _engine_desc(_d.name, _p.desc or "algorithmic (default) | studio:tripo")
BY_NAME = {d.name: d for d in DEFS}
SPECS = [d.spec() for d in DEFS]
