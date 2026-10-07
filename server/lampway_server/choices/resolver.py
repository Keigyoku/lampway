# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The resolver (choices_store.md 6.3): ``resolve(purpose, job, world, doc)``, pure and total. The candidates are the job's override
when the purpose's policy allows it for the job's origin (CH3), else the chain of the most specific scope that sets one: the
environment (a session layer, CH4), the project, the global choice, the shipped default. Chains never merge across scopes; params
merge per key, most specific first. Each candidate meets seven constraints in order - exists, capability, privacy, connection, route,
spend, local readiness - and the first that fails is why it was skipped, with the fix. Nothing passes: ``NoChoice``, before anything
is sent.

``doc`` = ``{shipped, global, project, env: {purpose: {preferred, fallbacks, params, override_policy}}, acknowledgements: {option:
{private, at}}, version}``: the store builds it, a test writes it."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

from . import registry as REG

SCOPES = ("env", "project", "global", "shipped")                 # most specific first
PRIVATE_OK = ("local", "zdr", "ok", "conditional")
CLICK_PROVIDER = {"openrouter": "openrouter", "higgsfield": "higgsfield", "studio:hyper3d": "hyper3d"}


class NoChoice(Exception):
    """Nothing can serve the job; the text names every candidate's reason and the one fix that unblocks the preferred option first."""

    def __init__(self, text: str, purpose: str, skipped=(), fix: str = ""):
        super().__init__(text)
        self.needs_choice, self.skipped, self.fix = purpose, list(skipped), fix


@dataclass
class Job:
    content_class: Optional[str] = None                      # public | synthetic | private; None = the purpose's own class
    needs: dict = field(default_factory=dict)                # runs_on: [providers this consumer can run]; refs: n
    project: Optional[str] = None
    override: Optional[str] = None
    origin: str = "user"                                     # user | agent | worker | mcp
    avoid: tuple = ()


@dataclass
class Resolution:
    purpose: str
    option: str
    params: dict
    scope: str
    reason: str                                              # preferred | fallback | override
    why: str
    skipped: list
    needs_click: bool
    content_class: str
    doc_version: str
    world: dict
    would_refuse_private: bool = False
    followed: Optional[str] = None

    @property
    def provider(self) -> str:
        return REG.option_facts(self.option)["provider"]

    @property
    def model(self) -> Optional[str]:
        return REG.option_facts(self.option)["model"]

    def record(self, at: Optional[str] = None) -> dict:
        """The dict a job receipt carries (CHOICES.md 5.5): no identity, balance, key or path."""
        out = {"purpose": self.purpose, "option": self.option, "provider": self.provider, "model": self.model,
               "params_sha8": hashlib.sha256(json.dumps(self.params, sort_keys=True).encode()).hexdigest()[:8], "scope": self.scope,
               "reason": self.reason, "why": self.why, "skipped": self.skipped, "content_class": self.content_class,
               "needs_click": self.needs_click, "would_refuse_private": self.would_refuse_private, "doc_version": self.doc_version,
               "world": self.world}
        if self.followed:
            out["followed"] = self.followed
        if at:
            out["resolved_at"] = at
        return out

    def egress_context(self) -> dict:
        """What the consumer passes to ``egress.context`` so the transport and the choice agree (CHOICES.md 4.1)."""
        ctx = {"content_class": self.content_class}
        if self.provider == "openrouter" and self.content_class == "private":
            ctx["constraints"] = {"zdr": True, "data_collection": "deny"}
        return ctx


# ------------------------------------------------------------------------------------------------------------------------- helpers
def _conn_label(cid: str) -> str:
    from ..connections import registry as CR
    spec = CR.SPECS.get(cid)
    return spec.label if spec else cid


def _retention(oid: str, world) -> str:
    facts = REG.option_facts(oid)
    if facts["provider"] == "openrouter":
        model = facts["model"] or ""
        return "zdr" if world.zdr is not None and model in world.zdr and not model.endswith(":free") else "unknown"
    if facts["provider"] == "openai":
        return "local" if world.custom_llm_local else "unknown"
    return facts["retention"]


def _route(oid: str, world) -> Optional[str]:
    facts = REG.option_facts(oid)
    if facts["provider"] == "openai" and world.custom_llm_local:
        return None
    return facts["route"]


def _price(oid, world):
    c = world.costs.get(oid)
    return (c or {}).get("amount")


def _check(purpose, oid, job, world, doc) -> Optional[tuple]:
    """The first constraint ``oid`` fails, as (constraint, text), or None. ``would_refuse_private`` is handled by the caller."""
    facts = REG.option_facts(oid)
    prov, model = facts["provider"], facts["model"]
    # 1 exists
    if not REG.offers(purpose, oid):
        return "exists", f"{oid} is not an option for {purpose.id}"
    cat = world.catalogue.get(prov)
    if cat is not None and model and model not in cat:
        return "exists", f"{model} is not offered by {prov} today"
    # 2 capability
    runs_on = job.needs.get("runs_on")
    if runs_on and prov not in runs_on:
        return "capability", f"{oid} cannot run here: this job runs on {' or '.join(runs_on)} only"
    bound = (purpose.caps.get(oid) or {}).get("refs")
    if bound is not None and int(job.needs.get("refs") or 0) > bound:
        return "capability", f"{oid} cannot take {job.needs['refs']} references (at most {bound})"
    # 3 privacy
    if _content_class(purpose, job) == "private" and world.enforce_private and not _private_ok(oid, world, doc):
        return "privacy", f"private content: {oid} keeps what it receives ({_retention(oid, world)}): pick a local or ZDR option"
    # 4 connection
    conn = facts["connection"] if not (prov == "openai" and world.custom_llm_local) else None
    if conn and world.connections.get(conn, "missing") not in ("connected", "not_checked"):
        return "connection", f"connect {_conn_label(conn)} in Connections"
    # 5 route
    route = _route(oid, world)
    if route and not world.routes.get(route, False):
        return "route", f"{route} is off: switch it on in Privacy"
    # 6 spend
    price = _price(oid, world)
    cap = (world.spend.get(CLICK_PROVIDER.get(prov, "studios" if prov.startswith("studio:") else prov)) or {}).get("job_cap")
    if price is not None and cap is not None and float(price) > float(cap):
        return "spend", f"over the per-job cap of {float(cap):g}"
    # 7 local readiness
    if oid in world.local:
        return "local", world.local[oid]
    return None


def _private_ok(oid, world, doc) -> bool:
    if _retention(oid, world) in PRIVATE_OK:
        return True
    return bool(((doc.get("acknowledgements") or {}).get(oid) or {}).get("private"))


def _content_class(purpose, job) -> str:
    return job.content_class or purpose.content_class


def _needs_click(oid, world) -> bool:
    prov = REG.option_facts(oid)["provider"]
    if prov in ("local", "deterministic", "mock", "follow") or prov in ("chatgpt_plan", "openai"):
        return False
    key = CLICK_PROVIDER.get(prov, "studios" if prov.startswith("studio:") else prov)
    from ..spendpolicy import DEFAULT_SPEND_POLICY
    cfg = world.spend.get(key) or DEFAULT_SPEND_POLICY.get(key) or {"click": "always"}
    mode, price = cfg.get("click", "always"), _price(oid, world)
    if mode == "off":
        return False
    if mode == "always" or price is None:
        return True
    return float(price) > float(cfg.get("above") or 0.0)


def _in_force(pid, doc):
    for scope in SCOPES:
        entry = (doc.get(scope) or {}).get(pid)
        if entry and entry.get("preferred"):
            return scope, [entry["preferred"]] + [f for f in entry.get("fallbacks") or [] if f != entry["preferred"]]
    return None, []


def _params(pid, doc) -> dict:
    out = {}
    for scope in reversed(SCOPES):                                      # shipped first, the environment last: most specific wins per key
        out.update(((doc.get(scope) or {}).get(pid) or {}).get("params") or {})
    return out


def _policy(purpose, doc) -> str:
    for scope in ("global", "shipped"):                                  # the policy is the user's (or shipped); never a session's
        pol = ((doc.get(scope) or {}).get(purpose.id) or {}).get("override_policy")
        if pol:
            return pol
    return purpose.policy


def _override_allowed(purpose, job, chain, doc):
    oid = job.override
    if not REG.offers(purpose, oid):
        raise NoChoice(f"{oid} is not an option for {purpose.id}: its options are {', '.join(REG.listed(purpose))}", purpose.id)
    if job.origin == "user":
        return
    policy = _policy(purpose, doc)
    if policy == "none":
        if purpose.id in ("agent.main", "agent.worker"):
            raise NoChoice("an agent must not change its own provider: say what you would change and why, and the user decides", purpose.id)
    elif policy == "any_local" and REG.option_facts(oid)["provider"] in ("local", "deterministic"):
        return
    elif oid in chain:
        return
    raise NoChoice(f"{oid} is not one of your choices for {purpose.id}: propose it with lampway_choices", purpose.id)


# ------------------------------------------------------------------------------------------------------------------------- resolve
def resolve(pid: str, job: Job, world, doc: dict, _depth: int = 0) -> Resolution:
    purpose = REG.get(pid)
    scope, chain = _in_force(pid, doc)
    cls = _content_class(purpose, job)
    if job.override:
        _override_allowed(purpose, job, chain, doc)
        candidates, reason0 = [job.override], "override"
    else:
        candidates, reason0 = chain, "preferred"
    if not candidates:
        raise NoChoice(f"no choice is set for {purpose.label} yet: choose one in Choices", pid)
    skipped = []
    for i, oid in enumerate(candidates):
        if oid in job.avoid:
            skipped.append({"option": oid, "constraint": "avoid", "text": "fallback: asked for another model"})
            continue
        if REG.option_facts(oid)["provider"] == "follow" and _depth < 3:
            target = oid.split(":", 1)[1]
            try:
                inner = resolve(target, Job(content_class=cls, needs=job.needs, project=job.project, origin=job.origin, avoid=job.avoid), world, doc, _depth + 1)
            except NoChoice as exc:
                skipped.append({"option": oid, "constraint": "follow", "text": str(exc)})
                continue
            inner.purpose, inner.scope = pid, scope or inner.scope
            inner.reason = "fallback" if (i > 0 or inner.reason == "fallback") else reason0      # a fallback at either level is a fallback
            inner.followed = target
            inner.skipped = skipped + inner.skipped
            inner.params = {**inner.params, **_params(pid, doc)}
            inner.doc_version = doc.get("version", "")
            return inner
        failure = _check(purpose, oid, job, world, doc)
        if failure is not None:
            skipped.append({"option": oid, "constraint": failure[0], "text": failure[1]})
            continue
        reason = reason0 if i == 0 else "fallback"
        why = "" if not skipped else "fallback: " + "; ".join(f"{s['option']}: {s['text']}" for s in skipped)
        would = cls == "private" and not world.enforce_private and not _private_ok(oid, world, doc)
        facts = REG.option_facts(oid)
        return Resolution(pid, oid, _params(pid, doc), scope if reason0 != "override" else "job", reason, why, skipped, _needs_click(oid, world), cls,
                          doc.get("version", ""), world.summary([facts["connection"]], [_route(oid, world)]), would)
    fix = skipped[0]["text"] if skipped else ""
    detail = "; ".join(f"{s['option']}: {s['text']}" for s in skipped)
    raise NoChoice(f"nothing can serve {purpose.label} now: {detail}", pid, skipped, fix)
