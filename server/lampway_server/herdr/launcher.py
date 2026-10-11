"""The ONE place a herdr process is spawned. See the package docstring for the invariants this enforces."""
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

PASS_THROUGH_FOR_PANES = ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "CLAUDE_CONFIG_DIR", "CODEX_HOME")
SOCK_LIMIT = 100


class HerdrError(RuntimeError):
    pass


#: Where scripts/lampway/herdr_env.py builds the pinned herdr (``third_party/herdr``): ``LAMPWAY_HERDR_BUILDS``, else the repository's
#: ``build/herdr``.
REPO_BUILDS = Path(__file__).resolve().parents[3] / "build" / "herdr"


def pinned_build() -> Optional[str]:
    """The newest FINISHED pinned build (``<builds>/<tag>/herdr.json`` written last by herdr_env.py), or None."""
    base = Path(os.environ.get("LAMPWAY_HERDR_BUILDS") or REPO_BUILDS)
    done = sorted((p for p in base.glob("*/herdr.json") if p.is_file()), key=lambda p: p.stat().st_mtime) if base.is_dir() else []
    for rec_path in reversed(done):
        try:
            binary = rec_path.parent / json.loads(rec_path.read_text()).get("binary", "herdr")
        except (OSError, ValueError):
            continue
        if binary.is_file() and os.access(binary, os.X_OK):
            return str(binary)
    return None


def bin_path() -> str:
    """The herdr Lampway runs: ``LAMPWAY_HERDR_BIN``; else the pinned build, as Blender is built from its pin; else one on PATH or in
    ``~/.local/bin``."""
    cand = (os.environ.get("LAMPWAY_HERDR_BIN") or pinned_build() or shutil.which("herdr")
            or str(Path.home() / ".local/bin/herdr"))
    if not Path(cand).exists():
        raise HerdrError("herdr is not installed: build Lampway's pinned herdr (scripts/lampway/herdr_env.py), or install one "
                         "(or set LAMPWAY_HERDR_BIN) and run it once yourself")
    return cand


def _runtime_dir(root: Path) -> Path:
    h = hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:8]
    base = Path(f"/run/user/{os.getuid()}")
    base = base if base.is_dir() else Path("/tmp")
    return base / f"lampway-herdr-{h}"


def socket_paths(root) -> tuple:
    root = Path(root)
    a, b = root / "run" / "h.sock", root / "run" / "hc.sock"
    if len(str(a)) >= SOCK_LIMIT or len(str(b)) >= SOCK_LIMIT:
        d = _runtime_dir(root)
        return d / "h.sock", d / "hc.sock"
    a.parent.mkdir(parents=True, exist_ok=True)
    return a, b


def scrubbed_base() -> dict:
    """The server's environment with every secret-shaped variable and every Connections name removed (connections.env_for([])):
    herdr, and so every pane, starts from it (agent-modes spec B5). A key reaches a pane only through the user's per-pane opt-in."""
    from .. import connections
    return dict(connections.env_for([]))


def env_for(root) -> dict:
    """herdr's environment: the scrubbed base, every herdr variable under the Lampway root, the fleet's HERDR_* scrubbed. The panes' real login environment is passed separately (pane_env)."""
    root = Path(root)
    sock, csock = socket_paths(root)
    env = {k: v for k, v in scrubbed_base().items() if not k.startswith("HERDR_")}
    home = root / "home"
    (home / ".config" / "herdr").mkdir(parents=True, exist_ok=True)
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"), HERDR_SOCKET_PATH=str(sock), HERDR_CLIENT_SOCKET_PATH=str(csock),
               HERDR_CONFIG_PATH=str(home / ".config" / "herdr" / "config.toml"))
    return env


def pane_env() -> list:
    """['--env', 'HOME=<real home>', ...] for panes created in the Lampway server: the agents must see the user's real login (the server itself runs on the redirected HOME)."""
    out = []
    for k in PASS_THROUGH_FOR_PANES:
        v = os.environ.get(k) or (str(Path.home()) if k == "HOME" else None)
        if v:
            out += ["--env", f"{k}={v}"]
    return out


def _check(root, env: dict) -> None:
    expected = str(socket_paths(root)[0])
    if env.get("HERDR_SOCKET_PATH") != expected or str(env.get("HERDR_CLIENT_SOCKET_PATH", "")) != str(socket_paths(root)[1]) or not env.get("HERDR_CONFIG_PATH", "").startswith(str(root)):
        raise HerdrError("refusing to run herdr without the Lampway socket environment: the fleet's server is never addressed")


def _spawn(cmd: list, env: dict, timeout=30, input=None, detached=False):
    """The single subprocess entry of the whole package."""
    if detached:
        return subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout, input=input)


def _probe_spawn(argv: list, env: dict, timeout: float, cwd=None):
    """Local version, startup or MCP identity qualification; no model turn or login command."""
    return subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)


def probe(argv: list, timeout: float = 10) -> tuple:
    """(exit code, output) of a harness's version flag, run with the scrubbed environment; (None, "") when it cannot run."""
    try:
        r = _probe_spawn([str(a) for a in argv], scrubbed_base(), timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    return r.returncode, r.stdout or r.stderr or ""


def worker_probe(argv: list, env: dict, timeout: float = 10, *, cwd=None) -> tuple:
    """Local startup/identity qualification; never a provider turn, login or frontend command."""
    try:
        args = ([str(a) for a in argv], {**scrubbed_base(), **env}, timeout)
        r = _probe_spawn(*args, cwd=cwd) if cwd is not None else _probe_spawn(*args)
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    return r.returncode, (r.stdout or "")[:16384]


def _status_spawn(argv: list, env: dict, timeout: float):
    """A harness's own login status command (harnesses/: Adapter.login_state). Only ever called inside guard(byoa:<harness>)."""
    return subprocess.run(argv, env=env, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)


def login_probe(route: str, argv: list, timeout: float = 20) -> tuple:
    """(exit code, output) of a harness's own status command, inside its egress route (the harness may ask its vendor): refused
    with the route off, logged before it starts. It runs with the scrubbed environment and the user's real home, so it reads its own
    login, which Lampway never does (spec B0)."""
    from .. import egress as EG
    with EG.guard(route, kind="request"):
        try:
            r = _status_spawn([str(a) for a in argv], scrubbed_base(), timeout)
        except (OSError, subprocess.TimeoutExpired):
            return None, ""
    return r.returncode, r.stdout or r.stderr or ""


def run(root, args: list, timeout=30, input=None) -> str:
    """One herdr command against the Lampway server; returns stdout. The environment is checked BEFORE the spawn."""
    env = env_for(root)
    _check(root, env)
    r = _spawn([bin_path(), *map(str, args)], env, timeout, input)
    if r.returncode != 0:
        raise HerdrError((r.stderr or r.stdout).strip()[:400] or f"herdr {' '.join(map(str, args[:2]))} exited {r.returncode}")
    return r.stdout


def server_status(root) -> dict:
    try:
        out = run(root, ["status", "server", "--json"], timeout=20)
        return json.loads(out)
    except (HerdrError, ValueError, subprocess.TimeoutExpired):
        return {"running": False, "status": "not_running"}


def _info_path(root) -> Path:
    return Path(root) / "server.json"


def server_info(root) -> dict:
    p = _info_path(root)
    return json.loads(p.read_text()) if p.exists() else {}


def _systemd_ok() -> bool:
    if not shutil.which("systemd-run") or not shutil.which("systemctl"):
        return False
    r = subprocess.run(["systemctl", "--user", "is-system-running"], capture_output=True, text=True, timeout=10)
    return r.stdout.strip() in ("running", "degraded")


def start_server(root, method="auto") -> dict:
    """Start the Lampway herdr server DETACHED (it must outlive Blender and the Lampway server). Idempotent: a running server is never started twice."""
    root = Path(root)
    if server_status(root).get("running"):
        return {"already_running": True, "method": server_info(root).get("method")}
    env = env_for(root)
    _check(root, env)
    Path(env["HERDR_SOCKET_PATH"]).parent.mkdir(mode=0o700, parents=True, exist_ok=True)       # a short runtime socket dir (a long root) is made only when a server really starts
    exe = bin_path()
    use_systemd = method == "systemd" or (method == "auto" and _systemd_ok())
    unit = "lampway-herdr-" + hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:8]
    if use_systemd:
        setenv = [f"--setenv={k}={env[k]}" for k in ("HOME", "XDG_CONFIG_HOME", "HERDR_SOCKET_PATH", "HERDR_CLIENT_SOCKET_PATH", "HERDR_CONFIG_PATH", "PATH") if k in env]
        r = _spawn(["systemd-run", "--user", f"--unit={unit}", "--collect", *setenv, exe, "server"], env, 30)
        if r.returncode != 0:
            raise HerdrError("systemd-run could not start the herdr server unit: " + (r.stderr or r.stdout).strip()[:300])
        info = {"method": "systemd", "unit": unit}
    else:
        proc = _spawn([exe, "server"], env, detached=True)
        info = {"method": "setsid", "pid": proc.pid}
    info.update(started_at=time.time(), bin=exe)
    _info_path(root).write_text(json.dumps(info))
    end = time.time() + 20
    while time.time() < end and not server_status(root).get("running"):
        time.sleep(0.2)
    if not server_status(root).get("running"):
        raise HerdrError("the herdr server did not come up within 20 s")
    return {"already_running": False, "method": info["method"]}


def stop_server(root, confirmed=False) -> dict:
    """Stops ONLY the Lampway server, and only on an explicit user action: panes and the server are never stopped implicitly (Blender exit, add-on unregister, a crash)."""
    if not confirmed:
        raise HerdrError("stopping the herdr server is an explicit user action: confirm it in the cockpit (every agent pane in it ends)")
    info = server_info(root)
    try:
        run(root, ["server", "stop"], timeout=30)
    except HerdrError:
        if info.get("unit"):
            _spawn(["systemctl", "--user", "stop", info["unit"] + ".service"], env_for(root), 30)
    return {"stopped": True}
