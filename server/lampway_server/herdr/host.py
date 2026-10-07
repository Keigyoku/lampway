"""The cockpit's session host: a durable registry of the agent sessions Lampway created in ITS OWN herdr server, and a reconcile that treats the live server as the truth (see the package
docstring for the invariants). Every herdr call goes through launcher.run; nothing here spawns a process or stops anything implicitly."""
import contextlib
import json
import os
import re
import shlex
import threading
import time
import uuid
from pathlib import Path

from .. import egress as EG
from . import harnesses as HN
from . import launcher as L

#: Every harness adapter (spec B1), then Lampway's two plain kinds: a shell, and a command the user typed.
AGENTS = (*HN.ids(), "shell", "command")
EFFORTS = (None, "medium", "high", "xhigh", "max")
GENERIC_NAMES = {"session", "new session", "untitled", "chat", "agent"}
WORKSPACE_LABEL = "lampway"
USER_TYPING_GRACE_S = 2.5
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|\x1b\[[0-9;?]*[ -/]*[@-~]")
_LOCK = threading.Lock()


class CockpitError(ValueError):
    pass


def _key_env(ad) -> list:
    """['--env', 'NAME=value', ...] for the user's per-pane API-key opt-in (spec B5): only the keys of this harness's own vendor."""
    from .. import connections
    out = []
    for cid in ad.api_key_connections:
        try:
            values = connections.credential(cid).env()
        except Exception:  # noqa: BLE001 - not connected: the pane runs on the harness's own login
            continue
        for k, v in values.items():
            out += ["--env", f"{k}={v}"]
    if not out:
        raise CockpitError(f"no API key is connected for {ad.label}: connect one in Connections, or start the pane on the harness's own login")
    return out


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
    def create_session(self, agent, name, cwd, task="", effort=None, bypass=False, resume_id=None, command=None, by="user", project_root=None, api_key=False, scene_session_id=None) -> dict:
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
        if api_key and by != "user":
            raise CockpitError("only the user can bill a pane to an API key, with their own click in the cockpit: an agent never can")
        if not L.server_status(self.root).get("running"):
            raise CockpitError("the herdr server is not running: start it from the cockpit first (nothing is launched automatically)")
        ad = HN.ADAPTERS.get(agent)
        if scene_session_id and ad is None:
            raise CockpitError("only a harness pane can be bound to a scene tab")
        with (EG.guard(ad.route, kind="request") if ad else contextlib.nullcontext()):    # B5: logged before herdr is asked; refused with the route off
            return self._create(agent, ad, name, real, pr, task, effort, bypass, resume_id, command, by, api_key, scene_session_id or None)

    def _create(self, agent, ad, name, real, pr, task, effort, bypass, resume_id, command, by, api_key, scene) -> dict:
        if api_key and ad is None:
            raise CockpitError("only a harness pane can be billed to an API key")
        rid = uuid.uuid4().hex[:12]
        sid = str(uuid.uuid4()) if ad is not None and ad.picks_session_id and not resume_id else None
        cfg = str(self.root / "panes" / rid / ad.config_name) if ad is not None and scene else None
        spec = HN.PaneSpec(cwd=real, project_root=pr, effort=effort, bypass=bool(bypass), session_id=sid, scene_session_id=scene, mcp_config_path=cfg,
                           launcher=HN.mcp_launcher() if cfg else ())
        wiring = ad.lampway_tools(spec) if cfg else None
        if wiring is not None:                                 # B2: the pane's own MCP config, pinned to its scene tab, before anything starts
            self._write_pane_files(wiring.files)
        snap = self.snapshot()
        ws = next((w for w in snap["workspaces"] if w.get("label") == WORKSPACE_LABEL), None)
        env = L.pane_env() + (_key_env(ad) if api_key else []) + [x for k, v in (wiring.env if wiring else {}).items() for x in ("--env", f"{k}={v}")]
        if ws is None:
            out = json.loads(L.run(self.root, ["workspace", "create", "--cwd", real, "--label", WORKSPACE_LABEL, "--no-focus", *env]))["result"]
        else:
            out = json.loads(L.run(self.root, ["tab", "create", "--workspace", ws["workspace_id"], "--cwd", real, "--label", name[:40], "--no-focus", *env]))["result"]
        pane = out["root_pane"]
        pane_id = pane["pane_id"]
        native_id = resume_id
        tokens = []
        if agent == "command" or ad is not None:
            self._wait_prompt(pane_id)
        if agent == "command":
            L.run(self.root, ["pane", "run", pane_id, *shlex.split(command)])
            tokens = [os.path.basename(shlex.split(command)[-1])]
        elif ad is not None:
            native_id = native_id or sid
            argv = ad.resume(resume_id, spec) if resume_id else ad.launch(spec)
            if ad.herdr_kind:                                  # herdr knows this agent kind and runs its binary itself
                L.run(self.root, ["agent", "start", name[:40], "--kind", ad.herdr_kind, "--pane", pane_id, "--", *argv[1:]], timeout=120)
            else:                                              # [UNVERIFIED] whether herdr's agent start knows more kinds: typed into the pane's shell
                L.run(self.root, ["pane", "run", pane_id, *argv])
            tokens = [ad.binary]
        rec = {"id": rid, "name": name, "agent": agent, "cwd": real, "task": task, "effort": effort, "bypass": bool(bypass), "pane_id": pane_id,
               "terminal_id": pane.get("terminal_id"), "workspace_id": pane.get("workspace_id"), "tab_id": pane.get("tab_id"), "native_id": native_id, "command": command, "match": tokens,
               "state": "live", "adopted": True, "agent_sends": False, "created_at": time.time(), "updated_at": time.time(), "ended_at": None, "end_reason": "", "created_by": by,
               "api_key": bool(api_key), "harness": ad.id if ad is not None else None, "scene_session_id": scene, "project_root": pr, "mcp_config_path": cfg}
        self._update(lambda d: d["sessions"].append(rec))
        return rec

    # ------------------------------------------------------------------------------------------------- binding (spec B2)
    def bind(self, sid: str, scene_session_id) -> dict:
        """Bind a harness pane to a scene tab, or unbind it (None). Only the pane's own config file under the Lampway root changes:
        the pane itself is never touched (law 5). A running harness reads the new binding when it next starts its Lampway server
        (a resume does); the record says which tab the pane belongs to from now on."""
        rec = self._get(sid)
        ad = HN.ADAPTERS.get(rec.get("agent"))
        if ad is None:
            raise CockpitError("only a harness pane can be bound to a scene tab: a shell or a command has no Lampway tools")
        scene = scene_session_id or None
        cfg = rec.get("mcp_config_path") or str(self.root / "panes" / sid / ad.config_name)
        spec = HN.PaneSpec(cwd=rec.get("cwd") or "", project_root=rec.get("project_root"), scene_session_id=scene, mcp_config_path=cfg, launcher=HN.mcp_launcher())
        self._write_pane_files(ad.lampway_tools(spec).files)

        def f(d):
            for s in d["sessions"]:
                if s["id"] == sid:
                    s.update(scene_session_id=scene, mcp_config_path=cfg, harness=ad.id, updated_at=time.time())
                    return dict(s)
        return self._update(f)

    def unbind(self, sid: str) -> dict:
        """What closing the scene tab calls: the binding ends, the pane runs on and is listed unbound (law 5)."""
        return self.bind(sid, None)

    def find_by_scene(self, scene_session_id: str) -> list:
        """The panes bound to a scene tab, live or ended (an ended one keeps its native id for a resume): what reopening a .blend offers."""
        return [s for s in self.list_sessions() if scene_session_id and s.get("scene_session_id") == scene_session_id]

    def _write_pane_files(self, files: dict) -> None:
        """A pane's own files, 0600 in a 0700 directory, only under the Lampway root (never the user's own config, never the project)."""
        root = os.path.realpath(self.root)
        for path, text in files.items():
            real = os.path.realpath(path)
            if not real.startswith(root + os.sep):
                raise CockpitError(f"refusing to write {path}: a pane's files live under the Lampway root")
            d = Path(real).parent
            d.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(d, 0o700)
            tmp = d / f".{Path(real).name}.tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, real)

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
