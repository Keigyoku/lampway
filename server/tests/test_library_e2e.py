"""The Asset Vault wired end to end in the real app (create_app + TestClient, lifespan included): the user previews and imports a folder over REST, then the agent's
``lampway_vault_search`` finds what was imported, an external MCP client finds it with no desktop instance connected, and the Blender-side place tool reads the record
over ``GET /api/v1/library/assets/{id}``."""
import json
import uuid

import pytest

from lampway_server.agent.providers.base import Text, ToolCall

from .test_library_ingest import QUAD, glb_bytes


@pytest.fixture
def folder(tmp_path, monkeypatch):
    root = tmp_path / "project"
    (root / "armour").mkdir(parents=True)
    (root / "armour" / "bronze_greaves.glb").write_bytes(glb_bytes(QUAD, [0, 1, 2, 0, 2, 3]))
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(root))
    return root / "armour"


def _import(fake, folder):
    scan = fake.post("/api/v1/library/ingest/scan", json={"paths": [str(folder)]})
    assert scan.status_code == 200, scan.text
    imp = fake.post("/api/v1/library/ingest/import", json={"scan_id": scan.json()["data"]["scan_id"]})
    assert imp.status_code == 200 and imp.json()["data"]["report"]["new_assets"] == 1, imp.text


def test_the_routes_need_the_bearer(http):
    assert http.get("/api/v1/library/status").status_code == 401
    assert http.post("/api/v1/library/query", json={}).status_code == 401


def test_an_imported_asset_is_found_by_the_agent_tool(fake, provider, folder):
    fake.login()
    _import(fake, folder)
    provider.script.append([ToolCall(id="call_1", name="lampway_vault_search", arguments={"text": "greaves"})])
    provider.script.append([Text("Found it.")])
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        command_id = fake.command(ws, "chat", fake.chat_payload("find the greaves in my library", str(uuid.uuid4())))
        fake.run_turn(ws, command_id, on_script=lambda p: fake.execute_script_result(p["script"]))
    results = [p for p in provider.requests[-1].messages[-1].content if p.get("type") == "tool_result"]
    assert results and not results[0].get("is_error"), results
    found = json.loads(results[0]["content"])
    assert [i["name"] for i in found["items"]] == ["bronze_greaves"] and found["items"][0]["kind"] == "mesh"


def test_the_record_route_and_the_mcp_family_answer_with_no_desktop_connected(fake, app, folder):
    fake.login()
    _import(fake, folder)
    page = fake.post("/api/v1/library/query", json={"text": "greaves"}).json()["data"]
    aid = page["items"][0]["id"]
    rec = fake.get(f"/api/v1/library/assets/{aid}?include=members").json()["data"]
    assert rec["files"][0]["locations"][0]["path"] == str(folder / "bronze_greaves.glb")
    assert fake.get("/api/v1/library/assets/nope").status_code == 404
    blob = fake.get(f"/api/v1/library/files/{rec['files'][0]['sha256']}")
    assert blob.status_code == 200 and blob.content[:4] == b"glTF"
    placed = fake.post("/api/v1/library/events", json={"verb": "placed", "asset_id": aid, "version": 1, "mode": "import", "project": "scene.blend"})
    assert placed.status_code == 200 and placed.json()["data"] == {"recorded": True}
    rows = app.state.vault.lib._reader().execute("SELECT actor, detail_json FROM event WHERE verb='placed' AND asset_id=?", (aid,)).fetchall()
    assert [(r[0], json.loads(r[1])["project"]) for r in rows] == [("user", "scene.blend")]
    rpc = fake.post("/api/v1/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "lampway_vault_search", "arguments": {"text": "greaves"}}},
                    headers={"X-Mixar-Instance-Id": "nobody", "X-Mixar-Session-Id": "s"}).json()
    assert rpc["result"]["isError"] is False and json.loads(rpc["result"]["content"][0]["text"])["items"][0]["id"] == aid
    names = {t["name"] for t in fake.post("/api/v1/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers={"X-Mixar-Instance-Id": "x"}).json()["result"]["tools"]}
    assert {"lampway_vault_search", "lampway_vault_get", "lampway_vault_rate", "lampway_vault_place"} <= names
