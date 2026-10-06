"""mcp_inventory (specs/mrmak/03): which MCP servers do the user's agent apps actually have, where from, which source is effective, what readiness, and an on-demand live check that opens its own short connection.
Fixtures are temp homes and projects in each app's format; the probe talks to a fake HTTP MCP server and a fake stdio one. No secret value, URL path or argument may leave in any result."""
import http.server
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from lampway_server.mcp_inventory import api as INV
from lampway_server.mcp_inventory import probe as PR

SECRETS = ("SECRETENV1", "SECRETPW", "SECRETQ", "SECRETHDR", "SECRETCODEXHDR", "SECRETOTHERPROJECT")


@pytest.fixture
def world(tmp_path, monkeypatch):
    home, proj, other = tmp_path / "home", tmp_path / "proj", tmp_path / "other-proj"
    for d in (home, proj, other, home / ".codex", proj / ".codex", home / ".config" / "opencode", home / ".cursor", home / ".kimi"):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    (home / ".claude.json").write_text(json.dumps({
        "mcpServers": {"globalsrv": {"command": "python3", "args": ["g.py"], "env": {"TOKEN_X": "SECRETENV1"}}, "shared": {"command": "python3", "args": ["global.py"]}},
        "projects": {str(proj): {"mcpServers": {"shared": {"command": "python3", "args": ["local.py"]}}}, str(other): {"mcpServers": {"leak": {"command": "python3", "args": ["SECRETOTHERPROJECT"]}}}}}))
    (proj / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "shared": {"command": "python3", "args": ["project.py"]},
        "projhttp": {"type": "http", "url": "https://user:SECRETPW" "@api.example.test/deep/path?token=SECRETQ", "headers": {"Authorization": "Bearer SECRETHDR"}},
        "unapproved": {"command": "python3", "args": ["u.py"]}, "needsenv": {"command": "python3", "args": ["${LAMPWAY_MCP_X:-}"]}, "nocmd": {"command": "definitely-not-a-command-xyz"}}}))
    (proj / ".claude").mkdir()
    (proj / ".claude" / "settings.json").write_text(json.dumps({"enabledMcpjsonServers": ["shared", "projhttp", "needsenv", "nocmd"]}))
    (home / ".codex" / "config.toml").write_text('[mcp_servers.alpha]\ncommand = "python3"\nargs = ["--x"]\n\n[mcp_servers.shared]\nurl = "https://global.example.test/mcp"\n[mcp_servers.shared.http_headers]\nX-Api = "SECRETCODEXHDR"\n')
    (proj / ".codex" / "config.toml").write_text('[mcp_servers.shared]\nurl = "https://project.example.test/mcp"\n\n[mcp_servers.alpha]\nenabled = false\n')
    (home / ".config" / "opencode" / "opencode.json").write_text(json.dumps({"mcp": {"ocl": {"type": "local", "command": ["python3", "o.py"], "enabled": True}, "ocr": {"type": "remote", "url": "https://oc.example.test/mcp"}}}))
    (home / ".cursor" / "mcp.json").write_text(json.dumps({"mcpServers": {"cur": {"command": "python3"}}}))
    (home / ".kimi" / "mcp.json").write_text(json.dumps({"mcpServers": {"kim": {"url": "https://kimi.example.test/mcp"}}}))
    return type("W", (), {"home": home, "proj": proj, "tmp": tmp_path})


def scan(w, **kw):
    return INV.inventory(w.proj, w.home, env={"PATH": os.environ["PATH"]}, **kw)


def by_id(res):
    return {s["id"]: s for s in res["servers"]}


def test_precedence_and_the_source_list_with_exactly_one_effective_source(world):
    res = scan(world)
    s = by_id(res)
    claude = s["claude:shared"]
    assert [x["scope"] for x in claude["sources"]] == ["local", "project", "global"] and [x["effective"] for x in claude["sources"]] == [True, False, False]
    assert claude["executable"] == "python3" and claude["scope"] == "local"
    codex = s["codex:shared"]
    assert codex["scope"] == "project" and codex["endpoint"] == "https://project.example.test" and codex["credential_names"] == ["X-Api"]          # the project layer wins, the user's header NAME is merged in
    assert s["codex:alpha"]["enabled"] is False and s["codex:alpha"]["readiness"] == "disabled"
    assert {"opencode:ocl", "opencode:ocr", "cursor:cur", "kimi:kim", "claude:globalsrv"} <= set(s)


def test_no_secret_user_info_path_query_header_value_or_other_projects_servers_in_the_whole_json(world):
    blob = json.dumps(scan(world))
    for secret in SECRETS:
        assert secret not in blob, secret
    assert "/deep/path" not in blob and "token=" not in blob and "leak" not in blob and "global.py" not in blob
    ph = by_id(scan(world))["claude:projhttp"]
    assert ph["endpoint"] == "https://api.example.test" and ph["transport"] == "http" and ph["credential_names"] == ["Authorization"] and ph["executable"] is None


def test_readiness_words(world):
    s = by_id(scan(world))
    assert s["claude:needsenv"]["readiness"] == "missing-env" and s["claude:needsenv"]["missing_env"] == ["LAMPWAY_MCP_X"] and s["claude:needsenv"]["can_check"] is False
    assert s["claude:nocmd"]["readiness"] == "missing-command" and s["claude:nocmd"]["can_check"] is False
    assert s["claude:unapproved"]["readiness"] == "approval" and s["claude:unapproved"]["can_check"] is False
    assert s["claude:shared"]["readiness"] == "configured" and s["claude:shared"]["can_check"] is True
    (world.proj / ".claude" / "settings.json").write_text(json.dumps({"enableAllProjectMcpServers": True}))
    assert by_id(scan(world))["claude:unapproved"]["readiness"] == "configured"
    (world.proj / ".claude" / "settings.json").write_text(json.dumps({"enableAllProjectMcpServers": True, "disabledMcpjsonServers": ["unapproved"]}))
    assert by_id(scan(world))["claude:unapproved"]["readiness"] == "disabled"


def test_a_broken_config_is_reported_without_quoting_it(world):
    (world.proj / ".mcp.json").write_text('{"mcpServers": {"x": {"command": "sk-notarealkeyatall' + "A" * 20 + '"}')           # truncated JSON with a key-looking string
    res = scan(world)
    assert res["problems"] and all("sk-" not in json.dumps(p) and "notarealkey" not in json.dumps(p) for p in res["problems"])
    assert any(p["message"] for p in res["problems"]) and "claude:shared" in by_id(res)                                              # the other layers still answer


def test_the_scope_filter_and_client_filter(world):
    only = scan(world, client="codex")
    assert {s["client"] for s in only["servers"]} == {"codex"}
    proj = scan(world, scope="project")
    assert proj["servers"] and all(s["scope"] == "project" for s in proj["servers"])


def test_a_legacy_mixar_entry_is_flagged_and_the_lampway_row_reports_the_launcher(world):
    (world.home / ".claude.json").write_text(json.dumps({"mcpServers": {"mixar": {"command": "python3"}, "lampway": {"command": "python3"}}}))
    res = scan(world, eligibility=lambda: (False, "desktop not connected"), tools_offered=lambda: 123)
    row = res["lampway"]
    assert row["launcher"] == "python3" and row["launcher_ok"] is True and row["eligible"] is False and row["eligibility_detail"] == "desktop not connected" and row["tools_offered"] == 123
    assert any("replace with lampway" in n for n in row["notes"])


# ------------------------------------------------------------------------------------------------ probe
class FakeMcp(http.server.BaseHTTPRequestHandler):
    log = []
    mode = "ok"

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        FakeMcp.log.append((body.get("method"), self.headers.get("authorization")))
        if self.path == "/elsewhere":
            FakeMcp.mode_local = "ok"
        if FakeMcp.mode == "auth":
            self.send_response(401); self.send_header("www-authenticate", "Bearer realm=ECHO-SECRETHDR"); self.end_headers(); self.wfile.write(b"bad token SECRETHDR"); return
        if FakeMcp.mode == "redirect" and self.path != "/elsewhere":
            self.send_response(307); self.send_header("location", f"http://127.0.0.1:{self.server.server_port}/elsewhere"); self.end_headers(); return
        if "id" not in body:
            self.send_response(202); self.end_headers(); return
        m = body["method"]
        res = {"initialize": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake"}}, "tools/list": {"tools": [{"name": "a"}, {"name": "b"}]}}.get(m, {})
        data = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": res}).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("mcp-session-id", "s1"); self.send_header("content-length", str(len(data))); self.end_headers(); self.wfile.write(data)


@pytest.fixture
def mcp_http():
    FakeMcp.log, FakeMcp.mode = [], "ok"
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeMcp)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/mcp"
    srv.shutdown()


def _serve_cfg(world, url):
    (world.proj / ".mcp.json").write_text(json.dumps({"mcpServers": {"live": {"type": "http", "url": url, "headers": {"Authorization": "Bearer SECRETHDR"}}}}))
    (world.proj / ".claude" / "settings.json").write_text(json.dumps({"enableAllProjectMcpServers": True}))


def test_the_http_probe_sends_initialize_initialized_and_tools_list_only_and_no_credential(world, mcp_http):
    _serve_cfg(world, mcp_http)
    out = INV.check(world.proj, world.home, "claude:live", env={"PATH": os.environ["PATH"]})
    assert out["connection"]["status"] == "available" and out["connection"]["tool_count"] == 2
    assert [m for m, _a in FakeMcp.log] == ["initialize", "notifications/initialized", "tools/list"] and all(a is None for _m, a in FakeMcp.log)       # the agent's private login is never reused


def test_a_private_auth_failure_is_agent_auth_and_the_remote_text_never_leaves(world, mcp_http):
    _serve_cfg(world, mcp_http)
    FakeMcp.mode = "auth"
    out = INV.check(world.proj, world.home, "claude:live", env={"PATH": os.environ["PATH"]})
    assert out["connection"]["status"] == "agent-auth" and "SECRETHDR" not in json.dumps(out) and "ECHO" not in json.dumps(out)


def test_redirects_are_refused(world, mcp_http):
    _serve_cfg(world, mcp_http)
    FakeMcp.mode = "redirect"
    out = INV.check(world.proj, world.home, "claude:live", env={"PATH": os.environ["PATH"]})
    assert out["connection"]["status"] == "unavailable"


STDIO = '''
import json, os, sys
log = open(os.environ["MCP_LOG"], "a")
log.write("pid " + str(os.getpid()) + "\\n"); log.flush()
for line in sys.stdin:
    msg = json.loads(line)
    log.write((msg.get("method") or "?") + "\\n"); log.flush()
    if "id" not in msg: continue
    res = {"initialize": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "s"}}, "tools/list": {"tools": [{"name": "t"}]}}.get(msg["method"], {})
    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": res}), flush=True)
'''


def test_a_stdio_probe_reaps_its_process_and_never_calls_a_tool(world):
    script = world.tmp / "fake_stdio.py"
    script.write_text(STDIO)
    log = world.tmp / "stdio.log"
    (world.proj / ".mcp.json").write_text(json.dumps({"mcpServers": {"st": {"command": sys.executable, "args": [str(script)], "env": {"MCP_LOG": str(log)}}}}))
    (world.proj / ".claude" / "settings.json").write_text(json.dumps({"enableAllProjectMcpServers": True}))
    out = INV.check(world.proj, world.home, "claude:st", env={"PATH": os.environ["PATH"]})
    assert out["connection"]["status"] == "available" and out["connection"]["tool_count"] == 1
    lines = log.read_text().split()
    assert "tools/call" not in lines and "tools/list" in lines
    pid = int(log.read_text().split("pid ")[1].split()[0])
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_the_fingerprint_invalidates_after_an_env_change_and_the_result_goes_stale(world, mcp_http):
    _serve_cfg(world, mcp_http)
    now = [1000.0]
    INV.check(world.proj, world.home, "claude:live", env={"PATH": os.environ["PATH"]}, clock=lambda: now[0])
    res = INV.inventory(world.proj, world.home, env={"PATH": os.environ["PATH"]}, clock=lambda: now[0])
    assert by_id(res)["claude:live"]["connection"]["status"] == "available" and by_id(res)["claude:live"]["connection"]["stale"] is False
    now[0] += 301
    assert INV.inventory(world.proj, world.home, env={"PATH": os.environ["PATH"]}, clock=lambda: now[0])["servers"][0] and by_id(INV.inventory(world.proj, world.home, env={"PATH": os.environ["PATH"]}, clock=lambda: now[0]))["claude:live"]["connection"]["stale"] is True
    (world.proj / ".mcp.json").write_text(json.dumps({"mcpServers": {"live": {"type": "http", "url": mcp_http, "headers": {"Authorization": "Bearer CHANGED"}}}}))
    assert by_id(INV.inventory(world.proj, world.home, env={"PATH": os.environ["PATH"]}))["claude:live"]["connection"] is None


def test_unknown_ids_and_unchecked_entries_are_refused_with_the_fix_and_at_most_two_checks_run(world, mcp_http, monkeypatch):
    with pytest.raises(INV.InventoryError, match="MCP configuration was not found: refresh the list"):
        INV.check(world.proj, world.home, "claude:nope", env={"PATH": os.environ["PATH"]})
    with pytest.raises(INV.InventoryError, match="cannot be checked"):
        INV.check(world.proj, world.home, "claude:unapproved", env={"PATH": os.environ["PATH"]})
    _serve_cfg(world, mcp_http)
    gate, started = threading.Event(), threading.Semaphore(0)
    real = PR.probe
    def slow(*a, **k):
        started.release(); gate.wait(5); return real(*a, **k)
    monkeypatch.setattr(INV.PR, "probe", slow)
    ts = [threading.Thread(target=lambda: INV.check(world.proj, world.home, "claude:live", env={"PATH": os.environ["PATH"]})) for _ in range(2)]
    [t.start() for t in ts]
    started.acquire(timeout=5); started.acquire(timeout=5)
    with pytest.raises(INV.InventoryError, match="Two connection checks are running: wait for one to finish"):
        INV.check(world.proj, world.home, "claude:live", env={"PATH": os.environ["PATH"]})
    gate.set()
    [t.join(10) for t in ts]


# ------------------------------------------------------------------------------------------------ routes
from starlette.testclient import TestClient  # noqa: E402

from lampway_server.app import create_app  # noqa: E402


def test_the_routes_need_the_bearer_and_return_the_inventory_and_a_refusal_with_the_fix(world, settings, provider, monkeypatch):
    monkeypatch.setenv("HOME", str(world.home))
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(world.proj))
    app = create_app(settings, provider=provider)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        assert http.get("/app/mcp/inventory").status_code == 401 and http.post("/app/mcp/check", json={"id": "x"}).status_code == 401
        from .fake_client import FakeMixarClient
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        h = fake.rest_headers()
        inv = http.get("/app/mcp/inventory?client=codex", headers=h).json()
        assert {s["client"] for s in inv["servers"]} == {"codex"} and inv["lampway"]["tools_offered"] > 10 and inv["lampway"]["eligible"] is False
        r = http.post("/app/mcp/check", headers=h, json={"id": "claude:nope"})
        assert r.status_code == 422 and "refresh the list" in r.json()["detail"]


def test_a_disabled_plugin_server_is_not_checkable(world):
    root = world.tmp / "plug"
    root.mkdir()
    (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"pl": {"command": "python3"}}}))
    (world.home / ".claude" / "plugins").mkdir(parents=True)
    (world.home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": {"p@m": [{"installPath": str(root)}]}}))
    (world.home / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"p@m": False}}))
    s = by_id(scan(world))["claude:p@m:pl"]
    assert s["plugin"] == "p@m" and s["readiness"] == "disabled" and s["can_check"] is False
