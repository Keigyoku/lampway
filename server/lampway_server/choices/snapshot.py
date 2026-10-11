# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What the resolver sees, frozen: the Connections states, the egress routes, the ZDR list and the catalogues, the spend rules, the
known costs and the local facts. The resolver never reads anything else and never touches the network; ``live_world`` builds the snapshot
from the running server (``FakeWorld`` is simply a ``World`` a test writes by hand)."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass(frozen=True)
class World:
    connections: dict = field(default_factory=dict)          # connection id -> Connections state word
    routes: dict = field(default_factory=dict)               # egress route id -> on
    zdr: Optional[frozenset] = None                          # OpenRouter models on the live ZDR list (None: not read yet)
    catalogue: dict = field(default_factory=dict)            # provider -> frozenset of model ids offered today (absent: not read yet)
    spend: dict = field(default_factory=dict)                # spend-policy provider -> {click, above, job_cap}
    costs: dict = field(default_factory=dict)                # option -> {amount, unit, basis, as_of}
    local: dict = field(default_factory=dict)                # option -> what is missing (absent: ready)
    custom_llm_local: bool = True                            # the OpenAI-compatible endpoint is on this machine
    enforce_private: bool = False                            # CH1: the first release observes the private rule and refuses nothing
    catalogue_at: Optional[str] = None

    def digest(self) -> str:
        def norm(o):
            if isinstance(o, (set, frozenset)):
                return sorted(o)
            return o
        raw = json.dumps({k: norm(v) for k, v in asdict(self).items()}, sort_keys=True, default=norm)
        return hashlib.sha256(raw.encode()).hexdigest()[:8]

    def summary(self, connections=(), routes=()) -> dict:
        """The part of the world one resolution depended on (what the receipt records): state words and switches, never an identity."""
        return {"connections": {c: self.connections.get(c, "missing") for c in sorted(set(connections)) if c},
                "routes": {r: bool(self.routes.get(r, False)) for r in sorted(set(routes)) if r}, "catalogue_at": self.catalogue_at}


def live_world(hub=None, egress=None, spend=None, enforce_private: bool = False, custom_llm_local: bool = True, zdr=None, catalogue=None,
               costs=None, local=None) -> World:
    """The snapshot of the running server: Connections' state words (never an identity), the egress switches, the spend policy."""
    from .. import connections as C
    from .. import egress as EG
    hub = hub or C.active()
    eg = egress or EG.ACTIVE
    conns = {v["id"]: v["state"] for v in hub.view()}
    routes = {r: bool(eg.enabled(r)) for r in EG.ROUTES} if eg is not None else {}
    readiness = byoa_worker_readiness()
    readiness.update(local or {})
    return World(connections=conns, routes=routes, zdr=zdr, catalogue=dict(catalogue or {}), spend=dict(spend or {}), costs=dict(costs or {}),
                 local=readiness, custom_llm_local=custom_llm_local, enforce_private=enforce_private)


def byoa_worker_readiness() -> dict:
    """Local installation, bounded startup qualification and opt-in facts; no login or credential-file inspection."""
    from .. import choices as CH
    from ..herdr import harnesses as HN
    state_dir = getattr(CH.active_store(), "state_dir", None)
    enabled = HN.enabled(state_dir)
    missing = {}
    for hid, adapter in HN.ADAPTERS.items():
        reason = None
        if not enabled:
            reason = "your own agents in Lampway's panes are off: enable Bring Your Own Agent first"
        elif not adapter.direct_ok:
            reason = f"{adapter.label} cannot run a worker: {adapter.tools_note or 'no supported per-pane tool endpoint'}"
        elif (problem := HN.worker_problem(adapter)):
            reason = f"{adapter.label} cannot run a worker: {problem}"
        elif adapter.locate() is None:
            reason = f"{adapter.label} is not installed: {adapter.install_hint}"
        if not reason and hasattr(adapter, "compatibility_note"):
            reason = adapter.compatibility_note()
        if reason:
            missing[f"byoa:{hid}"] = reason
    return missing
