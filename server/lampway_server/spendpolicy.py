"""Spend policy per provider, set from the Providers dialog (provider_prefs ``spend_policy``): ``click`` (off | above | always), ``above`` (the price over which a click
is needed), ``job_cap`` and ``session_cap`` (in the provider's own unit: dollars for OpenRouter, credits for Higgsfield / the Studios / Hyper3D). The policy decides WHETHER
a job waits for the user; it never lets anyone but the user click: the approvals store refuses any confirm that is not his. An unknown price is never waved
through (it needs a click unless the policy is off)."""

from typing import Callable, Optional

PROVIDERS = ("openrouter", "higgsfield", "studios", "hyper3d")
CLICKS = ("off", "above", "always")
DEFAULT_SPEND_POLICY = {"openrouter": {"click": "above", "above": 0.25}, "higgsfield": {"click": "always"}, "studios": {"click": "always"}, "hyper3d": {"click": "always"}}


class SpendRefused(ValueError):
    pass


class SpendPolicy:
    def __init__(self, getter: Callable[[], dict]):
        self._get = getter
        self.spent: dict = {}

    def _cfg(self, provider: str) -> dict:
        return (self._get() or {}).get(provider) or DEFAULT_SPEND_POLICY.get(provider) or {"click": "always"}

    def needs_click(self, provider: str, price: Optional[float]) -> bool:
        cfg = self._cfg(provider)
        mode = cfg.get("click", "always")
        if mode == "off":
            return False
        if mode == "always" or price is None:
            return True
        return price > float(cfg.get("above") or 0.0)

    def check(self, provider: str, price: Optional[float]) -> None:
        cfg = self._cfg(provider)
        if price is None:
            return
        if cfg.get("job_cap") is not None and price > float(cfg["job_cap"]):
            raise SpendRefused(f"{provider}: {price:g} is over the per-job cap of {float(cfg['job_cap']):g} (Providers dialog)")
        if cfg.get("session_cap") is not None and self.spent.get(provider, 0.0) + price > float(cfg["session_cap"]):
            raise SpendRefused(f"{provider}: {price:g} would pass the session cap of {float(cfg['session_cap']):g} ({self.spent.get(provider, 0.0):g} already spent; Providers dialog)")

    def record(self, provider: str, price: Optional[float]) -> None:
        if price:
            self.spent[provider] = self.spent.get(provider, 0.0) + float(price)
