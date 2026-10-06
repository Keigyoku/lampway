"""Shared helpers for the herdr cockpit tests: a short isolated root, the fake agent CLI, and the fleet-isolation witness. The fleet's own herdr is only ever READ (status and snapshot) to prove it is untouched."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

HERDR = os.environ.get("LAMPWAY_HERDR_BIN") or shutil.which("herdr") or str(Path.home() / ".local/bin/herdr")
needs_herdr = pytest.mark.skipif(not Path(HERDR).exists(), reason="herdr is not installed (LAMPWAY_HERDR_BIN)")
FAKE_CLI = '''import sys
print("fake agent ready", flush=True)
for line in sys.stdin:
    print("echo:", line.strip(), flush=True)
'''


def short_root(prefix="lwh-") -> Path:
    """A root short enough for a unix socket path (108 bytes): under the user's runtime dir, never /tmp's long pytest paths."""
    base = Path(f"/run/user/{os.getuid()}")
    base = base if base.is_dir() else Path(tempfile.gettempdir())
    return Path(tempfile.mkdtemp(prefix=prefix, dir=base))


def real_home() -> str:
    """The person's real home (the tests' HOME is isolated in the basetemp): only for the opt-in fleet witness."""
    import pwd
    return pwd.getpwuid(os.getuid()).pw_dir


def fleet_env() -> dict:
    """The DEFAULT environment (the fleet's herdr) in the real home, with this crew's own pane variables left out: used only for read-only status and snapshot queries."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_") and not k.startswith("XDG_")}
    env["HOME"] = real_home()
    return env


def fleet_witness() -> dict:
    """Read-only: the fleet server's status and the ids of its workspaces and panes (a marker leak or a stolen pane would show here).
    It looks at the REAL fleet in the person's real home, which no test does by default: opt in with LAMPWAY_TEST_FLEET_WITNESS=1."""
    if os.environ.get("LAMPWAY_TEST_FLEET_WITNESS") != "1":
        pytest.skip("the fleet witness reads the person's real herdr state: opt in with LAMPWAY_TEST_FLEET_WITNESS=1 (tests never read the real home by default)")
    def q(*a):
        r = subprocess.run([HERDR, *a], capture_output=True, text=True, env=fleet_env(), timeout=30)
        return r.stdout
    try:
        status = json.loads(q("status", "server", "--json"))
        snap = json.loads(q("api", "snapshot"))["result"]["snapshot"]
    except Exception:  # noqa: BLE001
        return {"running": False}
    sock = status.get("socket")
    ino = os.stat(sock).st_ino if sock and os.path.exists(sock) else None
    return {"running": bool(status.get("running")), "version": status.get("version"), "socket": sock, "socket_inode": ino,
            "workspaces": sorted(w["workspace_id"] for w in snap["workspaces"]), "panes": sorted(p["pane_id"] for p in snap["panes"]),
            "labels": sorted(str(w.get("label")) for w in snap["workspaces"]), "raw": json.dumps(snap, sort_keys=True)}


@pytest.fixture
def fake_cli(tmp_path):
    p = tmp_path / "fakecli.py"
    p.write_text(FAKE_CLI)
    return f"{sys.executable} {p}"


@pytest.fixture
def lroot():
    root = short_root()
    yield root
    try:
        from lampway_server.herdr import launcher
        if launcher.server_status(root).get("running"):
            launcher.stop_server(root, confirmed=True)
    except Exception:  # noqa: BLE001
        pass
    shutil.rmtree(root, ignore_errors=True)


def wait_for(cond, timeout=15.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        v = cond()
        if v:
            return v
        time.sleep(step)
    return cond()
