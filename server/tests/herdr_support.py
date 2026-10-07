"""Shared helpers for the herdr cockpit tests: a short isolated root, the fake agent CLI, and the fleet-isolation witness. The fleet's own herdr is only ever READ (status and snapshot) to prove it is untouched."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from lampway_server.herdr import launcher as L

try:
    HERDR = L.bin_path()                     # the one lookup: LAMPWAY_HERDR_BIN, the pinned build, PATH, ~/.local/bin
except L.HerdrError:
    HERDR = ""
needs_herdr = pytest.mark.skipif(not HERDR, reason="no herdr: build the pinned one (scripts/lampway/herdr_env.py) or set LAMPWAY_HERDR_BIN")
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


#: ``herdr pane report-metadata``'s options and the statuses a ``--state-label STATUS=TEXT`` may name (herdr 0.9.3 CLI reference).
METADATA_OPTIONS = {"--source", "--agent", "--applies-to-source", "--title", "--clear-title", "--display-agent", "--clear-display-agent",
                    "--state-label", "--clear-state-labels", "--token", "--clear-token", "--seq", "--ttl-ms"}
METADATA_STATES = {"idle", "working", "blocked", "done", "unknown"}

#: herdr 0.9.3's ``agent start --kind`` kinds (CLI reference; src/detect/mod.rs ``interactive_agent_executable``).
AGENT_KINDS = {"pi", "claude", "codex", "gemini", "cursor", "devin", "agy", "cline", "omp", "mastracode", "opencode", "copilot", "kimi",
               "kiro", "droid", "amp", "grok", "hermes", "kilo", "qodercli", "qwen", "letta", "maki", "muse"}
_AGENT_NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}")
_NAMED_KEYS = {"space", "enter", "return", "esc", "escape", "tab", "backspace", "bs", "left", "right", "up", "down", "minus", "comma",
               "period", "slash", "backslash", "quote", "double_quote", "double-quote", "semicolon", "colon", "percent", "ampersand",
               "backtick", "plus"}
_MODIFIERS = {"ctrl", "control", "shift", "alt", "option", "meta", "cmd", "command", "super", "hyper"}


def valid_key(key: str) -> bool:
    """herdr 0.9.3's key spelling (src/config/keybinds.rs parse_key_combo, src/app/api_helpers.rs): ``C-c``/``c-c`` alias ``ctrl+c``;
    otherwise ``+``-joined modifiers and one key, a named key, one character or ``f<n>``. ``ctrl-c`` is refused (``invalid_key``)."""
    key = {"C-c": "ctrl+c", "c-c": "ctrl+c", "+": "plus"}.get(key.strip(), key.strip())
    parts, main = key.split("+"), []
    if any(not p.strip() for p in parts):
        return False
    for p in parts:
        if p.strip().lower() not in _MODIFIERS:
            main.append(p.strip().lower())
    if len(main) != 1:
        return False
    k = main[0]
    return k in _NAMED_KEYS or len(k) == 1 or (k.startswith("f") and k[1:].isdigit())


def herdr_refusal(args: list):
    """What herdr 0.9.3 refuses before it does anything, as its own error text, or None. The played herdrs share it, so a spelling
    the real one refuses fails the unit suite too (``test_herdr_cockpit.py`` holds the same rules against the real binary)."""
    if args[:2] == ["agent", "start"]:
        if not _AGENT_NAME.fullmatch(args[2] if len(args) > 2 else ""):
            return ("agent name must start with a lowercase letter and contain only lowercase letters, digits, '-' or '_' "
                    "(1-32 characters)")
        if "--kind" not in args or args[args.index("--kind") + 1] not in AGENT_KINDS:
            return "unsupported agent kind"
    if args[:2] in (["pane", "send-keys"], ["agent", "send-keys"]):
        bad = next((k for k in args[3:] if not valid_key(k)), None)
        if bad is not None or len(args) < 4:
            return f'{{"error":{{"code":"invalid_key","message":"unsupported key {bad}"}}}}'
    return None


class PaneHerdr:
    """herdr, played (no binary runs). Every command is recorded with the egress rows written before it. It keeps herdr's layout:
    one ``lampway`` workspace, its tabs, and the panes of each tab in order. Panes appear on ``workspace create``, ``tab create`` and
    ``pane split``; run what ``agent start`` (or ``pane run``) named; answer ``process-info`` while they live; and vanish on
    ``pane close`` or ``exit`` (the harness quit). ``pane report-metadata`` is stored per pane.

    The CLI spellings of ``pane split`` and ``pane report-metadata`` are herdr's own (checked against herdr 0.9.3, its CLI
    reference and a live server; ``test_herdr_layout_live.py`` drives the real one): like herdr, this fake refuses an option it does
    not know, so a misspelling in ``herdr/layout.py`` fails here too.
    ``fail`` names verbs (``"split"``, ``"report-metadata"``) the played herdr refuses, as an older herdr would."""

    def __init__(self, egress=None):
        self.calls, self.panes, self.n, self.egress = [], {}, 0, egress
        self.tabs: dict = {}                 # tab id -> {"label": str, "panes": [pane ids in order]}
        self.workspace = None
        self.metadata: dict = {}             # pane id -> the last metadata it reported
        self.splits: dict = {}               # new pane id -> {"of": pane id, "direction": str, "ratio": float}
        self.fail: set = set()
        self.lock = threading.Lock()

    @staticmethod
    def _flag(args, name, default=None):
        return args[args.index(name) + 1] if name in args else default

    def _new_pane(self, tab_id):
        self.n += 1
        pid = f"p{self.n}"
        self.panes[pid] = {"terminal_id": f"t{self.n}", "cmd": "-bash", "tab_id": tab_id}
        self.tabs[tab_id]["panes"].append(pid)
        return {"pane_id": pid, "terminal_id": f"t{self.n}", "workspace_id": "w1", "tab_id": tab_id}

    def _new_tab(self, label):
        tab = f"tab{len(self.tabs) + 1}"
        self.tabs[tab] = {"label": label, "panes": []}
        return tab

    def __call__(self, root, args, timeout=30, input=None):
        args = [str(a) for a in args]
        with self.lock:
            sent = [r["route"] for r in (self.egress.log() if self.egress else []) if r.get("event") == "send"]
            self.calls.append({"args": args, "sends_before": sent})
            if (refused := herdr_refusal(args)) is not None:
                raise L.HerdrError(refused)
            if args[:2] == ["api", "snapshot"]:
                ws = [{"workspace_id": "w1", "label": self.workspace}] if self.workspace else []
                return json.dumps({"result": {"snapshot": {"workspaces": ws, "panes": [
                    {"pane_id": p, "terminal_id": v["terminal_id"], "tab_id": v["tab_id"]} for p, v in self.panes.items()]}}})
            if args[:2] == ["workspace", "create"]:
                self.workspace = self._flag(args, "--label")
                return json.dumps({"result": {"root_pane": self._new_pane(self._new_tab(None))}})
            if args[:2] == ["tab", "create"]:
                return json.dumps({"result": {"root_pane": self._new_pane(self._new_tab(self._flag(args, "--label")))}})
            if args[:2] == ["pane", "split"]:
                if "split" in self.fail:
                    raise L.HerdrError("unknown subcommand 'split'")
                of = args[2]
                if of not in self.panes:
                    raise L.HerdrError(f"no such pane {of}")
                pane = self._new_pane(self.panes[of]["tab_id"])
                self.splits[pane["pane_id"]] = {"of": of, "direction": self._flag(args, "--direction"),
                                                "ratio": float(self._flag(args, "--ratio"))}
                return json.dumps({"result": {"pane": pane}})
            if args[:2] == ["pane", "report-metadata"]:
                if "report-metadata" in self.fail:
                    raise L.HerdrError("unknown subcommand 'report-metadata'")
                if args[2] not in self.panes:
                    raise L.HerdrError(f"no such pane {args[2]}")
                labels, i = {}, 3
                while i < len(args):                     # herdr's options (CLI reference, pane report-metadata); anything else is refused
                    if args[i] not in METADATA_OPTIONS:
                        raise L.HerdrError(f"unknown option: {args[i]}")
                    if args[i] == "--state-label":
                        status, _, text = args[i + 1].partition("=")
                        if status not in METADATA_STATES:
                            raise L.HerdrError(f"invalid state label status: {status}")
                        labels[status] = text
                    i += 1 if args[i].startswith("--clear-") else 2
                self.metadata[args[2]] = {"source": self._flag(args, "--source"), "agent": self._flag(args, "--agent"),
                                          "display_agent": self._flag(args, "--display-agent"), "title": self._flag(args, "--title"),
                                          "state_labels": labels}
                return ""
            if args[:2] == ["pane", "read"]:
                return "user@box:~$ "
            if args[:2] == ["pane", "get"]:
                p = self.panes.get(args[2])
                if p is None:
                    raise L.HerdrError("no such pane")
                return json.dumps({"result": {"pane": {"pane_id": args[2], "agent_status": p.get("status", "unknown"),
                                                       "terminal_id": p["terminal_id"], "tab_id": p["tab_id"]}}})
            if args[:2] == ["agent", "start"]:
                pid = args[args.index("--pane") + 1]
                self.panes[pid]["cmd"] = " ".join([args[args.index("--kind") + 1], *args[args.index("--") + 1:]])
                return ""
            if args[:2] == ["pane", "run"]:
                self.panes[args[2]]["cmd"] = " ".join(args[3:])
                return ""
            if args[:2] == ["pane", "process-info"]:
                p = self.panes.get(args[args.index("--pane") + 1])
                if p is None:
                    raise L.HerdrError("no such pane")
                return json.dumps({"result": {"process_info": {"foreground_processes": [{"cmdline": p["cmd"]}]}}})
            if args[:2] == ["pane", "close"]:
                p = self.panes.pop(args[2], None)
                if p is not None:
                    self.tabs[p["tab_id"]]["panes"].remove(args[2])
                return ""
            return ""

    def exit(self, pane_id):
        """The harness quit and its pane closed (the user closed it, or herdr reaped it)."""
        with self.lock:
            p = self.panes.pop(pane_id, None)
            if p is not None:
                self.tabs[p["tab_id"]]["panes"].remove(pane_id)

    def renumber(self) -> dict:
        """herdr gave its panes new pane ids (same terminals, same tabs): what a reconcile after a restart must re-adopt."""
        with self.lock:
            moved = {pid: "q" + pid[1:] for pid in self.panes}
            self.panes = {moved[pid]: v for pid, v in self.panes.items()}
            for tab in self.tabs.values():
                tab["panes"] = [moved.get(p, p) for p in tab["panes"]]
            return moved

    def closed(self):
        return [c["args"][2] for c in self.calls if c["args"][:2] == ["pane", "close"]]

    def start_of(self, pane_id):
        return next(c for c in self.calls if c["args"][:2] == ["agent", "start"] and c["args"][c["args"].index("--pane") + 1] == pane_id)

    def made(self) -> list:
        """Every command that made a pane, in order (the fake numbers panes in that order)."""
        return [c for c in self.calls if c["args"][:2] in (["workspace", "create"], ["tab", "create"], ["pane", "split"])]

    def env_of(self, pane_id) -> dict:
        """The --env values herdr was given when it made this pane."""
        made = self.made()[int(pane_id[1:]) - 1]["args"]
        return dict(made[i + 1].split("=", 1) for i, a in enumerate(made) if a == "--env")
