"""The rig tools (specs/canon/rig_tools; STATUS O36) in the agent's registry: each a Def the model can call and the MCP endpoint offers, naming a client
function in rig_api.py that takes every parameter the Def declares; a WIP tool says so in its Def (wip) and its description."""

import ast
from pathlib import Path

from lampway_server.agent import lampway_tools as LT
from lampway_server.agent import rig_defs as RD
from lampway_server.agent import tools as T
from lampway_server.mcp import offered_tools

API = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/rig_api.py"
EXPECTED = ("lampway_rig_inspect", "lampway_rig_map", "lampway_rig_normalize", "lampway_rig_readback", "lampway_rig_convert", "lampway_rig_skin",
            "lampway_rig_conform", "lampway_rig_export_ue")


def _client_functions() -> dict:
    out = {}
    for n in ast.parse(API.read_text()).body:
        if isinstance(n, ast.FunctionDef) and any(getattr(d.func if isinstance(d, ast.Call) else d, "id", "") == "tool" for d in n.decorator_list):
            out[n.name] = {x.arg for x in n.args.args + n.args.kwonlyargs}
    return out


def test_every_rig_tool_is_registered_offered_and_names_its_client_function():
    names, offered, fns = {t.name for t in T.TOOLS}, {t.name for t in offered_tools()}, _client_functions()
    for name in EXPECTED:
        assert name in names and name in LT.BY_NAME and name in offered, name
    for d in RD.RIG_DEFS:
        assert d.api in fns, d.name
        assert {p.name for p in d.params} <= fns[d.api], (d.name, {p.name for p in d.params} - fns[d.api])
        if d.wip:
            assert "WIP" in d.description, d.name
    assert LT.BY_NAME["lampway_rig_skin"].wip is True and LT.BY_NAME["lampway_rig_convert"].wip is False
