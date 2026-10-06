"""studio_cross_pass (specs/generation/studio_cross_pass.md): one Studio's mesh uploaded into another Studio's mesh-taking action, priced and confirmed through
that Studio's own plan, and the result recorded in the ONE seed catalogue as a version with its parent; the lineage reads back as a chain."""

import asyncio
import json

import pytest

from lampway_server import crosspass as XP
from lampway_server.seeds import Catalog, SeedError


def _cat(tmp_path):
    cat = Catalog(tmp_path / "seeds" / "seeds.sqlite")
    return cat


def _seed(cat, tmp_path, name="a.glb", data=b"glTF-a"):
    f = tmp_path / name
    f.write_bytes(data)
    return cat.add_version(None, "Chest1", str(f), studio="tripo", action="tripo.mesh", root=True)


def test_inserting_a_child_without_a_parent_is_refused(tmp_path):
    cat = _cat(tmp_path)
    f = tmp_path / "b.glb"; f.write_bytes(b"x")
    with pytest.raises(SeedError, match="lineage requires parent_id: record the source version first"):
        cat.add_version(None, "Chest1", str(f), studio="hi3d", action="hi3d.split")
    with pytest.raises(SeedError, match="no seed"):
        cat.add_version("nope", "Chest1", str(f), studio="hi3d", action="hi3d.split")


def test_the_lineage_reads_back_a_to_b_to_a(tmp_path):
    cat = _cat(tmp_path)
    a = _seed(cat, tmp_path)
    fb = tmp_path / "b.glb"; fb.write_bytes(b"glTF-b")
    b = cat.add_version(a["id"], "Chest1", str(fb), studio="hi3d", action="hi3d.split")
    fc = tmp_path / "c.glb"; fc.write_bytes(b"glTF-c")
    c = cat.add_version(b["id"], "Chest1", str(fc), studio="tripo", action="tripo.rest.texture")
    chain = XP.lineage(cat, c["id"])
    assert [r["studio"] for r in chain] == ["tripo", "hi3d", "tripo"] and [r["action"] for r in chain][1] == "hi3d.split", chain
    assert chain[0]["parent_id"] is None and chain[2]["parent_id"] == b["id"]


def test_a_step_whose_result_is_its_input_is_flagged_a_no_op_pass(tmp_path):
    cat = _cat(tmp_path)
    a = _seed(cat, tmp_path)
    same = tmp_path / "same.glb"; same.write_bytes(b"glTF-a")
    row = cat.add_version(a["id"], "Chest1", str(same), studio="meshy", action="meshy.remesh")
    assert row["no_op_pass"] is True


def test_a_plan_goes_through_the_destination_studios_own_plan_with_the_mesh_and_refuses_unmapped_routes(tmp_path):
    cat = _cat(tmp_path)
    a = _seed(cat, tmp_path)
    seen = {}

    class FakeStudio:
        def jail(self, p):
            return str(tmp_path / p) if not p.startswith("/") else p

        async def plan(self, action, args, by):
            seen.update(action=action, args=args, by=by)
            return {"state": "needs_approval", "approval": {"price": 12}}

    xp = XP.CrossPass(cat, FakeStudio())
    out = asyncio.run(xp.plan("a.glb", "tripo", "hi3d", "hi3d.split", {}, a["id"], "agent"))
    assert out["plan"]["state"] == "needs_approval" and seen["action"] == "hi3d.split" and seen["args"]["model"].endswith("a.glb"), (out, seen)
    assert out["record_with"]["parent_id"] == a["id"]
    with pytest.raises(XP.CrossPassError, match="never assume a Tripo affordance"):
        asyncio.run(xp.plan("a.glb", "hi3d", "tripo", "tripo.uv.unwrap", {}, a["id"], "agent"))
    with pytest.raises(XP.CrossPassError, match="takes no uploaded mesh"):
        asyncio.run(xp.plan("a.glb", "tripo", "meshy", "meshy.text_to_3d", {}, a["id"], "agent"))
    with pytest.raises(XP.CrossPassError, match="lineage requires parent_id"):
        asyncio.run(xp.plan("a.glb", "tripo", "hi3d", "hi3d.split", {}, "", "agent"))


def test_the_agent_tool_records_and_reads_the_lineage(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    from lampway_server.agent import orphan_server_tools as OST
    cat = Catalog()
    a = _seed(cat, tmp_path)
    (tmp_path / "out.glb").write_bytes(b"glTF-out")
    text, err = asyncio.run(OST.call(None, "lampway_studio_cross_pass", {"verb": "record", "parent_id": a["id"], "file": "out.glb", "studio": "hi3d",
                                                                         "action": "hi3d.split", "piece": "Chest1"}))
    assert not err, text
    rid = json.loads(text)["row"]["id"]
    text, err = asyncio.run(OST.call(None, "lampway_studio_cross_pass", {"verb": "lineage", "id": rid}))
    assert not err and [r["studio"] for r in json.loads(text)["chain"]] == ["tripo", "hi3d"], text
