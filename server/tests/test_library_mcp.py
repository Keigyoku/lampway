"""The Asset Vault family wired into every caller (specs/asset_library/asset_mcp.md): the agent's tool list, swarm workers, the external MCP endpoint; the authority table per
origin (a worker never previews folders, nobody spends); the rate limit; the system prompt; a texture set read with its members. The tools' own behaviour is in
test_library_vault_tools.py; the app end to end in test_library_e2e.py."""
import asyncio
import json

import pytest
from PIL import Image

from lampway_server.agent import vault_tools as VT
from lampway_server.agent.tools import TOOLS
from lampway_server.library.vault import Vault

from .test_library_ingest import QUAD, glb_bytes


@pytest.fixture
def root(tmp_path, monkeypatch):
    r = tmp_path / "project"
    (r / "armour").mkdir(parents=True)
    (r / "armour" / "bronze_greaves.glb").write_bytes(glb_bytes(QUAD, [0, 1, 2, 0, 2, 3]))
    Image.new("RGB", (16, 12), (200, 100, 50)).save(r / "armour" / "greaves_front.png")
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(r))
    return r


@pytest.fixture
def vault(tmp_path):
    v = Vault.open(tmp_path / "state")
    yield v
    v.close()


def imported(vault, root):
    scan = vault.ingest.scan([str(root / "armour")])
    vault.ingest.import_(scan["scan_id"], by="captain")
    return {a["name"]: a["id"] for a in vault.query({"limit": 50})["items"]}


def call(vault, name, origin="agent", agent_id="main", limiter=None, **args):
    text, err = asyncio.run(VT.call(vault, name, args, {"origin": origin, "agent_id": agent_id}, limiter=limiter))
    return (json.loads(text) if not err else text), err


def test_the_agents_tool_list_carries_the_whole_family_and_the_blender_side_place():
    names = {t.name for t in TOOLS}
    family = VT.NAMES | {"lampway_vault_place", "lampway_vault_catalog_export"}
    assert family <= names, sorted(family - names)
    old = {"lampway_asset_search", "lampway_asset_get", "lampway_asset_similar", "lampway_asset_ingest", "lampway_asset_rate", "lampway_asset_place", "lampway_asset_library"}
    assert not (old & names), "the captain named the family lampway_vault_*"


def test_a_worker_cannot_preview_folders_and_the_rate_limit_holds_writes(vault, root):
    ids = imported(vault, root)
    out, err = call(vault, "lampway_vault_scan", origin="worker", agent_id="worker-1", paths=[str(root / "armour")])
    assert err and "not allowed" in out
    limiter = VT.Limiter(calls=120, writes=2)
    got = [call(vault, "lampway_vault_rate", origin="worker", agent_id="worker-1", limiter=limiter, id=ids["bronze_greaves"], stars=3) for _ in range(3)]
    assert [e for _, e in got] == [False, False, True] and "writes per minute" in got[2][0]


def test_nobody_spends_and_an_uploading_embedding_run_is_the_users_click(vault, root):
    assert all(VT.AUTHORITY[n] != "spend" for n in VT.NAMES)
    assert all("spend" not in g for g in VT.GRANTS.values())
    imported(vault, root)
    plan = {"plan_id": "plan-up", "space": "text_api:x", "base": "text_api", "model": "x", "targets": [], "planned": 0, "uploads": True, "content_class": "private",
            "estimate_usd": 0.0, "bytes_uploaded": 0}
    vault.embed.plans.mkdir(parents=True, exist_ok=True)
    (vault.embed.plans / "plan-up.json").write_text(json.dumps(plan))
    out, err = call(vault, "lampway_vault_embed", origin="mcp", agent_id="mcp", action="run", plan_id="plan-up")
    assert err and "ask the user to confirm in the Vault panel" in out


def test_swarm_workers_get_the_read_and_curation_tools_and_their_calls_run_on_the_server(vault, root):
    from types import SimpleNamespace

    from lampway_server.agent.providers.base import ToolCall
    from lampway_server.agent.swarm import SwarmManager, worker_tools
    ids = imported(vault, root)
    names = {t.name for t in worker_tools()}
    assert {"lampway_vault_search", "lampway_vault_rate", "lampway_vault_relate"} <= names and "lampway_vault_scan" not in names
    m = SwarmManager(lambda label: None, None)
    m.library = vault
    text, err = asyncio.run(m._worker_tool(None, SimpleNamespace(id="worker-2"), None, ToolCall(id="c1", name="lampway_vault_rate", arguments={"id": ids["bronze_greaves"], "stars": 2})))
    assert not err and json.loads(text)["rating"]["agents"] == [{"id": "worker-2", "stars": 2}]


def test_get_includes_the_members_of_a_set_through_part_of(vault, root):
    ids = imported(vault, root)
    s = vault.lib.put({"kind": "texture_set", "name": "Greaves Set", "source": {"key": "set:greaves"}})
    vault.lib.relate(ids["greaves_front"], "part_of", s["id"], by="rule")
    out, err = call(vault, "lampway_vault_get", id=s["id"], include=["members"])
    assert not err and [m["id"] for m in out["members"]] == [ids["greaves_front"]] and out["members"][0]["files"]["main"]["path"]


def test_the_agent_is_told_to_search_the_library_before_generating():
    from lampway_server.agent.prompt import SYSTEM_PROMPT
    assert "Search the library before generating: `lampway_vault_search`; `only_library` means never substitute a model-made asset" in SYSTEM_PROMPT
    assert "lampway_vault_place" in SYSTEM_PROMPT
