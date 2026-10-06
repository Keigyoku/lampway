"""material_experiment: the wiki's credit-efficient material matrix as planned, approval-gated rows with a measured comparison and a stop rule
(specs/wiki/material_experiment.md). Pure python on the Studio action catalogue and the experiment ledger.

Rows: T1 baseline, T2 T1 repeated exactly (is the seed operationally repeatable?), T3 seed only, T4 texture alignment only, M1 one shared material, L1 one
local patch. A row an engine cannot express is refused when asked for and listed as skipped (with the reason) when it came from the default set. Prices
come from the action catalogue (``studios.actions``: tripo.texture expects 30); an engine with no driver keeps the wiki's documentation figure, marked
[UNVERIFIED], and is plan-only. ``run`` never spends: it returns the needs_approval card the agent hands to ``lampway_studio_plan`` and the user confirms.
``record`` writes the result as one experiment-ledger row (the agent records; it never chooses a spend result) and ``compare`` measures texel RMS
between T1 and T2 / T3. The stop rule: after an identity or fit failure no further row runs. State: <root>/experiments/<piece>/material_<engine>.json."""

import hashlib
import json
import os
import re
import time
from pathlib import Path

import numpy as np

from .ledger import Ledger

ROWS = ("T1", "T2", "T3", "T4", "M1", "L1")
QUESTIONS = {"T1": "baseline", "T2": "repeat T1 exactly: is the recorded seed operationally repeatable?", "T3": "the winner's settings, the seed only changed",
             "T4": "the winner's seed, the texture alignment switched to geometry only: does legacy appearance mislead conditioning?",
             "M1": "one shared standalone material", "L1": "one local projection patch: can the remaining defect be patched?"}
#: engine -> studio action (None = no driver), its default args, ledger studio, seed control, alignment control, documentation price
ENGINES = {
    "tripo": {"action": "tripo.texture", "args": {"res": "8K", "remove_lighting": True}, "studio": "tripo", "seed": False, "alignment": False, "doc_price": None},
    "meshy": {"action": "meshy.retexture", "args": {}, "studio": "meshy", "seed": False, "alignment": False, "doc_price": None},
    "hi3d": {"action": "hi3d.texture_only", "args": {}, "studio": "hi3d", "seed": False, "alignment": False, "doc_price": None},
    "3dai_prism": {"action": None, "args": {}, "studio": None, "seed": True, "alignment": True, "doc_price": 20},
}
M1_DOC_PRICE = 10            # Material AI, the wiki's documentation figure [UNVERIFIED]; no driver
RMS_SAME = 0.01


class ExperimentError(ValueError):
    pass


def _engine(engine) -> dict:
    if engine not in ENGINES:
        raise ExperimentError(f"engine is one of {', '.join(ENGINES)}")
    return ENGINES[engine]


def _expected(action):
    from .studios.actions import ACTIONS
    a = ACTIONS.get(action)
    return None if a is None else a.expected_price


def _row_plan(engine, row) -> dict:
    e = _engine(engine)
    if row == "L1":
        return {"row": row, "question": QUESTIONS[row], "action": "repair_texture", "expected_credits": 0, "read_back_price": None, "price_source": "a local Lampway tool: free",
                "runnable": True}
    if row == "M1":
        return {"row": row, "question": QUESTIONS[row], "action": None, "expected_credits": M1_DOC_PRICE, "read_back_price": None,
                "price_source": "Material AI, the wiki's documentation figure [UNVERIFIED]; no driver", "runnable": False}
    if e["action"] is None:
        return {"row": row, "question": QUESTIONS[row], "action": None, "expected_credits": e["doc_price"], "read_back_price": None,
                "price_source": f"{engine}: the wiki's documentation figure [UNVERIFIED]; no driver", "runnable": False}
    price = _expected(e["action"])
    return {"row": row, "question": QUESTIONS[row], "action": e["action"], "expected_credits": price, "read_back_price": None,
            "price_source": "the action catalogue's expected price; the driver reads the real one back before any click" if price is not None else
            "unpublished: the driver's plan reads it back (accept_up_to_credits)", "runnable": True}


def _why_not(engine, row):
    e = _engine(engine)
    if row == "T3" and not e["seed"]:
        return f"{engine} exposes no seed control: a seed-only row cannot be run"
    if row == "T4" and not e["alignment"]:
        return f"T4 changes the texture alignment only: {engine} has no alignment control"
    return None


def plan(root, piece, engine, rows=None) -> dict:
    _piece(piece)
    e = _engine(engine)
    explicit = rows is not None
    rows = list(rows) if explicit else ["T1", "T2", "T3"]
    bad = [r for r in rows if r not in ROWS]
    if bad:
        raise ExperimentError(f"rows are {', '.join(ROWS)}; unknown: {bad}")
    out, skipped = [], []
    for r in rows:
        why = _why_not(engine, r)
        if why and explicit:
            raise ExperimentError(why if why.startswith("T4") else f"T3 changes the seed only: {why}")
        if why:
            skipped.append({"row": r, "reason": why})
            continue
        out.append(_row_plan(engine, r))
    known = [r["expected_credits"] for r in out if r["expected_credits"] is not None]
    return {"piece": piece, "engine": engine, "runnable": e["action"] is not None, "plan": out, "skipped": skipped,
            "total_expected_credits": sum(known) if len(known) == len(out) else None,
            "note": "every row is the user's confirm; T2 and T3 deliberately repeat a spend (T2 buys only repeatability knowledge); upscale after choosing a winner; "
                    "stop at the first identity or fit failure"}


def _piece(piece):
    if not re.match(r"^[A-Za-z0-9_\-]{1,64}$", str(piece or "")):
        raise ExperimentError("piece is a plain name")


def _state_path(root, piece, engine) -> Path:
    return Path(root) / "experiments" / piece / f"material_{engine}.json"


def _state(root, piece, engine) -> dict:
    p = _state_path(root, piece, engine)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"piece": piece, "engine": engine, "records": []}


def _latest(st, row):
    hits = [r for r in st["records"] if r["row"] == row]
    return hits[-1] if hits else None


def _stop(st):
    for r in st["records"]:
        failed = [k for k in ("identity", "fit") if not r[f"{k}_pass"]]
        if failed:
            return f"stop: {r['row']} failed {' and '.join(failed)}: fix the source (identity and fit come before any further texture spend)"
    return None


def run(root, piece, engine, row, acceptance) -> dict:
    _piece(piece)
    e = _engine(engine)
    if row not in ROWS:
        raise ExperimentError(f"row is one of {', '.join(ROWS)}")
    p = _row_plan(engine, row)
    if not p["runnable"]:
        have = [k for k, v in ENGINES.items() if v["action"]]
        raise ExperimentError(f"no driver for {engine if row not in ('M1',) else 'Material AI'}: only {', '.join(have)} have one; the plan is returned for the captain")
    why = _why_not(engine, row)
    if why:
        raise ExperimentError(why)
    if not (isinstance(acceptance, dict) and acceptance.get("accepted") is True):
        raise ExperimentError("the source needs a passing asset_acceptance first (run lampway_asset_acceptance on the saved Smart UV copy and pass its result)")
    st = _state(root, piece, engine)
    stop = _stop(st)
    if stop:
        raise ExperimentError(stop)
    if row in ("T2", "T3", "T4") and _latest(st, "T1") is None:
        raise ExperimentError(f"{row} {'repeats T1 exactly' if row == 'T2' else 'varies T1'}: record T1 first")
    args = dict(e["args"])
    if row == "L1":
        return {"state": "ready", "row": row, "tool": "repair_texture", "expected_credits": 0, "how": "a free local patch: call lampway_repair_texture, then record L1"}
    return {"state": "needs_approval", "row": row, "studio_action": e["action"], "args": args, "expected_credits": p["expected_credits"],
            "acceptance": {k: acceptance.get(k) for k in ("object", "mesh_hash")},
            "how": f"call lampway_studio_plan with action {e['action']!r} and these args; the driver reads the price back and the user confirms it in the Studios panel; "
                   "then record the row with the texture it produced"}


def _jail(root, rel) -> Path:
    full = Path(rel) if os.path.isabs(rel) else Path(root) / rel
    real_root, real = Path(os.path.realpath(root)), Path(os.path.realpath(full))
    if real != real_root and real_root not in real.parents:
        raise ExperimentError(f"{rel} is outside the project root")
    if not real.is_file():
        raise ExperimentError(f"{rel} is not a file")
    return real


def record(root, piece, engine, row, texture, identity_pass, fit_pass, read_back_price=None, seed=None, note="") -> dict:
    _piece(piece)
    e = _engine(engine)
    if row not in ROWS:
        raise ExperimentError(f"row is one of {', '.join(ROWS)}")
    path = _jail(root, texture)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    studio = "local" if row == "L1" else e["studio"]
    if studio is None:
        raise ExperimentError(f"{engine} has no driver: nothing of it can have run")
    cost = {} if row == "L1" else {"generation_credits": int(read_back_price), "price_source": "the driver's read-back"} if read_back_price is not None else {}
    led = Ledger(Path(root) / "ledger" / "runs.jsonl").record({
        "piece": piece, "stage": "texture", "studio": studio, "seed": seed if (isinstance(seed, int) and e["seed"]) else "not_exposed",
        "settings": {"experiment": "material", "row": row, "engine": engine, "args": e["args"], "identity_pass": bool(identity_pass), "fit_pass": bool(fit_pass)},
        "output_hashes": [sha], "cost": cost, "reason": f"{row}: {QUESTIONS[row]}" + (f"; {note}" if note else "")})
    st = _state(root, piece, engine)
    st["records"].append({"row": row, "texture": os.path.relpath(path, os.path.realpath(root)), "sha256": sha, "ledger_id": led["id"],
                          "identity_pass": bool(identity_pass), "fit_pass": bool(fit_pass), "when": time.strftime("%Y-%m-%dT%H:%M:%S")})
    p = _state_path(root, piece, engine)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, indent=1), encoding="utf-8")
    return {"row": row, "ledger_id": led["id"], "sha256": sha, "stop": _stop(st)}


def _rms(root, a, b):
    from PIL import Image
    A = np.asarray(Image.open(_jail(root, a)).convert("RGB"), dtype=np.float64) / 255.0
    B = np.asarray(Image.open(_jail(root, b)).convert("RGB"), dtype=np.float64) / 255.0
    if A.shape != B.shape:
        raise ExperimentError(f"{a} and {b} differ in size ({A.shape[:2]} vs {B.shape[:2]}): compare textures of the same resolution")
    return round(float(np.sqrt(((A - B) ** 2).mean())), 6)


def compare(root, piece, engine) -> dict:
    st = _state(root, piece, engine)
    t1, t2, t3 = (_latest(st, r) for r in ("T1", "T2", "T3"))
    c12 = _rms(root, t1["texture"], t2["texture"]) if t1 and t2 else None
    c13 = _rms(root, t1["texture"], t3["texture"]) if t1 and t3 else None
    verdicts = {}
    if c12 is not None:
        verdicts["T2"] = f"repeatable (texel RMS {c12})" if c12 <= RMS_SAME else f"not repeatable: identical inputs differ by texel RMS {c12}"
    if c13 is not None:
        verdicts["T3"] = f"the seed matters (texel RMS {c13})" if c13 > RMS_SAME else f"the seed changes little (texel RMS {c13})"
    return {"piece": piece, "engine": engine, "runs": [{k: r[k] for k in ("row", "ledger_id", "sha256", "identity_pass", "fit_pass")} for r in st["records"]],
            "comparison": {"t1_vs_t2_rms": c12, "t1_vs_t3_rms": c13, "verdicts": verdicts}, "stop": _stop(st)}
