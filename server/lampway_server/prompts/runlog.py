"""The run log: every image or video job records its template id@version, the filled variables, the rendered prompt, model, cost, output file, the
gate measurements and the captain's 1-5 rating. ``stats`` aggregates by template version; ``variant_of`` lets two versions run side by side. JSON lines,
append-only; a rating or a gate measurement is a later line for the same job."""

import json
import threading
import time
from pathlib import Path
from typing import Optional

_LOCK = threading.Lock()


class RunLog:
    def __init__(self, path):
        self.path = Path(path)

    def _append(self, row: dict) -> None:
        with _LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def record(self, job_id: str, *, prompt: str, model: str = "", template: Optional[str] = None, variables: Optional[dict] = None, cost: Optional[float] = None,
               output: Optional[str] = None, service: str = "", variant_of: Optional[str] = None, extra: Optional[dict] = None) -> None:
        self._append({"kind": "run", "t": time.time(), "job_id": job_id, "service": service, "template": template, "variables": variables or {}, "prompt": prompt,
                      "model": model, "cost": cost, "output": output, "variant_of": variant_of, **(extra or {})})

    def gates(self, job_id: str, measurements: dict) -> None:
        self._require(job_id)
        self._append({"kind": "gates", "t": time.time(), "job_id": job_id, "gates": measurements})

    def rate(self, job_id: str, rating: int, note: str = "") -> None:
        if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
            raise ValueError("the rating is a whole number from 1 to 5")
        self._require(job_id)
        self._append({"kind": "rating", "t": time.time(), "job_id": job_id, "rating": rating, "note": str(note)[:500]})

    def _rows(self) -> list:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def _require(self, job_id: str) -> None:
        if not any(r["kind"] == "run" and r["job_id"] == job_id for r in self._rows()):
            raise ValueError(f"no recorded run {job_id!r}")

    def runs(self, template: Optional[str] = None) -> list:
        """One merged row per job: the run plus its latest rating and gates."""
        merged: dict = {}
        for r in self._rows():
            if r["kind"] == "run":
                merged[r["job_id"]] = dict(r, rating=None, note="", gates={})
            elif r["job_id"] in merged:
                if r["kind"] == "rating":
                    merged[r["job_id"]].update(rating=r["rating"], note=r["note"])
                else:
                    merged[r["job_id"]]["gates"].update(r["gates"])
        rows = list(merged.values())
        return [r for r in rows if template in (None, r["template"], (r["template"] or "").split("@")[0])]

    def stats(self, template: Optional[str] = None) -> list:
        """Per template version: runs, rated count, mean rating, mean cost, and for each gate the pass rate (a gate value of true/false) or the mean (a number)."""
        groups: dict = {}
        for r in self.runs(template):
            if r["template"]:
                groups.setdefault(r["template"], []).append(r)
        out = []
        for name, rows in sorted(groups.items()):
            rated = [r["rating"] for r in rows if r["rating"]]
            costs = [r["cost"] for r in rows if isinstance(r["cost"], (int, float))]
            gate_names = sorted({g for r in rows for g in r["gates"]})
            gates = {}
            for g in gate_names:
                vals = [r["gates"][g] for r in rows if g in r["gates"]]
                if all(isinstance(v, bool) for v in vals):
                    gates[g] = {"n": len(vals), "pass_rate": round(sum(vals) / len(vals), 3)}
                else:
                    nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
                    gates[g] = {"n": len(nums), "mean": round(sum(nums) / len(nums), 4) if nums else None}
            out.append({"template": name, "runs": len(rows), "rated": len(rated), "mean_rating": round(sum(rated) / len(rated), 2) if rated else None,
                        "mean_cost": round(sum(costs) / len(costs), 4) if costs else None, "gates": gates,
                        "variant_of": next((r["variant_of"] for r in rows if r["variant_of"]), None)})
        return out
