# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Capabilities: one switchboard for what an agent can do in Lampway (docs/reports/agent-modes-spec.md E2).

Captain, 2026-10-06: "I want it all behind a single interface you can choose WHAT your agent can do. The user can choose like they
choose Routes." Nothing is removed from the harness; every ability is a row here, and the user switches it.

* The catalogue (``CATALOGUE``) is the spec's table: the engine's abilities, Lampway's own tool families and the user's MCP servers.
  ``messaging.*`` and ``mcp.*`` are families: ``get("messaging.telegram")`` is that family's row for one platform. Switching the
  family row is the default for every member with no setting of its own: ``setting`` reads, per scope (global, then project),
  the family and then the member, so a member's own choice wins over its family's in the same scope.
* State: ``<state_dir>/capabilities.json`` (0600) holds the user's choices, globally and per project (a project wins, as in
  Choices). Every change, refused change and refused use is a row in ``<state_dir>/capabilities/log.jsonl``.
* Only the user's click changes a capability (``by="user"``). An agent reads the board and proposes a change
  (``lampway_capabilities``); the proposal waits for the user, who accepts or declines it (``decide``). A project's own setting
  is dropped with ``clear``, back to the global value.
* Law 2 is unchanged: a capability that needs egress routes is in force only while each of its routes is on. A route that does
  not exist yet (``web_search``, ``msg:<platform>``) is off; ``web:any`` exists (spec E1.5, ``engine/proxy.py`` enforces both it and
  ``web.browse`` for the engine's network).
* Enforcement for Lampway's own tool families is ``check_tool``, at call time, for the in-app agent and for MCP clients alike.
"""

import json
import os
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Optional

RISKS = ("reads", "writes_project", "runs_code", "reaches_internet", "acts_outside", "spends_plan")
APPROVALS = ("none", "ask_each_time", "ask_once_per_session")
AGENT_WRITE = "only your click in Capabilities can change what an agent may do: an agent may propose a change"


class UnknownCapability(KeyError):
    pass


class Refused(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Capability:
    id: str
    label: str
    does: str                  # one plain sentence: what the agent can do with it
    risk: str
    hermes: tuple = ()         # the engine's toolsets or settings it turns on (spec E1.3)
    lampway: tuple = ()        # Lampway tool families it turns on
    routes: tuple = ()         # egress routes it needs (law 2)
    approval: str = "none"     # the default approval
    options: tuple = ()        # e.g. the terminal backends
    default: bool = False      # the captain's default (Q8)


C = Capability
CATALOGUE = (
    C("scene.read", "See the scene as data", "Inspect the scene, read summaries and renders.", "reads", lampway=("scene.read",), default=True),
    C("scene.edit", "Change the scene", "Use Lampway's tools and run Python in Lampway's sandbox on the open scene.", "writes_project",
      lampway=("scene.edit",), default=True),
    C("ui.control", "See and use Lampway's interface", "Take screenshots of Lampway and click and type in it.", "writes_project",
      lampway=("ui.control",)),
    C("files.project", "Read and write files in the project folder", "Read and write files inside the project folder.", "writes_project",
      hermes=("file",)),
    C("terminal", "Run shell commands", "Run shell commands; with the local backend they run on this computer as you.", "runs_code",
      hermes=("terminal",), approval="ask_each_time", options=("local", "docker", "ssh", "modal")),
    C("code.execute", "Run code in a sandbox", "Run code in a sandbox.", "runs_code", hermes=("execute_code",)),
    C("web.search", "Search the web", "Search the web through a search provider.", "reaches_internet", hermes=("web",),
      routes=("web_search",)),
    C("web.browse", "Browse the web", "Open and read any web page; every host it reaches is logged.", "reaches_internet",
      hermes=("browser",), routes=("web:any",)),
    C("vision", "Look at images", "Look at images you attach and renders it makes.", "reads", hermes=("vision",), default=True),
    C("memory", "Remember things about me and this project", "Keep notes about you and this project between conversations.", "reads",
      hermes=("memory",)),
    C("history.search", "Search past conversations", "Search your past conversations with it.", "reads", hermes=("session_search",),
      default=True),
    C("skills.use", "Use installed skills", "Use the skills installed for it.", "reads", hermes=("skills",), default=True),
    C("skills.write", "Write and improve its own skills", "Write new skills and change its own skills.", "writes_project",
      hermes=("skill_manage", "curator")),
    C("subagents", "Start helper agents", "Start helper agents for parts of a task.", "runs_code", hermes=("delegate_task",)),
    C("swarm", "Run parallel Lampway workers", "Start up to six Lampway workers, each in its own headless Lampway.", "runs_code",
      lampway=("swarm",)),
    C("schedule", "Run tasks on a schedule", "Run tasks on a schedule while the server runs.", "runs_code", hermes=("cron",)),
    C("computer.use", "Control this computer's desktop", "Move the mouse, type and read the screen of this computer.", "acts_outside",
      hermes=("computer_use",), approval="ask_each_time"),
    C("messaging.*", "Talk to me on a messaging app", "Send and receive messages on a messaging platform.", "acts_outside",
      hermes=("gateway",), routes=("msg:*",)),
    C("mcp.*", "Use an MCP server I added", "Use the tools of an MCP server you added.", "reads", hermes=("mcp",)),
    C("studio.plan", "Plan and price paid generations", "Plan and price paid generations; only your click confirms one (law 3).",
      "spends_plan", lampway=("studio.plan",), default=True),
    C("panes.drive", "Type into my agent panes on Lampway's herdr server", "Type into, open, interrupt and close agent panes on "
      "Lampway's own herdr server.", "acts_outside", lampway=("panes.drive",)),
)
_BY_ID = {c.id: c for c in CATALOGUE}


def get(cid: str) -> Capability:
    """The row for ``cid``; a family member (``messaging.telegram``, ``mcp.github``) is its family's row with its own id."""
    if cid in _BY_ID:
        return _BY_ID[cid]
    family, _, member = str(cid).partition(".")
    row = _BY_ID.get(f"{family}.*")
    if row is None or not member or "*" in member:
        raise UnknownCapability(cid)
    return replace(row, id=cid, routes=tuple(r.replace("*", member) for r in row.routes))


# ---------------------------------------------------------------------------------------------------- Lampway's tool families
#: Tools no switch gates: the agent must always be able to read the board, propose and ask the user.
UNGATED = {"lampway_capabilities", "ask_user"}
#: Lampway tools that only read. Everything else that touches the scene is scene.edit.
READ_TOOLS = {"scene_summary", "lampway_choices", "lampway_connections", "lampway_credit_balance", "lampway_call_status"}
DRIVE_ACTIONS = {"send", "open", "interrupt", "close"}


def family_of(name: str, arguments: Optional[dict] = None) -> Optional[str]:
    """The capability a Lampway tool call belongs to, or None for a tool no switch gates."""
    from ..agent.studio_tools import NAMES as STUDIO
    from ..agent.swarm import SWARM_NAMES
    if name in UNGATED:
        return None
    if name in SWARM_NAMES:
        return "swarm"
    if name in STUDIO:
        return "studio.plan"
    if name == "lampway_workbench":
        action = (arguments or {}).get("action") if isinstance(arguments, dict) else None
        return "panes.drive" if action in DRIVE_ACTIONS else "scene.read"
    if name.startswith("ui_"):
        return "ui.control"
    if name in READ_TOOLS:
        return "scene.read"
    return "scene.edit"


# ---------------------------------------------------------------------------------------------------- the store
def _routes_on_default(route: str) -> bool:
    from .. import egress as EG
    return route in EG.ROUTES and EG.ACTIVE is not None and EG.ACTIVE.enabled(route)


class Store:
    def __init__(self, state_dir):
        self.state_dir = Path(state_dir)
        self._path = self.state_dir / "capabilities.json"
        self._log = self.state_dir / "capabilities" / "log.jsonl"
        self._lock = threading.Lock()

    # -- file
    def _doc(self) -> dict:
        from ..connections import files as CF
        try:
            doc = CF.read_json(self._path)
        except CF.Unreadable:
            doc = {}
        doc.setdefault("global", {})
        doc.setdefault("projects", {})
        doc.setdefault("proposals", [])
        return doc

    def _save(self, doc: dict) -> None:
        from ..connections import files as CF
        CF.ensure_dir(self.state_dir)
        CF.atomic_write_json(self._path, doc)

    def _append(self, row: dict) -> None:
        from ..connections import files as CF
        CF.ensure_dir(self._log.parent)
        fd = os.open(self._log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as fh:
            fh.write(json.dumps({"t": time.time(), **row}) + "\n")

    # -- reading
    def setting(self, cid: str, project: Optional[str] = None) -> dict:
        cap = get(cid)
        doc = self._doc()
        out = {"enabled": cap.default, "approval": cap.approval, "options": {}, "scope": "default"}
        family = f"{cid.partition('.')[0]}.*" if cid not in _BY_ID else None    # a member falls back to its family's switch
        for scope, layer in (("global", doc["global"]), ("project", doc["projects"].get(project or "", {}))):
            for key in ((family, cid) if family else (cid,)):                  # within a scope, the member's own beats the family
                if key in layer:
                    out.update({k: v for k, v in layer[key].items() if k in ("enabled", "approval", "options")}, scope=scope)
        return out

    def effective(self, cid: str, project: Optional[str] = None, routes_on: Optional[Callable] = None) -> tuple:
        """(in force, why not). Chosen on AND every route it needs on."""
        cap = get(cid)
        if not self.setting(cid, project)["enabled"]:
            return False, f"{cid} is off"
        routes_on = routes_on or _routes_on_default
        off = [r for r in cap.routes if not routes_on(r)]
        if off:
            return False, f"{cid} needs the route{'s' if len(off) > 1 else ''} {', '.join(off)}, which {'are' if len(off) > 1 else 'is'} off"
        return True, ""

    def view(self, project: Optional[str] = None, routes_on: Optional[Callable] = None) -> list:
        routes_on = routes_on or _routes_on_default
        rows = []
        for cap in CATALOGUE:
            s = self.setting(cap.id, project)
            on, why = self.effective(cap.id, project, routes_on)
            rows.append({"id": cap.id, "label": cap.label, "does": cap.does, "risk": cap.risk, "enabled": bool(s["enabled"]),
                         "in_force": on, "why_not": why, "approval": s["approval"], "options": list(cap.options),
                         "chosen_options": s["options"], "scope": s["scope"], "default": cap.default,
                         "routes": [{"id": r, "on": bool(routes_on(r))} for r in cap.routes]})
        return rows

    def proposals(self) -> list:
        return [p for p in self._doc()["proposals"] if p.get("state") == "open"]

    # -- writing (the user only)
    def set(self, cid: str, *, enabled: Optional[bool] = None, approval: Optional[str] = None, options: Optional[dict] = None,
            project: Optional[str] = None, by: str = "user") -> dict:
        get(cid)
        if by != "user":
            self._append({"id": cid, "event": "refused_change", "by": by})
            raise Refused(AGENT_WRITE, 403)
        if approval is not None and approval not in APPROVALS:
            raise Refused(f"approval is one of {', '.join(APPROVALS)}")
        with self._lock:
            doc = self._doc()
            layer = doc["projects"].setdefault(project, {}) if project else doc["global"]
            entry = layer.setdefault(cid, {})
            if enabled is not None:
                entry["enabled"] = bool(enabled)
            if approval is not None:
                entry["approval"] = approval
            if options is not None:
                entry["options"] = dict(options)
            self._save(doc)
        self._append({"id": cid, "event": "changed", "by": by, "project": project, "enabled": enabled, "approval": approval})
        return self.setting(cid, project)

    def propose(self, origin: str, cid: str, change: dict, reason: str) -> str:
        get(cid)
        pid = f"cap_{int(time.time() * 1000):x}"
        with self._lock:
            doc = self._doc()
            doc["proposals"].append({"pid": pid, "id": cid, "change": change, "reason": reason[:500], "origin": origin, "state": "open",
                                     "t": time.time()})
            self._save(doc)
        self._append({"id": cid, "event": "proposed", "by": origin, "pid": pid})
        return pid

    def decide(self, pid: str, action: str, *, project: Optional[str] = None, by: str = "user") -> dict:
        """The user's answer to an agent's proposal: ``accept`` applies its change (globally, or to ``project``) and marks it
        accepted; ``decline`` marks it declined. Either way it leaves the open list. Only the user decides, and only once."""
        if by != "user":
            self._append({"pid": pid, "event": "refused_decision", "by": by})
            raise Refused(AGENT_WRITE, 403)
        if action not in ("accept", "decline"):
            raise Refused("action is accept or decline")
        with self._lock:
            doc = self._doc()
            prop = next((p for p in doc["proposals"] if p.get("pid") == pid and p.get("state") == "open"), None)
            if prop is None:
                raise Refused(f"no open proposal {pid!r}", 404)
            change = prop.get("change") or {}
            if action == "accept":
                cid = prop["id"]
                get(cid)
                layer = doc["projects"].setdefault(project, {}) if project else doc["global"]
                entry = layer.setdefault(cid, {})
                for key in ("enabled", "approval", "options"):
                    if key in change:
                        if key == "approval" and change[key] not in APPROVALS:
                            raise Refused(f"approval is one of {', '.join(APPROVALS)}")
                        entry[key] = bool(change[key]) if key == "enabled" else change[key]
            prop.update(state="accepted" if action == "accept" else "declined", decided_t=time.time(), decided_project=project)
            self._save(doc)
        self._append({"id": prop["id"], "event": prop["state"], "by": by, "pid": pid, "project": project,
                      **({"enabled": change.get("enabled")} if action == "accept" and "enabled" in change else {})})
        return {k: prop[k] for k in ("pid", "id", "change", "reason", "state")}

    def clear(self, cid: str, project: Optional[str], *, by: str = "user") -> dict:
        """Drop ``project``'s own setting for ``cid``: the project goes back to the global value (or the default)."""
        get(cid)
        if by != "user":
            self._append({"id": cid, "event": "refused_change", "by": by})
            raise Refused(AGENT_WRITE, 403)
        if not project:
            raise Refused("clearing is per project: name the project whose override goes")
        with self._lock:
            doc = self._doc()
            layer = doc["projects"].get(project) or {}
            had = layer.pop(cid, None) is not None
            if not layer:
                doc["projects"].pop(project, None)
            self._save(doc)
        self._append({"id": cid, "event": "cleared", "by": by, "project": project, "had_override": had})
        return self.setting(cid, project)

    def note_refused_use(self, cid: str, tool: str, origin: str, why: str) -> None:
        self._append({"id": cid, "event": "refused_use", "by": origin, "tool": tool, "why": why})


ACTIVE: Optional[Store] = None


def set_active(store: Optional[Store]) -> None:
    global ACTIVE
    ACTIVE = store


def project() -> Optional[str]:
    return os.environ.get("LAMPWAY_PROJECT_ROOT") or None


def check_tool(name: str, arguments=None, origin: str = "agent") -> Optional[str]:
    """None when the call may run; otherwise the refusal text, which names the capability and the next step. Without an active
    board (an embedding that never set one) nothing is gated."""
    cid = family_of(name, arguments)
    if cid is None or ACTIVE is None:
        return None
    on, why = ACTIVE.effective(cid, project())
    if on:
        return None
    ACTIVE.note_refused_use(cid, name, origin, why)
    return (f"refused: {name} needs the capability {cid} ({get(cid).label}), and {why}. The user can switch it on in Choices and "
            f"privacy > Capabilities; you can propose it with lampway_capabilities action=propose id={cid}.")


def tool_offered(name: str) -> bool:
    """Whether a tool belongs in the agent's list: a family gated per action (the workbench) stays listed and is checked per call."""
    if name == "lampway_workbench":
        return True
    return check_tool_quiet(name)


def check_tool_quiet(name: str) -> bool:
    cid = family_of(name)
    if cid is None or ACTIVE is None:
        return True
    return ACTIVE.effective(cid, project())[0]
