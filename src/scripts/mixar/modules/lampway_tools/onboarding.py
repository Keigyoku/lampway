# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The first run's steps (facelift contract 02, P1): language and keys, where the agent thinks, what may leave this machine, what may your agent do
(E2, only when the server has Capabilities), spending caps. No bpy, and the walk's logic (``read``, ``next``, ``finish``) imports nothing beyond the
standard library: the popup (``ui/onboarding.py``) draws a ``Walk`` and ``server/tests/test_onboarding_walk.py`` loads this file by its path and drives
one. The words of the capabilities step (``capability_warning``, ``capability_note``) come from ``capabilities_face``, imported where they are used.

Every route starts as the server has it (off on a fresh install) and changes only by the user's click, which is recorded. So does every
capability: the walk shows the server's defaults ticked and writes only what the user changed. Nothing leaves the machine during the walk:
``finish`` writes the choices to Lampway's own server, and only then."""

STEPS = ("Language and keys", "Where the agent thinks", "What may leave this machine", "Spending caps")
STEP_CAPABILITIES = "What may your agent do?"
KINDS = ("language", "agent", "routes", "spending")
OFFLINE = "Lampway's server is not running: Start it"
# BUILD_ORDER.md cloud D1 for OpenRouter (dollars). The server keeps a session ledger, not a day one: the D1 "$5 per day" is the session cap.
DEFAULT_CAPS = {"job_cap": 1.0, "session_cap": 5.0, "above": 0.25}
# The route a main provider needs to think; a provider with none runs on this machine. Labels are the egress route's own.
# Claude Code and Codex are not here: they run as the user's own agent, not as Lampway's model (agent-modes spec R0).
PROVIDER_ROUTE = {"anthropic": "claude_plan", "openai": "chatgpt_plan", "chatgpt_plan": "chatgpt_plan", "openrouter": "openrouter"}
ROUTE_HOST = {"claude_plan": "api.anthropic.com", "chatgpt_plan": "chatgpt.com", "openrouter": "openrouter.ai"}
ROUTE_LABEL = {"claude_plan": "Claude plan", "chatgpt_plan": "ChatGPT plan", "openrouter": "OpenRouter"}


def continue_label(n: int) -> str:
    return f"Continue with {n} route{'' if n == 1 else 's'} on"


class Walk:
    def __init__(self, routes=None, provider="", caps=None, capabilities=None):
        self.online = routes is not None
        self.routes = [dict(r) for r in routes or []]
        self._server = {r["id"]: bool(r.get("enabled")) for r in self.routes}
        self.chosen = dict(self._server)
        self.provider = provider or ""
        self._provider_was = self.provider
        self.caps = dict(DEFAULT_CAPS if caps is None else caps)
        self.clicks = []
        self.step = 1
        # The capabilities step exists only when the server answered with something a person can switch: a family (messaging.*, mcp.*) has no
        # platform or server to switch on yet, so it is left to the Capabilities page. Offline there is no step and nothing to save.
        rows = [dict(c) for c in capabilities or [] if "*" not in str(c.get("id"))] if self.online else []
        self.capability_rows = rows or None
        self._capability_server = {c["id"]: bool(c.get("enabled")) for c in rows}
        self.capability_chosen = dict(self._capability_server)
        self.capability_clicks = []

    @classmethod
    def read(cls, client):
        """The walk as the server has things now; offline when it cannot be reached."""
        try:
            routes = client.egress()["routes"]
            provider = (client.provider_settings().get("values") or {}).get("provider") or ""
        except Exception:  # noqa: BLE001  (any failure to reach the server reads as offline; the steps say so)
            return cls(routes=None)
        try:
            capabilities = client.capabilities().get("capabilities")
        except Exception:  # noqa: BLE001  (an older server, a door without the call, a failed read: the walk goes on without the step)
            capabilities = None
        return cls(routes=routes, provider=provider, capabilities=capabilities)

    @property
    def kinds(self) -> tuple:
        """What each step is, in order: the steps of THIS walk (the capabilities step follows the routes when there is one)."""
        return KINDS[:3] + ("capabilities",) + KINDS[3:] if self.capability_rows is not None else KINDS

    @property
    def steps(self) -> tuple:
        return STEPS[:3] + (STEP_CAPABILITIES,) + STEPS[3:] if self.capability_rows is not None else STEPS

    @property
    def kind(self) -> str:
        return self.kinds[self.step - 1]

    def routes_on(self) -> list:
        return [r for r, on in self.chosen.items() if on]

    def click_route(self, route: str, on: bool) -> None:
        if route not in self.chosen:
            raise KeyError(f"no route {route!r}")
        self.chosen[route] = bool(on)
        self.clicks.append((route, bool(on)))

    def capabilities_on(self) -> list:
        return [c for c, on in self.capability_chosen.items() if on]

    def click_capability(self, cid: str, on: bool) -> None:
        if cid not in self.capability_chosen:
            raise KeyError(f"no capability {cid!r}")
        self.capability_chosen[cid] = bool(on)
        self.capability_clicks.append((cid, bool(on)))

    def _capability(self, cid: str) -> dict:
        return next(r for r in self.capability_rows if r["id"] == cid)

    def capability_warning(self, cid: str) -> str:
        """The one plain sentence under a ticked capability that runs code or acts outside Lampway ('' otherwise)."""
        from . import capabilities_face as face
        row = self._capability(cid)
        return face.warning(row) if self.capability_chosen.get(cid) and face.needs_confirm(row) else ""

    def capability_note(self, cid: str) -> str:
        """Under a ticked capability: the route it needs and where it is switched ('' when none is off). A route chosen in step 3 counts at once."""
        if not self.capability_chosen.get(cid):
            return ""
        from . import capabilities_face as face
        off = [r["id"] for r in self._capability(cid).get("routes") or [] if not (self.chosen[r["id"]] if r["id"] in self.chosen else r.get("on"))]
        if not off:
            return ""
        unoffered = [r for r in off if r not in self.chosen]
        named = [face.route_word(r) for r in (unoffered or off)]
        many = len(named) > 1
        needs = f"Needs the {', '.join(named)} route{'s' if many else ''}"
        if unoffered:   # step 3 lists the server's routes: one it does not list cannot be switched on from here
            return f"{needs}, which this setup does not offer yet"
        return f"{needs}, which {'are' if many else 'is'} off: switch {'them' if many else 'it'} on in step 3"

    def refusal(self):
        """Step 2's refusal: a provider whose route is off cannot think."""
        route = PROVIDER_ROUTE.get(self.provider)
        if not self.online or route is None or self.chosen.get(route):
            return None
        return f"{ROUTE_LABEL[route]} needs the {ROUTE_HOST[route]} route: switch it on in step 3, or pick a local provider"

    def next(self):
        """Advance one step; a refusal leaves the step where it is and is returned."""
        if self.step == 2 and (why := self.refusal()):
            return why
        self.step = min(self.step + 1, len(self.steps))
        return None

    def back(self) -> None:
        self.step = max(1, self.step - 1)

    def continue_label(self) -> str:
        return continue_label(len(self.routes_on()))

    def finish(self, client) -> list:
        """Write the choices to the server (the preferences file is the popup's: ``wm.save_userpref``). Offline, only the preferences."""
        saved = ["preferences"]
        if not self.online or client is None:
            return saved
        for route, on in self.chosen.items():
            if on != self._server.get(route):
                client.set_route(route, on)
        saved.append("routes")
        if self.capability_rows is not None:
            for cid, on in self.capability_chosen.items():
                if on != self._capability_server.get(cid):
                    client.set_capability(cid, enabled=on)
                    self._capability_server[cid] = on   # a retry after a failure writes only the rest
            saved.append("capabilities")
        values = {"spend_policy": {"openrouter": {"click": "above", **self.caps}}}
        if self.provider != self._provider_was:
            values["provider"] = self.provider
        client.save_provider_settings(values)
        saved.append("caps")
        return saved
