"""/app/workbench: the cockpit over the Lampway server (specs/mrmak/01): bearer-guarded routes, the local-CLI switch for real agent CLIs, server start/stop as explicit user actions, and the agent tool."""
import json
import time

import pytest
from starlette.testclient import TestClient

from lampway_server.app import create_app
from lampway_server.herdr.host import Cockpit

from .herdr_support import fake_cli, lroot, needs_herdr, wait_for  # noqa: F401


@pytest.fixture
def stack(settings, provider, lroot, tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    app = create_app(settings, provider=provider, cockpit=Cockpit(lroot, project_root=str(tmp_path)))
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        from .fake_client import FakeMixarClient
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        yield http, fake, app, tmp_path


def authed(fake):
    return fake.rest_headers()


def test_the_routes_need_the_bearer(stack):
    http, fake, app, _ = stack
    assert http.get("/app/workbench").status_code == 401 and http.post("/app/workbench/server/start").status_code == 401


@needs_herdr
def test_start_create_read_input_close_and_reconcile_through_the_routes(stack, fake_cli):
    http, fake, app, tmp = stack
    h = authed(fake)
    home = http.get("/app/workbench", headers=h).json()
    assert home["server"]["running"] is False and home["sessions"] == [] and set(home["offered"]) == {"start", "resume"}
    r = http.post("/app/workbench/sessions", headers=h, json={"agent": "command", "name": "Route session", "cwd": str(tmp), "command": fake_cli})
    assert r.status_code == 409 and "start it from the cockpit" in r.json()["detail"]                 # nothing launches automatically
    assert http.post("/app/workbench/server/start", headers=h).json()["method"] in ("systemd", "setsid")
    made = http.post("/app/workbench/sessions", headers=h, json={"agent": "command", "name": "Route session", "cwd": str(tmp), "command": fake_cli})
    assert made.status_code == 200
    sid = made.json()["id"]
    assert wait_for(lambda: "fake agent ready" in http.get(f"/app/workbench/sessions/{sid}/screen", headers=h).json()["screen"])
    assert http.post(f"/app/workbench/sessions/{sid}/input", headers={**h, "X-Lampway-Origin": "agent"}, json={"text": "hi", "by": "user"}).status_code == 409   # agent sends off by default; the caller, not body.by, is the agent (spec B6)
    assert http.post(f"/app/workbench/sessions/{sid}/input", headers=h, json={"text": "hi from user", "by": "user"}).status_code == 200
    assert wait_for(lambda: "echo: hi from user" in http.get(f"/app/workbench/sessions/{sid}/screen", headers=h).json()["screen"])
    rec = http.post("/app/workbench/reconcile", headers=h).json()
    assert rec["adopted"] == [sid] and rec["new_panes"] == 0
    assert http.post(f"/app/workbench/sessions/{sid}/close", headers=h, json={}).status_code == 409           # no confirm
    assert http.post(f"/app/workbench/sessions/{sid}/close", headers=h, json={"confirm": True}).status_code == 200
    assert http.post("/app/workbench/server/stop", headers=h, json={}).status_code == 409
    assert http.post("/app/workbench/server/stop", headers=h, json={"confirm": True}).status_code == 200


def test_real_agent_clis_are_refused_unless_the_local_cli_switch_is_on(stack, monkeypatch):
    http, fake, app, tmp = stack
    h = authed(fake)
    monkeypatch.delenv("LAMPWAY_LOCAL_CLI", raising=False)
    r = http.post("/app/workbench/sessions", headers=h, json={"agent": "claude", "name": "Chest audit", "cwd": str(tmp)})
    assert r.status_code == 403 and "local CLI" in r.json()["detail"]


def test_bypass_from_a_request_is_refused_the_users_click_in_the_cockpit_is_the_only_door(stack, monkeypatch):
    http, fake, app, tmp = stack
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    r = http.post("/app/workbench/sessions", headers=authed(fake), json={"agent": "claude", "name": "Chest audit", "cwd": str(tmp), "bypass": True})
    assert r.status_code == 403 and "bypass" in r.json()["detail"]


@pytest.mark.anyio
async def test_the_agent_tool_lists_and_reads_and_never_creates_or_closes(tmp_path, lroot):
    from lampway_server.agent import workbench_tools as WT
    from lampway_server.agent import tools as T
    assert "lampway_workbench" in {t.name for t in T.TOOLS}
    out, err = await WT.call(Cockpit(lroot), "lampway_workbench", {"action": "list"})
    assert not err and json.loads(out)["server"]["running"] is False
    bad, err = await WT.call(Cockpit(lroot), "lampway_workbench", {"action": "close", "id": "x"})
    assert err and "action is list | read | send" in bad
    sent, err = await WT.call(Cockpit(lroot), "lampway_workbench", {"action": "send", "id": "nope", "text": "x"})
    assert err and "not a Lampway session" in sent
