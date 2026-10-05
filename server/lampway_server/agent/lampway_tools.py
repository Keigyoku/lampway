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
                prop["items"] = {"type": "string"}
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
        "mesh's own frame (the lift). `orig_poly` is a rebuild's source-face map (-1 = patch). Must be called once per scene." + _PATHS,
        [P("object", desc="Name of the mesh object", required=True), P("recipe", desc="Parts recipe json", required=True),
         P("owner", desc="Owner map .npy"), P("piece", desc="Piece name (rulings live in <root>/<piece>/rulings)"),
         P("session", desc="Decision-log session name"), P("offset", "array", "Live frame minus mesh frame, [x, y, z] as strings"),
         P("orig_poly", desc="Rebuild's orig_poly .npy"), P("turn", "number", "Turn about Z in degrees (the rebuild's)"),
         P("rulings_dir", desc="Rulings directory"), P("min_perimeter", "number", "Open loops shorter than this (m) are ignored; default 0.15"),
         P("max_shell_tris", "integer", "A floating shell has at most this many triangles; default 400"),
         P("float_mm", "number", "A shell floats when its nearest neighbour is further than this (mm); default 3")], api="qa_setup"),
    Def("lampway_qa_tag_layers", "Add the three annotation tag layers the captain draws on: Red = Delete, Green = Mislabel, "
        "Yellow = Hole (placement Surface). Existing layers are kept.", api="qa_tag_layers"),
    Def("lampway_qa_candidates", "Find open loops (holes) and floating shells on the piece and write them as typed candidates "
        "(descriptor: size, bordering parts and their motion classes, side of the body, which views see it, what lies behind). "
        "Ruled deletions are applied first. `draw` also draws them into the scene.", [P("draw", "boolean", "Also draw them")],
        api="qa_candidates"),
    Def("lampway_qa_draw", "Draw the candidates into the scene (collection QA_candidates): yellow tubes along open loops, rings "
        "around floating shells, each labelled with its id, so the captain can review them and answer with the tag layers.", api="qa_draw"),
    Def("lampway_qa_read_tags", "Read the captain's Red/Green/Yellow annotation strokes: faces and Smart UV islands per stroke, the "
        "candidate loops a Hole stroke circles or runs along (or an orphan the generator missed), and the floating shell a Delete "
        "stroke sits on. With apply (default) writes the decision log and the rulings (deletions, relabels, texel overrides). A Green "
        "stroke needs a target part in `mislabel_to` ({stroke index: part}); without one it is returned in "
        "relabels_needing_a_target - never guess it. `close_round` answers every candidate nobody named 'keep'.",
        [P("apply", "boolean", "Write decisions and rulings (default true); false = a dry run"),
         P("close_round", "boolean", "Everything not named is intentional"),
         P("mislabel_to", "object", "Target part per green stroke index, e.g. {\"0\": \"cuirass_back_plate\"}")], api="qa_read_tags"),
    Def("lampway_qa_rulings", "Summarise the rulings so far: deleted faces, relabels, texel overrides, decision rows, and the latest "
        "answer per candidate.", api="qa_rulings"),
    Def("lampway_rebuild_setup", "Save what a rebuild needs besides the rulings: the SOURCE mesh and its owner map (rebuilds always "
        "start from the source), the relief views and plates, the live material to copy, where outputs go, the objects to hide."
        + _PATHS, [P("source_mesh", required=True), P("source_owner", required=True), P("relief_dir", required=True),
                   P("plates_dir", required=True), P("template_material", desc="Live textured material to copy", required=True),
                   P("out_root"), P("relabel_rules", "array", "FROM:TO:WITH relabel rules for patch_holes"),
                   P("turn", "number"), P("lift", "number"), P("previous", "array", "Object names to hide when the new one loads")],
        api="rebuild_setup"),
    Def("lampway_rebuild", "Read the captain's tags, write the rulings, rebuild the piece (patch holes, patch UVs, project colour, "
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
