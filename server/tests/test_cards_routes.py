"""Cards wired into the app and the agent (specs/mrmak/09-report-cards.md section 4): the /app/cards routes behind the bearer, a build from the real ledger file, the
open URL on the content server's own origin, and the lampway_cards agent tool with the same actions."""
import asyncio
import json

from lampway_server.agent import cards_tools as CT
from lampway_server.agent.tools import TOOLS
from lampway_server.ledger import Ledger


def seed(project):
    led = Ledger(project / "ledger" / "runs.jsonl")
    for letter in "AB":
        led.record({"piece": "Boots1", "stage": "image", "studio": "openrouter", "id": f"r1-{letter}", "settings": {"round": "1", "variant": letter},
                    "cost": {"developer_api_usd": 0.07}})
    return led


def test_the_routes_need_the_bearer(http):
    assert http.get("/app/cards").status_code == 401
    assert http.post("/app/cards/build", json={"card": "boots1", "kind": "receipt", "piece": "Boots1"}).status_code == 401


def test_build_list_read_update_open_and_activity_over_rest(fake, tmp_path):
    project = tmp_path / "project"
    seed(project)
    fake.login()
    built = fake.post("/app/cards/build", json={"card": "Boots1", "kind": "design_versions", "piece": "Boots1", "round": "auto"})
    assert built.status_code == 200, built.text
    cid = built.json()["data"]["card"]["id"]
    assert built.json()["data"]["card"]["steps"] == ["Round 1"]
    listed = fake.get("/app/cards").json()["data"]
    assert [c["id"] for c in listed["cards"]] == [cid]
    read = fake.get(f"/app/cards/{cid}?step=0").json()["data"]
    assert "Round 1: the variants" in read["text"] and "<" not in read["text"]
    upd = fake.post(f"/app/cards/{cid}", json={"status": "done", "pinned": True}).json()["data"]
    assert upd["status"] == "done" and upd["pinned"] is True
    bad = fake.post(f"/app/cards/{cid}", json={"status": "finished"})
    assert bad.status_code == 422 and "status is active, done or archived" in bad.json()["detail"]
    opened = fake.get(f"/app/cards/{cid}/open?step=0").json()["data"]
    assert opened["url"].startswith("http://127.0.0.1:") and ":8787/" not in opened["url"] and opened["url"].endswith("/round-1.html")
    day = fake.get(f"/app/cards/activity?date={upd['updated']}").json()["data"]
    assert [c["id"] for c in day["cards"]] == [cid] and day["basis"]
    nothing = fake.post("/app/cards/build", json={"card": "Ghost", "kind": "receipt", "piece": "Ghost"})
    assert nothing.status_code == 422 and "no runs recorded for Ghost" in nothing.json()["detail"]


def test_the_agent_tool_has_the_same_actions(tmp_path, monkeypatch):
    project = tmp_path / "project"
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(project))
    seed(project)
    assert "lampway_cards" in {t.name for t in TOOLS}
    def call(**a):
        text, err = asyncio.run(CT.call(None, "lampway_cards", a))
        return (json.loads(text) if not err else text), err
    built, err = call(action="build", card="Boots1", kind="receipt", piece="Boots1")
    assert not err and built["card"]["steps"] == ["Receipt"]
    listed, _ = call(action="list")
    assert [c["title"] for c in listed["cards"]] == ["Boots1"]
    out, err = call(action="update", id=listed["cards"][0]["id"], status="nope")
    assert err and "status is active, done or archived" in out
    out, err = call(action="explode")
    assert err and "action is one of" in out
