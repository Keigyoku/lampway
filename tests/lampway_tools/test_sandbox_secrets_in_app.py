# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Connections audit F1/F2 (specs/connections/connections_store.md section 9 and test 14), through the REAL ScriptExecutor in the real binary.

F1: an agent-written script must not read any secret Lampway holds (the server state directory, the client keyring, every *_auth.json, jwt_secret,
refresh_tokens.json, agent_settings.json) nor write a route switch (egress.json, local_cli.json), by any path spelling: direct, '..', or a symlink planted
in the temp dir. F2: it must not reach a module that holds the client's bearer (the /app/* client doors, the auth store), so it cannot forge the user's
click. (c) is measured and reported: the sandbox's own urllib may GET loopback (the local asset server), without any bearer."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

SECRETS = ["server-state/chatgpt_auth.json", "server-state/higgsfield_auth.json", "server-state/agent_settings.json", "server-state/jwt_secret",
           "server-state/refresh_tokens.json", "server-state/egress.json", "server-state/local_cli.json", "keyring.json", "secrets/openrouter.key"]

DRIVER = r'''
import http.server, json, os, threading, tempfile
from mixar.modules.space_mixie_chat.core.executor import ScriptExecutor
home = os.environ["LAMPWAY_HOME"]
for rel in json.loads(os.environ["LW_SECRETS"]):
    p = os.path.join(home, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write("SENTINEL-" + rel)
os.makedirs(os.path.join(home, "projects"), exist_ok=True)
link = os.path.join(tempfile.gettempdir(), "innocent.json")
os.symlink(os.path.join(home, "server-state/chatgpt_auth.json"), link)
seen = []
class H(http.server.BaseHTTPRequestHandler):
    def _rec(self):
        seen.append({"method": self.command, "path": self.path, "auth": self.headers.get("Authorization")})
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b"{}")
    do_GET = do_POST = do_PUT = _rec
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = "http://127.0.0.1:%d" % srv.server_address[1]
ex = ScriptExecutor()
out = {}
def run(name, src):
    res = ex.execute(src.replace("%HOME%", repr(home)).replace("%URL%", repr(url)).replace("%LINK%", repr(link)), push_undo=False)
    out[name] = {"success": res.success, "error": (res.error or "")[:240], "result": res.return_value}
for rel in json.loads(os.environ["LW_SECRETS"]):
    run("read:" + rel, "__RESULT__ = open(%HOME% + '/" + rel + "').read()")
run("read:dotdot", "__RESULT__ = open(%HOME% + '/projects/../server-state/jwt_secret').read()")
run("read:symlink", "__RESULT__ = open(%LINK%).read()")
run("write:egress", "f = open(%HOME% + '/server-state/egress.json', 'w'); f.write('{\"routes\": {\"openrouter\": {\"enabled\": true}}}'); f.close()")
run("write:local_cli", "f = open(%HOME% + '/server-state/local_cli.json', 'w'); f.write('{}'); f.close()")
run("import:egress_client", "import mixar.modules.lampway_tools.egress_client as e\ne.EgressClient(base_url=%URL%, token_getter=lambda: 'forged').set_route('openrouter', True)")
run("import:auth_token", "from mixar.modules.auth.core.auth import get_access_token\n__RESULT__ = get_access_token()")
run("import:studio_client_via_attr", "import mixar.modules.lampway_tools as lt\n__RESULT__ = str(lt.studio_client.StudioClient)")
run("import:common_api_client", "import mixar.modules.common.api.client as c\n__RESULT__ = str(c)")
run("urllib_get_loopback", "r = urllib.urlopen(%URL% + '/app/egress')\n__RESULT__ = r.read().decode()")
out["_server_saw"] = seen
out["_egress_after"] = open(os.path.join(home, "server-state/egress.json")).read()
print("RESULT", json.dumps(out))
'''


@pytest.fixture(scope="module")
def outcomes():
    r = run_script(DRIVER, env={"LAMPWAY_HOME": "@RUN_TMP@/home", "LAMPWAY_STATE_DIR": "@RUN_TMP@/home/server-state",
                                "LAMPWAY_KEYRING_FILE": "@RUN_TMP@/home/keyring.json", "LW_SECRETS": json.dumps(SECRETS)})
    assert r.rc == 0 and r.results, r.out[-3000:]
    return r.results[0]


@pytest.mark.parametrize("rel", SECRETS + ["dotdot", "symlink"])
def test_a_sandboxed_script_cannot_read_a_secret(outcomes, rel):
    got = outcomes["read:" + rel]
    assert got["success"] is False and "SENTINEL" not in json.dumps(got), got


@pytest.mark.parametrize("name", ["write:egress", "write:local_cli"])
def test_a_sandboxed_script_cannot_write_a_route_switch(outcomes, name):
    assert outcomes[name]["success"] is False, outcomes[name]
    assert outcomes["_egress_after"].startswith("SENTINEL"), "egress.json was changed"


@pytest.mark.parametrize("name", ["import:egress_client", "import:auth_token", "import:studio_client_via_attr", "import:common_api_client"])
def test_a_sandboxed_script_cannot_reach_a_bearer_holding_module(outcomes, name):
    assert outcomes[name]["success"] is False, outcomes[name]
    assert not [s for s in outcomes["_server_saw"] if s["method"] != "GET"], outcomes["_server_saw"]


def test_the_sandbox_urllib_get_to_loopback_carries_no_bearer(outcomes):
    """Measured, not changed by this hotfix: the sandbox's urllib may GET loopback (DEFAULT_ASSET_HOSTS); it never adds the client's bearer."""
    gets = [s for s in outcomes["_server_saw"] if s["method"] == "GET"]
    assert all(s["auth"] is None for s in gets), gets
