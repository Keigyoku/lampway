"""The Wave 6 tools reach the agent: each Blender-side Def is in the agent's tool list and the MCP offer, builds one api.call script, and declares item
schemas that match what the tool reads (a list of objects is not a list of strings)."""

import ast
import json

from lampway_server.agent import lampway_tools as LT
from lampway_server.agent import tools as T
from lampway_server.agent import wave6_tools as W6
from lampway_server.mcp import offered_tools


def _args(script):
    call = next(n for n in ast.walk(ast.parse(script)) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "call")
    return call.args[0].value, json.loads(ast.literal_eval(call.args[1]))


def test_every_wave6_def_is_an_agent_tool_offered_over_mcp_and_one_api_call():
    names = {d.name for d in W6.DEFS}
    assert names and names <= T.TOOL_NAMES and names <= {t.name for t in offered_tools()} and names <= set(LT.BY_NAME)
    for d in W6.DEFS:
        args = {p.name: "x" for p in d.params if p.required}
        fn, payload = _args(T.script_for(d.name, args))
        assert fn == d.api and payload == args


def _schema(name):
    return next(t for t in T.TOOLS if t.name == name).parameters["properties"]


def test_modular_character_parts_are_objects_and_outfits_are_lists_of_part_ids():
    props = _schema("lampway_modular_character")
    assert props["parts"]["items"] == {"type": "object"}
    assert props["allowed_outfits"]["items"] == {"type": "array", "items": {"type": "string"}}
