# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""workflow_reference_to_asset (specs/mixar_docs/workflow_reference_to_asset.md): one piece through the existing tools in order, stopping at every gate.

The steps are the Lampway tools of the docs' 'Reference to finished asset' chain (image, mesh, prep, retopo, uv, bake, texture, pbr, rig, preview, export),
each with its cost class: local steps run through the same api door the agent uses (each on a COPY: _prep, _retopo, _uv ...), a SPEND step is never run here:
it is blocked with the plan to make and the user's click as its only confirm (gates.spend has no value but stop). The first blocked or failed step stops the
chain. Every step appends one row to <root>/<piece>/decisions.jsonl ({id, at, step, kind: choice | refusal | measurement | approval, by, detail}, never
rewritten); state.json lets resume skip what is done; workflow_report.md is the plan as a table. Two runs touching the same object at once are refused."""

import json
import time
import uuid
from pathlib import Path

from . import common as C

# step -> (agent tool, api function or None, cost)
STEPS = {
    "image": ("lampway_image_gen", None, "spend"),
    "mesh": ("lampway_image_to_3d", "image_to_3d", "local"),
    "prep": ("lampway_mesh_prep", "mesh_prep", "local"),
    "retopo": ("lampway_retopo", "retopo", "local"),
    "uv": ("lampway_uv_unwrap", "uv_unwrap", "local"),
    "bake": ("lampway_bake_maps", "bake_maps", "local"),
    "texture": ("lampway_texture_gen", "texture_gen", "spend"),
    "pbr": ("lampway_pbr_pack", "pbr_pack", "local"),
    "rig": ("lampway_auto_rig", "auto_rig", "local"),
    "preview": ("lampway_render_video", "render_video", "local"),
    "export": ("lampway_export_piece", "export_piece", "local"),
}
ROUTES = ("generate", "algorithmic", "existing")
TARGETS = ("unreal", "unity", "godot")
_BUSY = set()


def _dir(root, piece):
    d = Path(root) / piece
    d.mkdir(parents=True, exist_ok=True)
    return d


def _row(d, step, kind, by, detail):
    r = {"id": uuid.uuid4().hex[:12], "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": step, "kind": kind, "by": by, "detail": detail}
    with open(d / "decisions.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(r, sort_keys=True) + "\n")
    return r


def _args(step, cur, piece, first, reference, target):
    if step == "prep":
        return {"object": cur}
    if step == "retopo":
        return {"object": cur, "target_faces": 2000}
    if step == "uv":
        return {"object": cur}
    if step == "bake":
        return {"source": first, "target": cur, "out_dir": f"{piece}/bake"}
    if step == "rig":
        return {"object": cur}
    if step == "preview":
        return {"object": cur, "out": f"{piece}/preview.mp4", "frames": 24}
    if step == "export":
        return {"object": cur, "out_dir": f"{piece}/export_{target}"}
    if step == "mesh":
        return {"images": {"Front": reference}, "mode": "extrude", "name": f"{piece}_mesh"}
    return {}


def _summary(res):
    keep = {k: res[k] for k in ("object", "mesh", "armature", "files", "file", "out", "atlas") if k in res}
    rep = res.get("report") if isinstance(res.get("report"), dict) else {}
    keep["report"] = {k: v for k, v in list(rep.items())[:8] if not isinstance(v, (dict, list))}
    return keep


def _write_report(d, piece, plan):
    lines = [f"# {piece}: reference to asset", "", "| step | tool | cost | gate | status | object / reason |", "|---|---|---|---|---|---|"]
    for s in plan:
        lines.append(f"| {s['step']} | {s['tool']} | {s['cost']} | {s['gate']} | {s['status']} | {s.get('object') or s.get('reason') or ''} |")
    (d / "workflow_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(root, piece, reference="", route="existing", existing_object="", steps=None, gates=None, target="unreal", run=False, resume=False, call=None):
    if not piece:
        raise C.FeatureError("piece names the piece (its folder holds decisions.jsonl and the report)")
    if route not in ROUTES:
        raise C.FeatureError("route is generate | algorithmic | existing")
    g = dict(gates or {})
    if g.get("spend", "stop") != "stop":
        raise C.FeatureError("gates.spend is stop: there is no 'auto' spend; only the user confirms a spend, in the Client (the runner never can)")
    if target not in TARGETS:
        raise C.FeatureError("target is unreal | unity | godot")
    if route == "existing" and not existing_object:
        raise C.FeatureError("route existing needs existing_object (the mesh to take through the chain)")
    if route != "existing" and not reference:
        raise C.FeatureError(f"route {route} needs reference (the clean reference image)")
    order = list(steps or (["prep", "retopo", "uv", "texture", "pbr", "rig", "preview", "export"] if route == "existing" else
                           ["image", "mesh", "prep", "retopo", "uv", "texture", "pbr", "rig", "preview", "export"]))
    bad = [s for s in order if s not in STEPS]
    if bad:
        raise C.FeatureError(f"unknown step {bad[0]!r}: the steps are {', '.join(STEPS)}")
    d = _dir(root, piece)
    stp = d / "workflow_state.json"
    state = json.loads(stp.read_text()) if (resume and stp.exists()) else {}
    plan = []
    for s in order:
        tool, _fn, cost = STEPS[s]
        cost = "spend" if (s == "mesh" and route == "generate") else cost
        plan.append({"step": s, "tool": tool, "cost": cost, "gate": "captain" if cost == "spend" else "none", "status": "pending"})
    if not run:
        _write_report(d, piece, plan)
        return {"piece": piece, "run": False, "plan": plan, "decisions": str(d / "decisions.jsonl"), "report": str(d / "workflow_report.md")}
    first = existing_object or ""
    if first:
        C.need_object(first)
    cur = state.get("current") or first
    if cur and cur in _BUSY:
        raise C.FeatureError(f"{cur} is in another chain's step right now: one chain per object at a time")
    try:
        if cur:
            _BUSY.add(cur)
        stop = False
        for s in plan:
            name = s["step"]
            if stop:
                continue
            done = state.get("done", {})
            if resume and name in done:
                s.update(status="done", skipped=True, object=done[name].get("object"))
                cur = done[name].get("object") or cur
                continue
            tool, fn, _cost = STEPS[name]
            if s["cost"] == "spend":
                reason = (f"a spend step: plan it with {tool} (it answers with the action and price) and wait for the user's click in the Client; the "
                          "runner never confirms a spend")
                s.update(status="blocked", reason=reason)
                _row(d, name, "refusal", "rule", {"tool": tool, "reason": reason})
                stop = True
                continue
            args = _args(name, cur, piece, first, reference, target)
            res = call(fn, args)
            if not res.get("ok"):
                s.update(status="blocked", reason=res.get("error"), help=res.get("help"))
                _row(d, name, "refusal", "rule", {"tool": tool, "args": args, "error": res.get("error")})
                stop = True
                continue
            obj = res.get("object") or res.get("mesh") or cur
            s.update(status="done", object=obj)
            _row(d, name, "measurement", "agent", {"tool": tool, "args": args, "result": _summary(res)})
            state.setdefault("done", {})[name] = {"object": obj}
            cur = obj
            state["current"] = cur
            stp.write_text(json.dumps(state, indent=1))
    finally:
        _BUSY.discard(first)
    _write_report(d, piece, plan)
    return {"piece": piece, "run": True, "plan": plan, "current_object": cur, "decisions": str(d / "decisions.jsonl"), "report": str(d / "workflow_report.md")}
