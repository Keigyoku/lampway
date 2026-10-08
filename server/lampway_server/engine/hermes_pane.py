# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lampway's Mode 1 pane wrapper (docs/reports/agent-modes-spec.md A1): what runs in a ``lampway_hermes`` pane on Lampway's herdr
server. The server's own interpreter runs THIS FILE by path (``<python> .../hermes_pane.py --home <unit home>``), so it needs nothing
but the standard library and never imports the server.

In order, it:

1. **starts the backend**: ``hermes serve --host 127.0.0.1 --port <P>`` as its own child, in a process group of its own (so a Ctrl+C
   typed into the TUI never reaches it), within the pane's session so herdr's forced pane close includes it, with the environment
   ``serve_env`` builds: the unit's ``HERMES_HOME``, a ``HOME`` inside it,
   the serve token from the home's 0600 ``serve.token`` (``HERMES_DASHBOARD_SESSION_TOKEN``: never on a command line),
   ``HERMES_TUI_WS_ORPHAN_REAP_GRACE_S=0`` (a session with no client parks, never reaped), ``HERMES_GATEWAY_LOCK_DIR`` in the home
   (one serve per unit, not one per OS user), the egress proxy's variables, no key of the user's, never ``HERMES_DESKTOP``;
2. **waits** until serve answers HTTP on its port;
3. **runs Hermes's own TUI in the foreground**: ``hermes --tui --resume <stored id>`` against the prebuilt bundle
   (``HERMES_TUI_DIR``) with ``HERMES_TUI_GATEWAY_URL`` naming this serve, ``HERMES_NODE`` the Node Lampway found and
   ``HERMES_SKIP_NODE_BOOTSTRAP=1``: the TUI never builds, installs or fetches anything (law 2). The stored session id is the one the
   server created and wrote to the home's ``session.json``; without one in time the TUI starts its own session and the server
   follows it;
4. **when the TUI exits** keeps serve running and reopens the TUI only when the user presses Enter (law 5: nothing respawns without a
   click). When serve itself stops (the user's own ``hermes serve --stop`` or ``hermes update`` stops every serve by its command
   line), it says so and starts it again only on Enter. Closing the pane (or Ctrl+C at the prompt) ends serve; its conversation stays
   in the home's ``state.db`` and a reopened pane resumes it.

``pane.json`` in the home (0600, written by the server; no secret in it) says what to run: ``hermes`` (the pinned engine's binary),
``port``, ``cwd`` (the project root), ``tui_dir``, ``node``, ``env`` (the proxy variables) and ``label``.
"""

import argparse
import http.client
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

SPEC_FILE = "pane.json"
TOKEN_FILE = "serve.token"
SESSION_FILE = "session.json"
SCRUB = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
DROP_PREFIXES = ("HERMES_", "OPENAI_", "ANTHROPIC_", "OPENROUTER_")
PROXY_NAMES = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY")
LISTEN_TIMEOUT_S = 60.0
SESSION_WAIT_S = 90.0
NODE_MAJORS = (22, 24)          # the pinned TUI's engines field: ^22.22 || ^24.11 || >=26 (package.json at the pin)

REOPEN = "Hermes's window closed; Lampway's agent keeps its conversation running. Press Enter to reopen Hermes (Ctrl+C ends it)."
STOPPED = ("Lampway's Hermes backend stopped (exit {code}). Your own Hermes's `hermes serve --stop` or `hermes update` stops every "
           "Hermes backend on this computer, Lampway's too. Your conversation is kept. Press Enter to start it again (Ctrl+C ends it).")


def base_env(environ=None) -> dict:
    """The pane's environment with every secret-shaped variable, every Hermes variable, every provider variable and every proxy
    variable removed: Hermes holds no key (E1.3, B5) and reaches out only through what ``pane.json`` names."""
    src = os.environ if environ is None else environ
    return {k: v for k, v in src.items()
            if not any(t in k.upper() for t in SCRUB) and not k.upper().startswith(DROP_PREFIXES) and k.upper() not in PROXY_NAMES}


def serve_env(spec: dict, home: Path, token: str, environ=None) -> dict:
    env = base_env(environ)
    managed = home / "managed"
    env.update(HERMES_HOME=str(home), HOME=str(home / "home"), HERMES_MANAGED_DIR=str(managed), PYTHONUNBUFFERED="1",
               HERMES_GATEWAY_LOCK_DIR=str(home / "locks"), HERMES_TUI_WS_ORPHAN_REAP_GRACE_S="0",
               HERMES_DASHBOARD_SESSION_TOKEN=token)
    env.update({str(k): str(v) for k, v in (spec.get("env") or {}).items()})
    if spec.get("toolsets"):
        # The chosen toolsets and Lampway's MCP server, pinned: serve otherwise folds a GUI's toolsets into every session (A1).
        env["HERMES_TUI_TOOLSETS"] = ",".join(str(t) for t in spec["toolsets"])
    env.pop("HERMES_DESKTOP", None)
    return env


def tui_env(spec: dict, home: Path, token: str, environ=None) -> dict:
    env = serve_env(spec, home, token, environ)
    env.pop("HERMES_DASHBOARD_SESSION_TOKEN", None)
    node = str(spec.get("node") or "")
    if node:
        env["PATH"] = os.pathsep.join([str(Path(node).parent), env.get("PATH", "")])
        env["HERMES_NODE"] = node
    env.update(HERMES_TUI_DIR=str(spec["tui_dir"]), HERMES_SKIP_NODE_BOOTSTRAP="1", HERMES_TUI_CWD=str(spec.get("cwd") or home),
               HERMES_TUI_GATEWAY_URL=f"ws://127.0.0.1:{int(spec['port'])}/api/ws?token={token}")
    env.setdefault("TERM", "xterm-256color")
    return env


def serve_argv(spec: dict) -> list:
    return [str(spec["hermes"]), "serve", "--host", "127.0.0.1", "--port", str(int(spec["port"]))]


def tui_argv(spec: dict, stored_id: str) -> list:
    return [str(spec["hermes"]), "--tui"] + (["--resume", stored_id] if stored_id else [])


def stored_session(home: Path) -> str:
    try:
        return str(json.loads((home / SESSION_FILE).read_text(encoding="utf-8")).get("stored_session_id") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def listening(port: int, timeout: float = 1.0) -> bool:
    """serve answers HTTP on its port (any status: /api/ws without the upgrade is refused, which still means it is up)."""
    conn = http.client.HTTPConnection("127.0.0.1", int(port), timeout=timeout)
    try:
        conn.request("GET", "/api/ws")
        conn.getresponse().read()
        return True
    except OSError:
        return False
    finally:
        conn.close()


def node_problem(node: str) -> str:
    """Why the TUI cannot run on this Node, or "" (spec A1: Node is found or refused with help, never fetched)."""
    if not node or not os.access(node, os.X_OK):
        return ("Node.js is not available to Lampway's agent pane. Install Node.js 22 or 24 (nodejs.org or your package manager), "
                "or point LAMPWAY_NODE at it, then reopen the pane")
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=15).stdout.strip()
        major = int(out.lstrip("v").split(".")[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return f"{node} does not answer --version; install Node.js 22 or 24"
    if major not in NODE_MAJORS and major < 26:
        return f"Hermes's TUI needs Node.js 22, 24 or 26+, and {node} is {out}; install a supported Node and reopen the pane"
    return ""


class Pane:
    def __init__(self, home: Path, environ=None, out=None, inp=None):
        self.home = Path(home)
        self.spec = json.loads((self.home / SPEC_FILE).read_text(encoding="utf-8"))
        self.token = (self.home / TOKEN_FILE).read_text(encoding="utf-8").strip()
        self.environ = environ
        self.out = out or sys.stdout
        self.inp = inp or sys.stdin
        self.serve = None
        self._stopping_serve = False

    def say(self, text: str) -> None:
        print(text, file=self.out, flush=True)

    def wait_enter(self) -> bool:
        """True on Enter, False on end of input (the pane is gone)."""
        line = self.inp.readline()
        return bool(line)

    # ------------------------------------------------------------------ serve
    def start_serve(self):
        logs = self.home / "logs"
        logs.mkdir(mode=0o700, exist_ok=True)
        fd = os.open(logs / "serve.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        cwd = self.spec.get("cwd") or str(self.home)
        self.serve = subprocess.Popen(serve_argv(self.spec), env=serve_env(self.spec, self.home, self.token, self.environ), cwd=cwd,
                                      stdin=subprocess.DEVNULL, stdout=fd, stderr=fd, process_group=0)
        os.close(fd)
        (self.home / "serve.pid").write_text(str(self.serve.pid))
        deadline = time.monotonic() + LISTEN_TIMEOUT_S
        while time.monotonic() < deadline:
            if self.serve.poll() is not None:
                return False
            if listening(int(self.spec["port"])):
                return True
            time.sleep(0.2)
        return False

    def stop_serve(self) -> None:
        """Ends the serve THIS wrapper started, by its recorded process group (never a pattern kill)."""
        if self._stopping_serve:
            return
        p = self.serve
        if p is None:
            return
        self._stopping_serve = True
        try:
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGTERM)
                    p.wait(timeout=15)
                except ProcessLookupError:
                    p.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    p.wait(timeout=15)
            if p.poll() is not None:
                self.serve = None
        finally:
            self._stopping_serve = False

    def serve_alive(self) -> bool:
        return self.serve is not None and self.serve.poll() is None

    # ------------------------------------------------------------------ the TUI
    def session_id(self) -> str:
        deadline = time.monotonic() + float(self.spec.get("session_wait_s", SESSION_WAIT_S))
        while time.monotonic() < deadline and self.serve_alive():
            sid = stored_session(self.home)
            if sid:
                return sid
            time.sleep(0.2)
        return stored_session(self.home)

    def run_tui(self) -> int:
        sid = self.session_id()
        main = threading.current_thread() is threading.main_thread()
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN) if main else None    # Ctrl+C is the TUI's while it runs
        try:
            tui = subprocess.Popen(tui_argv(self.spec, sid), env=tui_env(self.spec, self.home, self.token, self.environ),
                                   cwd=self.spec.get("cwd") or str(self.home))
            return tui.wait()
        finally:
            if main:
                signal.signal(signal.SIGINT, previous)

    # ------------------------------------------------------------------ the loop
    def run(self) -> int:
        label = self.spec.get("label") or "Lampway Agent"
        problem = node_problem(str(self.spec.get("node") or ""))
        if problem:
            self.say(f"error: {problem}")
            return 1
        self.say(f"{label}: starting Lampway's Hermes backend...")
        while True:
            if not self.serve_alive():
                if not self.start_serve():
                    code = self.serve.poll() if self.serve is not None else None
                    self.stop_serve()
                    self.say(f"error: Lampway's Hermes backend did not start (exit {code}); its log is {self.home / 'logs' / 'serve.log'}. "
                             "Press Enter to try again (Ctrl+C ends it).")
                    if not self.wait_enter():
                        return 1
                    continue
            self.run_tui()
            if not self.serve_alive():
                code = self.serve.returncode if self.serve is not None else None
                self.serve = None
                self.say(STOPPED.format(code=code))
            else:
                self.say(REOPEN)
            if not self.wait_enter():
                return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lampway's Mode 1 pane: hermes serve plus Hermes's own TUI (agent-modes spec A1)")
    ap.add_argument("--home", required=True, help="the unit's Hermes home, written by Lampway's server")
    args = ap.parse_args(argv)
    pane = Pane(Path(args.home))
    ending = False

    def ended(signum, frame):              # the pane closed (SIGHUP) or the server's user closed it (SIGTERM): serve ends with it
        nonlocal ending
        if ending:
            return                        # repeated HUP/TERM must not interrupt the owned child's wait/reap
        ending = True
        pane.stop_serve()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, ended)
    signal.signal(signal.SIGHUP, ended)
    try:
        return pane.run()
    except KeyboardInterrupt:
        return 0
    finally:
        ending = True                      # normal EOF/Ctrl+C cleanup owns the same uninterrupted child join
        pane.stop_serve()


if __name__ == "__main__":
    sys.exit(main())
