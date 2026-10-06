# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""character_pipeline: the character route the videos repeat (concept, parts, assemble, retopo/UV/bake, texture, rig, weights, export, retarget test) as
thirteen gated stages (specs/wiki/character_pipeline.md).

A SEQUENCER and a RECORD like armor_piece_pipeline. ``plan`` lists the stages with their tools (availability read from the live tool door), spend flags and
budgets. ``record`` appends one gate (pass | fail + evidence) after the order laws: a stage needs the stage before it passed ("nothing proceeds on an
unverified stage") and rigging needs the assembly passed ("fit before rigging"). ``run`` executes the calls the caller gives per stage through the executor
(``api.call``), stops at the first failed gate, at the first spend stage (the user's click confirms spends, never this tool) and at a stage whose tools are
not built. The MetaHuman conform is a UE editor action: it is a ``needs_decision`` leg until the Blender-to-UE render parity exploration settles the UE side."""

import json
import time
from pathlib import Path
from typing import Callable, Optional

#: n, name, tools, studio_action (spend) or None, credits per part
STAGES = (
    (1, "reference pack", ("view_verify",), None, 0),
    (2, "generate parts", (), "tripo.mesh", 100),
    (3, "prep and segment", ("mesh_prep", "segment_mesh"), None, 0),
    (4, "assemble (fit)", ("mirror_pair", "mesh_join_boolean"), None, 0),
    (5, "retopology to the part budgets", ("retopo", "part_budget_plan"), None, 0),
    (6, "UV unwrap", ("uv_unwrap",), None, 0),
    (7, "bake maps", ("bake_maps",), None, 0),
    (8, "projection texture", ("texture_gen", "repair_texture"), "tripo.texture", 35),
    (9, "auto rig", ("auto_rig",), None, 0),
    (10, "weights", ("weight_audit", "weight_cleanup"), None, 0),
    (11, "secondary chains", ("secondary_chain_rig",), None, 0),
    (12, "skeleton check and export", ("skeleton_export_check", "export_piece"), None, 0),
    (13, "retarget test", ("animation_retarget", "anim_check"), None, 0),
)
ASSEMBLY, RIG_STAGES = 4, (9, 10, 11)
TARGETS = ("unreal_mannequin", "metahuman", "mixamo", "vrm")
UE_LEG = {"state": "needs_decision", "step": "MetaHuman conform (Mesh to MetaHuman identity, a saved baking pose, a separately exported weight target)",
          "reason": "a UE editor action recorded as a captain-run receipt (editor_connection_receipt); the UE editor leg waits on the Blender-to-UE render "
                    "parity exploration, so nothing here runs or plans it yet"}


class PipelineError(ValueError):
    pass


def _dir(root, cid) -> Path:
    if not str(cid or "").strip() or any(c in str(cid) for c in "/\\") or str(cid).startswith("."):
        raise PipelineError("character_id is a plain name (no slashes)")
    return Path(root) / str(cid) / "pipeline"


def run_record(root, cid) -> dict:
    p = _dir(root, cid) / "run.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"character_id": cid, "gates": []}


def _save(root, cid, rec):
    d = _dir(root, cid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "run.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")


def _last(rec, n) -> Optional[str]:
    g = [x["gate"] for x in rec["gates"] if x["stage"] == n]
    return g[-1] if g else None


def _stage(n):
    for s in STAGES:
        if s[0] == int(n):
            return s
    raise PipelineError("stages are 1..13")


def _check_order(rec, n):
    if n in RIG_STAGES and _last(rec, ASSEMBLY) != "pass":
        raise PipelineError(f"fit before rigging: stage {n} ({_stage(n)[1]}) needs the assembly (stage {ASSEMBLY}) passed first")
    if n > 1 and _last(rec, n - 1) != "pass":
        raise PipelineError(f"stage {n - 1} ({_stage(n - 1)[1]}) has not passed: nothing proceeds on an unverified stage; record its gate first")


def _parts(parts) -> list:
    out = []
    for p in parts or []:
        if not isinstance(p, dict) or not str(p.get("name") or "").strip():
            raise PipelineError("each part is {name, budget (triangles), rigid_bone (or null)}")
        if p.get("budget") is not None and (not isinstance(p["budget"], int) or p["budget"] <= 0):
            raise PipelineError(f"part {p['name']!r}: budget is a whole number of triangles")
        out.append({"name": p["name"], "budget": p.get("budget"), "rigid_bone": p.get("rigid_bone")})
    if not out:
        raise PipelineError("the pipeline needs the character's parts: [{name, budget, rigid_bone}]")
    return out


def plan(root, character_id, parts, target="unreal_mannequin", from_stage=1, to_stage=13, tools=None) -> dict:
    if target not in TARGETS:
        raise PipelineError(f"target {target!r} is not one of {', '.join(TARGETS)}")
    parts = _parts(parts)
    a, b = int(from_stage), int(to_stage)
    if not (1 <= a <= 13 and 1 <= b <= 13) or b < a:
        raise PipelineError("from_stage and to_stage are 1..13, from_stage first")
    door = set(tools or [])
    rec = run_record(root, character_id)
    stages = []
    for n, name, tl, action, per_part in STAGES:
        if not a <= n <= b:
            continue
        missing = [t for t in tl if t not in door]
        last = _last(rec, n)
        state = ("done" if last == "pass" else "gate_failed" if last == "fail" else "needs_approval" if action else "no_tool" if missing else "ready")
        row = {"n": n, "name": name, "tools": list(tl), "missing_tools": missing, "spend": bool(action), "studio_action": action,
               "credits_planned": per_part * len(parts) if action and last != "pass" else 0, "state": state}
        if n == 5:
            row["part_budgets"] = {p["name"]: p["budget"] for p in parts}
        if n == 9:
            row["rigid_parts"] = {p["name"]: p["rigid_bone"] for p in parts if p["rigid_bone"]}
        stages.append(row)
    nxt = next((s for s in stages if s["state"] != "done"), None)
    return {"character_id": character_id, "target": target, "stages": stages, "total_credits_planned": sum(s["credits_planned"] for s in stages),
            "next": nxt and {"n": nxt["n"], "state": nxt["state"]}, "ue_leg": dict(UE_LEG) if target == "metahuman" else None,
            "note": "spend stages are needs_approval: the user's click in the Client confirms them; this tool never does"}


def record(root, character_id, stage, gate, evidence="", by="agent", tools=None) -> dict:
    n = int(stage)
    _stage(n)
    if gate not in ("pass", "fail"):
        raise PipelineError("gate is pass | fail")
    if not str(evidence or "").strip():
        raise PipelineError("a gate names its evidence (a measurement, a file, the user's word)")
    rec = run_record(root, character_id)
    _check_order(rec, n)
    rec["gates"].append({"stage": n, "gate": gate, "evidence": str(evidence), "by": by, "when": time.strftime("%Y-%m-%dT%H:%M:%S")})
    _save(root, character_id, rec)
    return {"stage": n, "gate": gate, "gates": len(rec["gates"])}


def _gate_of(out) -> bool:
    if not isinstance(out, dict) or not out.get("ok", True):
        return False
    return out.get("pass", True) is not False


def run(root, character_id, parts, from_stage, to_stage, stage_calls, executor: Callable, target="unreal_mannequin", tools=None) -> dict:
    p = plan(root, character_id, parts, target, from_stage, to_stage, tools)
    calls = {str(k): v for k, v in (stage_calls or {}).items()}
    done = []
    for s in p["stages"]:
        n = s["n"]
        if s["state"] == "done":
            continue
        _check_order(run_record(root, character_id), n)
        if s["spend"]:
            return {"state": "needs_approval", "stopped_at": n, "studio_action": s["studio_action"], "credits_planned": s["credits_planned"], "ran": done,
                    "reason": "a spend stage: the user confirms it in the Studios panel; record its gate once the result is accepted"}
        if s["missing_tools"]:
            return {"state": "no_tool", "stopped_at": n, "ran": done, "reason": f"stage {n} needs {', '.join(s['missing_tools'])}, which Lampway does not have yet"}
        todo = calls.get(str(n)) or []
        if not todo:
            return {"state": "waiting", "stopped_at": n, "ran": done, "reason": f"no calls given for stage {n}: pass stage_calls['{n}'] = [{{tool, args}}]"}
        outs = []
        for c in todo:
            if c.get("tool") not in s["tools"]:
                raise PipelineError(f"stage {n} runs {', '.join(s['tools'])}; {c.get('tool')!r} belongs elsewhere")
        for c in todo:
            out = executor(c["tool"], dict(c.get("args") or {}))
            outs.append({"tool": c["tool"], "ok": _gate_of(out), "error": (out or {}).get("error") if isinstance(out, dict) else None})
            if not outs[-1]["ok"]:
                break
        ok = all(o["ok"] for o in outs)
        record(root, character_id, n, "pass" if ok else "fail", evidence=json.dumps(outs), by="rule", tools=tools)
        done.append(n)
        if not ok:
            return {"state": "gate_failed", "stopped_at": n, "ran": done, "calls": outs, "reason": f"stage {n} failed its gate: fix it and run from stage {n} again"}
    return {"state": "done", "stopped_at": None, "ran": done}
