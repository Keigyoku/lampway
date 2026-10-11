# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The agent's view of Choices (specs/choices/choices_agent_tool.md): read what serves each purpose, explain what a job would run and why,
and PROPOSE a change for the user to accept. There is no set, clear, acknowledge or accept: an agent never changes a choice, and never
proposes its own provider. Every answer goes through one allow-list; the MCP server serves the same projection."""

import json

from .providers.base import ToolSpec

NAMES = {"lampway_choices"}
ACTIONS = ["list", "view", "explain", "propose", "proposals"]
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["action"], "properties": {
    "action": {"enum": ACTIONS},
    "purpose": {"type": "string", "description": "a purpose id (PURPOSES.md); view, explain and propose need it"},
    "group": {"type": "string", "description": "list: one group only"},
    "job": {"type": "object", "additionalProperties": False, "properties": {
        "content_class": {"enum": ["public", "synthetic", "private"]}, "needs": {"type": "object"},
        "override": {"type": "string", "description": "explain only: would this option be allowed as my per-job override?"}}},
    "preferred": {"type": "string"}, "fallbacks": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
    "params": {"type": "object"}, "reason": {"type": "string", "maxLength": 400},
    "evidence": {"type": "array", "items": {"type": "string"}, "maxItems": 10, "description": "ledger or receipt ids"}}}
_OPTION = ("id", "label", "provider", "model", "runs", "cost", "retention", "quality", "verdict", "skipped")
_VIEW = ("id", "label", "needs", "content_class", "params", "override_policy", "now")


def specs() -> list:
    return [ToolSpec("lampway_choices",
                     "What Lampway uses for each purpose (the main agent, plates, retopology, ...): `list` them, `view` one purpose's chain with each "
                     "option's connection state, route, cost and retention, `explain` what a job would run and why (and whether an override you have in "
                     "mind is allowed), and `propose` a change with a reason - the user accepts or declines it in Choices. You cannot set, clear or "
                     "acknowledge anything, and you never propose your own provider.", SCHEMA)]


def _option(o: dict) -> dict:
    out = {k: o[k] for k in _OPTION if k in o}
    out["connection"] = (o.get("connection") or {}).get("state") if o.get("connection") else None
    out["route_on"] = (o.get("route") or {}).get("on") if o.get("route") else None
    out["acknowledged"] = bool(o.get("acknowledged"))
    return out


def project_view(v: dict) -> dict:
    out = {k: v.get(k) for k in _VIEW}
    out["chain"] = [_option(o) for o in v.get("chain") or []]
    out["other_options"] = [_option(o) for o in v.get("other_options") or []]
    return out


def _answer(args: dict, origin: str) -> dict:
    from .. import choices as CH
    from ..choices import registry as REG
    from ..choices import views as V
    extra = set(args) - set(SCHEMA["properties"])
    if extra:
        raise ValueError(f"unknown field {sorted(extra)[0]!r}: there is none (the agent's project is the server's)")
    action = args.get("action")
    if action not in ACTIONS:
        raise ValueError(f"action is one of {', '.join(ACTIONS)}: there is no set, clear, acknowledge or accept")
    if action == "list":
        listing = CH.list_view(group=args.get("group"))
        return {"groups": [{"id": g["id"], "purposes": [{k: p.get(k) for k in ("id", "label", "now", "cue")} for p in g["purposes"]]} for g in listing["groups"]]}
    if action == "proposals":
        return {"proposals": [{k: p[k] for k in ("id", "purpose", "change", "reason", "state", "at")} for p in CH.active_store().proposals(origin=origin)]}
    pid = str(args.get("purpose") or "")
    REG.get(pid)
    job_raw = args.get("job") or {}
    if action == "view":
        return project_view(CH.purpose_view(pid, CH.Job(content_class=job_raw.get("content_class"))))
    if action == "explain":
        w, d = CH.world(), CH.document()
        job = CH.Job(content_class=job_raw.get("content_class"), needs=dict(job_raw.get("needs") or {}), origin="agent")
        out = {}
        try:
            r = CH.resolve(pid, job, world_=w, doc=d)
            rv = V.resolution_view(r, REG.get(pid), job, w, d)
            out = {k: rv[k] for k in ("purpose", "params", "scope", "reason", "why", "skipped", "needs_click", "content_class", "would_refuse_private")}
            out["option"] = _option(rv["option"])
        except CH.NoChoice as exc:
            out = {"purpose": pid, "refused": str(exc), "skipped": exc.skipped, "fix": exc.fix}
        if job_raw.get("override"):
            try:
                CH.resolve(pid, CH.Job(content_class=job.content_class, needs=job.needs, override=job_raw["override"], origin="agent"), world_=w, doc=d)
                out.update(override_allowed=True, override_reason="")
            except CH.NoChoice as exc:
                out.update(override_allowed=False, override_reason=str(exc))
        return out
    # propose
    if pid in ("agent.main", "agent.worker") and origin.startswith(("agent", "worker")):
        raise ValueError("an agent must not change its own provider: say what you would change and why, and the user decides")
    change = {k: args[k] for k in ("preferred", "fallbacks", "params") if k in args}
    if not change:
        raise ValueError("a proposal names the preferred option, the fallbacks or the params it would change")
    pid_ = CH.active_store().propose(origin, pid, change, str(args.get("reason") or ""), args.get("evidence") or [])
    return {"proposal": pid_, "state": "open", "note": "the user decides in Choices; nothing has changed"}


async def call(name: str, arguments: dict, origin: str = "agent:main") -> tuple:
    import asyncio
    from .. import choices as CH
    from ..choices import registry as REG
    try:
        return json.dumps(await asyncio.to_thread(_answer, arguments if isinstance(arguments, dict) else {}, origin), default=str), False
    except (ValueError, CH.Refused, CH.NoChoice, REG.UnknownPurpose) as exc:
        return str(exc) + "\nNext call: lampway_choices action=list", True
