# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What the routes and the agent tool show (choices_store.md 4.1): a purpose's summary and view, each option with its six facts (where it
runs, the connection's state word, the route, cost, retention, quality) and its verdict for the job described. No identity, balance,
credential, source path or variable value: a connection is its state word only (Connections' agent allow-list)."""

from . import registry as REG
from . import resolver as R


def option_view(purpose, oid: str, job, world, doc) -> dict:
    facts = REG.option_facts(oid)
    conn = facts["connection"] if not (facts["provider"] == "openai" and world.custom_llm_local) else None
    route = R._route(oid, world)
    failure = R._check(purpose, oid, job, world, doc)
    ack = ((doc.get("acknowledgements") or {}).get(oid) or {}).get("at")
    out = {"id": oid, "label": facts["model"] or oid.split(":", 1)[-1], "provider": facts["provider"], "model": facts["model"],
           "runs": "this machine" if R._retention(oid, world) == "local" and not route else facts["runs"],
           "connection": {"id": conn, "state": world.connections.get(conn, "missing")} if conn else None,
           "route": {"id": route, "on": bool(world.routes.get(route, False))} if route else None,
           "cost": world.costs.get(oid) or {"basis": "unknown"}, "retention": R._retention(oid, world), "acknowledged": ack,
           "quality": [], "verdict": "ok" if failure is None else "skipped"}
    if failure is not None:
        out["skipped"] = {"constraint": failure[0], "text": failure[1]}
    return out


def summary(pid: str, job, world, doc) -> dict:
    purpose = REG.get(pid)
    out = {"id": pid, "label": purpose.label, "group": purpose.group}
    try:
        r = R.resolve(pid, job, world, doc)
        out["now"] = {"option": r.option, "label": REG.option_facts(r.option)["model"] or r.option, "scope": r.scope, "reason": r.reason}
        out["cue"] = "override" if r.reason == "override" else r.reason
        if r.why:
            out["why"] = r.why
    except R.NoChoice as exc:
        out["now"] = None
        out["cue"] = "unset" if not exc.skipped else "blocked"
        out["why"] = str(exc)
    return out


def view(pid: str, job, world, doc, history=(), proposals=()) -> dict:
    purpose = REG.get(pid)
    out = summary(pid, job, world, doc)
    scope, chain = R._in_force(pid, doc)
    out.update(needs=purpose.needs, content_class=job.content_class or purpose.content_class, params=R._params(pid, doc),
               override_policy=R._policy(purpose, doc), note=purpose.note,
               chain=[dict(option_view(purpose, o, job, world, doc), rank=i) for i, o in enumerate(chain)],
               other_options=[option_view(purpose, o, job, world, doc) for o in REG.listed(purpose) if o not in chain],
               scopes={s: (doc.get(s) or {}).get(pid) for s in ("env", "project", "global", "shipped") if (doc.get(s) or {}).get(pid)},
               history=list(history)[-10:], proposals=list(proposals))
    env, mine = (doc.get("env") or {}).get(pid), (doc.get("project") or {}).get(pid) or (doc.get("global") or {}).get(pid)
    out["conflict"] = (f"this session: {env.get('source')} sets {env['preferred']}; your choice is {mine['preferred']}"
                       if env and mine and env.get("preferred") != mine.get("preferred") else None)
    return out


def resolution_view(r, purpose, job, world, doc) -> dict:
    return {"purpose": r.purpose, "option": option_view(purpose, r.option, job, world, doc) if REG.offers(purpose, r.option) else {"id": r.option},
            "params": r.params, "scope": r.scope, "reason": r.reason, "why": r.why, "skipped": r.skipped, "needs_click": r.needs_click,
            "content_class": r.content_class, "doc_version": r.doc_version, "would_refuse_private": r.would_refuse_private}
