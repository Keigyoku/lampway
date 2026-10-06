"""Compute prefs (the Providers dialog's `compute` block): caps, click policy, enabled and private-allowed backends, orphan action. The captain's answers are the defaults (BUILD_ORDER, Cloud compute D1/D7):
$1 a job, $5 a (local) day, a click above $0.25, orphans reported and never stopped. NO backend is enabled until the user picks one."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

DEFAULTS = {"spend": {"job_cap": 1.0, "day_cap": 5.0, "click": "above", "above": 0.25}, "backends": [], "private_backends": [], "orphan_action": "report", "day_timezone": "local"}


class Prefs:
    def __init__(self, path):
        self.path = Path(path)

    @property
    def data(self) -> dict:
        d = copy.deepcopy(DEFAULTS)
        try:
            saved = json.loads(self.path.read_text())
        except (OSError, ValueError):
            saved = {}
        for k, v in saved.items():
            if isinstance(v, dict) and isinstance(d.get(k), dict):
                d[k].update(v)
            else:
                d[k] = v
        return d

    def update(self, changes: dict) -> dict:
        cur = self.data
        for k, v in changes.items():
            if isinstance(v, dict) and isinstance(cur.get(k), dict):
                cur[k] = {**cur[k], **v} if k != "spend" else dict(v)
            else:
                cur[k] = v
        if cur["orphan_action"] not in ("report", "stop") or cur["spend"].get("click") not in ("off", "above", "always"):
            raise ValueError("orphan_action is report | stop; click is off | above | always")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(cur, fh, indent=1)
        os.replace(tmp, self.path)
        return cur
