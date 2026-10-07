"""Spend policy per provider, set from the Providers dialog (provider_prefs ``spend_policy``): ``click`` (off | above | always), ``above`` (the price over which a click
is needed), ``job_cap`` and ``day_cap`` (in the provider's own unit: dollars for OpenRouter, credits for Higgsfield / the Studios / Hyper3D). The policy decides WHETHER
a job waits for the user; it never lets anyone but the user click: the approvals store refuses any confirm that is not his. An unknown price is never waved
through (it needs a click unless the policy is off).

The captain's ruling 5 (2026-10-07): the day cap is a SAVED total for the local day (``<state>/spend/day.json``, written atomically, read again after a
restart, reset when the local date changes). The defaults are $1 per job, $5 per day and a click above $0.25 for OpenRouter, the provider spending dollars;
the prefs override them key by key (``None`` removes a cap). An unreadable day file refuses a spend rather than resetting the total."""

import json
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

PROVIDERS = ("openrouter", "higgsfield", "studios", "hyper3d")
CLICKS = ("off", "above", "always")
DEFAULT_SPEND_POLICY = {"openrouter": {"click": "above", "above": 0.25, "job_cap": 1.0, "day_cap": 5.0},
                        "higgsfield": {"click": "always"}, "studios": {"click": "always"}, "hyper3d": {"click": "always"}}


class SpendRefused(ValueError):
    pass


def _money(provider: str, amount: float) -> str:
    return f"${amount:.2f}" if provider == "openrouter" else f"{amount:g} credits"


class SpendPolicy:
    def __init__(self, getter: Callable[[], dict], path=None, clock: Callable[[], float] = time.time):
        self._get = getter
        self._path = Path(path) if path is not None else None              # None: an in-memory day (tests and stand-alone queues)
        self._clock = clock
        self._lock = threading.RLock()
        self._mem: dict = {"day": None, "spent": {}}

    def _cfg(self, provider: str) -> dict:
        return {**(DEFAULT_SPEND_POLICY.get(provider) or {"click": "always"}), **((self._get() or {}).get(provider) or {})}

    # ------------------------------------------------------------------------------------------------ the day's total
    def _today(self) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(self._clock()))

    def _load(self) -> dict:
        if self._path is None:
            doc = self._mem
        else:
            try:
                doc = json.loads(self._path.read_text())
            except FileNotFoundError:
                doc = {"day": None, "spent": {}}
            except (OSError, ValueError) as exc:
                raise SpendRefused(f"the day's spend total is unreadable ({self._path}: {exc}): nothing is spent until it is repaired or removed") from None
            if not isinstance(doc, dict) or not isinstance(doc.get("spent"), dict):
                raise SpendRefused(f"the day's spend total is unreadable ({self._path}): nothing is spent until it is repaired or removed")
        return doc if doc.get("day") == self._today() else {"day": self._today(), "spent": {}}

    def _save(self, doc: dict) -> None:
        if self._path is None:
            self._mem = doc
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(doc, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self._path)

    def spent_today(self, provider: str) -> float:
        with self._lock:
            return float(self._load()["spent"].get(provider, 0.0))

    @property
    def spent(self) -> dict:
        """Today's totals per provider (the local day)."""
        with self._lock:
            return dict(self._load()["spent"])

    def status_text(self, provider: str) -> str:
        cap, spent = self._cfg(provider).get("day_cap"), self.spent_today(provider)
        return f"spent today {_money(provider, spent)} of {_money(provider, float(cap))}" if cap is not None else f"spent today {_money(provider, spent)} (no daily cap)"

    # ------------------------------------------------------------------------------------------------ the decisions
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
        if cfg.get("day_cap") is not None:
            spent = self.spent_today(provider)
            if spent + price > float(cfg["day_cap"]):
                raise SpendRefused(f"{provider}: {price:g} would pass today's cap of {float(cfg['day_cap']):g} ({spent:g} already spent today, local day; Providers dialog)")

    def record(self, provider: str, price: Optional[float]) -> None:
        if price:
            with self._lock:
                doc = self._load()
                doc["spent"][provider] = float(doc["spent"].get(provider, 0.0)) + float(price)
                self._save(doc)
