"""The Vault's agent / swarm / external-MCP tool family (asset_mcp.md section 10; the captain's answer, BUILD_ORDER.md Wave 5b item 3: the name is the Asset Vault, MCP tool
names are lampway_vault_*). Drafted by the integrator (scratch/test_library_vault_tools.draft.py), adopted by lane vault-ui with the changes its notes name."""
import json

import pytest
from PIL import Image

from lampway_server.agent import vault_tools as VT
from lampway_server.library.vault import Vault

pytestmark = pytest.mark.anyio


@pytest.fixture
def vault(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    return Vault.open(tmp_path / "state", project_root=proj)


def seed(vault, n=3):
    ids = []
    for i in range(n):
        ids.append(vault.lib.put({"kind": "mesh", "name": f"greave {i}", "description": "bronze", "source": {"kind": "t", "key": str(i)},
                                  "files": [{"role": "main", "bytes": f"g{i}".encode(), "storage": "cas"}], "stats": {"faces": 1000 * (i + 1)},
                                  "terms": [{"facet": "piece_type", "label": "greaves"}]})["id"])
    return ids


async def call(vault, name, args=None, origin="agent", agent_id="main"):
    text, is_error = await VT.call(vault, name, args or {}, {"origin": origin, "agent_id": agent_id})
    return json.loads(text) if not is_error else text, is_error


def schema_keys(o, acc=None):
    acc = set() if acc is None else acc
    if isinstance(o, dict):
        for k, v in o.items():
            acc.add(k)
            schema_keys(v, acc)
    elif isinstance(o, list):
        for v in o:
            schema_keys(v, acc)
    return acc


def test_the_family_is_named_vault_has_object_schemas_and_no_sql_and_no_import():
    names = {s.name for s in VT.specs()}
    assert names == VT.NAMES and all(n.startswith("lampway_vault") for n in names)
    assert {"lampway_vault", "lampway_vault_search", "lampway_vault_get", "lampway_vault_similar", "lampway_vault_scan", "lampway_vault_rate", "lampway_vault_relate",
            "lampway_vault_collect", "lampway_vault_provenance", "lampway_vault_embed"} <= names
    for s in VT.specs():
        assert s.parameters["type"] == "object" and s.parameters.get("additionalProperties") is False and s.description
        assert "sql" not in {k.lower() for k in schema_keys(s.parameters)}
    assert not [n for n in names if "import" in n or "watch" in n or "sql" in n]            # the user's click imports; no agent surface does


async def test_the_no_args_call_is_a_live_overview_with_next_steps(vault):
    out, err = await call(vault, "lampway_vault")
    assert not err and out["assets"]["total"] == 0 and any("scan" in h for h in out["help"])
    seed(vault)
    out, _ = await call(vault, "lampway_vault")
    assert out["assets"]["by_kind"] == {"mesh": 3} and any("lampway_vault_search" in h for h in out["help"])


async def test_search_is_compact_ranked_and_an_empty_library_says_so(vault):
    out, _ = await call(vault, "lampway_vault_search", {"text": "greave"})
    assert out["items"] == [] and "empty" in out["note"] and out["help"]
    seed(vault, 5)
    out, _ = await call(vault, "lampway_vault_search", {"text": "greave", "limit": 2})
    assert len(out["items"]) == 2 and out["total"] == 5 and out["next_cursor"]
    assert set(out["items"][0]) <= {"id", "kind", "subtype", "name", "version", "score", "rating", "thumb", "why", "tags"} and "stats" not in out["items"][0]
    nxt, _ = await call(vault, "lampway_vault_search", {"text": "greave", "limit": 2, "cursor": out["next_cursor"]})
    assert len(nxt["items"]) == 2


async def test_default_page_is_twenty_and_the_cap_is_two_hundred(vault):
    seed(vault, 25)
    out, _ = await call(vault, "lampway_vault_search", {"kinds": ["mesh"]})
    assert len(out["items"]) == 20
    text, err = await call(vault, "lampway_vault_search", {"limit": 201})
    assert err and "limit max 200" in text


async def test_an_injected_field_is_refused_with_the_nearest_names_not_executed(vault):
    seed(vault)
    text, err = await call(vault, "lampway_vault_search", {"where": {"all": [{"field": "name; DROP TABLE asset", "op": "=", "value": 1}]}})
    assert err and "unknown field" in text and vault.lib.status()["assets"]["total"] == 3


async def test_get_returns_files_as_role_to_path_bytes_sha(vault):
    a = seed(vault)[0]
    out, _ = await call(vault, "lampway_vault_get", {"id": a})
    f = out["files"]["main"]
    assert set(f) >= {"path", "bytes", "sha256"} and out["stats"]["faces"] == 1000 and out["name"] == "greave 0"
    text, err = await call(vault, "lampway_vault_get", {"id": "nope"})
    assert err and "no asset nope" in text


async def test_a_rating_is_attributed_to_the_agent_and_never_moves_the_users(vault):
    a = seed(vault)[0]
    out, _ = await call(vault, "lampway_vault_rate", {"id": a, "stars": 5, "flag": "pick", "note": "passed my gate"}, agent_id="worker-3")
    assert out["rating"]["agents"] == [{"id": "worker-3", "stars": 5}] and out["rating"]["captain"] is None
    from lampway_server.library import curate as C
    C.rate(vault.lib, a, rater="captain", stars=1)
    out, _ = await call(vault, "lampway_vault_rate", {"id": a, "stars": 5}, agent_id="worker-3")
    assert vault.lib.get(a)["rating"] == 1 and out["rating"]["captain"] == 1
    assert "agent:worker-3" in {row[0] for row in vault.lib._db.execute("select actor from event where asset_id=?", (a,))}


async def test_the_rater_cannot_be_chosen_by_the_agent(vault):
    a = seed(vault)[0]
    text, err = await call(vault, "lampway_vault_rate", {"id": a, "stars": 5, "rater": "captain"})
    assert err and "rater" in text.lower()


async def test_scan_previews_inside_the_project_root_and_refuses_outside(vault, tmp_path):
    Image.new("RGB", (8, 8), (1, 2, 3)).save(vault.project_root / "a.png")
    out, err = await call(vault, "lampway_vault_scan", {"paths": [str(vault.project_root)]})
    assert not err and out["report"]["by_kind"] == {"image": 1} and out["scan_id"] and "import" in out["note"] and "click" in out["note"]
    assert vault.lib.status()["assets"]["total"] == 0 and vault.lib.sources() == []                  # a preview enrols and imports nothing
    other = tmp_path / "elsewhere"
    other.mkdir()
    text, err = await call(vault, "lampway_vault_scan", {"paths": [str(other)]})
    assert err and "outside the project root" in text and "Vault panel" in text


async def test_a_registered_source_may_be_scanned_by_an_agent(vault, tmp_path):
    other = tmp_path / "mine"
    other.mkdir()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(other / "b.png")
    vault.ingest.watch_add(other, by="captain")                                                       # the user registered it
    out, err = await call(vault, "lampway_vault_scan", {"paths": [str(other)]})
    assert not err and out["report"]["by_kind"] == {"image": 1}


async def test_relate_collect_and_provenance_are_agent_usable(vault):
    a, b, c = seed(vault)
    out, _ = await call(vault, "lampway_vault_relate", {"src": a, "dst": b, "type": "derived_from"}, agent_id="worker-3")
    assert out["created"] is True
    text, err = await call(vault, "lampway_vault_relate", {"src": b, "dst": a, "type": "derived_from"})
    assert err and "derived_from cycle" in text
    col, _ = await call(vault, "lampway_vault_collect", {"action": "create", "name": "picks", "kind": "board"})
    got, _ = await call(vault, "lampway_vault_collect", {"action": "add", "collection": col["collection"]["id"], "asset_ids": [a, b]})
    assert got["collection"]["items"] == 2
    prov, _ = await call(vault, "lampway_vault_provenance", {"action": "audit"})
    assert "generated_assets" in prov and c


async def test_embed_plan_is_free_for_an_agent_and_an_uploading_run_names_the_plan(vault):
    import io
    seed(vault)                                            # meshes whose bytes are not a GLB: no shape space understands them
    for i, rgb in enumerate(((200, 10, 10), (10, 200, 10))):
        b = io.BytesIO()
        Image.new("RGB", (8, 8), rgb).save(b, "PNG")
        vault.lib.put({"kind": "image", "name": f"plate {i}", "source": {"kind": "t", "key": f"img{i}"}, "files": [{"role": "main", "bytes": b.getvalue(), "storage": "cas"}]})
    plan, err = await call(vault, "lampway_vault_embed", {"action": "plan", "space": "image_hist"})
    assert not err and plan["uploads"] is False and plan["planned"] == 2
    run, err = await call(vault, "lampway_vault_embed", {"action": "run", "plan_id": plan["plan_id"]})
    assert not err and run["done"] == 2 and run["bytes_uploaded"] == 0 and run["failed"] == []
    text, err = await call(vault, "lampway_vault_embed", {"action": "plan", "space": "text_api", "model": "baai/bge-m3"})
    assert err and "OpenRouter key" in text


async def test_a_swarm_worker_flow_search_get_relate_rate_is_attributed_to_it(vault):
    a, b, c = seed(vault)
    s, _ = await call(vault, "lampway_vault_search", {"text": "greave 1"}, agent_id="worker-7")
    top = s["items"][0]["id"]
    g, _ = await call(vault, "lampway_vault_get", {"id": top}, agent_id="worker-7")
    await call(vault, "lampway_vault_relate", {"src": c, "dst": top, "type": "variant_of"}, agent_id="worker-7")
    r, _ = await call(vault, "lampway_vault_rate", {"id": top, "stars": 4}, agent_id="worker-7")
    assert g["id"] == top and r["rating"]["agents"] == [{"id": "worker-7", "stars": 4}]
    actors = {row[0] for row in vault.lib._db.execute("select actor from event where verb in ('relate','rate')")}
    assert actors == {"agent:worker-7"}


async def test_one_bare_condition_goes_through_the_field_registry_too(vault):
    seed(vault)
    text, err = await call(vault, "lampway_vault_search", {"where": {"field": "1=1) OR (1", "op": "=", "value": 1}})
    assert err and "unknown field" in text
    out, err = await call(vault, "lampway_vault_search", {"where": {"field": "mesh_stats.faces", "op": ">", "value": 1500}})
    assert not err and sorted(i["name"] for i in out["items"]) == ["greave 1", "greave 2"]
