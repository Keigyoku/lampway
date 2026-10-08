"""The cockpit's session host: a durable registry of the agent sessions Lampway created in ITS OWN herdr server, and a reconcile that treats the live server as the truth (see the package
docstring for the invariants). Every herdr call goes through launcher.run; nothing here spawns a process or stops anything implicitly.

Where a pane goes is the herdr view of agent-modes spec A4 (``layout.py``): a unit's main agent in a tab of its own, its swarm
workers split into that tab, an ad-hoc pane in a tab of its own. Each record names its ``unit`` and ``role``, so a reconcile after a
restart re-adopts the layout."""
import contextlib
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shlex
import threading
import time
import uuid
from pathlib import Path

from .. import egress as EG
from . import harnesses as HN
from . import launcher as L
from . import layout as LY

log = logging.getLogger("lampway.herdr")

#: Every harness adapter (spec B1), then Lampway's two plain kinds: a shell, and a command the user typed.
AGENTS = (*HN.ids(), "shell", "command")
EFFORTS = (None, "medium", "high", "xhigh", "max")
GENERIC_NAMES = {"session", "new session", "untitled", "chat", "agent"}
WORKSPACE_LABEL = LY.WORKSPACE_LABEL
USER_TYPING_GRACE_S = 2.5
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|\x1b\[[0-9;?]*[ -/]*[@-~]")
_LOCK = threading.Lock()
#: Spec S3. A bound pane's swarm entry (the swarm tools, on Lampway's own loopback endpoint with the pane's key as its bearer),
#: and the variables a harness whose entries are on its command line reads the bearer from.
SWARM_ENTRY = "lampway_swarm"
PANE_KEY_ENV = "LAMPWAY_PANE_KEY"
WORKER_TOKEN_ENV = "LAMPWAY_WORKER_TOKEN"
PANE_KEY_FILE = "pane.key"
#: Spec A1: what Lampway's own pane's record keeps beyond any pane's (its home, its serve's port, the 0600 file the serve token is in,
#: the stored session id, and the digests the restarted server adopts its tokens again by). Never a token.
MODE1_FIELDS = ("home", "port", "token_file", "stored_session_id", "gateway_token_sha256", "mcp_token_sha256")


#: The island's images into a pane (spec B4): how many go with one message, and how large each may be.
MAX_PANE_IMAGES = 8
MAX_PANE_IMAGE_BYTES = 20 << 20


def image_kind(data: bytes):
    """The file type from the bytes themselves (never a client's name or type): png, jpg, gif, webp, or None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def agent_name(rid: str) -> str:
    """The name ``agent start`` gives a harness pane's agent: herdr 0.9.3 takes only ``[a-z][a-z0-9_-]{0,31}``, unique among live
    agents (src/app/agents.rs ``valid_agent_name``; a session's display name such as "Chest fit audit" is refused,
    ``invalid_agent_name``, measured on the real server). The record's id is unique and short."""
    return f"lw-{rid}"[:32]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        #: Lampway's own loopback MCP endpoint for panes (``/api/v1/mcp/pane``), set by the server (spec S3). None: no swarm entry
        #: is written for a bound pane and no worker pane can be opened.
        self.pane_mcp_url = None
        #: Spec A4: one placement at a time (a swarm opens its workers' panes at once), and the panes opened but not yet recorded,
        #: so the next worker finds the one before it in its unit's column.
        self._layout = threading.Lock()
        self._opening: dict = {}
        #: Spec A1: Lampway's own Mode 1 panes (``lampway_hermes``) are prepared by the server's engine (``engine/units.py``):
        #: ``prepare(**)`` writes the pane's home before herdr is asked and returns the record's fields; ``opened(rec)`` hears
        #: of the recorded pane; ``abandon(prepared)`` undoes a prepare whose pane never opened. None: no Mode 1 pane can start.
        self.mode1 = None

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
    def create_session(self, agent, name, cwd, task="", effort=None, bypass=False, resume_id=None, command=None, by="user", project_root=None, api_key=False, scene_session_id=None,
                       prompt=None, swarm_worker=None, unit=None, unit_label=None, display_agent=None,
                       planned=None) -> dict:
        """``prompt``: the new session's first prompt, on the harness's own command line (spec S3). ``swarm_worker``: (binding, token)
        for a swarm's worker pane: its only Lampway server is the pane endpoint, reached with that token as its bearer and pinned to
        ``swarm:<swarm_id>:<worker_id>``; it gets no desktop launcher (whose UI and scene-tab tools reach the user's scene).
        The herdr view (spec A4): a pane bound to a scene tab is its unit's main agent (the unit is that scene session; ``unit_label``
        the scene tab's name, if known); a worker pane names its ``unit`` (its swarm's scene session) and splits into that unit's
        tab; ``display_agent`` is what herdr's sidebar shows for it.
        Lampway's own pane (``lampway_hermes``, spec A1) is a unit's main agent when it names its ``unit`` (never bound to a scene
        tab: a binding is Mode 2's), or a Mode 1 swarm worker; the engine prepares its home first (``self.mode1``)."""
        lampway = HN.is_lampway(agent)
        if lampway:                                            # Lampway's own (Mode 1, spec A1): only on a server running the engine
            if self.mode1 is None:
                raise CockpitError(HN.MODE1_UNAVAILABLE)
            if scene_session_id:
                raise CockpitError("Lampway's own pane is its unit's main agent by its unit, never bound to a scene tab (binding is Your agent mode)")
        elif agent not in AGENTS:
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
        ad = HN.ADAPTERS.get(agent) or HN.LAMPWAY_ADAPTERS.get(agent)
        if scene_session_id and ad is None:
            raise CockpitError("only a harness pane can be bound to a scene tab")
        if prompt and (ad is None or resume_id):
            raise CockpitError("only a new harness session takes a first prompt")
        if prompt and not lampway:                             # Lampway's pane takes its task from the server, not its argv (S2)
            try:
                ad.launch(HN.PaneSpec(cwd=real), task=prompt)
            except ValueError as exc:
                raise CockpitError(str(exc)) from None
        if swarm_worker is not None:
            if by != "swarm":
                raise CockpitError("only a swarm opens a worker pane")
            if ad is None or not ad.direct_ok or not getattr(ad, "worker_ok", True):
                note = getattr(ad, "worker_note", "") if ad is not None else ""
                raise CockpitError(note or f"{agent} cannot run a swarm worker yet: no recorded way to point it at Lampway's own endpoint")
            if not self.pane_mcp_url:
                raise CockpitError("the server's pane endpoint is not known here: no worker pane can be opened")
            if scene_session_id:
                raise CockpitError("a worker pane is bound to its worker, never to a scene tab")
        scene = scene_session_id or None
        main_unit = (unit or None) if lampway and swarm_worker is None else None
        role = LY.WORKER if swarm_worker is not None else (LY.MAIN if scene or main_unit else None)
        view = (role, (unit or None) if swarm_worker is not None else (main_unit or scene), unit_label, display_agent,
                (swarm_worker[0] if swarm_worker is not None else None, planned))
        # B5: a user's harness is logged before herdr is asked and refused with its route off. Lampway's own pane has no route
        # (route None): its model traffic is the gateway's on loopback and every other host goes through the egress proxy (A1).
        with (EG.guard(ad.route, kind="request") if ad is not None and ad.route else contextlib.nullcontext()):
            return self._create(agent, ad, name, real, pr, task, effort, bypass, resume_id, command, by, api_key, scene, prompt, swarm_worker, view)

    def _open(self, where, snap, real, env, label) -> dict:
        """Make the pane where ``layout.place`` put it. A herdr that cannot split (an older one, or a spelling it does not know:
        [UNVERIFIED]) still gets the pane, in a tab of its own; the failure is logged."""
        ws = next((w for w in snap["workspaces"] if w.get("label") == WORKSPACE_LABEL), None)
        if where.verb == "workspace":
            return LY.created_pane(L.run(self.root, LY.workspace_create(real, env)))
        if where.verb == "split":
            try:
                pane = LY.created_pane(L.run(self.root, LY.pane_split(where.of, where.direction, where.ratio, real, env)))
            except L.HerdrError as exc:
                log.warning("herdr could not split pane %s (%s): the new pane opens in a tab of its own", where.of, exc)
            else:
                if not pane.get("tab_id"):                     # [UNVERIFIED] whether a split's answer names its tab: it is the split pane's
                    pane["tab_id"] = next((p.get("tab_id") for p in snap["panes"] if p["pane_id"] == where.of), None)
                return pane
        return LY.created_pane(L.run(self.root, LY.tab_create(ws["workspace_id"], real, label, env)))

    def _report(self, pane_id: str, meta: dict) -> None:
        """Tell herdr what the pane is (spec A4). Best effort: a failure is logged and never fails the start."""
        try:
            L.run(self.root, LY.pane_report_metadata(pane_id, meta), timeout=10)
        except Exception as exc:  # noqa: BLE001 - an older herdr, a spelling it does not know ([UNVERIFIED]), a timeout
            log.warning("herdr did not take pane %s's metadata (%s): the pane runs on without it", pane_id, exc)

    def _create(self, agent, ad, name, real, pr, task, effort, bypass, resume_id, command, by, api_key, scene, prompt=None, swarm_worker=None,
                view=(None, None, None, None, (None, None))) -> dict:
        if api_key and ad is None:
            raise CockpitError("only a harness pane can be billed to an API key")
        rid = uuid.uuid4().hex[:12]
        lampway = ad is not None and HN.is_lampway(ad.id)
        sid = str(uuid.uuid4()) if ad is not None and ad.picks_session_id and not resume_id else None
        cfg = str(self.root / "panes" / rid / ad.config_name) if ad is not None and not lampway and (
            scene or swarm_worker or getattr(ad, "always_pane_config", False)) else None
        direct, key = (), None
        if swarm_worker is not None:                           # S3: the worker's only server; its token never in the registry
            direct = (HN.DirectServer(HN.SERVER_NAME, self.pane_mcp_url, {HN.SESSION_HEADER: swarm_worker[0]}, WORKER_TOKEN_ENV, swarm_worker[1]),)
        elif cfg:
            direct, key = self._swarm_entry(ad, rid)
        role, unit, unit_label, display_agent, (binding, planned) = view
        prepared = None
        if lampway:                                            # A1: the pane's home, config and serve token, before herdr is asked
            prepared = self.mode1.prepare(rid=rid, unit=unit, role=role, cwd=real, project_root=pr, direct=direct,
                                          task=prompt, name=name, unit_label=unit_label)
        spec = HN.PaneSpec(cwd=real, project_root=pr, effort=effort, bypass=bool(bypass), session_id=sid, scene_session_id=scene, mcp_config_path=cfg,
                           launcher=HN.mcp_launcher() if cfg and swarm_worker is None else (), desktop=swarm_worker is None, direct=direct,
                           home=(prepared or {}).get("home"))
        wiring = ad.lampway_tools(spec) if cfg else None
        if wiring is not None:                                 # B2: the pane's own MCP config, pinned to its scene tab, before anything starts
            self._write_pane_files(wiring.files)
        env = L.pane_env() + (_key_env(ad) if api_key else []) + [x for k, v in (wiring.env if wiring else {}).items() for x in ("--env", f"{k}={v}")]
        try:
            with self._layout:
                snap = self.snapshot()
                sessions = self.list_sessions() + list(self._opening.values())
                ulabel = LY.unit_label(unit, unit_label or (LY.unit_main(unit, sessions, snap) or {}).get("unit_label")) if unit else None
                label = ulabel if unit else name[:LY.LABEL_MAX]
                pane = self._open(LY.place(role, unit, label, sessions, snap, swarm=LY.swarm_of(binding), planned=planned), snap, real, env,
                                  label)
                pane_id, opened = pane["pane_id"], time.time()
                self._opening[pane_id] = {"pane_id": pane_id, "tab_id": pane.get("tab_id"), "unit": unit, "role": role, "unit_label": ulabel,
                                          "swarm_binding": binding, "state": "live", "created_at": opened}
        except BaseException:
            if prepared is not None:
                self.mode1.abandon(prepared)
            raise
        try:
            native_id = resume_id
            tokens = []
            if agent == "command" or ad is not None:
                self._wait_prompt(pane_id)
            if agent == "command":
                L.run(self.root, ["pane", "run", pane_id, *shlex.split(command)])
                tokens = [os.path.basename(shlex.split(command)[-1])]
            elif ad is not None:
                native_id = native_id or sid
                argv = ad.resume(resume_id, spec) if resume_id else ad.launch(spec, task=None if lampway else prompt)
                if ad.herdr_kind:                                  # herdr knows this agent kind and runs its binary itself
                    L.run(self.root, ["agent", "start", agent_name(rid), "--kind", ad.herdr_kind, "--pane", pane_id, "--", *argv[1:]], timeout=120)
                else:                                              # [UNVERIFIED] whether herdr's agent start knows more kinds: typed into the pane's shell
                    # one shell-quoted command: herdr 0.9.3's `pane run` joins its arguments with spaces, unquoted (measured 2026-10-07)
                    L.run(self.root, ["pane", "run", pane_id, shlex.join(argv)])
                tokens = [ad.process_match or ad.binary]
            self._report(pane_id, LY.metadata(ad.id if ad is not None else agent, role, unit_name=ulabel or "", name=name, task=task,
                                              display_agent=display_agent))
            rec = {"id": rid, "name": name, "agent": agent, "cwd": real, "task": task, "effort": effort, "bypass": bool(bypass), "pane_id": pane_id,
                   "terminal_id": pane.get("terminal_id"), "workspace_id": pane.get("workspace_id"), "tab_id": pane.get("tab_id"), "native_id": native_id, "command": command, "match": tokens,
                   "state": "live", "adopted": True, "agent_sends": False, "created_at": opened, "updated_at": time.time(), "ended_at": None, "end_reason": "", "created_by": by,
                   "api_key": bool(api_key), "harness": ad.id if ad is not None else None, "scene_session_id": scene, "project_root": pr, "mcp_config_path": cfg,
                   "swarm_binding": swarm_worker[0] if swarm_worker is not None else None, "pane_key_sha256": _sha(key) if key else None,
                   "unit": unit, "role": role, "unit_label": ulabel, **{k: v for k, v in (prepared or {}).items() if k in MODE1_FIELDS}}
            self._update(lambda d: d["sessions"].append(rec))
        except BaseException:
            if prepared is not None:
                self.mode1.abandon(prepared)
            raise
        finally:
            self._opening.pop(pane_id, None)
        if prepared is not None:
            self.mode1.opened(dict(rec))                           # A1: the server creates the pane's session (and a worker's first prompt)
        return rec

    def update_mode1(self, sid: str, **fields) -> dict:
        """Lampway's own pane's record: only its Mode 1 fields change (the stored session id once the server created or followed it,
        spec A1, Q15). Never another pane's record, never the pane."""
        bad = set(fields) - set(MODE1_FIELDS)
        if bad:
            raise CockpitError(f"only a Mode 1 pane's own fields change here, not {sorted(bad)}")

        def f(d):
            for s in d["sessions"]:
                if s["id"] == sid:
                    if not HN.is_lampway(s.get("agent")):
                        raise CockpitError(f"{sid} is not Lampway's own pane")
                    s.update(fields, updated_at=time.time())
                    return dict(s)
            raise CockpitError(f"{sid} is not a Lampway session")
        return self._update(f)

    # ------------------------------------------------------------------------------------------------- binding (spec B2)
    def bind(self, sid: str, scene_session_id, unit_label=None) -> dict:
        """Bind a harness pane to a scene tab, or unbind it (None). Only the pane's own config file under the Lampway root changes:
        the pane itself is never touched (law 5). A running harness reads the new binding when it next starts its Lampway server
        (a resume does); the record says which tab the pane belongs to from now on, and that it is that unit's main agent (spec
        A4: its swarm's workers split into its herdr tab; ``unit_label`` is the scene tab's name, if known). The pane is not moved:
        its herdr tab keeps the label it was opened with."""
        rec = self._get(sid)
        ad = HN.ADAPTERS.get(rec.get("agent"))
        if ad is None:
            raise CockpitError("only a harness pane can be bound to a scene tab: a shell or a command has no Lampway tools")
        if rec.get("swarm_binding"):
            raise CockpitError("a swarm worker's pane is bound to its worker: it cannot be bound to a scene tab")
        scene = scene_session_id or None
        cfg = rec.get("mcp_config_path") or str(self.root / "panes" / sid / ad.config_name)
        direct, key = self._swarm_entry(ad, sid)                # the pane keeps its key across bindings: the running harness holds it
        spec = HN.PaneSpec(cwd=rec.get("cwd") or "", project_root=rec.get("project_root"), scene_session_id=scene, mcp_config_path=cfg, launcher=HN.mcp_launcher(),
                           direct=direct)
        self._write_pane_files(ad.lampway_tools(spec).files)

        def f(d):
            for s in d["sessions"]:
                if s["id"] == sid:
                    s.update(scene_session_id=scene, mcp_config_path=cfg, harness=ad.id, updated_at=time.time(),     # A4: its unit's main agent
                             unit=scene, role=LY.MAIN if scene else None,
                             unit_label=(LY.unit_label(scene, unit_label or (s.get("unit_label") if s.get("unit") == scene else None))
                                         if scene else None))
                    if key:
                        s["pane_key_sha256"] = _sha(key)
                    return dict(s)
        return self._update(f)

    # ------------------------------------------------------------------------------------------------- the swarm's panes (spec S3)
    def _swarm_entry(self, ad, rid: str) -> tuple:
        """A bound pane's swarm entry and its key: Lampway's pane endpoint with the pane's own key as its bearer. The key lives only in
        the pane's own files (0600, under the Lampway root); the registry keeps its sha256. None when the endpoint is not known or the
        harness has no recorded way to reach it."""
        if not self.pane_mcp_url or ad is None or not ad.direct_ok:
            return (), None
        path = self.root / "panes" / rid / PANE_KEY_FILE
        try:
            key = path.read_text(encoding="utf-8").strip()
        except OSError:
            key = ""
        if not key:
            key = secrets.token_urlsafe(32)
            self._write_pane_files({str(path): key})
        return (HN.DirectServer(SWARM_ENTRY, self.pane_mcp_url, {}, PANE_KEY_ENV, key),), key

    def pane_for_key(self, key: str):
        """The live harness pane this key was minted for, or None: what proves an MCP call comes from a pane Lampway started."""
        if not key:
            return None
        digest = _sha(key)
        for s in self.list_sessions():
            known = s.get("pane_key_sha256") or ""
            if known and hmac.compare_digest(known, digest) and s.get("state") != "ended" and not s.get("swarm_binding"):
                return s
        return None

    def pane_alive(self, sid: str) -> tuple:
        """(alive, why not) for one session, judged like reconcile but without writing anything."""
        rec = self._get(sid)
        if rec.get("state") == "ended":
            return False, rec.get("end_reason") or "the session ended"
        snap = self.snapshot()
        pane = self._find_pane(rec, snap["panes"])
        if pane is None:
            return False, "its pane is gone from the server"
        why = self._agent_gone(rec, pane)
        return not why, why

    def end_swarm_pane(self, sid: str, binding: str, why: str, close: bool) -> None:
        """A swarm ends a worker pane it opened: closes it (cancel, timeout) or records that it exited. It refuses any pane it did
        not open (law 5): the record must be the swarm's, for exactly this worker."""
        rec = self._get(sid)
        if rec.get("created_by") != "swarm" or not binding or rec.get("swarm_binding") != binding:
            raise CockpitError(f"{sid} was not opened by the swarm for {binding}: the swarm never closes a pane it did not start")
        if close:
            if HN.is_lampway(rec.get("agent")) and self.mode1 is not None:
                self.mode1.forget(rec)                     # revoke before pane shutdown can race another model call
            try:
                L.run(self.root, ["pane", "close", rec["pane_id"]])
            except L.HerdrError:
                pass

        def f(d):
            for s in d["sessions"]:
                if s["id"] == sid and s.get("state") != "ended":
                    s.update(state="ended", ended_at=time.time(), end_reason=why, updated_at=time.time())
        self._update(f)

    def close_ended_workers(self, unit, live) -> list:
        """Spec A4, Q13 (built 2026-10-07): what a unit's next swarm calls before it splits its own workers. A finished worker's
        pane stays readable until then; now the previous runs' ENDED worker panes of this unit are closed, so the new run starts a
        fresh column right of the main pane. ``live(binding)`` is the swarm's own table: True while that worker's binding is live.

        A pane is closed only when ALL of these hold, each from Lampway's own record and herdr's live server:
        * its record says Lampway opened it as a swarm worker (``created_by`` swarm, ``role`` worker, a ``swarm_binding``) of THIS
          unit; never a main pane, another unit's pane, an ad-hoc pane, or a pane no record names (law 5);
        * herdr still shows that pane for the terminal the record names (a pane id herdr gave another terminal is unknown);
        * its worker has ENDED: the record is ended (the swarm ended it, or reconcile found its harness gone), or its binding is
          not live in this server (``lampway_worker_done`` finished it; a failure, cancel or timeout revoked it; a server restart
          dropped it, so the pane can no longer reach any scene), or herdr's process info shows its harness no longer runs.
          A pane herdr cannot inspect is not proof of an end: it stays.
        Returns ``[{id, name, pane_id, why}]`` for the panes closed; their records end with the reason. Serialized with the
        placements (one at a time), so a swarm opening workers at the same moment never splits a pane being closed."""
        if not unit or not L.server_status(self.root).get("running"):
            return []
        out = []
        with self._layout:
            snap = self.snapshot()
            by_term = {p.get("terminal_id"): p for p in snap.get("panes") or [] if p.get("terminal_id")}
            by_id = {p["pane_id"]: p for p in snap.get("panes") or []}
            for rec in self.list_sessions():
                binding = rec.get("swarm_binding")
                if rec.get("created_by") != "swarm" or rec.get("role") != LY.WORKER or rec.get("unit") != unit or not binding:
                    continue
                pane = by_term.get(rec["terminal_id"]) if rec.get("terminal_id") else by_id.get(rec.get("pane_id"))
                if pane is None:                                # already gone from herdr: nothing to close
                    continue
                why = self._worker_ended(rec, pane, binding, live)
                if not why:
                    continue
                try:
                    L.run(self.root, ["pane", "close", pane["pane_id"]])
                except L.HerdrError as exc:
                    log.warning("could not close the ended worker pane %s (%s): it stays", pane["pane_id"], exc)
                    continue
                self._closed_ended(rec["id"], why)
                if HN.is_lampway(rec.get("agent")) and self.mode1 is not None and hasattr(self.mode1, "forget"):
                    self.mode1.forget(rec)                  # a Mode 1 worker's gateway key ends with its pane
                out.append({"id": rec["id"], "name": rec.get("name"), "pane_id": pane["pane_id"], "why": why})
        return out

    def _worker_ended(self, rec: dict, pane: dict, binding: str, live) -> str:
        """Why a worker pane's worker has ended, or "" while it may still be working (see ``close_ended_workers``)."""
        if rec.get("state") == "ended":
            return rec.get("end_reason") or "its worker ended"
        if not live(binding):
            return "its worker finished (its binding is done or revoked, so the pane can no longer reach a scene)"
        try:
            info = json.loads(L.run(self.root, ["pane", "process-info", "--pane", pane["pane_id"]]))["result"]["process_info"]
        except (L.HerdrError, ValueError, KeyError, TypeError):
            return ""
        cmd = " ".join(p.get("cmdline", "") for p in info.get("foreground_processes", []))
        if rec.get("match") and not any(t in cmd for t in rec["match"]):
            return "its harness is no longer running (the pane is at a shell prompt)"
        return ""

    def _closed_ended(self, sid: str, why: str) -> None:
        def f(d):
            for s in d["sessions"]:
                if s["id"] == sid:
                    now = time.time()
                    if s.get("state") != "ended":
                        s.update(state="ended", ended_at=now)
                    s.update(end_reason=f"closed when its unit's next swarm started (Q13): {why}", closed_at=now, updated_at=now)
        self._update(f)

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

    def note_native_id(self, sid: str, native_id: str) -> None:
        """Record the harness's own session id once it is known (Codex names it in its rollout, spec B2): only an empty one is
        filled, only the record changes."""
        def f(d):
            for s in d["sessions"]:
                if s["id"] == sid and not s.get("native_id") and s.get("harness") in HN.ADAPTERS:
                    s.update(native_id=str(native_id), updated_at=time.time())
        self._update(f)

    def agent_status(self, sid: str) -> str:
        """herdr's own reading of the pane's agent (``pane get``: idle, working, blocked, done, unknown), for a harness whose session
        the island shows by its screen. Read only; "unknown" when herdr cannot say."""
        rec = self._get(sid)
        try:
            pane = json.loads(L.run(self.root, ["pane", "get", rec["pane_id"]], timeout=10))["result"]["pane"]
        except (L.HerdrError, ValueError, KeyError, TypeError):
            return "unknown"
        status = str(pane.get("agent_status") or "unknown")
        return status if status in ("idle", "working", "blocked", "done", "unknown") else "unknown"

    def write_pane_images(self, sid: str, images: list) -> list:
        """The island's images for one harness pane (agent-modes spec B4), written where the pane's harness can read them: a
        Lampway-owned directory inside the pane's project root, ``<project root>/.lampway/panes/<id>/images/`` (``.lampway`` is
        Lampway's own folder in a project), 0600 files in 0700 directories. Never outside the project root (the same jail as the
        tools, every path checked after symlinks are resolved), never a name or type the client chose: the bytes must be a PNG,
        JPEG, GIF or WebP image, and Lampway names the file. Ownership metadata retains each copy for 30 days; originals and
        unrecorded legacy files are untouched. Returns the absolute paths, in order."""
        rec = self._get(sid)
        pr = rec.get("project_root") or self.project_root
        if not pr:
            raise CockpitError("this pane has no project root, so there is nowhere inside the project to put the image: nothing was sent")
        if not images:
            return []
        if len(images) > MAX_PANE_IMAGES:
            raise CockpitError(f"at most {MAX_PANE_IMAGES} images go with one message")
        for data in images:                                        # every image is checked before anything is written
            if image_kind(data) is None:
                raise CockpitError("an attachment is not a PNG, JPEG, GIF or WebP image: nothing was sent")
            if len(data) > MAX_PANE_IMAGE_BYTES:
                raise CockpitError(f"an image is larger than {MAX_PANE_IMAGE_BYTES // (1 << 20)} MB: nothing was sent")
        root = os.path.realpath(pr)
        target = Path(root) / ".lampway" / "panes" / rec["id"] / "images"
        for d in (Path(root) / ".lampway", Path(root) / ".lampway" / "panes", Path(root) / ".lampway" / "panes" / rec["id"], target):
            d.mkdir(mode=0o700, exist_ok=True)
            real = os.path.realpath(d)
            if not real.startswith(root + os.sep):
                raise CockpitError(f"refusing to write images through {d}: it leads outside the project root")
        os.chmod(target, 0o700)
        from .image_copies import ImageCopies
        copies = ImageCopies(self.root)
        copies.expire(sid, root, time.time())
        out = []
        for data in images:
            path = target / f"image-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(4)}.{image_kind(data)}"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            real = os.path.realpath(path)
            if not real.startswith(root + os.sep):                      # cannot happen after the checks above; never trusted
                os.unlink(path)
                raise CockpitError("refusing an image path outside the project root")
            out.append(real)
        copies.remember(sid, root, out, time.time())
        return out

    def expire_pane_images(self) -> list:
        """30-day retention for metadata-owned copies only; originals and unrecorded legacy files stay untouched."""
        from .image_copies import ImageCopies
        return ImageCopies(self.root).expire_all(time.time())

    def resume_bound(self, sid: str, scene_session_id: str, unit_label=None) -> dict:
        """The user's Resume of an ended harness pane bound to a scene tab (agent-modes spec B2; law 5: only the user's click, never
        automatic). A new pane runs the adapter's resume with the stored native session id, bound to the same tab; the ended record
        stays in the registry, unbound, so the tab has one pane. The harness's route and the BYOA switch are checked as for any
        start (``create_session``)."""
        rec = self._get(sid)
        ad = HN.ADAPTERS.get(rec.get("harness") or rec.get("agent"))
        if ad is None:
            raise CockpitError("only a harness pane can be resumed")
        if rec.get("state") == "live":
            raise CockpitError("this pane is still running: nothing to resume")
        if not rec.get("native_id"):
            raise CockpitError(f"no {ad.label} session id was recorded for this pane, so it cannot be resumed: start a new one")
        name = rec.get("name") or f"{ad.label} for a scene tab"
        new = self.create_session(ad.id, name, rec.get("cwd") or self.project_root or ".", resume_id=rec["native_id"], by="user",
                                  project_root=rec.get("project_root"), scene_session_id=scene_session_id, unit_label=unit_label,
                                  effort=rec.get("effort"))
        self.unbind(sid)
        return new

    def interrupt(self, sid: str) -> list:
        """Interrupt a live session's running turn (the cockpit's interrupt and the island's Stop: a user request or the user's
        click; the callers decide who may). A harness pane gets its adapter's own keys (``interrupt_keys``); anything else one
        Ctrl+C. Spelled as herdr 0.9.3 takes them (``ctrl+c``; ``ctrl-c`` is refused). Returns the keys sent."""
        rec = self._get(sid)
        if rec["state"] != "live":
            raise CockpitError("the session is not running")
        ad = HN.ADAPTERS.get(rec.get("harness") or rec.get("agent"))
        keys = list(ad.interrupt_keys) if ad is not None else ["ctrl+c"]
        if not keys:
            raise CockpitError(f"no way to interrupt {ad.label} is recorded: stop it in its own pane")
        L.run(self.root, ["pane", "send-keys", rec["pane_id"], *keys])
        return keys

    def close_session(self, sid: str, confirmed=False) -> dict:
        if not confirmed:
            raise CockpitError("closing a session is an explicit user action: confirm it (its agent process ends; its history stays)")
        rec = self._get(sid)
        if HN.is_lampway(rec.get("agent")) and self.mode1 is not None:
            self.mode1.forget(rec)                         # revoke before pane shutdown can race another model call
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
    @staticmethod
    def _find_pane(rec, snap_panes):
        by_term = {p.get("terminal_id"): p for p in snap_panes if p.get("terminal_id")}
        return by_term.get(rec.get("terminal_id")) or next((p for p in snap_panes if p["pane_id"] == rec["pane_id"]), None)

    def _agent_gone(self, rec, pane) -> str:
        """Why the session's agent is not running in its pane, or "" while it is."""
        try:
            info = json.loads(L.run(self.root, ["pane", "process-info", "--pane", pane["pane_id"]]))["result"]["process_info"]
        except (L.HerdrError, ValueError):
            return "its pane could not be inspected"
        cmd = " ".join(p.get("cmdline", "") for p in info.get("foreground_processes", []))
        if rec.get("match") and not any(t in cmd for t in rec["match"]):
            return "the agent process is no longer running (the pane is at a shell prompt)"
        return ""

    def reconcile(self) -> dict:
        """The live server is the truth, the registry the map. Never spawns, never kills, idempotent. A re-adopted pane keeps its
        record's ``unit`` and ``role`` and takes herdr's current pane and tab ids, so the layout (spec A4) is re-adopted with it:
        ``units`` maps each unit with a live pane to its tab, its main panes and its workers, in the order they were opened."""
        self.expire_pane_images()  # retention runs even when herdr has stopped
        out = {"server": "running", "adopted": [], "ended": [], "unadopted": [], "new_panes": 0, "offered": [], "units": {}}
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
            why = self._agent_gone(rec, pane)
            return (None, why) if why else (pane, "")

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
                    changed = rec.get("pane_id") != pane["pane_id"] or (pane.get("tab_id") and rec.get("tab_id") != pane["tab_id"])
                    rec.update(pane_id=pane["pane_id"], terminal_id=pane.get("terminal_id"), adopted=True)
                    if pane.get("tab_id"):
                        rec["tab_id"] = pane["tab_id"]
                    if changed:
                        rec["updated_at"] = time.time()
                    out["adopted"].append(rec["id"])
            for rec in sorted((r for r in d["sessions"] if r["id"] in out["adopted"] and r.get("unit") and r.get("role")),
                              key=lambda r: r.get("created_at") or 0):
                u = out["units"].setdefault(rec["unit"], {"tab_id": None, "main": [], "workers": []})
                u["main" if rec["role"] == LY.MAIN else "workers"].append(rec["id"])
                if rec["role"] == LY.MAIN or u["tab_id"] is None:
                    u["tab_id"] = rec.get("tab_id")
        self._update(f)
        out["unadopted"] = [pid for pid in panes if pid not in claimed]
        out["new_panes"] = max(0, len(self.snapshot()["panes"]) - before)
        return out
