# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Choices: what Lampway uses for each thing (specs/choices/CHOICES.md). Connections answers WHO Lampway can use; Choices answers WHAT
it uses for each purpose, what that falls back to, and why a job was served the way it was.

The consumer interface:

    r = choices.resolve("image.plates", choices.Job(content_class="private", needs={"runs_on": ["openrouter"]}))
    r.option, r.params, r.reason, r.why      # the option, its params, preferred | fallback | override, and why
    r.record()                                # the dict a job receipt carries
    r.egress_context()                        # what egress.context gets, so the transport and the choice agree

``NoChoice`` is raised (with ``needs_choice``) when nothing can serve the job; nothing has been sent."""

import json
import os
from pathlib import Path
from typing import Optional

from . import bridge as BR
from . import registry as REG
from . import views as V
from .resolver import Job, NoChoice, Resolution, resolve as _resolve
from .store import FileStore, MemoryStore, Refused

__all__ = ["Job", "NoChoice", "Resolution", "Refused", "active_store", "document", "list_view", "purpose_view", "resolve", "set_active"]

_STORE = None
_STATE: Optional[Path] = None
WORLD_FACTORY = None                       # tests or the app may set a callable returning a World; default: the live world


def set_active(store, state_dir) -> None:
    global _STORE, _STATE
    _STORE, _STATE = store, (Path(state_dir) if state_dir else None)


def _state_dir() -> Path:
    if _STATE is not None:
        return _STATE
    from ..config import _default_state_dir
    return Path(os.environ.get("LAMPWAY_STATE_DIR") or _default_state_dir())


def active_store():
    global _STORE
    if _STORE is None:
        _STORE = FileStore(_state_dir())
    return _STORE


def document(project: Optional[str] = None, env=None) -> dict:
    """The resolver's input: the shipped defaults, the global scope (the Providers dialog's saved values under the user's Choices),
    the project's scope, the environment's session layer, the acknowledgements and the document's version."""
    store = active_store()
    g = store.global_doc()
    glob = dict(BR.providers_scope(_state_dir()))
    glob.update(g.get("purposes") or {})
    out = {"shipped": BR.shipped(), "global": glob, "project": dict(store.project_doc(project).get("purposes") or {}),
           "env": BR.env_scope(env), "acknowledgements": dict(g.get("acknowledgements") or {})}
    import hashlib
    import json
    out["version"] = hashlib.sha256(json.dumps({k: out[k] for k in ("global", "project", "acknowledgements")}, sort_keys=True).encode()).hexdigest()[:8]
    if g.get("error"):
        out["error"] = g["error"]
    return out


def world():
    if WORLD_FACTORY is not None:
        return WORLD_FACTORY()
    from .snapshot import live_world
    return live_world()


def resolve(pid: str, job: Optional[Job] = None, *, world_=None, doc=None) -> Resolution:
    job = job or Job()
    return _resolve(pid, job, world_ or world(), doc or document(job.project))


def purpose_view(pid: str, job: Optional[Job] = None) -> dict:
    job = job or Job()
    return V.view(pid, job, world(), document(job.project), proposals=active_store().proposals(state="open"))


def list_view(job: Optional[Job] = None, group: Optional[str] = None) -> dict:
    job = job or Job()
    w, d = world(), document(job.project)
    groups = []
    for gid, label in REG.GROUPS:
        if group and gid != group:
            continue
        groups.append({"id": gid, "label": label, "purposes": [V.summary(p.id, job, w, d) for p in REG.PURPOSES.values() if p.group == gid]})
    return {"doc_version": d["version"], "catalogue_at": w.catalogue_at, "groups": groups, "proposals_open": len(active_store().proposals(state="open"))}


def preferred(pid: str, project: Optional[str] = None) -> Optional[str]:
    """The head of the chain in force for ``pid`` (what the user chose), with no world applied: what a catalogue marks as the default."""
    from .resolver import _in_force
    _, chain = _in_force(pid, document(project))
    return chain[0] if chain else None


def chain(pid: str, project: Optional[str] = None) -> list:
    from .resolver import _in_force
    return _in_force(pid, document(project))[1]


_ROLE_PROVIDER = {"anthropic": "anthropic:{model}", "openrouter": "openrouter:{model}", "chatgpt_plan": "chatgpt_plan:{model}", "openai": "openai:local",
                  "mock": "mock"}


def propose_dead_preferences(preferences: dict) -> list:
    """choices_migration.md step 2: the Mixar client's per-role model preferences were stored and never applied (HC22); each becomes ONE
    proposal the user accepts or declines - applying it silently would change what runs."""
    made = []
    store = active_store()
    seen = {(p["purpose"], json.dumps(p["change"], sort_keys=True)) for p in store.proposals() if p["origin"] == "migration"}
    for role, pick in sorted((preferences or {}).items()):
        fmt = _ROLE_PROVIDER.get(str((pick or {}).get("provider") or ""))
        if not fmt:
            continue
        pid = "agent.main" if role in ("default", "main") else "agent.worker"
        change = {"preferred": fmt.format(model=pick.get("model") or "")}
        if (pid, json.dumps(change, sort_keys=True)) in seen or not REG.offers(REG.get(pid), change["preferred"]):
            continue
        try:
            made.append(store.propose("migration", pid, change, f"the client's model picker saved this model for the {role} role; Lampway never applied it", []))
        except Refused:
            continue
    return made


def passing(pid: str, job: Optional[Job] = None, world_=None, doc=None) -> list:
    """Every option of the chain in force that passes all seven constraints, in the user's order (for a caller that tries them in turn)."""
    from .resolver import _check, _in_force
    job = job or Job()
    w, d = world_ or world(), doc or document(job.project)
    purpose = REG.get(pid)
    return [o for o in _in_force(pid, d)[1] if _check(purpose, o, job, w, d) is None]


def resolve_params(pid: str, project: Optional[str] = None) -> dict:
    """The params in force for ``pid`` (per key, most specific scope first), with no world applied."""
    from .resolver import _params
    return _params(pid, document(project))


def option_param(oid: str, key: str, project: Optional[str] = None):
    """A param a purpose sets for one of its options (``meshy.ai_model``), from the first purpose that offers ``oid`` and sets ``key``."""
    for p in REG.PURPOSES.values():
        if oid in p.options:
            value = resolve_params(p.id, project).get(key)
            if value not in (None, ""):
                return value
    return None


def import_quality(source: str, path: str, by: str) -> int:
    """The user's import of measured quality (choices_store.md 4.1): ``bakeoff`` reads the 2026-10-05 image bake-off's results.json
    (``{model: {status, cost, s, file}}``) into cost_usd and seconds for image.plates. The file must be inside the project root."""
    from .store import Refused
    if by != "user":
        raise Refused("only your click in Choices can change a choice: an agent may propose one", 403)
    if source != "bakeoff":
        raise Refused("source is bakeoff")
    from ..agent.server_tools import project_root
    real, root = Path(os.path.realpath(path if os.path.isabs(path) else project_root() / path)), Path(os.path.realpath(project_root()))
    if root not in real.parents or not real.is_file():
        raise Refused(f"{path} must be a file inside the project root ({root})")
    try:
        data = json.loads(real.read_text())
    except ValueError:
        raise Refused(f"{real.name} is not JSON") from None
    import time as _t
    when = _t.strftime("%Y-%m-%d", _t.gmtime(real.stat().st_mtime))
    records = []
    for model, row in sorted((data or {}).items()):
        if not isinstance(row, dict) or row.get("status") != 200:
            continue
        for metric, key in (("cost_usd", "cost"), ("seconds", "s")):
            if isinstance(row.get(key), (int, float)):
                records.append({"purpose": "image.plates", "option": f"openrouter:{model}", "metric": metric, "value": row[key], "n": 1,
                                "source": f"bakeoff:{real.name}", "measured_at": when})
    return active_store().add_quality(records, by)
