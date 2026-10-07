# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The first run's four steps (facelift contract 02, P1): language and keys, what may leave this machine, where the agent thinks, spending
caps. The routes come before the provider (the audit's F3, the captain's ruling): a plan provider needs its route, so it is switched first. No bpy and no import beyond the standard library: the popup (``ui/onboarding.py``) draws a ``Walk`` and the server tests drive one.

Every route starts as the server has it (off on a fresh install) and changes only by the user's click, which is recorded. Nothing leaves the
machine during the walk: ``finish`` writes the choices to Lampway's own server, and only then."""

STEPS = ("Language and keys", "What may leave this machine", "Where the agent thinks", "Spending caps")
ROUTES_STEP, PROVIDER_STEP, CAPS_STEP = 2, 3, 4
OFFLINE = "Lampway's server is not running: Start it"
# The captain's ruling 5 (2026-10-07): a saved per-day total, $1 per job, $5 per local day, a click above $0.25 (OpenRouter, dollars).
DEFAULT_CAPS = {"job_cap": 1.0, "day_cap": 5.0, "above": 0.25}
# The route a main provider needs to think; a provider with none runs on this machine. Labels are the egress route's own.
PROVIDER_ROUTE = {"anthropic": "claude_plan", "claude_cli": "claude_plan", "openai": "chatgpt_plan", "chatgpt_plan": "chatgpt_plan",
                  "codex_cli": "chatgpt_plan", "codex_app_server": "chatgpt_plan", "openrouter": "openrouter"}
ROUTE_HOST = {"claude_plan": "api.anthropic.com", "chatgpt_plan": "chatgpt.com", "openrouter": "openrouter.ai"}
ROUTE_LABEL = {"claude_plan": "Claude plan", "chatgpt_plan": "ChatGPT plan", "openrouter": "OpenRouter"}


def continue_label(n: int) -> str:
    return f"Continue with {n} route{'' if n == 1 else 's'} on"


class Walk:
    def __init__(self, routes=None, provider="", caps=None):
        self.online = routes is not None
        self.routes = [dict(r) for r in routes or []]
        self._server = {r["id"]: bool(r.get("enabled")) for r in self.routes}
        self.chosen = dict(self._server)
        self.provider = provider or ""
        self._provider_was = self.provider
        self.caps = dict(DEFAULT_CAPS if caps is None else caps)
        self.clicks = []
        self.step = 1

    @classmethod
    def read(cls, client):
        """The walk as the server has things now; offline when it cannot be reached."""
        try:
            routes = client.egress()["routes"]
            provider = (client.provider_settings().get("values") or {}).get("provider") or ""
        except Exception:  # noqa: BLE001  (any failure to reach the server reads as offline; the steps say so)
            return cls(routes=None)
        return cls(routes=routes, provider=provider)

    def routes_on(self) -> list:
        return [r for r, on in self.chosen.items() if on]

    def click_route(self, route: str, on: bool) -> None:
        if route not in self.chosen:
            raise KeyError(f"no route {route!r}")
        self.chosen[route] = bool(on)
        self.clicks.append((route, bool(on)))

    def refusal(self):
        """The provider step's refusal: a provider whose route is off cannot think."""
        route = PROVIDER_ROUTE.get(self.provider)
        if not self.online or route is None or self.chosen.get(route):
            return None
        return f"{ROUTE_LABEL[route]} needs the {ROUTE_HOST[route]} route: go Back and switch it on, or pick a local provider"

    def next(self):
        """Advance one step; a refusal leaves the step where it is and is returned."""
        if self.step == PROVIDER_STEP and (why := self.refusal()):
            return why
        self.step = min(self.step + 1, len(STEPS))
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
        values = {"spend_policy": {"openrouter": {"click": "above", **self.caps}}}
        if self.provider != self._provider_was:
            values["provider"] = self.provider
        client.save_provider_settings(values)
        saved.append("caps")
        return saved
