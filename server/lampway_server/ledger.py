"""The experiment ledger: ONE append-only JSON-lines record of every generation or experiment run, shared with the prompt run log (prompts/runlog.py is a
view of the same file). Pure python, no server imports, so the Client's tools can write rows with the same code (tests pin the two copies together).

A row is never edited: a correction is a new row with ``supersedes``. Cost is four separate quantities (subscription text, generation credits, developer-API
dollars, work seconds) and a credit price needs the source it was read back from. An agent can never ``choose`` a spend result: only the user (or a rule) does.
Appends take an exclusive file lock, so threads and worker processes lose no row."""

import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

try:
    import fcntl
except ImportError:                                  # pragma: no cover  (Windows: the thread lock only)
    fcntl = None

STAGES = ("image", "mesh", "uv", "texture", "pbr", "video", "motion", "rig", "fit", "export", "decision", "other")
STUDIOS = ("tripo", "meshy", "hi3d", "hyper3d", "openrouter", "higgsfield", "local")
SPEND_STAGES = ("image", "mesh", "uv", "texture", "pbr", "video", "motion")
VERDICT_KEYS = ("shape", "uv", "rig", "material", "handedness")
_LOCK = threading.Lock()


def default_path() -> Path:
    """<project root>/ledger/runs.jsonl (the project root is LAMPWAY_PROJECT_ROOT, as the studios and the agent tools read it)."""
    import os
    return Path(os.environ.get("LAMPWAY_PROJECT_ROOT") or Path.home() / ".local/share/lampway/projects") / "ledger" / "runs.jsonl"


class LedgerError(ValueError):
    pass


_SECRET = re.compile(r"(?<![A-Za-z0-9])(sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{12,}|AIza[0-9A-Za-z_-]{20,})|[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@")


def find_secret(value):
    """The first string in ``value`` (any depth) that looks like a credential (sk-, ghp_, AKIA, AIza prefixes) or a URL with userinfo; None when clean."""
    if isinstance(value, str):
        m = _SECRET.search(value)
        return m.group(0)[:6] + "..." if m else None
    if isinstance(value, dict):
        for k, v in value.items():
            hit = find_secret(k) or find_secret(v)
            if hit:
                return hit
    if isinstance(value, (list, tuple)):
        for v in value:
            hit = find_secret(v)
            if hit:
                return hit
    return None


def reject_secret(value, where: str) -> None:
    hit = find_secret(value)
    if hit:
        raise LedgerError(f"{where} looks like a secret ({hit}): a ledger row holds ids, hashes and prices, never a credential or a URL with userinfo")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


class Ledger:
    def __init__(self, path):
        self.path = Path(path)

    # ------------------------------------------------------------------ the file
    def _append(self, row: dict) -> None:
        line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
        with _LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                if fcntl:
                    fcntl.flock(fh, fcntl.LOCK_EX)
                try:
                    fh.write(line)
                    fh.flush()
                finally:
                    if fcntl:
                        fcntl.flock(fh, fcntl.LOCK_UN)

    def rows(self, kind: Optional[str] = None) -> list:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and kind in (None, row.get("kind")):
                out.append(row)
        return out

    # ------------------------------------------------------------------ experiment rows
    @staticmethod
    def _check(run: dict) -> dict:
        if not isinstance(run, dict):
            raise LedgerError("a run is an object")
        piece = str(run.get("piece") or "").strip()
        if not piece:
            raise LedgerError("a run names its piece")
        stage, studio = run.get("stage"), run.get("studio")
        if stage not in STAGES:
            raise LedgerError(f"stage {stage!r} is not one of {', '.join(STAGES)}")
        if studio not in STUDIOS:
            raise LedgerError(f"studio {studio!r} is not one of {', '.join(STUDIOS)}")
        seed = run.get("seed", "not_exposed")
        if not (seed == "not_exposed" or (isinstance(seed, int) and not isinstance(seed, bool))):
            raise LedgerError("seed is a whole number or 'not_exposed' (never borrow a seed the studio does not expose)")
        cost = run.get("cost") or {}
        if not isinstance(cost, dict):
            raise LedgerError("cost is an object of the four quantities")
        for key in ("generation_credits", "developer_api_usd", "work_s"):
            if cost.get(key) is not None and not _num(cost[key]):
                raise LedgerError(f"cost.{key} is a number (got {cost[key]!r})")
        if cost.get("generation_credits") is not None and not str(cost.get("price_source") or "").strip():
            raise LedgerError("cost.generation_credits needs cost.price_source: record the price the driver read back, not a guess")
        decision, by = run.get("decision"), run.get("by") or "agent"
        if decision not in (None, "chosen", "rejected"):
            raise LedgerError("decision is chosen or rejected")
        if by not in ("captain", "agent", "rule"):
            raise LedgerError("by is captain, agent or rule")
        if decision == "chosen" and by == "agent" and stage in SPEND_STAGES and studio != "local":
            raise LedgerError("only the user chooses a result of a spend stage (an agent may reject, never choose)")
        verdict = run.get("verdict") or {}
        if not isinstance(verdict, dict) or set(verdict) - set(VERDICT_KEYS):
            raise LedgerError(f"verdict keys are {', '.join(VERDICT_KEYS)}")
        return {"piece": piece, "stage": stage, "studio": studio, "seed": seed, "cost": cost, "decision": decision, "by": by, "verdict": verdict}

    def record(self, run: dict) -> dict:
        reject_secret(run, "a ledger row")
        clean = self._check(run)
        sup = run.get("supersedes")
        if sup and not any(r.get("kind") == "experiment" and r.get("id") == sup for r in self.rows()):
            raise LedgerError(f"no row {sup!r} to supersede")
        row = {"kind": "experiment", "id": str(run.get("id") or uuid.uuid4()), "t": time.time(),
               "model_version": run.get("model_version"), "settings": run.get("settings") or {}, "prompt_hash": run.get("prompt_hash"),
               "reference_hashes": run.get("reference_hashes") or [], "parent_hashes": run.get("parent_hashes") or [],
               "output_hashes": run.get("output_hashes") or [], "reason": str(run.get("reason") or ""), "supersedes": sup, **clean}
        self._append(row)
        return row

    def record_job(self, row: dict) -> dict:
        """One row per terminal job receipt (kind ``job``): ids, hashes, state and the price with its source; never a URL or a secret (jobreceipts.export_safe is applied first)."""
        out = {"kind": "job", "t": time.time(), **{k: row.get(k) for k in ("job_key", "provider", "model", "state", "price", "output_hashes", "origin")}}
        reject_secret(out, "a job ledger row")
        self._append(out)
        return out

    def list(self, piece: Optional[str] = None, stage: Optional[str] = None, include_superseded: bool = False) -> list:
        rows = [r for r in self.rows("experiment") if piece in (None, r["piece"]) and stage in (None, r["stage"])]
        if include_superseded:
            return rows
        gone = {r["supersedes"] for r in self.rows("experiment") if r.get("supersedes")}
        return [r for r in rows if r["id"] not in gone]

    def _get(self, run_id: str) -> dict:
        row = next((r for r in self.rows("experiment") if r["id"] == run_id), None)
        if row is None:
            raise LedgerError(f"no row {run_id!r}")
        return row

    def compare(self, ids: list) -> dict:
        rows = [self._get(i) for i in ids]
        keys = sorted({k for r in rows for k in r["settings"]})
        diff = {k: {r["id"]: r["settings"].get(k) for r in rows} for k in keys if len({json.dumps(r["settings"].get(k), sort_keys=True) for r in rows}) > 1}
        return {"ids": list(ids), "settings_diff": diff, "seed": {r["id"]: r["seed"] for r in rows},
                "output_changed": len({tuple(r["output_hashes"]) for r in rows}) > 1,
                "cost": {r["id"]: r["cost"] for r in rows}, "verdict": {r["id"]: r["verdict"] for r in rows}}

    def receipt(self, piece: str) -> dict:
        """The four quantities for one piece, summed separately (superseded rows excluded). Prompt-run rows that name the piece add their dollars."""
        total = {"generation_credits": 0, "developer_api_usd": 0.0, "work_s": 0.0}
        subs, n = [], 0
        for r in self.list(piece=piece):
            n += 1
            for k in total:
                if _num(r["cost"].get(k)):
                    total[k] += r["cost"][k]
            if r["cost"].get("subscription"):
                subs.append(str(r["cost"]["subscription"]))
        for r in self.rows("run"):
            if r.get("piece") == piece and _num(r.get("cost")):
                n += 1
                total["developer_api_usd"] += r["cost"]
        return {"piece": piece, **total, "subscription": subs, "rows": n}
