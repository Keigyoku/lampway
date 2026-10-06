"""What was worked on that day (specs/mrmak/09-report-cards.md section 5): the cards created or updated on the date, the ledger's rows of that local day with their
spend, and the git subjects recorded under the project when it is a repository (absent git is not an error). The basis is said with the answer."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from .archive import brief

BASIS = "registry dates, ledger rows and recorded git changes; not a record of unsaved work"


def _commits(git_root, date: str) -> list:
    if not git_root or not (Path(git_root) / ".git").exists():
        return []
    try:
        p = subprocess.run(["git", "-C", str(git_root), "log", f"--since={date} 00:00:00", f"--until={date} 23:59:59", "--format=%s", "--", "cards"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line for line in p.stdout.splitlines() if line.strip()] if p.returncode == 0 else []


def activity(reg, ledger, date: str, git_root=None) -> dict:
    cards = [brief(c, date) for c in reg.all() if date in (c.get("created"), c.get("updated"))]
    rows = [r for r in ledger.rows("experiment") if time.strftime("%Y-%m-%d", time.localtime(r.get("t") or 0)) == date]
    spend = {"generation_credits": 0, "developer_api_usd": 0.0, "work_s": 0.0}
    for r in rows:
        for k in spend:
            v = (r.get("cost") or {}).get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                spend[k] += v
    spend["developer_api_usd"] = round(spend["developer_api_usd"], 6)
    return {"date": date, "cards": cards, "ledger": {"rows": len(rows), "spend": spend}, "commits": _commits(git_root, date), "basis": BASIS}
