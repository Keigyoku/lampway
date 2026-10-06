# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""lampway_fit (canon 03 B and G, IMPLEMENTATION_PLAN item 13): the fit of one piece as the canonical ORDER, each arrow a refusal, and
the record of what ran.

    intake -> proportion -> match -> place -> pose_correct -> pose -> openings -> conform -> bind -> weights -> validate -> export

* A stage runs only after every earlier stage is recorded (``conform`` is not applicable when no part is cloth or leather); a refusal
  names every missing stage and its tool.
* ``intake`` records each part's ROLE (metal | leather | cloth | embroidery): "the captain or the recipe says, never the render's
  colour" (G03.3).
* ``match`` is the captain's sign-off on the render beside the V3 turnarounds (INV-03.5): ``captain_seen`` with the render's sha256.
* ``pose_correct`` has no tool in Lampway (canon 03 F.2): the stage records the measured rigid correction per segment the caller passes.
* ``conform`` refuses a metal part (INV-03.2) and is otherwise not built: the soft-part deformer waits on the captain's decision 03-H2.
* ``intake`` needs ``body``, a fit_body package: verified there (its package_sha256 recorded); ``weights`` needs its native weight
  sidecar (fit_body verb=weights) and the same package_sha256.
* A geometry stage (pose_correct, openings, conform: armor_piece's geometry steps) after a texture recorded in the piece's
  armor_piece run (step 13) needs ``texture_discard_ack`` (INV-03.14).
* Every other stage delegates to its canon tool through ``call(tool, args)`` (the tool's own door and refusals apply) and appends
  {stage, tool, inputs_sha256, receipt_sha256, decider} to ``<piece>/fit/fit.json``; a failing tool records nothing.
* Receipt: {piece, stage, ok, receipt_path, sha256, next, limits_status}; ``status`` adds why each later stage is refused.

Not built here: the source-part check (the detached-glove guard) and the body package's "closed, head included" check (canon 03 G);
the motion acceptance in UE (B.13) is outside the order."""

import hashlib
import json
import time
from pathlib import Path

STAGES = ("intake", "proportion", "match", "place", "pose_correct", "pose", "openings", "conform", "bind", "weights", "validate", "export")
ROLES = ("metal", "leather", "cloth", "embroidery")
SOFT = ("leather", "cloth")
#: stage -> (the api tool it delegates to, the default arguments it adds) - None: no tool (a recorded decision or measurement)
TOOLS = {"intake": ("normalize_mesh", {}), "proportion": ("run_tool", {"name": "piece_ratios"}), "match": (None, {}), "place": ("fit_place", {}),
         "pose_correct": (None, {}), "pose": ("fit_pose", {}), "openings": ("fit_openings", {"stage": "detect"}), "conform": (None, {}),
         "bind": ("fit_bind", {"stage": "bind"}), "weights": ("fit_bind", {"stage": "weights"}), "validate": ("fit_validate", {"stage": "validate"}),
         "export": ("fit_export", {})}
KIND_ARG = ("place", "pose")             # the tools that take the piece kind
GEOMETRY = ("pose_correct", "openings", "conform")    # armor_piece STEPS marks openings geometry and fit_place not


def _sha(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, default=str).encode()).hexdigest()


def _path(root, piece):
    return Path(root) / piece / "fit" / "fit.json"


def _load(root, piece):
    p = _path(root, piece)
    return json.loads(p.read_text()) if p.exists() else {"schema": "lampway.fit/1", "piece": piece, "kind": None, "roles": {}, "stages": []}


def _not_applicable(rec):
    return [] if not rec["roles"] or any(r in SOFT for r in rec["roles"].values()) else ["conform"]


def _tool_name(stage):
    t = TOOLS[stage][0]
    if t is None:
        return {"match": "the captain's sign-off", "pose_correct": "a recorded rigid correction per segment", "conform": "not built"}[stage]
    return "lampway_run_tool piece_ratios" if t == "run_tool" else f"lampway_{t}"


def _status(rec):
    done = [s["stage"] for s in rec["stages"]]
    skip = _not_applicable(rec)
    todo = [s for s in STAGES if s not in done and s not in skip]
    return {"ok": True, "piece": rec["piece"], "kind": rec["kind"], "roles": rec["roles"], "body": rec.get("body"), "done": done,
            "not_applicable": skip, "next": [f"lampway_fit stage={s}" for s in todo[:1]],
            "refused": {s: f"needs {todo[0]} first" for s in todo[1:]}}


def _textured(root, piece):
    from . import armor_piece as _AP
    return any(e["step"] == _AP.TEXTURE for e in _AP.run_record(root, piece)["events"])


def _refuse(error, *help_):
    return {"ok": False, "error": error, "help": list(help_)}


def run(stage, piece, root, call, kind="", roles=None, args=None, decider="agent", body="", texture_discard_ack=False):
    if stage != "status" and stage not in STAGES:
        return _refuse(f"stage is status | {' | '.join(STAGES)}", "lampway_fit stage=status")
    rec = _load(root, piece)
    if stage == "status":
        return _status(rec)
    args = dict(args or {})
    done = {s["stage"] for s in rec["stages"]}
    skip = set(_not_applicable(rec))
    missing = [s for s in STAGES[: STAGES.index(stage)] if s not in done and s not in skip]
    if missing:
        names = ", ".join(f"{s} ({_tool_name(s)})" for s in missing)
        return _refuse(f"{stage} needs {names} first: canon 03 B - each arrow of the fit order is a refusal if skipped",
                       f"lampway_fit stage={missing[0]}")
    if stage in GEOMETRY and _textured(root, piece) and not texture_discard_ack:
        return _refuse(f"{stage} changes the geometry and {piece} has a texture recorded (armor_piece step 13): texturing comes last (canon 03 "
                       f"INV-03.14). Pass texture_discard_ack=true to discard it (then re-run steps 13-14)")
    if stage == "intake":
        roles = dict(roles or {})
        parts = list(args.pop("parts", None) or roles)
        bad = [f"{p} ({roles[p]})" for p in parts if p in roles and roles[p] not in ROLES]
        if bad:
            return _refuse(f"unknown role for {', '.join(bad)}: a role is {' | '.join(ROLES)}")
        unroled = [p for p in parts if p not in roles]
        if not parts or unroled:
            return _refuse(f"no role for {', '.join(unroled) or 'any part'}: the captain or the recipe says metal/leather/cloth/embroidery, "
                           f"never the render's colour (canon 03 INV-03.2, G03.3)")
        if not body:
            return _refuse("intake needs body: the fit_body package dir (lampway_fit_body verb=build; canon 03 A input 2, the native body)",
                           "lampway_fit_body verb=build")
        pkg = call("fit_body", {"verb": "verify", "out": body})
        if not pkg.get("ok"):
            return _refuse(f"intake: lampway_fit_body refused the body package: {pkg.get('error')}", *(pkg.get("help") or []))
        rec["roles"], rec["kind"] = roles, kind or rec["kind"]
        rec["body"] = {"package": body, "package_sha256": pkg.get("package_sha256")}
    if stage == "match":
        if args.get("captain_seen") is not True or len(str(args.get("render_sha256", ""))) != 64:
            return _refuse("match is the captain's review of the render beside the V3 turnarounds (canon 03 INV-03.5): pass captain_seen=true "
                           "with the render's sha256")
    if stage == "pose_correct" and not isinstance(args.get("segments"), list):
        return _refuse("pose_correct records the measured rigid correction per segment (canon 03 B.5; no Lampway tool yet): pass segments "
                       "[{segment, bone, angle_deg, axis}] (an empty list when every segment is within its bone)")
    if stage == "conform":
        parts = list(args.get("parts") or [])
        metal = [p for p in parts if rec["roles"].get(p) == "metal"]
        if metal:
            return _refuse(f"{', '.join(metal)} {'is' if len(metal) == 1 else 'are'} metal: a metal part never conforms - it moves by ONE "
                           f"similarity (canon 03 INV-03.2)")
        return _refuse("conform is not built: the soft-part deformer for cloth and leather waits on the captain's decision 03-H2 (canon 03 B, "
                       "the measured candidates)")
    if stage == "weights":
        pkg = call("fit_body", {"verb": "weights", "out": rec["body"]["package"]})
        if not pkg.get("ok"):
            return _refuse(f"weights: lampway_fit_body refused the body package: {pkg.get('error')}", *(pkg.get("help") or []))
        if pkg.get("package_sha256") != rec["body"]["package_sha256"]:
            return _refuse("weights: the body package changed since intake (package_sha256): re-run the fit from intake on one body",
                           "lampway_fit stage=status")
    if stage == "openings" and texture_discard_ack:
        args["texture_discard_ack"] = True
    tool, defaults = TOOLS[stage]
    result = None
    if tool is not None:
        targs = dict(defaults, **args)
        if stage in KIND_ARG and kind and "kind" not in targs:
            targs["kind"] = kind
        result = call(tool, targs)
        if not result.get("ok"):
            return _refuse(f"{stage}: {_tool_name(stage)} refused: {result.get('error')}", *(result.get("help") or []))
    else:
        result = {"recorded": args, "decider": decider}
    row = {"stage": stage, "tool": tool, "inputs_sha256": _sha(args), "receipt_sha256": _sha(result), "decider": decider, "at": round(time.time(), 3)}
    rec["stages"].append(row)
    p = _path(root, piece)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=1, sort_keys=True))
    st = _status(rec)
    return {"ok": True, "piece": piece, "stage": stage, "receipt_path": str(p.relative_to(root)) if p.is_relative_to(root) else str(p),
            "sha256": row["receipt_sha256"], "next": st["next"], "limits_status": (result.get("limits") or {}).get("status"), "result": result}
