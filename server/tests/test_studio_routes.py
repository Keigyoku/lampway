"""The Studio service through the Client's REST routes and the agent's tools. The Client (the user) can plan, confirm and reject;
the agent can only plan and read - there is no tool, and no route an agent has a token for, that confirms a spend."""


import pytest
from starlette.testclient import TestClient

from lampway_server.app import create_app
from lampway_server.studios.service import StudioService

from .fake_client import FakeMixarClient
from .test_studio_service import Exec, MESH_PLAN, STATE_FRESH, make_shelf


@pytest.fixture
def studio(tmp_path):
    root = tmp_path / "root"
    (root / "plates").mkdir(parents=True)
    for v in ("front", "left", "right", "back"):
        (root / "plates" / f"{v}.png").write_bytes(b"png")
    ex = Exec({"tripo_mesh": MESH_PLAN, "tripo_uv": STATE_FRESH})
    return StudioService(root, ex, shelf=make_shelf(tmp_path / "shelf")), ex


ARGS = {k: f"plates/{k}.png" for k in ("front", "left", "right", "back")}


def test_every_studio_route_needs_a_token(settings, studio):
    svc, _ = studio
    with TestClient(create_app(settings, studio_service=svc), base_url="http://127.0.0.1:8787") as http:
        for method, path in (("get", "/app/studio"), ("post", "/app/studio/plan"), ("post", "/app/studio/approvals/x/confirm"),
                             ("post", "/app/studio/approvals/x/reject"), ("get", "/app/studio/jobs/x"), ("get", "/app/studio/jobs/x/files/a.fbx"),
                             ("post", "/app/studio/jobs/x/acknowledge-hung")):
            assert getattr(http, method)(path).status_code == 401, path


def test_the_client_plans_then_the_captain_confirms_and_the_job_serves_its_files(settings, studio):
    svc, ex = studio
    with TestClient(create_app(settings, studio_service=svc), base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        home = fake.get("/app/studio").json()
        assert {a["id"] for a in home["actions"]} >= {"tripo.mesh", "tripo.uv.unwrap"} and home["engine"] == {"shelf": True}
        plan = fake.post("/app/studio/plan", json={"action": "tripo.mesh", "args": ARGS})
        assert plan.status_code == 200 and plan.json()["state"] == "needs_approval"
        approval = plan.json()["approval"]
        wrong = fake.post(f"/app/studio/approvals/{approval['id']}/confirm", json={"price": 99})
        assert wrong.status_code == 409 and "price" in wrong.json()["detail"]
        ok = fake.post(f"/app/studio/approvals/{approval['id']}/confirm", json={"price": 100})
        assert ok.status_code == 200 and ok.json()["action"] == "tripo.mesh"
        import time
        for _ in range(100):
            job = fake.get(f"/app/studio/jobs/{ok.json()['id']}").json()
            if job["state"] != "running":
                break
            time.sleep(0.02)
        assert job["state"] == "done" and [c["armed"] for c in ex.calls] == [False, True]
        assert fake.get("/app/studio/jobs/nope").status_code == 404
        assert fake.post("/app/studio/plan", json={"action": "tripo.nope", "args": {}}).status_code == 400
        assert fake.post("/app/studio/plan", json={"action": "tripo.mesh", "args": {**ARGS, "front": "/etc/passwd"}}).status_code == 400


def test_a_job_file_is_served_by_name_only(settings, studio):
    svc, ex = studio
    ex.outputs["tripo_uv"] = lambda argv: STATE_FRESH if argv[-1] == "state" else "row: 1\n"
    with TestClient(create_app(settings, studio_service=svc), base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        plan = fake.post("/app/studio/plan", json={"action": "tripo.uv.unwrap", "args": {}}).json()
        job = fake.post(f"/app/studio/approvals/{plan['approval']['id']}/confirm", json={"price": 20}).json()
        import time
        for _ in range(100):
            j = fake.get(f"/app/studio/jobs/{job['id']}").json()
            if j["state"] != "running":
                break
            time.sleep(0.02)
        assert [f["name"] for f in j["files"]] == ["attempt_1.fbx"]
        got = fake.get(f"/app/studio/jobs/{job['id']}/files/attempt_1.fbx")
        assert got.status_code == 200 and got.content == b"fbx"
        assert fake.get(f"/app/studio/jobs/{job['id']}/files/..%2Fsecret").status_code == 404


def test_the_agent_can_plan_and_read_but_has_no_way_to_confirm(settings, studio, monkeypatch):
    from .serve_support import mode1_turn
    from lampway_server.agent.tools import TOOLS
    names = {t.name for t in TOOLS}
    assert {"studio_plan", "studio_job", "studio_actions"} <= names
    assert not [n for n in names if "confirm" in n or "approve" in n], "no agent tool confirms a spend"
    svc, ex = studio
    app = create_app(settings, studio_service=svc)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        frames, serve = mode1_turn(monkeypatch, http, fake, [            # Mode 1's Hermes plans through its MCP endpoint (spec A3, A5)
            ("mcp", "studio_plan", {"action": "tripo.mesh", "args": ARGS}),
            ("mcp", "studio_plan", {"action": "tripo.mesh", "args": {**ARGS, "polycount": "9000"}}),
            ("say", "The mesh is waiting for the user.")], "make the helmet mesh", on_script=lambda p: {"success": True})
        approvals = svc.approvals()
    assert len(approvals) == 1 and approvals[0]["state"] == "pending" and approvals[0]["price"] == 100 and approvals[0]["requested_by"] == "agent"
    assert [c["armed"] for c in ex.calls] == [False], "the agent's plan clicked nothing and spent nothing"
    final = []
    for f in frames:
        rows = ((f.get("params") or {}).get("event", {}).get("steps") or {}).get("items", []) if f.get("method") == "agent.turn.event" else []
        final = rows or final
    assert [(r["label"], r["status"]) for r in final] == [("studio_plan", "done"), ("studio_plan", "failed")], \
        "a refused plan (a lower polycount) is a failed step"
    assert [r["isError"] for r in serve.mcp_results] == [False, True]
