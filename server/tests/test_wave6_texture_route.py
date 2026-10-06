"""texture_route_select (specs/wiki/texture_route_select.md): the one table that maps a need (restyle, keep the UV layout, a local defect, a shared material, a
shape fix) to the supported routes with each one's acceptance condition. Driver and tool flags are read from the live registries (studios/actions.py, the
agent's Lampway Defs), never written by hand; a shape fix never gets a texture route."""

import pytest

from lampway_server import texture_routes as TR
from lampway_server.studios import actions as A

TEXTURE_WORDS = ("texture", "retexture", "repair", "tile", "material", "paint", "projection")


def _texture_route(r):
    return any(w in str(r.get(k) or "").lower() for k in ("lampway_tool", "studio_action") for w in TEXTURE_WORDS)


def test_shape_fix_never_returns_a_texture_route():
    out = TR.select("shape_fix")
    assert out["routes"] and not any(_texture_route(r) for r in out["routes"])
    assert all("silhouette" in r["acceptance"].lower() for r in out["routes"])


def test_every_other_need_returns_texture_routes_with_their_acceptance():
    for need in ("restyle", "keep_uv", "local_defect", "shared_material"):
        out = TR.select(need)
        assert out["routes"] and all(r["acceptance"] for r in out["routes"]) and any(_texture_route(r) for r in out["routes"]), need


def test_keep_uv_marks_meshy_by_the_action_registry(monkeypatch):
    meshy = next(r for r in TR.select("keep_uv")["routes"] if r["studio"] == "meshy")
    assert meshy["studio_action"] == "meshy.retexture" and meshy["driver_exists"] is ("meshy.retexture" in A.ACTIONS)
    monkeypatch.delitem(A.ACTIONS, "meshy.retexture")
    assert next(r for r in TR.select("keep_uv")["routes"] if r["studio"] == "meshy")["driver_exists"] is False


def test_driver_and_tool_flags_match_the_registries():
    from lampway_server.agent import lampway_tools as LT
    for need in TR.NEEDS:
        for r in TR.select(need)["routes"]:
            if r["studio_action"]:
                assert r["driver_exists"] is (r["studio_action"] in A.ACTIONS), r
            if r["lampway_tool"]:
                assert r["tool_exists"] is (f"lampway_{r['lampway_tool']}" in LT.BY_NAME), r


def test_unknown_need_lists_the_five_and_engine_available_filters():
    with pytest.raises(TR.RouteError, match="restyle, keep_uv, local_defect, shared_material, shape_fix"):
        TR.select("retopo")
    only = TR.select("restyle", engine_available=["tripo"])
    assert {r["studio"] for r in only["routes"] if r["available"]} <= {"tripo", None}
    assert any(not r["available"] for r in only["routes"])


def test_the_agent_tool_answers_through_the_agent_loop(tmp_path, monkeypatch):
    import asyncio
    import json
    from lampway_server.agent.providers.base import ToolCall
    from lampway_server.agent.turns import AgentHub
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    out, err = asyncio.run(AgentHub.__new__(AgentHub)._run_tool(None, None, None, ToolCall("c", "lampway_texture_route_select", {"need": "shape_fix"})))
    assert not err and json.loads(out)["need"] == "shape_fix"
