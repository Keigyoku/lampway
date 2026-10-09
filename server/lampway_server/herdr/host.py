"""The cockpit's session host: a durable registry of the agent sessions Lampway created in ITS OWN herdr server, and a reconcile that treats the live server as the truth (see the package
docstring for the invariants). Every herdr call goes through launcher.run; nothing here spawns a process or stops anything implicitly."""
import json
import os
import re
import shlex
import threading
import time
import uuid
from pathlib import Path

from . import launcher as L

AGENTS = ("claude", "codex", "opencode", "shell", "command")
EFFORTS = (None, "medium", "high", "xhigh", "max")
GENERIC_NAMES = {"session", "new session", "untitled", "chat", "agent"}
WORKSPACE_LABEL = "lampway"
USER_TYPING_GRACE_S = 2.5
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|\x1b\[[0-9;?]*[ -/]*[@-~]")
_LOCK = threading.Lock()


class CockpitError(ValueError):
    pass


def agent_args(agent, effort=None, bypass=False, resume_id=None, session_id=None) -> list:
    """The CLI arguments exactly as the cockpit contract fixes them: Codex `[resume <id>] --no-alt-screen ...`, Claude `[--resume <id> | --session-id <uuid>] ...`, OpenCode `[--session <id>] [--auto]`."""
    a = []
    if agent == "codex":
        if resume_id:
            a += ["resume", resume_id]
        a += ["--no-alt-screen"]
        if bypass:
            a += ["--dangerously-bypass-approvals-and-sandbox"]
        if effort:
            a += ["-c", f'model_reasoning_effort="{effort}"']
    elif agent == "claude":
        a += ["--resume", resume_id] if resume_id else (["--session-id", session_id] if session_id else [])
        if bypass:
            a += ["--dangerously-skip-permissions"]
        if effort:
            a += ["--effort", effort]
    elif agent == "opencode":
        if resume_id:
            a += ["--session", resume_id]
        if bypass:
            a += ["--auto"]
    return a


class Cockpit:
    def __init__(self, root, project_root=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.project_root = str(project_root) if project_root else None
        self.path = self.root / "sessions.json"

    # ------------------------------------------------------------------------------------------------- registry
    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {"version": 1, "sessions": []}

    def _save(self, data: dict) -> None:
        tmp = self.root / ".sessions.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(data, indent=1, sort_keys=True))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def _update(self, fn):
        with _LOCK:
            data = self._load()
            out = fn(data)
            self._save(data)
            return out

    def list_sessions(self) -> list:
        return self._load()["sessions"]

    def _get(self, sid: str) -> dict:
        for s in self._load()["sessions"]:
            if s["id"] == sid:
                return s
        raise CockpitError(f"{sid} is not a Lampway session: Lampway never types into or closes a pane it did not create")

    # ------------------------------------------------------------------------------------------------- the server
    def ensure_server(self) -> dict:
        """Start the Lampway herdr server detached: a USER action (the cockpit's Start), never an implicit one."""
        return L.start_server(self.root)

    def stop_server(self, confirmed=False) -> dict:
        return L.stop_server(self.root, confirmed)

    def shutdown(self) -> None:
        """What Blender exit, add-on unregister and Lampway server shutdown call: it deliberately does NOTHING to the herdr server or any pane."""
        return None

    def snapshot(self) -> dict:
        return json.loads(L.run(self.root, ["api", "snapshot"]))["result"]["snapshot"]

    # ------------------------------------------------------------------------------------------------- sessions
    def create_session(self, agent, name, cwd, task="", effort=None, bypass=False, resume_id=None, command=None, by="user", project_root=None) -> dict:
        if agent not in AGENTS:
            raise CockpitError(f"unknown agent {agent!r}: the agents are {', '.join(AGENTS)}")
        name = str(name or "").strip()
        if not 2 <= len(name) <= 100 or name.lower() in GENERIC_NAMES:
            raise CockpitError("name is 2..100 characters and not a generic placeholder (say what the session is for)")
        if bypass and by != "user":
            raise CockpitError("bypass can only be raised by the user's own click in the cockpit: an agent can never lift the permission level")
        if effort not in EFFORTS:
            raise CockpitError("effort is medium, high, xhigh or max")
        pr = project_root or self.project_root
        real = os.path.realpath(cwd)
        if pr and not (real == os.path.realpath(pr) or real.startswith(os.path.realpath(pr) + os.sep)):
            raise CockpitError("the folder must be inside the project root")
        if agent == "command" and not command:
            raise CockpitError("a command session needs the command")
        if not L.server_status(self.root).get("running"):
            raise CockpitError("the herdr server is not running: start it from the cockpit first (nothing is launched automatically)")
        record_id = uuid.uuid4().hex[:12]
        herdr_agent_name = "lampway-" + record_id
        snap = self.snapshot()
        ws = next((w for w in snap["workspaces"] if w.get("label") == WORKSPACE_LABEL), None)
        env = L.pane_env()
        if ws is None:
            out = json.loads(L.run(self.root, ["workspace", "create", "--cwd", real, "--label", WORKSPACE_LABEL, "--no-focus", *env]))["result"]
        else:
            out = json.loads(L.run(self.root, ["tab", "create", "--workspace", ws["workspace_id"], "--cwd", real, "--label", name[:40], "--no-focus", *env]))["result"]
        pane = out["root_pane"]
        pane_id = pane["pane_id"]
        native_id = resume_id
        tokens = []
        if agent in ("command", "claude", "codex", "opencode"):
            self._wait_prompt(pane_id)
        if agent == "command":
            L.run(self.root, ["pane", "run", pane_id, *shlex.split(command)])
            tokens = [os.path.basename(shlex.split(command)[-1])]
        elif agent in ("claude", "codex", "opencode"):
            sid = str(uuid.uuid4()) if agent == "claude" and not resume_id else None
            native_id = native_id or sid
            L.run(self.root, ["agent", "start", herdr_agent_name, "--kind", agent, "--pane", pane_id, "--", *agent_args(agent, effort, bypass, resume_id, sid)], timeout=120)
            tokens = [agent]
        rec = {"id": record_id, "name": name, "herdr_agent_name": herdr_agent_name if agent in ("claude", "codex", "opencode") else None, "agent": agent, "cwd": real, "task": task, "effort": effort, "bypass": bool(bypass), "pane_id": pane_id,
               "terminal_id": pane.get("terminal_id"), "workspace_id": pane.get("workspace_id"), "tab_id": pane.get("tab_id"), "native_id": native_id, "command": command, "match": tokens,
               "state": "live", "adopted": True, "agent_sends": False, "created_at": time.time(), "updated_at": time.time(), "ended_at": None, "end_reason": "", "created_by": by}
        self._update(lambda d: d["sessions"].append(rec))
        return rec

    def _wait_prompt(self, pane_id: str, timeout: float = 25.0) -> None:
        """A new pane's login shell prints its banner first; a command typed before the prompt is lost. Wait for a prompt-looking last line (the pane must be at an interactive shell prompt)."""
        end = time.time() + timeout
        while time.time() < end:
            text = _CTRL.sub("", L.run(self.root, ["pane", "read", pane_id, "--lines", "60", "--source", "recent"]))
            last = [ln for ln in text.splitlines() if ln.strip()]
            if last and re.search(r"[$#%>] ?$", last[-1].rstrip() + " ") and not last[-1].strip().startswith("•"):
                time.sleep(0.2)
                return
            time.sleep(0.25)
        raise CockpitError("the new pane never showed a shell prompt: nothing was started in it")

    def set_agent_sends(self, sid: str, on: bool) -> None:
        def f(d):
            for s in d["sessions"]:
                if s["id"] == sid:
                    s["agent_sends"] = bool(on)
                    return
            raise CockpitError(f"{sid} is not a Lampway session")
        self._update(f)

    def read_screen(self, sid: str, lines: int = 70) -> str:
        rec = self._get(sid)
        text = L.run(self.root, ["pane", "read", rec["pane_id"], "--lines", str(max(1, min(int(lines), 150))), "--source", "recent"])
        return _CTRL.sub("", text)

    def send_input(self, sid: str, text: str, submit=True, by="agent", user_typed_at=None) -> None:
        rec = self._get(sid)
        if rec["state"] != "live":
            raise CockpitError("the session is not running")
        if by != "user":
            if rec["agent"] == "shell":
                raise CockpitError("an agent can never type into a shell session")
            if not rec.get("agent_sends"):
                raise CockpitError("agent sends are off for this session: the user enables them in the cockpit")
            if user_typed_at is not None and time.time() - user_typed_at < USER_TYPING_GRACE_S:
                raise CockpitError("You are typing in this session: the agent's send is held back")
        if len(text) > 64000:
            raise CockpitError("input is limited to 64000 characters")
        L.run(self.root, ["pane", "send-text", rec["pane_id"], text])
        if submit:
            L.run(self.root, ["pane", "send-keys", rec["pane_id"], "enter"])

    def interrupt(self, sid: str) -> None:
        """One Ctrl+C into a live session (the cockpit's interrupt: a user request or the user's click)."""
        rec = self._get(sid)
        if rec["state"] != "live":
            raise CockpitError("the session is not running")
        L.run(self.root, ["pane", "send-keys", rec["pane_id"], "ctrl-c"])

    def close_session(self, sid: str, confirmed=False) -> dict:
        if not confirmed:
            raise CockpitError("closing a session is an explicit user action: confirm it (its agent process ends; its history stays)")
        rec = self._get(sid)
        try:
            L.run(self.root, ["pane", "close", rec["pane_id"]])
        except L.HerdrError:
            pass

        def f(d):
            for s in d["sessions"]:
                if s["id"] == sid:
                    s.update(state="ended", ended_at=time.time(), end_reason="closed by the user", updated_at=time.time())
        self._update(f)
        return {"closed": sid}

    # ------------------------------------------------------------------------------------------------- reconcile
    def reconcile(self) -> dict:
        """The live server is the truth, the registry the map. Never spawns, never kills, idempotent."""
        out = {"server": "running", "adopted": [], "ended": [], "unadopted": [], "new_panes": 0, "offered": []}
        if not L.server_status(self.root).get("running"):
            out.update(server="not_running", offered=["start", "resume"])
            return out
        snap = self.snapshot()
        before = len(snap["panes"])
        panes = {p["pane_id"]: p for p in snap["panes"]}
        by_term = {p.get("terminal_id"): p for p in snap["panes"] if p.get("terminal_id")}
        claimed = set()

        def judge(rec):
            pane = by_term.get(rec.get("terminal_id")) or panes.get(rec["pane_id"])
            if pane is None:
                return None, "its pane is gone from the server"
            claimed.add(pane["pane_id"])
            try:
                info = json.loads(L.run(self.root, ["pane", "process-info", "--pane", pane["pane_id"]]))["result"]["process_info"]
            except (L.HerdrError, ValueError):
                return None, "its pane could not be inspected"
            cmd = " ".join(p.get("cmdline", "") for p in info.get("foreground_processes", []))
            if rec.get("match") and not any(t in cmd for t in rec["match"]):
                return None, "the agent process is no longer running (the pane is at a shell prompt)"
            return pane, ""

        def f(d):
            for rec in d["sessions"]:
                if rec["state"] == "ended":
                    out["ended"].append(rec["id"])
                    continue
                pane, why = judge(rec)
                if pane is None:
                    rec.update(state="ended", ended_at=rec.get("ended_at") or time.time(), end_reason=why, adopted=False, updated_at=time.time())
                    out["ended"].append(rec["id"])
                else:
                    changed = rec.get("pane_id") != pane["pane_id"]
                    rec.update(pane_id=pane["pane_id"], terminal_id=pane.get("terminal_id"), adopted=True)
                    if changed:
                        rec["updated_at"] = time.time()
                    out["adopted"].append(rec["id"])
        self._update(f)
        out["unadopted"] = [pid for pid in panes if pid not in claimed]
        out["new_panes"] = max(0, len(self.snapshot()["panes"]) - before)
        return out
