"""The agent's Lampway tools: definitions the model can call, each implemented as a script run through
blender.execute_script that calls mixar.modules.lampway_tools.api inside the app. The server never touches the
files itself. Arguments reach the script as a JSON string literal, so no argument value can change the code."""

import ast
import json

import pytest

from lampway_server.agent import lampway_tools as LT
from lampway_server.agent import vault_tools as LIB
from lampway_server.agent import tools as T
from lampway_server.agent import plan_tools as PLAN_TOOLS
from lampway_server.agent import orphan_server_tools as OST
from lampway_server.agent import blender_docs_tools as BDT


def args_of(script):
    """The api call's keyword arguments as the app will see them: evaluate only the JSON literal."""
    tree = ast.parse(script)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "call")
    return json.loads(ast.literal_eval(call.args[1]))


def test_every_lampway_tool_is_in_the_agents_tool_list_with_a_schema():
    names = {t.name for t in T.TOOLS}
    for expect in ("lampway_status", "lampway_qa_setup", "lampway_qa_candidates", "lampway_qa_draw", "lampway_qa_read_tags",
                   "lampway_qa_rulings", "lampway_rebuild_setup", "lampway_rebuild", "lampway_job_status", "lampway_run_tool",
                   "lampway_delete_caps", "lampway_render_owner", "lampway_split_relief", "lampway_transfer_parts",
                   "lampway_apply_part_fixes", "lampway_mesh_to_npz", "lampway_proportion_ratios", "lampway_place_piece",
                   "lampway_pose_clearance", "lampway_mesh_compare", "lampway_pauldron_symmetry", "lampway_meshpaint", "run_blender_python", "scene_summary"):
        assert expect in names, expect
    for t in T.TOOLS:
        assert t.parameters["type"] == "object" and t.description and len(t.description) > 30, t.name
    assert T.TOOL_NAMES == names


def test_a_tool_script_is_one_api_call_and_valid_python():
    s = T.script_for("lampway_qa_candidates", {"draw": True})
    ast.parse(s)
    assert "from mixar.modules.lampway_tools import api" in s and 'api.call("qa_candidates"' in s and "__RESULT__ =" in s
    assert args_of(s) == {"draw": True}


def test_arguments_cannot_break_out_of_the_script():
    nasty = "x'); import os; os.system('id'); ('"
    s = T.script_for("lampway_qa_setup", {"object": nasty, "recipe": "r.json"})
    tree = ast.parse(s)
    assert [type(n).__name__ for n in tree.body] == ["ImportFrom", "Assign"]            # nothing else was smuggled in
    assert args_of(s)["object"] == nasty


def test_unknown_arguments_are_dropped_not_forwarded():
    s = T.script_for("lampway_qa_candidates", {"draw": False, "evil": "x"})
    assert args_of(s) == {"draw": False}


def test_a_missing_required_argument_is_refused_before_blender_is_asked():
    with pytest.raises(T.UnknownTool, match="recipe"):
        T.script_for("lampway_qa_setup", {"object": "piece"})


def test_a_typed_batch_tool_builds_the_tools_argument_list_in_order():
    s = T.script_for("lampway_delete_caps", {"input": "a/in.fbx", "output": "a/out.fbx", "axis": "z+", "footprint": "-0.1,0.1,-0.1,0.1",
                                              "beyond": 0.33, "grow": 1})
    a = args_of(s)
    assert a["name"] == "delete_caps"
    assert a["args"] == ["a/in.fbx", "a/out.fbx", "--axis", "z+", "--footprint", "-0.1,0.1,-0.1,0.1", "--beyond", "0.33", "--grow", "1"]


def test_a_repeated_flag_tool_expands_each_value():
    s = T.script_for("lampway_split_relief", {"out_prefix": "o", "piece_uv": "p.npz", "owner_tri": "t.npy", "recipe": "r.json",
                                               "split": ["pauldron_right:lion_right", "pauldron_left:lion_left"]})
    assert args_of(s)["args"] == ["o", "p.npz", "t.npy", "r.json", "--split", "pauldron_right:lion_right", "--split", "pauldron_left:lion_left"]


def test_a_list_of_positional_values_is_flattened_in_place():
    s = T.script_for("lampway_proportion_ratios", {"out": "s.json", "body": "b.npz", "pieces": ["a=a.npz:-90", "b=b.npz:-90"]})
    assert args_of(s)["args"] == ["s.json", "b.npz", "a=a.npz:-90", "b=b.npz:-90"]


def test_a_mislabel_target_map_keeps_its_keys():
    s = T.script_for("lampway_qa_read_tags", {"mislabel_to": {"0": "plate"}, "close_round": True})
    assert args_of(s) == {"mislabel_to": {"0": "plate"}, "close_round": True}


def test_the_rebuild_tool_says_it_is_a_background_job():
    spec = next(t for t in T.TOOLS if t.name == "lampway_rebuild")
    assert "background" in spec.description.lower() and "lampway_job_status" in spec.description


def test_the_system_prompt_names_the_workflow():
    from lampway_server.agent.prompt import SYSTEM_PROMPT
    for needle in ("lampway_qa_setup", "Red", "Delete", "Mislabel", "Hole", "lampway_rebuild"):
        assert needle in SYSTEM_PROMPT


EXTRA_SERVER_TOOLS = {"lampway_engine_project", "lampway_workbench", "lampway_compute", "lampway_agent_files", "lampway_skills_list", "lampway_skill_read", "lampway_note_write"} | LIB.NAMES | {"lampway_cards", "lampway_connections", "lampway_choices"} | PLAN_TOOLS.NAMES | OST.NAMES | BDT.NAMES          # server-run tools added since the explicit list above (the Asset Vault family: vault_tools)


def test_every_tool_script_passes_the_clients_sandbox_dunder_rules():
    """The client rejects scripts that touch blocked dunder attributes (sandbox_validator.py); ours must not."""
    blocked = {"__subclasses__", "__bases__", "__mro__", "__globals__", "__code__", "__builtins__", "__loader__", "__spec__",
               "__class__", "__dict__", "__closure__", "__self__", "__func__", "__getattribute__", "__reduce__"}
    for t in T.TOOLS:
        if t.name in ("run_blender_python", "ask_user") or t.name.startswith("studio_") or t.name in ("lampway_video_gen", "lampway_video_models", "lampway_video_gate", "lampway_job_receipt", "lampway_video_ingest_url", "lampway_image_gen") or t.name.startswith("lampway_prompt_") or t.name.startswith("lampway_ledger_") or t.name == "lampway_job_services" or t.name == "lampway_seed_catalog" or t.name in EXTRA_SERVER_TOOLS:   # no script: the studio tools run on the server, ask_user is answered by the user
            continue
        sample = {}
        for k, v in t.parameters.get("properties", {}).items():
            if k in t.parameters.get("required", []):
                sample[k] = {"string": "x", "array": ["x"], "boolean": True, "number": 1, "integer": 1, "object": {}}[v.get("type", "string")]
        script = T.script_for(t.name, sample)
        attrs = {n.attr for n in ast.walk(ast.parse(script)) if isinstance(n, ast.Attribute)}
        assert not (attrs & blocked), t.name


def test_the_meshpaint_tool_is_one_api_call_with_its_stage():
    s = T.script_for("lampway_meshpaint", {"stage": "prompt", "view": "Left", "junk": 1})
    assert 'api.call("meshpaint"' in s and args_of(s) == {"stage": "prompt", "view": "Left"}
    with pytest.raises(T.UnknownTool, match="stage"):
        T.script_for("lampway_meshpaint", {"view": "Left"})


def test_wave0_tools_expose_the_new_arguments_to_the_agent():
    """Wave 0: detail_normals has a caller; asset_acceptance takes source_hash; rig_armor takes the clearance and seam arguments; auto_rig takes copy;
    pose_test takes clearance_body. Every argument reaches the script (an undeclared one would be dropped)."""
    byname = {t.name: t for t in T.TOOLS}
    assert "lampway_detail_normals" in byname
    s = T.script_for("lampway_detail_normals", {"material": "textured_x", "strengths": {"plate": 0.9}, "ambientcg_dir": "acg"})
    assert 'api.call("detail_normals"' in s and args_of(s) == {"material": "textured_x", "strengths": {"plate": 0.9}, "ambientcg_dir": "acg"}
    for name, extra in (("lampway_asset_acceptance", {"source_hash": "ab" * 32}),
                        ("lampway_rig_armor", {"clearance_body": "body_rigged", "min_clearance_m": 0.01, "seam_limit_m": 0.02}),
                        ("lampway_auto_rig", {"copy": False}), ("lampway_pose_test", {"clearance_body": "b", "seam_radius_m": 0.03})):
        args = {"object": "o", "armature": "a", "poses": []}
        got = args_of(T.script_for(name, {**args, **extra}))
        assert all(got.get(k) == v for k, v in extra.items()), (name, got)


def test_the_lineage_tool_reaches_blender_with_its_anchors_as_objects():
    t = {t.name: t for t in T.TOOLS}["lampway_asset_lineage"]
    assert t.parameters["properties"]["anchors"]["items"] == {"type": "object"} and set(t.parameters["required"]) == {"action", "object"}
    anchors = [{"name": "toe", "point": [1, 0, 0]}] * 3
    got = args_of(T.script_for("lampway_asset_lineage", {"action": "record", "object": "boot", "anchors": anchors, "junk": 1}))
    assert got == {"action": "record", "object": "boot", "anchors": anchors}


def test_piece_ratios_is_a_batch_tool_with_the_kind_first_and_the_clearance_as_a_flag():
    names = {t.name for t in T.TOOLS}
    assert "lampway_piece_ratios" in names
    s = T.script_for("lampway_piece_ratios", {"kind": "boots", "out": "s.json", "body": "b.npz", "pieces": ["a=a.npz:-90", "b=b.npz:-90"], "clear_mm": 20})
    assert 'api.call("run_tool"' in s
    got = args_of(s)
    assert got["name"] == "piece_ratios" and got["args"][:5] == ["boots", "s.json", "b.npz", "a=a.npz:-90", "b=b.npz:-90"] and got["args"][5:] == ["--clear-mm", "20"], got


def test_uv_tools_reach_blender_with_their_arguments():
    names = {t.name for t in T.TOOLS}
    assert {"lampway_uv_score", "lampway_uv_texel_density"} <= names
    got = args_of(T.script_for("lampway_uv_score", {"files": ["a.fbx"], "res": 2048, "gates": {"max_overlap": 0.01}, "junk": 1}))
    assert got == {"files": ["a.fbx"], "res": 2048, "gates": {"max_overlap": 0.01}}
    got = args_of(T.script_for("lampway_uv_texel_density", {"object": "boot", "weights": {"face": 1.5}, "target": "10.24 px/cm"}))
    assert got == {"object": "boot", "weights": {"face": 1.5}, "target": "10.24 px/cm"}


def test_seed_audit_reaches_blender_with_its_proposals_as_an_object():
    got = args_of(T.script_for("lampway_seed_audit", {"stage": "record", "piece": "Boots1", "proposals": {"v1": {"verdict": "usable"}}, "by": "model"}))
    assert got == {"stage": "record", "piece": "Boots1", "proposals": {"v1": {"verdict": "usable"}}, "by": "model"}


def test_qa_tag_layers_requires_the_explicit_target_piece():
    spec = next(t for t in T.TOOLS if t.name == "lampway_qa_tag_layers")
    assert "piece" in spec.parameters.get("required", [])
    with pytest.raises(ValueError, match="piece"):
        LT.build_script(next(d for d in LT.DEFS if d.name == "lampway_qa_tag_layers"), {})
