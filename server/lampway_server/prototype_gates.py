"""prototype_gates: "playable core before asset polish" as recorded gates (specs/wiki/prototype_gates.md). Pure python on the experiment ledger.

Passes run in the wiki's order (Core, Look, Feedback, Export), each with a generation allowance (the wiki's proposals, editable per project) and a gate text.
A generation spend for a pass is answered from the record, not from the agent's say-so: refused until every earlier pass has passed, refused when the pass
allows no generation or its allowance is used; each allowed answer uses one generation (a ledger row). A pass owned by the captain is passed only by the
captain: an agent's pass with evidence is recorded as ``proposed`` and passes nothing; without evidence it is refused. Nothing here spends: it only answers
whether a spend may be planned. Every event is a ledger row of kind ``gate`` (<root>/ledger/runs.jsonl)."""

import time
from pathlib import Path

from .ledger import Ledger

ORDER = ("Core", "Look", "Feedback", "Export")


class GateError(ValueError):
    pass


def _ledger(root) -> Ledger:
    return Ledger(Path(root) / "ledger" / "runs.jsonl")


def _rows(root, project):
    return [r for r in _ledger(root).rows("gate") if r.get("project") == project]


def define(root, project, passes) -> dict:
    if not str(project or "").strip():
        raise GateError("name the project")
    names = [p.get("name") for p in passes or []]
    if not names or names != [n for n in ORDER if n in names] or len(set(names)) != len(names):
        raise GateError(f"passes are named from Core, Look, Feedback, Export, in that order (got {names})")
    clean = []
    for p in passes:
        a = p.get("generation_allowance")
        if not isinstance(a, int) or isinstance(a, bool) or a < 0:
            raise GateError(f"{p['name']}: generation_allowance is a whole number >= 0")
        if not str(p.get("gate") or "").strip():
            raise GateError(f"{p['name']}: the gate says what must work (the wiki's matrix gives one per pass)")
        owner = p.get("owner", "captain")
        if owner not in ("captain", "agent"):
            raise GateError(f"{p['name']}: owner is captain | agent")
        clean.append({"name": p["name"], "generation_allowance": a, "gate": str(p["gate"]), "owner": owner})
    _ledger(root).record_event("gate", {"project": project, "event": "define", "passes": clean})
    return {"project": project, "passes": clean, "note": "the allowances are proposed limits, not claims about vendor minimum charges"}


def _state(root, project):
    rows = _rows(root, project)
    defs = [r for r in rows if r["event"] == "define"]
    if not defs:
        raise GateError(f"no passes for {project!r}: define the passes first")
    passes = {p["name"]: dict(p, state="open", used=0) for p in defs[-1]["passes"]}
    t0 = defs[-1]["t"]
    for r in rows:
        if r["t"] < t0 or r["event"] == "define":
            continue
        p = passes.get(r.get("pass"))
        if p is None:
            continue
        if r["event"] == "record_gate":
            p["state"] = r["state"]
        elif r["event"] == "spend":
            p["used"] += 1
    return list(passes.values())


def record_gate(root, project, gate_result) -> dict:
    g = gate_result if isinstance(gate_result, dict) else {}
    passes = {p["name"]: p for p in _state(root, project)}
    p = passes.get(g.get("pass"))
    if p is None:
        raise GateError(f"no pass {g.get('pass')!r}; the passes are {list(passes)}")
    if g.get("result") not in ("pass", "fail"):
        raise GateError("result is pass | fail")
    by = g.get("by") if g.get("by") in ("captain", "agent") else "agent"
    evidence = str(g.get("evidence") or "").strip()
    if by == "agent" and p["owner"] == "captain" and g["result"] == "pass" and not evidence:
        raise GateError(f"{p['name']} is the captain's gate: an agent can only propose its pass, with evidence (a build, a capture, a file)")
    state = ("proposed" if by == "agent" and p["owner"] == "captain" else "passed") if g["result"] == "pass" else "failed"
    _ledger(root).record_event("gate", {"project": project, "event": "record_gate", "pass": p["name"], "result": g["result"], "state": state, "by": by,
                                        "evidence": evidence, "when": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return {"pass": p["name"], "state": state, "by": by}


def may_spend(root, project, spend) -> dict:
    s = spend if isinstance(spend, dict) else {}
    if s.get("kind") not in ("asset", "material", "vfx"):
        raise GateError("spend.kind is asset | material | vfx")
    passes = _state(root, project)
    names = [p["name"] for p in passes]
    target = s.get("pass") or next((p["name"] for p in passes if p["state"] != "passed"), names[-1])
    if target not in names:
        raise GateError(f"no pass {target!r}; the passes are {names}")
    for p in passes:
        if p["name"] == target:
            break
        if p["state"] != "passed":
            raise GateError(f"{p['name']} has not passed: {p['gate']} (state {p['state']}); no {target} spend until it does")
    p = next(x for x in passes if x["name"] == target)
    if p["generation_allowance"] == 0:
        raise GateError(f"{p['name']} allows no generation: {p['gate']}")
    if p["used"] >= p["generation_allowance"]:
        raise GateError(f"the {p['name']} allowance of {p['generation_allowance']} generations is used; pass the gate ({p['gate']}) or raise the allowance")
    _ledger(root).record_event("gate", {"project": project, "event": "spend", "pass": p["name"], "spend_kind": s["kind"], "credits": s.get("credits"),
                                        "when": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return {"allowed": True, "pass": p["name"], "remaining_allowance": p["generation_allowance"] - p["used"] - 1,
            "reason": f"every pass before {p['name']} has passed; the spend itself is still the user's click in the Client"}


def status(root, project) -> dict:
    passes = _state(root, project)
    cur = next((p["name"] for p in passes if p["state"] != "passed"), None)
    return {"project": project, "passes": passes, "current": cur}
