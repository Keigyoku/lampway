# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The shadow log and its report (choices_migration.md steps 0-1): a consumer records what the resolver would pick beside what actually ran,
one row ``{t, purpose, resolved, ran, same}`` in ``<state>/choices/shadow.jsonl``. Recording never changes what runs and never fails a call.

    python -m lampway_server.choices.shadow --report [--state DIR]      # every purpose where the resolver and the run differ (AXI, TOON)"""

import argparse
import json
import os
import time
from pathlib import Path
from typing import Optional


def _path(state=None) -> Path:
    from .. import choices as CH
    return Path(state or CH._state_dir()) / "choices" / "shadow.jsonl"


def record(purpose: str, ran: str, job=None) -> None:
    from .. import choices as CH
    try:
        try:
            resolved = CH.resolve(purpose, job or CH.Job()).option
        except CH.NoChoice:
            resolved = None
        row = {"t": time.time(), "purpose": purpose, "resolved": resolved, "ran": ran, "same": resolved == ran}
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception:  # noqa: BLE001 - a shadow row is evidence, never a reason to fail the call it describes
        pass


def report(state=None) -> dict:
    try:
        rows = [json.loads(l) for l in _path(state).read_text().splitlines() if l.strip()]
    except OSError:
        rows = []
    diffs: dict = {}
    for r in rows:
        if not r.get("same"):
            k = (r["purpose"], r.get("resolved"), r.get("ran"))
            diffs[k] = diffs.get(k, 0) + 1
    return {"rows": len(rows), "differences": [{"purpose": p, "resolved": res, "ran": ran, "count": n} for (p, res, ran), n in sorted(diffs.items(), key=str)]}


def main(argv: Optional[list] = None) -> int:
    from ..studios import axi
    ap = argparse.ArgumentParser(prog="lampway-choices shadow", description="What the Choices resolver would pick beside what ran")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--state", default=None, help="the server state directory (default LAMPWAY_STATE_DIR)")
    a = ap.parse_args(argv)
    if not a.report:
        axi.home(__file__, "Choices shadow log: what the resolver would pick beside what ran")
        axi.helps(["python -m lampway_server.choices.shadow --report"])
        return 0
    rep = report(a.state or os.environ.get("LAMPWAY_STATE_DIR") or None)
    axi.kv({"rows": rep["rows"]})
    axi.table("differences", rep["differences"], ["purpose", "resolved", "ran", "count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
