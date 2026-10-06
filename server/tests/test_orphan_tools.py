"""The orphan tools (STATUS.md ORPHANS) in the agent's registry: each is a Def the model can call and the MCP endpoint offers, and each Def names an api
function that exists in the client's orphans_api.py with every parameter the Def declares (a Def the client cannot run is the defect Waves 2-4 shipped)."""

import ast
from pathlib import Path

from lampway_server.agent import lampway_tools as LT
from lampway_server.agent import orphan_tools as OT
from lampway_server.agent import tools as T
from lampway_server.mcp import offered_tools

API = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/orphans_api.py"
EXPECTED = ("lampway_side_label_check", "lampway_mirror_pair", "lampway_scale_to_measure", "lampway_uv_check")


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
