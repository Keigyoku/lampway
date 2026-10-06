"""The orphan tools (STATUS.md ORPHANS) in the agent's registry: each is a Def the model can call and the MCP endpoint offers, and each Def names an api
function that exists in the client's orphans_api.py with every parameter the Def declares (a Def the client cannot run is the defect Waves 2-4 shipped)."""

import ast
from pathlib import Path

from lampway_server.agent import lampway_tools as LT
from lampway_server.agent import orphan_tools as OT
from lampway_server.agent import tools as T
from lampway_server.mcp import offered_tools

API = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/orphans_api.py"
EXPECTED = ("lampway_side_label_check", "lampway_mirror_pair", "lampway_scale_to_measure", "lampway_uv_check", "lampway_render_condition_passes", "lampway_image_material_id", "lampway_parts_material_slots", "lampway_zone_sheet", "lampway_mesh_region_extract", "lampway_mesh_local_edit", "lampway_edit_locality_check", "lampway_mesh_join_boolean", "lampway_multi_piece_material", "lampway_seamless_tile", "lampway_relief_tiles", "lampway_image_upscale", "lampway_reference_pack", "lampway_workflow_reference_to_asset", "lampway_scribble_read")


def _client_functions() -> dict:
    tree = ast.parse(API.read_text())
    out = {}
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and any(getattr(d, "id", "") == "tool" for d in n.decorator_list):
            a = n.args
            out[n.name] = {x.arg for x in a.args + a.kwonlyargs} | ({"**"} if a.kwarg else set())
    return out


def test_every_orphan_tool_is_registered_offered_and_described():
    names = {t.name for t in T.TOOLS}
    offered = {t.name for t in offered_tools()}
    for name in EXPECTED:
        assert name in names and name in LT.BY_NAME and name in offered, name
    for d in OT.ORPHAN_DEFS:
        assert d.name.startswith("lampway_") and len(d.description) > 80, d.name


def test_every_orphan_def_names_a_client_function_with_its_parameters():
    fns = _client_functions()
    for d in OT.ORPHAN_DEFS:
        assert d.api in fns, f"{d.name}: no @tool {d.api} in orphans_api.py"
        params = {p.name for p in d.params}
        missing = params - fns[d.api]
        assert not missing or "**" in fns[d.api], f"{d.name}: the client function lacks {missing}"


def test_an_orphan_tool_script_is_one_api_call():
    s = T.script_for("lampway_side_label_check", {"object": "gauntlet_l", "declared_side": "left", "body_midline_x": 0.0})
    ast.parse(s)
    assert 'api.call("side_label_check"' in s


def test_segment_mesh_takes_island_labels():
    props = LT.BY_NAME["lampway_segment_mesh"].spec().parameters["properties"]
    assert props["labels"]["type"] == "object" and "island_labels" in props["labels"]["description"]
    s = T.script_for("lampway_segment_mesh", {"object": "chest", "labels": {"mode": "map", "island_labels": {"0": "skirt"}}})
    call = next(n for n in ast.walk(ast.parse(s)) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "call")
    import json
    assert json.loads(ast.literal_eval(call.args[1]))["labels"] == {"mode": "map", "island_labels": {"0": "skirt"}}


def test_texture_gen_takes_a_material_reference_variants_and_a_ledger_row():
    props = LT.BY_NAME["lampway_texture_gen"].spec().parameters["properties"]
    for k in ("reference_image", "count", "keep_original", "record", "piece", "delight", "min_coverage"):
        assert k in props, k


def test_layered_material_offers_mask_invert():
    d = LT.BY_NAME["lampway_layered_material"].description
    assert "mask_invert" in d and "Mask invert is not built" not in d


def test_auto_rig_takes_body_plans_naming_and_parts():
    props = LT.BY_NAME["lampway_auto_rig"].spec().parameters["properties"]
    assert {"naming", "parts", "chain_bones"} <= set(props) and "quadruped" in props["kind"]["description"]


def test_image_to_3d_takes_a_sheet_paired_and_the_multi_view_slots():
    sp = LT.BY_NAME["lampway_image_to_3d"].spec().parameters
    assert {"detect_views", "views", "paired", "plate_check"} <= set(sp["properties"]) and "images" not in sp["required"]
    assert "studio:meshy" in LT.BY_NAME["lampway_image_to_3d"].description


def test_anim_multiview_fit_offers_detect_and_refine():
    d = LT.BY_NAME["lampway_anim_multiview_fit"]
    props = d.spec().parameters["properties"]
    assert {"frames", "onnx", "armature", "mesh", "masks", "bones"} <= set(props) and "refine" in d.description and "not wired" not in d.description
