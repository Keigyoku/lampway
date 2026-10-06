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
