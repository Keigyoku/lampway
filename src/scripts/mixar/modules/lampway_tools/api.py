# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The tools API: what the panel's buttons, the operators and the agent's tools all call.

The server's agent tools reach it through ``blender.execute_script``::

    from mixar.modules.lampway_tools import api
    __RESULT__ = api.qa_read_tags(close_round=True)

JSON in, JSON out. A failure is ``{"ok": false, "error": ..., "help": [...]}`` (the AXI shape: it names the cause and the
next step), never a traceback into the model. Every path an argument names stays inside the project root
(``settings.project_root``); a path outside it is refused. The scene is only touched from the main thread: slow work runs
as a job (``jobs.py``) and its scene-touching tail runs from the app's timer.
"""

import functools
import inspect
import json
import os
from pathlib import Path

import bpy

from . import TOOLS_VERSION
from . import jobs
from . import albedo as AB
from . import live_load
from . import meshpaint as MP
from . import rebuild as RB
from . import runner as RUN
from .canon_door import LEGACY, NONE, Need, validate_declaration  # noqa: F401  (the door: NONE / Need for tool authors)
from .canon_door import refusal as _door_refusal, unmet as _door_unmet
from . import settings as S
from .meshqa import decisions as D
from .meshqa import live as L
from .meshqa import marks as M
from .meshqa import proposals as QP
from .meshqa import rules as QR
from .meshqa.rulings import Rulings

_rebuild_run = RB.run                    # replaced by tests: the real thing is minutes of batch work

_HELP = {
    LookupError: ["Run `api.qa_setup(object=..., recipe=...)` first, or `api.status()` to see what is configured"],
    FileNotFoundError: ["Check the path (relative paths resolve under the project root); `api.status()` shows the root"],
    S.PathOutsideProject: ["Put the file under the project root or change it: `api.settings_set(project_root=...)`"],
    RUN.ToolUnavailable: ["`api.status()` lists the interpreters; set the one named with `api.settings_set(...)`"],
    RB.TagExists: ["A tag is never overwritten: pick a new tag, or pass resume=True to finish an interrupted one"],
    ValueError: ["Fix the argument named in the error and call again"],
}


_REGISTRY = []
TOOL_DOORS = {}             # name -> (consumes, produces): derived from the same decorator as TOOL_FUNCS (the normalization door)


def tool(fn=None, *, consumes=None, produces=None):
    """Register a tool behind its door. ``consumes`` is REQUIRED: {arg: Need(...)} (the argument must name a canonical asset that
    satisfies the Need - a raw, unstamped or changed one is refused with "normalize first"), NONE("why") for a tool that reads no
    asset, or LEGACY("issue") during migration (the ratchet in canon_legacy_count.txt may only fall). The wrapped call returns
    {'ok': True, ...} from the function's dict, or {'ok': False, 'error', 'help'} for a refusal; the function joins TOOL_FUNCS, the
    door the agent's scripts call by name."""
    if fn is not None:
        raise TypeError("@tool needs consumes=: declare what this tool reads (Need(...)), or NONE('why') if it reads no asset")
    validate_declaration(consumes)

    def deco(fn):
        _REGISTRY.append(fn.__name__)
        TOOL_DOORS[fn.__name__] = (consumes, produces or {})
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*a, **kw):
            if isinstance(consumes, dict):
                try:
                    bound = sig.bind_partial(*a, **kw).arguments
                except TypeError:
                    bound = {}
                for arg, need in consumes.items():
                    value = bound.get(arg)
                    if value not in (None, ""):
                        reasons = _door_unmet(arg, value, need)
                        if reasons:
                            return _door_refusal(arg, value, reasons, need)
            try:
                out = fn(*a, **kw)
                return {"ok": True, **out} if isinstance(out, dict) else {"ok": True, "result": out}
            except Exception as exc:
                help_ = next((h for t, h in _HELP.items() if isinstance(exc, t)), ["See the error"])
                if isinstance(exc, ValueError) and not isinstance(exc, (LookupError, FileNotFoundError)):
                    help_ = help_ + [f"The call: {fn.__name__}{sig}"]          # audit F13: the shape the next call needs, not just "fix it"
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}" if not isinstance(exc, (LookupError, S.PathOutsideProject,
                        FileNotFoundError, ValueError, RUN.ToolUnavailable)) else str(exc).strip("'\""), "help": help_}
        return wrapper
    return deco


def _settings() -> S.Settings:
    return S.load()


def _p(path, root=None) -> str:
    """A path argument resolved inside the project root ('' stays '')."""
    if path in (None, ""):
        return ""
    return str(S.resolve_in_root(path, root or _settings().project_root))


# ---- settings and status

@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def settings_get():
    s = _settings()
    return {"settings": {k: (str(getattr(s, k)) if getattr(s, k) is not None else None) for k in S._FIELDS},
            "interpreters": S.interpreter_report(s)}


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def settings_set(**kw):
    s = _settings()
    for k, v in kw.items():
        if k not in S._FIELDS:
            raise ValueError(f"unknown setting {k!r}; the settings are {', '.join(S._FIELDS)}")
        setattr(s, k, int(v) if k == "nice" else str(v) if k in S._TEXT_FIELDS else Path(v))
    S.save(s)
    return {"saved": str(S._settings_file())}


def tools() -> list:
    return [{"name": t.name, "kind": t.kind, "summary": t.summary} for t in RUN.TOOLS.values()]


def _qa_summary() -> dict:
    try:
        cfg = L.load_config(bpy.context.scene)
    except LookupError:
        return {"configured": False}
    return {"configured": True, "object": cfg.object, "piece": cfg.piece, "session": cfg.session,
            "rulings_dir": cfg.rulings_dir, "candidates": cfg.candidates_path.exists(),
            "pieces": L.piece_names(bpy.context.scene)}


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def status():
    s = _settings()
    return {"version": TOOLS_VERSION, "project_root": str(s.project_root), "interpreters": S.interpreter_report(s),
            "qa": _qa_summary(), "jobs": jobs.status(), "tools": tools()}


# ---- mesh QA

@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def qa_setup(object, recipe, owner="", piece="", session="", offset=(0, 0, 0), orig_poly="", turn=0.0, rulings_dir="",
             min_perimeter=0.15, max_shell_tris=400, float_mm=3.0):
    """Point mesh QA at a mesh object. ``recipe`` = the parts json, ``owner`` = a .npy of one part index per polygon (or
    '' to use the mesh's int face attribute 'part'), ``offset`` = live frame minus the mesh's own frame (his LIFT),
    ``orig_poly`` = a rebuild's source-face map (-1 = patch)."""
    s = _settings()
    piece = piece or object
    rd = _p(rulings_dir, s.project_root) if rulings_dir else str(s.project_root / piece / "rulings")
    S.resolve_in_root(rd, s.project_root)
    cfg = L.QAConfig(object=object, recipe=_p(recipe), owner=_p(owner), rulings_dir=rd, piece=piece,
                     session=session or f"{piece}_{__import__('datetime').date.today().isoformat()}",
                     offset=tuple(float(x) for x in offset), orig_poly=_p(orig_poly), turn=float(turn),
                     min_perimeter=float(min_perimeter), max_shell_tris=int(max_shell_tris), float_mm=float(float_mm))
    if bpy.data.objects.get(object) is None:
        raise LookupError(f"no object named {object!r}; the meshes are: {sorted(o.name for o in bpy.data.objects if o.type == 'MESH')}")
    L.save_config(bpy.context.scene, cfg)
    return {"piece": piece, "object": object, "rulings_dir": rd, "session": cfg.session}


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def qa_tag_layers():
    ann = M.create_tag_layers()
    return {"layers": [l.info for l in ann.layers]}


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def qa_candidates(draw=False, piece="", collection="", prefix=None):
    """Candidates for ``piece`` (default: the active piece); with ``draw`` they are drawn into ``collection`` (default
    ``QA_<piece>``) with marker names starting ``prefix`` (default ``<piece>_``)."""
    cfg = L.load_config(bpy.context.scene, piece or None)
    out = L.compute_candidates(cfg)
    if draw:
        out["drawn"] = L.draw_candidates(cfg, collection or None, prefix)["drawn"]
    return out


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def qa_draw(piece="", collection="", prefix=None):
    return L.draw_candidates(L.load_config(bpy.context.scene, piece or None), collection or None, prefix)


def _qa_candidates_by_id(cfg) -> dict:
    if not cfg.candidates_path.exists():
        raise FileNotFoundError(f"{cfg.candidates_path} does not exist: compute the candidates first")
    return {c["id"]: c for c in json.loads(cfg.candidates_path.read_text(encoding="utf-8"))["candidates"]}


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def qa_propose(proposals=None, piece="", by="agent", rules=None, collection="", prefix=None):
    """Propose a verdict per candidate and recolour the piece's markers (delete red, hole yellow, mislabel green, keep grey and hidden;
    the label reads ``<id> <VERDICT>``). RULES FIRST: with no ``proposals`` the rules (meshqa/rules.py) decide every candidate their
    descriptors make clear and each reason names its rule; the rest is returned as ``ambiguous`` for YOUR judgement, which you give as
    ``proposals`` ({id: {verdict: delete|hole|mislabel|keep, reason?, target?}}, ``rules`` false). A re-run of the rules never replaces a
    row somebody else wrote. A proposal is NOT a ruling: only the user's tags or typed answers become rulings."""
    cfg = L.load_config(bpy.context.scene, piece or None)
    cands = _qa_candidates_by_id(cfg)
    run_rules = (proposals is None) if rules is None else bool(rules)
    new_rows, out = [], {}
    if proposals is not None:
        new_rows += QP.validate(proposals, cands, by=by)
    if run_rules:
        res = QR.propose(list(cands.values()), QR.Params(float_mm=cfg.float_mm))
        new_rows += QP.rule_rows(res["verdicts"])
        out["ambiguous"], out["ambiguous_why"] = res["ambiguous"], res["ambiguous_why"]
        out["applied"] = QP.counts(QP.rule_rows(res["verdicts"]))
    rows = QP.merge(QP.load_rows(cfg.rulings_dir, cfg.piece), new_rows, rules_run=run_rules)
    path = QP.save(cfg.rulings_dir, cfg.piece, rows)
    if not run_rules:
        decided = {r["id"] for r in rows}
        out["ambiguous"] = [i for i in cands if i not in decided]
    out.update(L.recolour(cfg, collection or None, prefix))
    return {"piece": cfg.piece, "path": str(path), "counts": QP.counts(rows), **out}


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def qa_proposals(piece=""):
    """The proposals so far for the piece (rows {id, kind, verdict, reason, by}), with counts per verdict."""
    cfg = L.load_config(bpy.context.scene, piece or None)
    rows = QP.load_rows(cfg.rulings_dir, cfg.piece)
    return {"piece": cfg.piece, "counts": QP.counts(rows), "proposals": QP.as_map(rows)}


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def qa_descriptors(piece="", ids=None, ambiguous_only=False, limit=10, offset=0):
    """COMPACT descriptors (never segments_m) of the piece's candidates, in small batches: ``ids`` picks some, ``ambiguous_only`` the ones
    nobody has proposed a verdict for yet. ``limit`` is capped at 20; page with ``offset``. This is what a model reads to judge what the
    rules left ambiguous."""
    cfg = L.load_config(bpy.context.scene, piece or None)
    cands = _qa_candidates_by_id(cfg)
    wanted = list(cands)
    if ids:
        wanted = [i for i in ids if i in cands]
    if ambiguous_only:
        decided = {r["id"] for r in QP.load_rows(cfg.rulings_dir, cfg.piece)}
        wanted = [i for i in wanted if i not in decided]
    limit = max(1, min(int(limit), 20))
    offset = max(0, int(offset))
    batch = wanted[offset:offset + limit]
    return {"piece": cfg.piece, "total": len(wanted), "offset": offset, "next_offset": offset + limit if offset + limit < len(wanted) else None,
            "descriptors": [QR.compact(cands[i]) for i in batch]}


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def qa_read_tags(apply=True, close_round=False, mislabel_to=None, piece=""):
    cfg = L.load_config(bpy.context.scene, piece or None)
    targets = {int(k): v for k, v in (mislabel_to or {}).items()}
    return L.read_tags(cfg, apply=apply, close_round=close_round, mislabel_to=targets)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def qa_rulings(piece=""):
    cfg = L.load_config(bpy.context.scene, piece or None)
    r = Rulings(cfg.rulings_dir, cfg.piece)

    def load(kind, default):
        p = r.path(kind)
        return json.loads(p.read_text()) if p.exists() else default

    rows = D.read_rows(cfg.decisions_path)
    return {"rulings_dir": cfg.rulings_dir, "deletions": len(load("deletions", {"polys": []}).get("polys", [])),
            "relabels": len(load("relabels_orig", {"relabels": []}).get("relabels", [])),
            "force_class": len(load("texel_overrides_orig", {"force_class": []}).get("force_class", [])),
            "decision_rows": len(rows),
            "answers": {"open_loop": D.latest_answers(rows, "open_loop"), "loose_shell": D.latest_answers(rows, "loose_shell")}}


# ---- the rebuild loop

_REBUILD_FIELDS = ("source_mesh", "source_owner", "relief_dir", "plates_dir", "relabel_rules", "turn", "template_material",
                   "lift", "out_root", "previous")


def _rebuild_path(cfg) -> Path:
    return Path(cfg.rulings_dir) / f"{cfg.piece}_rebuild.json"


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def rebuild_setup(source_mesh, source_owner, relief_dir, plates_dir, template_material, out_root="", relabel_rules=(),
                  turn=-90.0, lift=0.0, previous=(), piece=""):
    """What a rebuild needs besides the rulings: the SOURCE mesh and its owner map (rebuilds always start from the
    source), the relief views and plates, the live material to copy, where the outputs go, the objects to hide."""
    cfg = L.load_config(bpy.context.scene, piece or None)
    s = _settings()
    data = {"source_mesh": _p(source_mesh), "source_owner": _p(source_owner), "relief_dir": _p(relief_dir),
            "plates_dir": _p(plates_dir), "relabel_rules": list(relabel_rules), "turn": float(turn),
            "template_material": template_material, "lift": float(lift),
            "out_root": _p(out_root) if out_root else str(s.project_root / cfg.piece / "rebuilds"), "previous": list(previous)}
    S.resolve_in_root(data["out_root"], s.project_root)
    path = _rebuild_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return {"saved": str(path)}


def _spec(cfg, setup, tag, res, color_full, ornament, mesh_gold) -> RB.RebuildSpec:
    r = Rulings(cfg.rulings_dir, cfg.piece)
    for kind, empty in (("deletions", {"polys": [], "decisions": []}), ("relabels_orig", {"relabels": []}),
                        ("texel_overrides_orig", {"force_class": []})):
        if not r.path(kind).exists():
            r.path(kind).parent.mkdir(parents=True, exist_ok=True)
            r.path(kind).write_text(json.dumps(empty), encoding="utf-8")
    merged = r.path("candidates_merged")
    return RB.RebuildSpec(
        piece=cfg.piece, source_mesh=setup["source_mesh"], owner=setup["source_owner"], recipe=cfg.recipe,
        candidates=str(merged if merged.exists() else cfg.candidates_path), decisions=str(cfg.decisions_path),
        deletions=str(r.path("deletions")), relabels_orig=str(r.path("relabels_orig")),
        texel_overrides=str(r.path("texel_overrides_orig")), relief_dir=setup["relief_dir"], plates_dir=setup["plates_dir"],
        out_root=setup["out_root"], turn=setup["turn"], relabel_rules=setup["relabel_rules"], res=int(res),
        color_full=bool(color_full), ornament=ornament, mesh_gold=bool(mesh_gold))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def rebuild(tag, res=2048, color_full=False, ornament="", mesh_gold=False, read_tags=True, close_round=False,
            mislabel_to=None, resume=False, piece=""):
    """Read his tags, write the rulings, rebuild, and load the result beside the previous version.

    The rebuild runs as a background job (minutes); this returns its id at once. When it finishes the app's timer loads
    the new mesh textured next to the old one, hides the old, and points mesh QA at the new object so the loop continues.
    ``api.job_status(<id>)`` reports it."""
    cfg = L.load_config(bpy.context.scene, piece or None)
    path = _rebuild_path(cfg)
    if not path.exists():
        raise LookupError(f"no rebuild setup at {path}: call api.rebuild_setup(...) once for this piece")
    setup = json.loads(path.read_text(encoding="utf-8"))
    reading = None
    if read_tags:
        targets = {int(k): v for k, v in (mislabel_to or {}).items()}
        reading = L.read_tags(cfg, apply=True, close_round=close_round, mislabel_to=targets)
        if reading["relabels_needing_a_target"]:
            raise ValueError("green strokes still need a target part: pass mislabel_to={stroke: part} "
                             f"for {[r['stroke'] for r in reading['relabels_needing_a_target']]}, or erase them")
    spec = _spec(cfg, setup, tag, res, color_full, ornament, mesh_gold)
    RB.plan(spec, tag)                                      # validates the tag before anything starts
    if not resume:
        RB.check_fresh(spec, tag)
    settings = _settings()
    piece, previous = cfg.piece, list(setup["previous"]) + [cfg.object]

    def work():
        rep = _rebuild_run(spec, tag, settings, resume=resume, log_dir=Path(spec.out_root) / "logs" / tag)
        if not rep["ok"]:
            raise RuntimeError(f"step {rep['failed']} failed: {rep.get('error') or rep['steps'][-1].get('tail', '')[-300:]}")
        return rep

    def land(job):
        rep = job.result
        name = f"{piece}_{tag}_textured"
        res_ = live_load.load_rebuild(rep["mesh"], rep["out"], name, setup["template_material"], hide=previous,
                                      lift=setup["lift"], turn=setup["turn"])
        job.loaded = res_["name"]
        patched = Path(rep["patched"])
        cfg2 = L.load_config(bpy.context.scene, piece)
        cfg2.object = res_["name"]
        cfg2.offset = (0.0, 0.0, float(setup["lift"]))
        cfg2.owner = str(patched / f"{piece}_{tag}_owner_poly.npy")
        cfg2.orig_poly = str(patched / f"{piece}_{tag}_orig_poly.npy")
        cfg2.turn = 0.0                       # the loaded object has the rebuild's turn baked in: already the analysis frame
        L.save_config(bpy.context.scene, cfg2)

    job = jobs.start("rebuild", work, on_done=land)
    jobs.ensure_timer()
    return {"job": job.id, "tag": tag, "reading": reading, "next": f"api.job_status('{job.id}')"}


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def job_status(job=None):
    rows = jobs.status()
    if job is None:
        return {"jobs": rows}
    j = jobs.get(job)
    if j is None:
        raise LookupError(f"no job {job!r}; the jobs are: {[r['id'] for r in rows]}")
    out = {"id": j.id, "state": j.state, "error": j.error, "finish_error": j.finish_error, "loaded": getattr(j, "loaded", "")}
    if j.state == "done" and isinstance(j.result, dict):
        out["steps"] = [{"name": s["name"], "rc": s["rc"]} for s in j.result.get("steps", [])]
        out["skipped"] = j.result.get("skipped", [])
        out["mesh"] = j.result.get("mesh")
    return out


# ---- the other ported tools

@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def run_tool(name, args=(), timeout=3600):
    """Run any ported tool (``api.tools()``) as a batch job: every argument that names a path stays inside the project root."""
    s = _settings()
    if name not in RUN.TOOLS:
        raise RUN.ToolUnavailable(f"no tool {name!r}; the tools are: {', '.join(sorted(RUN.TOOLS))}")
    jailed = S.jail_args(args, s.project_root)
    # The tool's working directory is the root, so a bare file name it writes lands inside it too.
    res = RUN.run(name, jailed, s, timeout=float(timeout), log_dir=s.project_root / "logs", cwd=str(s.project_root))
    out = {"rc": res.rc, "output": res.stdout, "log": res.log, "timed_out": res.timed_out, "ok_run": res.rc == 0}
    if res.rc != 0 or res.timed_out:                  # audit F6: a failed worker is a failed call, never ok: true with rc: 1
        out.update(ok=False, error=_last_error_line(res.stdout) or f"{name} exited with code {res.rc}",
                   help=([f"The full log: {res.log}"] if res.log else []) + [
                       f"{name} timed out: pass a larger timeout, or a smaller input" if res.timed_out
                       else "Fix the input the error names, then call the tool again with the same arguments"])
    return out


def _last_error_line(text):
    """The worker's last error line (``ValueError: ...``, ``error: ...``), else its last non-empty line."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for ln in reversed(lines):
        head = ln.split(":", 1)[0]
        if ":" in ln and (head.lower() == "error" or head.endswith(("Error", "Exception", "Exit"))):
            return ln
    return lines[-1] if lines else ""


# ---- mesh-paint texturing (one entry for the panel button and the agent tool)

_MP_STAGES = ("setup", "clay", "prompt", "image", "pick", "plates", "project", "run", "albedo", "status")
_MP_KEY = "lampway_meshpaint"
_mp_generate_cmd = None                  # replaced by tests: the real thing runs lampway_server.imagegen under the server python


def _mp_setup_path(piece, root) -> Path:
    return Path(root) / piece / "meshpaint" / "setup.json"


def _mp_load():
    raw = bpy.context.scene.get(_MP_KEY)
    if not raw:
        raise LookupError("no mesh-paint setup on this scene: call meshpaint(stage='setup', piece=..., mesh=..., design_dir=...) first")
    setup = json.loads(Path(json.loads(raw)["setup"]).read_text(encoding="utf-8"))
    spec = MP.MeshPaintSpec(piece=setup["piece"], mesh=setup["mesh"], design_dir=setup["design_dir"], work_dir=setup["work_dir"],
                            turn=setup["turn"], clay_res=setup["clay_res"])
    return spec, setup


def _mp_run_tool(name, args, s, timeout=900):
    res = RUN.run(name, [str(a) for a in args], s, timeout=timeout, log_dir=s.project_root / "logs")
    if res.rc != 0:
        raise RuntimeError(f"{name} failed (rc {res.rc}): {res.stdout.strip()[-400:]}")
    return res


def _mp_clay(spec, s, res=None):
    out = Path(spec.work_dir) / "clay"
    out.mkdir(parents=True, exist_ok=True)
    for view in MP.VIEWS:
        _mp_run_tool("clay_view", [spec.mesh, out / f"clay_{view}.png", view, res or spec.clay_res, "--turn", spec.turn], s, 300)
    return {"views": list(MP.VIEWS), "dir": str(out)}


def _mp_plates(spec, s, require_all=True):
    args = MP.plate_args(spec, require_all)
    _mp_run_tool("mesh_paint_set", args, s, 300)
    return {"set": args[1]}


def _mp_projection(spec, setup, s, tag):
    base = RB.RebuildSpec(piece=spec.piece, source_mesh="", owner="", recipe=setup["recipe"], candidates="", decisions="", deletions="",
                          relabels_orig="", texel_overrides="", relief_dir=setup["relief_dir"], plates_dir="", out_root=setup["out_root"],
                          turn=spec.turn)
    return MP.projection_spec(base, spec)


def _mp_project_job(spec, setup, s, tag):
    proj = _mp_projection(spec, setup, s, tag)
    if not (Path(spec.work_dir) / "set").is_dir():
        raise LookupError("no plate set yet: pick a variant for each view and run stage 'plates' first")
    patched = Path(proj.out_root) / "patched" / f"{spec.piece}_{tag}_uv_front-y.npz"
    if not patched.exists():
        raise LookupError(f"no rebuild for tag {tag!r} yet ({patched} is missing): the projection reuses the rebuild's patched "
                          f"mesh, so run lampway_rebuild(tag={tag!r}) first, or name the tag of an existing rebuild")
    piece, template, lift, turn = spec.piece, setup["template_material"], setup["lift"], spec.turn

    def work():
        rep = _rebuild_run(proj, tag, s, resume=True, only=("relief_project", "material_masks"), out_name=MP.output_name(tag),
                           log_dir=Path(proj.out_root) / "logs" / MP.output_name(tag))
        if not rep["ok"]:
            raise RuntimeError(f"step {rep['failed']} failed: {rep.get('error') or rep['steps'][-1].get('tail', '')[-300:]}")
        return rep

    def land(job):
        rep = job.result
        name = f"{piece}_{tag}_meshpaint_textured"
        res_ = live_load.load_rebuild(rep["mesh"], rep["out"], name, template, hide=[], lift=lift, turn=turn)
        job.loaded = res_["name"]
        atlas = Path(rep["out"]) / "v3_colour_atlas.png"
        if atlas.exists():                                    # the projected albedo as the live material's base colour toggle
            ab = AB.apply(res_["material"], str(atlas))
            bpy.data.objects[res_["name"]].data.materials.clear()
            bpy.data.objects[res_["name"]].data.materials.append(bpy.data.materials[ab["material"]])
            job.albedo = ab["material"]

    job = jobs.start("meshpaint-project", work, on_done=land)
    jobs.ensure_timer()
    return job


def _mp_generate(spec, setup, s, view, template, refs, out_dir, live, count=4, named=None):
    """Run the image backend (the server's imagegen module under the server python) for one view with a prompt-library TEMPLATE; the server renders it,
    stores the rendered prompt as <out_dir>/prompt.txt and enforces the reference order by role. Returns the image files."""
    if _mp_generate_cmd is not None:
        return _mp_generate_cmd(view, template, refs, out_dir, live, count)
    if not s.python_server or not s.server_dir:
        raise RUN.ToolUnavailable("the image backend runs in the Lampway server's python: set LAMPWAY_PYTHON_SERVER and LAMPWAY_SERVER_DIR (the repo's server/)")
    import os
    import subprocess
    cmd = ["nice", "-n", str(s.nice), str(s.python_server), "-m", "lampway_server.imagegen", "--template", template,
           "--out", out_dir, "--count", str(count)] + [x for k, v in (named or {}).items() for x in ("--ref", f"{k}={v}")] + (["--live"] if live else []) \
        + (["--backend", str(s.image_backend)] if s.image_backend else [])
    # A clean Python environment for the server's own interpreter: the app's PYTHONHOME / PYTHONPATH would make a venv
    # python import Blender's stdlib and site-packages instead of its own (seen live: `No module named 'httpx'`).
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env.update(PYTHONPATH=str(s.server_dir), LAMPWAY_PROJECT_ROOT=str(s.project_root))
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=7200)
    if p.returncode != 0:
        raise RuntimeError(f"the image backend refused or failed for {view}: {(p.stdout + p.stderr).strip()[-500:]}")
    if not live:
        raise RuntimeError(f"{view}: the image backend ran as a DRY RUN (settings verified, nothing generated): pass live=true "
                           "(Tripo also needs the owner's LAMPWAY_STUDIO_ARMED=1; codex_cli needs LAMPWAY_LOCAL_CLI=1)")
    return sorted(str(f) for f in Path(out_dir).glob("*") if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and f.stem.isdigit())


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def meshpaint(stage, **kw):
    """Mesh-paint texturing. Stages: setup, clay, prompt, pick, plates, project, run (all of it, background), albedo, status."""
    s = _settings()
    if stage not in _MP_STAGES:
        raise ValueError(f"unknown stage {stage!r}; the stages are {', '.join(_MP_STAGES)}")
    if stage == "setup":
        piece = kw["piece"]
        work = str(s.project_root / piece / "meshpaint")
        data = {"piece": piece, "mesh": _p(kw["mesh"]), "design_dir": _p(kw["design_dir"]), "work_dir": work, "tag": kw["tag"],
                "recipe": _p(kw["recipe"]), "relief_dir": _p(kw["relief_dir"]), "out_root": _p(kw["out_root"]),
                "template_material": kw["template_material"], "lift": float(kw.get("lift", 0.0)), "turn": float(kw.get("turn", -90.0)),
                "clay_res": int(kw.get("clay_res", 2048))}
        path = _mp_setup_path(piece, s.project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")
        bpy.context.scene[_MP_KEY] = json.dumps({"setup": str(path)})
        return {"saved": str(path), "work_dir": work}
    if stage == "albedo":
        name = kw.get("material")
        if not name:
            raise ValueError("albedo needs material (the _albedo material)")
        AB.set_albedo(name, bool(kw.get("on", True)))
        return {"material": name, "on": AB.state(name)}
    spec, setup = _mp_load()
    if stage == "status":
        picks = MP.load_picks(spec)
        return {"piece": spec.piece, "work_dir": spec.work_dir, "clay": (Path(spec.work_dir) / "clay").is_dir(),
                "picks": picks, "plates": (Path(spec.work_dir) / "set").is_dir(), "tag": setup["tag"]}
    if stage == "clay":
        return _mp_clay(spec, s, kw.get("res"))
    if stage in ("prompt", "image"):
        view = kw["view"]
        if view not in MP.VIEWS:
            raise ValueError(f"view {view!r}: one of {list(MP.VIEWS)}")
        picks = MP.load_picks(spec)
        cons = MP.consistency_view(view, [v for v in MP.ORDER if v in picks])
        template = MP.template_for(view, cons)
        parts = {"view": view, "consistency": cons, "template": template, "refs": MP.refs_for(spec, view, cons, picks),
                 "roles": list(MP.refs_named(spec, view, cons, picks)), "out_dir": str(Path(spec.work_dir) / "runs" / view)}
        if stage == "prompt":
            return parts
        count = int(kw.get("count", 4))
        if not 1 <= count <= 4:
            raise ValueError(f"count {count}: 1 to 4 images per view")
        files = _mp_generate(spec, setup, s, view, template, parts["refs"], parts["out_dir"], bool(kw.get("live", False)), count,
                             named=MP.refs_named(spec, view, cons, picks))
        return {"view": view, "files": files, "out_dir": parts["out_dir"], "count": count}
    if stage == "pick":
        view = kw["view"]
        clay = Path(spec.work_dir) / "clay" / f"clay_{view}.png"
        run_dir = Path(spec.work_dir) / "runs" / view
        if kw.get("file"):
            chosen = _p(kw["file"])
            iou = MP.silhouette_iou(clay, chosen)
            ranking = [(chosen, iou)]
        else:
            ranking = MP.rank_variants(run_dir, clay)
            if not ranking:
                raise FileNotFoundError(f"no variants in {run_dir}: generate them first (studio_image_generate)")
            chosen, iou = ranking[0]
        MP.record_pick(spec, view, chosen, iou)
        return {"view": view, "picked": chosen, "iou": round(iou, 4), "ranking": [{"file": f, "iou": round(i, 4)} for f, i in ranking]}
    if stage == "plates":
        return _mp_plates(spec, s, kw.get("require_all", True))
    if stage == "project":
        job = _mp_project_job(spec, setup, s, kw.get("tag") or setup["tag"])
        return {"job": job.id, "tag": kw.get("tag") or setup["tag"], "next": f"api.job_status('{job.id}')"}
    # run: everything, as one background job
    tag, live = kw.get("tag") or setup["tag"], bool(kw.get("live", False))
    if not live and _mp_generate_cmd is None:
        pass                                             # a dry run is allowed: it fails the job with the instruction to pass live=true

    def work():
        rep = MP.run_all(spec, clay=lambda: _mp_clay(spec, s), generate=lambda v, pr, refs, out: _mp_generate(spec, setup, s, v, pr, refs, out, live),
                         plates=lambda: _mp_plates(spec, s), project=lambda: None)
        return rep

    def landed(job):
        pj = _mp_project_job(spec, setup, s, tag)
        job.followup = pj.id

    job = jobs.start("meshpaint-run", work, on_done=landed)
    jobs.ensure_timer()
    return {"job": job.id, "tag": tag, "next": f"api.job_status('{job.id}')"}


# ---- the export (PIECE_PIPELINE step 15): FBX + Textures/ + README, the look is judged in the engine

_MAP_NOTES = (("BaseColor", "base colour, sRGB"), ("ORM", "R = occlusion, G = roughness, B = metallic (Unreal order), linear"),
              ("Normal_DX", "tangent-space normal, DirectX convention (green down): Unreal"),
              ("Normal_GL", "tangent-space normal, OpenGL convention (green up): Unity, Blender, Godot"),
              ("Roughness", "linear"), ("Metallic", "linear"))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def export_piece(object, out_dir, textures=(), note=""):
    """Export ``object`` as FBX into ``out_dir`` with its texture maps copied under Textures/ and a README that names
    every file, what each map is, and its sha256. Nothing in the scene is changed: the selection is restored."""
    import hashlib
    import shutil
    s = _settings()
    ob = bpy.data.objects.get(object)
    if ob is None:
        raise LookupError(f"no object named {object!r}; the meshes are: {sorted(o.name for o in bpy.data.objects if o.type == 'MESH')}")
    out = Path(_p(out_dir, s.project_root))
    S.resolve_in_root(out, s.project_root)
    maps = [Path(_p(t, s.project_root)) for t in textures]
    missing = [str(m) for m in maps if not m.is_file()]
    if missing:
        raise FileNotFoundError(f"texture(s) not found: {', '.join(missing)}")
    (out / "Textures").mkdir(parents=True, exist_ok=True)
    fbx = out / f"{ob.name}.fbx"
    selected = [o for o in bpy.context.selected_objects]
    active = bpy.context.view_layer.objects.active
    try:
        for o in bpy.context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, path_mode="COPY", embed_textures=False,
                                 mesh_smooth_type="FACE", add_leaf_bones=False)
    finally:
        for o in bpy.data.objects:
            o.select_set(o in selected)
        bpy.context.view_layer.objects.active = active
    copied = []
    for m in maps:
        dst = out / "Textures" / m.name
        shutil.copyfile(m, dst)
        copied.append(dst)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    lines = [f"# {ob.name}", "", f"Exported by Lampway from the object `{ob.name}` ({len(ob.data.polygons)} polygons, "
             f"{len(ob.data.uv_layers)} UV layer(s)).", ""]
    if note:
        lines += [note, ""]
    lines += ["## Files", "", f"- `{fbx.name}` (FBX, selection only, textures not embedded) sha256 {sha(fbx)}"]
    for dst in copied:
        kind = next((n for key, n in _MAP_NOTES if key.lower() in dst.name.lower()), "texture map")
        lines.append(f"- `Textures/{dst.name}`: {kind}; sha256 {sha(dst)}")
    lines += ["", "## Conventions", "", "- ORM packs occlusion / roughness / metallic in R / G / B (Unreal Engine's order); "
              "with no AO map R is 1.", "- Normal_DX is the DirectX convention (green down) for Unreal; Normal_GL is OpenGL "
              "(green up) for Unity, Blender and Godot: use one, never both.", "- BaseColor is sRGB; every other map is linear.", ""]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return {"out_dir": str(out), "fbx": str(fbx), "textures": [str(p) for p in copied], "readme": str(out / "README.md")}


# ---- the Mixar-docs features (features/): proven algorithmic code, a studio slot behind the same interface

from .features import retopo as _F_retopo                  # noqa: E402
from .features import image3d as _F_image3d                # noqa: E402
from .features import rig as _F_rig                        # noqa: E402
from .features import lineage as _F_lineage                # noqa: E402
from .features import splat as _F_splat                    # noqa: E402
from .features import texture as _F_texture                # noqa: E402
from .features import video as _F_video                    # noqa: E402
from .features import segment as _F_segment                # noqa: E402
from .features import uv as _F_uv                          # noqa: E402
from .features import uv_rectify as _F_uvr                # noqa: E402
from .features import uv_layout as _F_uvl                  # noqa: E402
from .features import model_compare as _F_mc                # noqa: E402
from .features import clip_classify as _F_cc                # noqa: E402
from .features import scene_cleanup as _F_sc                # noqa: E402
from .features import batch_export as _F_bx                 # noqa: E402
from .features import camera_shot as _F_cs                  # noqa: E402
from .features import procedural_library as _F_pl          # noqa: E402
from .features import layered_material as _F_lm            # noqa: E402
from .features import asset_place as _F_ap                # noqa: E402
from .features import asset_catalog as _F_ac              # noqa: E402
from .features import material_bake_export as _F_mbe        # noqa: E402
from .features import workflows as _F_wf                   # noqa: E402


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def retopo(object, target_faces=2000, method="quadriflow", engine="algorithmic", symmetry=False, adaptivity=1.0, anisotropy=1.0, sharp_edge=90.0, smooth_normal=0.0, edge_scaling=1.0,
           timeout=900, fallback=False, hard_surface=False, preserve_sharp=True):
    """A new all-quad mesh ``<object>_retopo`` near ``target_faces`` (QuadriFlow, voxel fallback, or AutoRemesher) with a measured report; the original is untouched. method=autoremesher runs the Qt-free
    lampway-quadremesh configured by the settings key autoremesher_bin (never an argument: the app downloads nothing) niced in its own process group with a timeout: adaptivity 0..1, anisotropy 0..1, sharp_edge
    30..180 degrees, smooth_normal 0..180, edge_scaling 1..4, timeout 10..3600 s; refused: symmetry, a target above 3x the source, an engine that exits non-zero (its last 20 log lines; fallback=true uses the
    voxel remesh instead), and a QuadriFlow run that leaves the mesh unchanged (CANCELLED on a non-manifold input; fallback=true uses the
    voxel remesh and says so in ``note``). QuadriFlow keeps sharp (hard-surface) edges unless preserve_sharp=false; any method refuses
    a target above 3x the source. The result has no UV layer. ``engine="studio:tripo"`` answers with the action and price for approval and clicks nothing."""
    s = _settings()
    return _F_retopo.retopo(object, target_faces, method, engine, symmetry, True, adaptivity, anisotropy, sharp_edge, smooth_normal, edge_scaling, timeout, fallback, hard_surface,
                            str(s.autoremesher_bin or ""), str(s.project_root), s.nice, preserve_sharp=preserve_sharp)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def uv_unwrap(object, method="smart", angle_limit=66.0, margin=None, texel_density=None, texture_size=2048, engine="algorithmic", margin_px=None, seam_rule=None, checker=False):
    """A new mesh ``<object>_uv`` with a packed UV layout (smart project, angle-based or conformal with seams at sharp edges) and
    a measured report: islands, coverage, overlap, texel-density spread. The original keeps its UVs. engine=studio:tripo is the
    Smart UV slot: it answers with the action and price for approval. margin_px sets the island margin in pixels (default 1 px per 256 px of map: 4 at 1K, 8 at 2K, 16 at 4K; margin is then
    margin_px / texture_size). texel_density (texels per metre at texture_size) is ENFORCED by one uniform scale of the whole layout, and refused when it cannot fit (raise texture_size or lower it).
    seam_rule {hide_from: +X -X +Y -Y +Z -Z top bottom front back left right, along: sharp | panel_lines, avoid_faces: [polygon index]} places seams through the edges least visible from that direction
    (a minimum spanning cut, plus the sharp hidden edges) and uses the angle-based solver; the report says how many seam edges are still visible. The report carries worst_stretch {angle, area, face,
    island, location}: the singular values of the UV Jacobian per triangle, located so it can be clicked. checker adds a UV-grid material to the new object only. texture_size is a power of two 256..8192.
    Refused: unapplied non-uniform scale (apply scale first with scene_cleanup)."""
    return _F_uv.uv_unwrap(object, method, angle_limit, margin, texel_density, texture_size, engine, margin_px, seam_rule, checker)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def segment_mesh(object, method="shells", angle=40.0, min_faces=1, engine="algorithmic", labels=None):
    """Split a mesh into part objects in the collection ``<object>_parts`` (largest first): connected ``shells``, regions bounded by
    ``sharp`` edges (dihedral > angle), or ``uv_islands``; regions under min_faces merge into a neighbour. The original is hidden,
    never deleted. engine=studio:tripo is the part-detection slot. ``labels`` ({mode: map | recipe, island_labels, recipe, owner}) labels the
    UV islands as vertex groups <object>_<label> instead (the Client's island enumeration; nothing is split)."""
    if labels:
        from .features import island_labels as _IL
        return _IL.label(object, labels, _p(labels.get("recipe", "")), _p(labels.get("owner", "")))
    return _F_segment.segment_mesh(object, method, angle, min_faces, engine)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def auto_rig(object, kind="humanoid", engine="algorithmic", weights="auto", facing="-Y", copy=True, naming="ue", parts=None, chain_bones=10):
    """A fitted armature with skin weights (heat map, proximity fallback). kind humanoid (UE names), or the body plans quadruped | hexapod | octopod |
    avian | serpentine | aquatic | auto (features/rig_plans.py); naming ue | mixamo | metahuman; parts rigs several meshes as ONE character."""
    if engine == "algorithmic" and (kind != "humanoid" or naming != "ue" or parts):
        from .features import rig_plans as _RP
        return _RP.auto_rig(object, kind, naming, parts, weights, facing, copy, chain_bones)
    # the humanoid: a UE-named armature <object>_rig from landmarks on a T-pose mesh; _l/_r are the figure's own sides; the source is never touched
    # (<object>_rigged is the rigged copy; copy=false rigs in place); engine=studio:tripo is the Auto Rig slot (action and price only)
    return _F_rig.auto_rig(object, kind, engine, weights, facing, copy)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def bind_to_armature(object, armature, mode="rigid", bone="", source=""):
    """Bind a piece to an armature: ``rigid`` = one bone at full weight (plates), ``transfer`` = weights copied from ``source`` (the
    aligned body; deforming pieces), ``auto`` = heat-map weights."""
    return _F_rig.bind_to_armature(object, armature, mode, bone, source)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def pose_test(armature, object, poses, clearance_body="", seam_radius_m=0.02):
    """Rotate bones ([{name, bone, rotate: [x, y, z] degrees}] or {name, bones: [{bone, rotate}]}) and measure the evaluated mesh: max/min edge
    stretch, the largest vertex displacement, the seam gap growth between shells, and with ``clearance_body`` the clearance to that posed body;
    every pose is reset afterwards."""
    return _F_rig.pose_test(armature, object, poses, clearance_body, seam_radius_m)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def chat_transcript(last=0, include_steps=True):
    """The chat transcript for an external driver. ``scene.mixie_chat_messages[i].content`` is empty for a user message (its text
    is in ``.text``) and for an agent bubble while its turn runs (live narration is in ``.ephemeral`` and ``.thinking_text``,
    tool calls in ``step_items``; ``.content`` holds only the curated final answer). Each row carries the best text of all of
    them, whether it is still running, and the steps. ``last`` = only the final N messages."""
    msgs = list(bpy.context.scene.mixie_chat_messages)
    first = max(0, len(msgs) - int(last)) if last else 0
    rows = []
    for i in range(first, len(msgs)):
        m = msgs[i]
        content, text, live = m.content, m.text, m.ephemeral
        running = bool(m.loader_visible or m.thinking_active or (live and not content))
        row = {"index": i, "sender": m.sender, "bubble_id": m.bubble_id, "text": content or text or live, "content": content,
               "running": running, "thinking": m.thinking_text}
        if include_steps:
            row["steps"] = [st.label for st in m.step_items]
        rows.append(row)
    return {"count": len(msgs), "messages": rows}


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def mesh_prep(object, merge_distance=1e-5):
    """Workflow: a branch ``<object>_prep`` of a generated mesh with its source hash recorded, loose and doubled vertices removed and
    inverted normals fixed; a before/after report. The source is untouched."""
    return _F_wf.mesh_prep(object, merge_distance)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def asset_acceptance(object, reference="", tolerance=0.1, source_hash=""):
    """Workflow: identity, orientation, geometry and materials gates for a candidate asset (against an optional reference), each with
    reasons, and an overall accepted flag. Identity fails unless the object records the source it came from and that matches the
    reference (or ``source_hash``). It lists what it did not check (engine import, collision, skeleton)."""
    return _F_wf.asset_acceptance(object, reference, tolerance, source_hash)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def rig_armor(object, armature, bone="", body="", poses=None, max_stretch=None, clearance_body="", min_clearance_m=0.0, seam_limit_m=0.01):
    """Workflow: fit a copy ``<object>_fit`` of a piece to an armature (bone=one bone at full weight for rigid plates, body=weights
    transferred from the aligned body, else heat map), then measure edge stretch over a pose set. The original is never bound."""
    return _F_wf.rig_armor(object, armature, bone, body, poses, max_stretch, clearance_body, min_clearance_m, seam_limit_m)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def asset_lineage(action, object, source="", transform="", anchors=None, changed_region=None, tolerance_m=0.01, parent="", piece=""):
    """Where a derivative came from. record: store the source's geometry/UV/material hashes, the transformation and exactly THREE identity anchors
    ([{name, point: [x, y, z]}] in object space, landmarks that must not move) on the object and in <root>/<piece>/lineage.jsonl; verify: each anchor's
    nearest-point distance to the derivative must stay within tolerance_m (default 1 cm); show: the lineage and its parent chain. A second record on a
    derived object needs parent=<its lineage id>."""
    return _F_lineage.run(action, object, str(_settings().project_root), source, transform, anchors, changed_region, tolerance_m, parent, piece)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def workflow_graph(action, name="", graph=None, inputs=None, from_node="", version="", template="", description=""):
    """A typed DAG of Lampway tool calls as data. define (graph = {nodes: [{id, tool, args, after, spend, studio_action, credits}], outputs}; args may use
    {{inputs}} and @node.key for an upstream output) | plan (order, cached?, credits_planned) | run | rerun (from_node: it and what follows re-execute) |
    confirm (from_node: ONE spend node runs, on the user's word; its output is kept for those inputs) |
    version / rollback (version) | template_save / template_use (template, description) | show. Outputs are cached by the hash of (tool, args, upstream outputs);
    a spend node is planned and priced, never run (the user confirms in the Studios panel)."""
    from . import workflow_graph as WG
    g = WG.Graphs(_settings().project_root)
    if action == "define":
        return g.define(name, graph or {}, inputs)
    if action == "plan":
        return g.plan(name)
    if action == "run":
        return g.run(name)
    if action == "rerun":
        return g.rerun(name, from_node)
    if action == "confirm":
        return g.confirm(name, from_node)
    if action == "version":
        return g.version(name, version)
    if action == "rollback":
        return g.rollback(name, version)
    if action == "template_save":
        return g.template_save(name, template, description)
    if action == "template_use":
        return g.template_use(template, name, inputs)
    if action == "show":
        return g.show(name)
    raise WG.GraphError("action is define|plan|run|rerun|confirm|version|rollback|template_save|template_use|show")


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def plate_pick(stage, piece="", view="Front", paired=False, v3_dir="", variants_dir="", design_words="", palette="", pick=None, bg_threshold=0.06, opening_iters=3, min_px=1024,
               template=""):
    """Plates stage of the piece pipeline. prompt: the library template (plate-4k-crisper) and its variables for one view (render it, generate 4 images per view); score: rank
    the 4 regenerations (variants_dir/1..4) against the approved V3 plate (v3_dir/<View>.png, RGBA): silhouette IoU x DoG structure x (1 - colour error); cut: the pick's alpha
    (luminance threshold, opening, fill holes, 1 px feather); run: score + cut + checks (margins, aspect, view correspondence) -> <piece>/plates_4k_alpha/<View>.png + alpha.json;
    status. A the user's `pick` (1-4) overrides the best score. Paired pieces: Front and Back only. Free, local, never overwrites."""
    from .pipeline import plates as PL
    return PL.tool(stage, str(_settings().project_root), piece, view, paired, _p(v3_dir), _p(variants_dir), design_words, palette, pick, bg_threshold, opening_iters, min_px,
                   template)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def uv_score(objects=None, files=None, res=1024, out="uv_score.json", gates=None):
    """Score UV layouts on measurements, not by eye: utilization (rasterised at res, 256..4096), overlap, UV-connected islands, stretch p90/p10, the fraction of area off by 2x, flipped
    (mirrored) faces, seam length and a composite score (the shelf's uv_score). objects: mesh objects in the scene; files: .fbx/.glb attempts inside the project root, measured in a
    headless Blender (the live scene is untouched). Each row carries gates {pass, failed} (overlap <= 0.005, flipped <= 0.02, off-density <= 0.05, overridable). `best` is advice: the user picks."""
    from .features import uv_score as _UVS
    return _UVS.run(objects, files, res, out, str(_settings().project_root), gates)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def uv_rectify(object, op="auto", islands=None, edges=None, evenness=0.0, geometry_ratio=0.5, keep_length=True, name="", discard_texture=False):
    """Straighten, rectify and gridify UV islands of strap-like geometry (straps, belts, bracers, skirt strips) on a NEW object ``<object>_rect``; the 3D mesh and the source's UVs are never changed. op auto: an
    island of quads forming a regular grid is gridified (quad-ring propagation; the spacing is the mean 3D edge length per column and row, `evenness` 0..1 blends it toward uniform, `geometry_ratio` 0..1 blends the
    aspect between the grid counts and the 3D lengths); a non-grid island with a bounding aspect over 3 is rectified; any other is SKIPPED with the reason, never dropped. op rectify: one simple boundary loop onto a
    rectangle from four corners (largest turns), the interior solved harmonically. op straighten: `edges` [[v, v], ...] an ordered chain goes onto an axis-aligned line at its cumulative 3D lengths (keep_length), the
    island's boundary stays, the rest relaxes. `islands` are ids from uv_score. Returns per island rectangularity (UV area / bounding box) and stretch p90/p10 before and after. Refused: no UV layer, a textured
    object (texturing comes last: discard_texture=true to override), a chain that is not one path inside one island."""
    return _F_uvr.run(object, op, islands, edges, evenness, geometry_ratio, keep_length, name, discard_texture, str(_settings().project_root))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def uv_layout(object, ops=None, world_axis="z", per_face=False, mirror_axis="x", match_tolerance=0.003, padding=0.01, repack=False, name="", discard_texture=False):
    """Island layout operations the packer does not do, on a NEW object ``<object>_lay`` (the source keeps its UVs). ops (default [orient]): orient (each island to its minimal axis-aligned box), align_world (rotate so
    world_axis x|y|z|auto maps to UV +V, from the UV->3D Jacobian), stack_mirrored (islands whose geometry mirrors across mirror_axis, symmetric Chamfer <= match_tolerance metres: NOT a face-count rule, share one UV
    vertex by vertex; the mesh must be centred on the plane; stacking overlaps UVs so bake_maps refuses it unless stacked_ok), fix_flipped (the minority-winding islands are mirrored in U), sort (a shelf layout, padding).
    Returns oriented/aligned/flipped_fixed counts, the stacked pairs with their Chamfer distance, and a report (accidental overlap excluding stacked, the deliberate stacked overlap, flipped fraction, coverage).
    per_face is not built. Refused: unknown op, no UV layer, a textured object (discard_texture=true overrides), an off-plane mesh for stacking."""
    return _F_uvl.run(object, ops, world_axis, per_face, mirror_axis, match_tolerance, padding, repack, name, discard_texture, str(_settings().project_root))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def model_compare(action="stats", set=None, views=None, size=512, blind=False, pick=None, require_pick=False):
    """Put 2..4 models (GLB files under the project root, or scene objects) side by side with the numbers that decide. stats: read from the FILES without Blender: triangles, vertices, textures with their sizes and
    roles, which PBR channels were actually baked (a flat fallback is the finding), n-gon encoding, compression, generator. build: every model is normalised into the same 2-unit box in a scratch scene (yaw, scale the
    longest axis to 2, measure again, THEN centre), saved as compare.json under <root>/<piece>/compare/<id>/; blind=true replaces the names with aliases A..D assigned by file hash and seals the real labels until the
    user picks. numbers: per pair and view the silhouette IoU, area ratio, centroid shift AND the interior difference with ten height bands and the enclosed holes. reveal shows the labels (after the pick when
    require_pick). pick is the USER's: an agent is refused. close removes the scratch scene. Refused: fewer than 2 or more than 4 models, a file outside the root, not a glTF binary, a meshopt-only file for the 3D
    view. The live windowed viewer with synchronised cameras is not built (it needs the pop-out probe)."""
    return _F_mc.run(action, set, views, size, blind, pick, require_pick, str(_settings().project_root))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def scene_cleanup(objects=None, steps=None, merge_distance="auto", ngon_policy="report", convention=None, plan_only=True, copy=True):
    """Report first, then clean. plan_only (the default) reads the scene and changes nothing: per object the non-uniform scale, loose vertices, doubled vertices at the merge distance, non-manifold edges (wire,
    boundary, multi-face), flipped faces (found on closed shells with doubles welded, so a double cannot hide a flip), n-gons, material slots (unused, duplicates) and UV layers, plus the scene's orphan data blocks.
    plan_only=false runs the steps IN THE DOCUMENTED ORDER whatever order you list: apply_transforms, loose, merge_by_distance, non_manifold, normals (closed shells only), ngons (policy report | triangulate |
    keep), purge_orphans, naming (needs `convention`: prefix, suffix, lowercase, replace_spaces, strip_numeric_suffix: it will not invent one), materials_uvs (removes unused slots; duplicates are reported).
    merge_distance 'auto' = 1e-4 x the bounding diagonal (scale-aware); a merge that would remove more than 5 % of the vertices stops and says the threshold is wrong. Work happens on `<object>_clean` copies with
    the source hash recorded (copy=false edits in place and refuses shared mesh data). Refused: Edit Mode."""
    return _F_sc.scene_cleanup(objects, steps, merge_distance, ngon_policy, convention, plan_only, copy)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def batch_export(objects=None, collection=None, convention=None, format="glb", preset="unreal", apply=None, out_dir="export", per="object", textures=None, plan_only=True, verify=True, undo=None):
    """Audit meshes against YOUR convention, fix it as one pass, and export each object to its own file. plan_only (the default) lists, per object, the violations (name, scale, origin, default material names,
    unused slots) and its new name, and changes and writes nothing. convention is required: {prefix, set, pattern ('{prefix}{set}_{piece}_{nn}'), origin base|center|keep, unit_scale, forward, up}: the tool will
    not invent one. A real run (plan_only=false) writes rename_map.json, renames, applies transforms and the base origin (apply: transforms, modifiers, merge_materials, drop_unused_slots), then exports each
    object from a temporary copy as fbx | glb | gltf | obj under out_dir (inside the project root), re-imports it and compares the bounding box (verified when within 1e-4), and writes manifest.json. The
    project's convention (unit scale and axes) is recorded on the first real run; a later differing call is refused. undo=<rename_map.json> restores the names (not transforms). Refused: a name collision, an unknown
    preset (unreal | unity | godot), usd (not built), glTF with a unit scale other than 1, a path outside the root, Edit Mode. The presets only default the axes and are unverified against each engine's importer."""
    s = _settings()
    return _F_bx.batch_export(str(s.project_root), objects, collection, convention, format, preset, apply, out_dir, per, textures, plan_only, verify, _p(undo) if undo else None,
                              resolve=lambda p: _p(p, s.project_root))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def camera_shot(action="list", shot=None, camera=None, lens_mm=None, aspect=None, frame=1, preset=None, target=None, passes=None, out_dir="guides", handheld=False, size=512):
    """Cinema-mode shots from the agent. A shot is a camera tagged with its name; its keys are ordinary location, rotation and lens keyframes (editable in the scene). new: a camera framed on `target` (or the selected
    mesh) at lens_mm 18..135 and an aspect (16:9, 2.39:1, 9:16, 1:1, 4:3), key at `frame`. frame / key: re-frame or key the current pose. preset: the Client Director's moves from the camera's live pose, keys 12 frames
    apart: ORBIT_LEFT/RIGHT (an arc that keeps the subject framed), DOLLY_IN/OUT, DOLLY_ZOOM (widens the lens by 0.6 while dollying in), CRANE_UP/DOWN, PAN_LEFT/RIGHT; handheld adds a small deterministic jitter.
    render_guides: beauty, clay (Workbench, never Cycles) and depth (ray-cast, fixed near/far so frames compare; nearer is brighter) PNGs at every key under out_dir, the longest side `size`; refused with fewer than
    two keyed poses. delete removes a camera this tool made (or just the shot tag and keys from yours). list shows the shots. Your frame and render engine are restored."""
    s = _settings()
    return _F_cs.camera_shot(str(s.project_root), action, shot, camera, lens_mm, aspect, frame, preset, target, passes, out_dir, handheld, size, resolve=lambda p: _p(p, s.project_root))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def segment_image(image, method="alpha_components", min_pixels=6000, expected_parts=None, out_dir="segments", engine="algorithmic"):
    """One image to per-part masks, no model: connected components (8-connected) on the alpha channel of a transparent plate (alpha_components) or on the foreground of an opaque sheet (color_regions: pixels
    that differ from the border's commonest colour). Writes mask_NN.png (8-bit, same size as the image, white = the part) and overlay.png (numbered tints) under out_dir inside the project root; masks are in
    reading order, left to right. expected_parts labels them only when the count matches. min_pixels (default 6000) drops specks and reports how many. Touching or overlapping parts are ONE component (the note says
    so). Refused: no transparency for alpha_components (use color_regions), more than 64 components (raise min_pixels), over 16 megapixels, a mask that already exists and differs (a record is never overwritten),
    a path outside the root, engine studio:* or model:* (no driver or provider exists for segmentation yet). Nothing lands in the scene."""
    from .pipeline import segment_image as _SI
    if engine != "algorithmic":
        raise _SI.SegmentError(f"engine {engine!r}: no Studio driver or model provider exists for segment yet: use engine=algorithmic")
    return _SI.segment(_p(image), _p(out_dir), method, int(min_pixels), expected_parts)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def procedural_library(action="list", category=None, query=None, material_id=None, object=None, layer_name=None, params=None, size=64, bake_stats=False, compare_to=None, upgrade=False):
    """The procedural material library: 12 armour materials (bronze, gold, brass, steel, iron, two leathers, two cloths) built from parametric node-group templates and a preset table, registered in the Client's
    own material registry. Every material is one node group with a single Shader output and bounded inputs (Tint, Roughness Scale, Wear, Scale, Bump Strength, Seed, Mask: a mask input lets curvature drive edge
    wear), in Object space so no UVs are needed. list / find (query ranks by name; material_id for one; category metal|leather|cloth) return the materials with their inputs. seed registers them (idempotent; a
    changed manifest at the same library_version is refused unless upgrade). verify builds every group and reports shader outputs, input bounds and build time (bake_stats adds real Cycles bakes: base colour mean,
    hue, metallic and roughness means, and near-duplicate pairs). bake renders one material at size px with params to a PNG and its sha256 (compare_to another PNG for the mean difference). add_to_layer puts
    the material on `object` as a procedural layer of its paint stack (initialise one first if the refusal says so)."""
    return _F_pl.procedural_library(str(_settings().project_root), action, category, query, material_id, object, layer_name, params, size, bake_stats, _p(compare_to) if compare_to else None, upgrade)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def layered_material(action="inspect", object=None, material=None, layer=None, manifest=None, layer_index=-1, params=None):
    """The Client's layer-paint stack (an editable material built from layers and masks) from the agent. init puts a paint project on the mesh's material (a material that samples image maps is refused, naming them: init rebuilds the material and would drop them; params {discard_textures: true} starts anyway); inspect returns the stack ({index, name, type, enabled,
    blend, opacity, channels, mask}); add_layer {type: fill | paint | image | group, name, blend: MIX|ADD|MULTIPLY|SUBTRACT|SCREEN|OVERLAY, opacity 0..1, color [r,g,b] for fill, size for paint/image, mask: {type:
    edge_detect | color_id | vcol | image}, projection: uv | triplanar | planar | spherical | cylindrical | decal} (uv needs a UV map: otherwise use triplanar or unwrap first); add_procedural puts a library
    material (see procedural_library) on as a layer; set_params {opacity, enabled, name, blend_type, projection_type, translation, rotation, scale ...} edits layer_index (-1 = the active layer); apply_manifest
    builds a whole stack from a manifest (index 0 must be a PBR layer). Refused: not a mesh, no paint project yet (the refusal names init), unknown blend / type / mask / projection (each lists the choices).
    mask_invert (params {invert: true, the default | false}) inverts layer_index's first mask (add_layer takes mask.invert too). One undo step per Blender operator the Client's package uses."""
    return _F_lm.layered_material(action, object, material, layer, manifest, layer_index, params)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def asset_place(asset_id=None, mode="auto", target=None, options=None, version=None, asset=None):
    """Put an Asset Vault asset into the open scene in the way its kind needs (specs/asset_library/asset_place.md), as one undo step, stamping lw_asset_id / lw_asset_version / lw_asset_sha256
    on what it places. mode auto picks by kind (mesh: import or append, material: assign_material, hdri: set_world, ...); target {where: cursor | origin | object:<name> | slot:<object>:<index>
    | node_tree:<material> | world | sequencer}; options {collection, scale_to_unit, force, replace, ...}. ``asset`` is the library record (given, no fetch); otherwise the record of asset_id
    is read from the server. A placement is recorded on the server as a ``placed`` event (event_recorded false when the server could not take it: the placement stands)."""
    from . import library_client as LC
    if asset is None:
        if not asset_id:
            raise ValueError("asset_place needs asset_id: find one with lampway_vault_search")
        try:
            asset = LC.get_asset(asset_id, version)
        except LC.LibraryClientError as exc:
            raise ValueError(f"{exc}; the asset was not placed") from None
    out = _F_ap.asset_place(asset, mode, target, options)
    try:
        LC.record_event("placed", str(asset.get("id")), version=asset.get("version"), mode=out["mode_used"], project=bpy.data.filepath or "",
                        datablocks=[p.get("name") for p in out["placed"]])
        out["event_recorded"] = True
    except LC.LibraryClientError:
        out["event_recorded"] = False
    return out


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def asset_catalog_export(dest_library, assets=None, asset_ids=None, register=False, library_name="Lampway Vault"):
    """Publish Asset Vault assets (their library records: materials and node groups from their .blend, meshes, rigs, actions) as a Blender asset library under dest_library (inside the project
    root): a headless worker writes lampway_library.blend with every datablock marked as an asset (never your live file), and blender_assets.cats.txt from the taxonomy (<facet>/<label>,
    catalogue ids are UUID5 of the path, stable across exports). register=true adds the folder to Blender's asset libraries as library_name. Refused: a lampway_library.blend Lampway did
    not write, a kind that does not publish, a moved file. Pass the records (assets) or their ids (asset_ids, read from the server)."""
    from . import library_client as LC
    if assets is None:
        try:
            assets = [LC.get_asset(a) for a in asset_ids or []]
        except LC.LibraryClientError as exc:
            raise ValueError(f"{exc}; nothing was published") from None
    return _F_ac.asset_catalog_export(list(assets), Path(_p(dest_library)), bool(register), str(library_name))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def material_bake_export(object, material=None, channels=None, size=1024, format="png", pack="none", normal_green="gl", out_dir="bake_export", samples=8, allow_dirty=False):
    """Bake the layer-stack material of `object` to the images a destination needs, in a niced HEADLESS Cycles worker (never your live scene). channels: base_color, roughness, metallic, normal, ao, emission
    (default base_color, roughness, metallic, normal); size a power of two 1024..8192; format png | exr | tiff | jpeg (jpeg with normal is refused: lossy normals); normal_green gl (OpenGL, Unity/Blender/Godot) |
    dx (DirectX, Unreal); pack=orm also writes <object>_orm (R occlusion, G roughness, B metallic; R is 1.0 with a warning when no ao was baked; roughness and metallic must be baked too). Base colour and
    emission are sRGB, everything else Non-Color. Writes the images and a README with every file's sha256 and the conventions under out_dir (inside the project root). The layer stack is untouched. Refused: no
    paint-stack material (build one with layered_material), no UV map, an unsaved project (allow_dirty=true to override), a bad size or channel, a path outside the root."""
    s = _settings()
    return _F_mbe.material_bake_export(str(s.project_root), object, material, channels, size, format, pack, normal_green, out_dir, samples, allow_dirty, resolve=lambda p: _p(p, s.project_root))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def clip_classify(armature, action=None, samples=25, fps=None, landmarks=None, figure_height_m=None, thresholds="default", apply="none", labels_for_naming=None):
    """What kind of motion is each action on this armature, what should it be called, does it loop: all measured from six landmark bones (hip, head, hand.l, hand.r, foot.l, foot.r; the bone names default from the UE,
    MetaHuman and mannequin skeletons or are passed in `landmarks`), every length a fraction of the figure's height H (given, else the deform mesh's rest height, else head-bone to foot-bone; the source is reported).
    Returns per action the features (speed in H per SECOND: duration is (last - first) / fps), every class label that fits plus the primary one (null in a gap: a gap is a finding), the loop decision (true / false /
    null when not measurable; upstream's 0.5 deg + 0.01 H rule and what anim_loop_export's 1 deg limit would say, neither chosen), and a measured name with `inferred` true when its wording implies intent no number can
    prove. The default thresholds come from ONE subject on one rig (11 clips): single-subject, recalibrate before trusting a gap. A rig that scales joints is listed first. apply=props stores lw_clip_* on the
    Action; apply=rename is the USER's click (an agent is refused and may only propose names). The frame, action and pose are restored."""
    return _F_cc.classify_actions(armature, action, fps, samples, landmarks, figure_height_m, thresholds, apply, labels_for_naming, by="agent")


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def view_verify(action="verify", image="", category="sheet", view="front", approved_front="", mask="", asymmetric_ok=False, judge="none", known_images=None, attempts=None, max_attempts=3,
                original_prompt="", models=None):
    """Is this generated image really the view that was asked for? admit: reject an empty, tiny, fragmented (largest piece under 0.60 of the figure) or duplicate (perceptual hash within 6 of a known_images
    plate) reference BEFORE any model is paid, with the reason. verify: measured checks on the silhouette (alpha, `mask`, or a flat background): shoulder-width ratio and mirror IoU about the figure's own
    axis, feet baseline, arm angle (A-pose is 30 to 60), framing margins, background flatness; verdict pass | soft_fail | hard_fail | uncertain with the signed estimated rotation, and every threshold (they
    are PLACEHOLDERS until calibrated on labelled images) in the result; asymmetric_ok (a weapon in one hand) skips the symmetry checks as not_applicable. A side view is `uncertain` (a profile cannot be read
    from a silhouette). A vision judge may rescue an uncertain and never override a measured hard failure; none is configured here (judge=vision is refused). ladder: the bounded retry decision over
    `attempts` [{verdict, reason, model, rotation_deg}]: accept | accept_with_warning | retry (the first on the same model, the second on the fallback, with the escalated prompt built from
    `original_prompt`) | stop at max_attempts (1..4, default 3, never bypassed) with the user's three options; it never generates. templates: the built-in prompt-library set."""
    from .pipeline import view_verify_io as _VVI
    s = _settings()
    return _VVI.run(action, str(s.project_root), image, category, view, approved_front, mask, bool(asymmetric_ok), judge, known_images, attempts, max_attempts, original_prompt,
                    resolve=lambda p: _p(p, s.project_root), models=models)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def uv_texel_density(object, texture_size=2048, target="auto", weights=None, mode="island", repack=True, margin=0.005, name="", discard_texture=False):
    """Set and equalise texel density per UV island on a NEW object `<object>_td` (the source keeps its UVs), then repack and report the density actually achieved. target: px/metre,
    'N px/cm' or 'auto' (the current mean: only the spread changes); weights: {material | vertex group | island:N: factor 0.1..4}; mode island | all; texture_size a power of two.
    The layout is only ever shrunk to fit 0..1 (`shortfall` = achieved/requested says so). Refuses a textured object (a UV change discards the texture) unless discard_texture."""
    from .features import uv_texel as _UVT
    return _UVT.run(object, texture_size, target, weights, mode, repack, margin, name, discard_texture, str(_settings().project_root))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def mesh_defect_scan(object, piece="", kinds=None, thin_threshold_m=0.002, max_candidates=100):
    """A read-only clay inspection: typed defect candidates for the user's decisions, never an edit. kinds (default all): open_loop (boundary loops), floating_shell (a small shell
    >3 mm from the body), intersection (faces crossing faces, by BVH), thin (thinner than thin_threshold_m inward, default 2 mm, an unverified default), flipped_shell (a shell pointing
    into itself, closed or open), degenerate (zero-area faces), isolated_tri. Each candidate: id, kind, descriptor {faces, area_m2, centroid, bbox, normal, rim_length_m}, rule_verdict
    (keep | delete | hole | ambiguous), rule, severity. More than max_candidates (1..500): the first N plus truncated and total."""
    from .features import defect_scan as _DS
    return _DS.run(object, piece, kinds, thin_threshold_m, max_candidates)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def silhouette_compare(a, b, piece="", views=None, size=512, min_iou=0.9, landmarks=None, interior=False):
    """Did the piece drift? Render the approved source `a` and the candidate `b` (a mesh, or a plate image with an alpha or a flat background) from the SAME orthographic cameras
    (Front/Back/Left/Right, framed on `a`) and report per view the silhouette IoU, area ratio, centroid shift and, with landmarks [{name, point}] in world space, the drift to b's
    surface; `pass` = worst IoU >= min_iou (0.9 is a placeholder, unverified). Side-by-side PNGs go to <root>/<piece>/compare/. A mirrored candidate fails the view that sees the mirror.
    interior=true (mesh vs mesh) adds what outline IoU cannot see: `interior_diff` (mean luminance difference on the cells that are figure in BOTH, 192 lattice after bounding-box alignment), ten height
    bands, `cells_compared` with an `evidence` flag (a handful of cells is `insufficient`), and the enclosed background holes of each side (a face with a hole through it reads IoU-identical)."""
    from .features import silhouette as _SIL
    return _SIL.run(a, b, str(_settings().project_root), piece, views, size, min_iou, landmarks, interior)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def seed_audit(stage, piece, seeds=None, scores=None, proposals=None, by="agent", turn=-90.0, engine="WORKBENCH"):
    """Rank a piece's seeds (the 4 generation variants, then the pick plus its rerolls). measure: per seed the dihedral fold counts (>120 and >90 degrees), boundary / non-manifold edges,
    components and closed bowls across the opening, ranked PROPORTIONS first (scores {seed: score_rms}; within 5 % is a tie), DEFECTS second, V3 fidelity third; lineup: front + side Workbench
    renders at 420 px per seed (never Cycles); judge: the packet (numbers + renders, at most 6 seeds) for a model to propose verdicts; record: audit.json from the proposals, a decision
    row only when by=captain (a model's or agent's verdict is not a ruling). seeds are npz paths (mesh_to_npz output) inside the project root."""
    root = str(_settings().project_root)
    if stage == "lineup":
        from .features import seed_lineup as _SL
        return _SL.run(piece, seeds, root, turn, engine)
    from .pipeline import seed_audit as _SA
    return _SA.run(root, stage, piece, seeds, scores, proposals, by)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def fit_place(kind, piece, body, turn=0.0, clear_mm=15.0, scale_anchor="", sides="both", out="placed.npz"):
    """Place a piece on the body by ENCLOSURE with ONE uniform scale (never registration, never a per-region push): helmet = the widest head level above neck_02, waist = the band at
    spine_01 + 3 cm, boots = shaft width | knee height | foot length (scale_anchor is REQUIRED: the user has not ruled which), gauntlets = the bracer at 35 % vs the forearm's middle (an axis
    more than 25 degrees off is refused), chest = the audits' placement unchanged. piece/body are npz files (mesh_to_npz, body with joints); turn brings the piece to -Y front, +Z up. Writes
    placed.npz and placed.npz.json (scale, translation, anchor_shift, turn, norm_lo/hi) and returns the report."""
    return _fit_place_run(kind, piece, body, turn, clear_mm, scale_anchor, sides, out)


def _fit_place_run(kind, piece, body, turn, clear_mm, scale_anchor, sides, out):
    from .pipeline import fit_place as _FP
    V, T, meta, rep = _FP.place(kind, _p(body), _p(piece), turn, clear_mm, scale_anchor or None, sides)
    import numpy as _np
    o = Path(_p(out or "placed.npz"))
    o.parent.mkdir(parents=True, exist_ok=True)
    _np.savez(o, V=V, T=T)
    Path(str(o) + ".json").write_text(json.dumps(meta, indent=1))
    return {"kind": kind, "scale": meta["scale"], "placed": str(o), "meta": meta, "report": rep}


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def fit_openings(stage, object, axis=None, plane_origin=None, limb="", pose=None, answers=None, flange_mm=None, lip_mm=4.0, clearance_mm=15.0, piece="", captain_words="",
                 texture_discard_ack=False, depths_mm=None, size=384):
    """The openings decision at fit: every cap a seed put across a limb, neck or waist opening gets keep | gasket | delete, logged append-only in <piece>/fit/decisions.jsonl. detect: the capped
    sites along `axis` (pointing out of the piece); propose: proposals only (the user rules); apply: answers {"OP000": "gasket"}. A GASKET cuts the POSED limb's cross-section (`limb`, an
    object) plus clearance_mm (5..40, default 15) into the cap plane and forms a COLLAR - a tubular flange into the piece whose free edge rolls outward into a lip (an exhaust/intake manifold
    port, not a raw hole); its depth `flange_mm` (2..60) is the user's number: without it apply answers needs_decision, and `variants` builds and renders three depths (depths_mm) to pick.
    Needs `pose` (the fit_pose result): never the rest pose. Result `<object>_openings`; the source is untouched. Discards a studio texture (texture_discard_ack). keep changes no geometry."""
    from .features import opening as _OP
    return _OP.run(stage, object, str(_settings().project_root), axis, plane_origin, limb, pose, answers, flange_mm, lip_mm, clearance_mm, piece, captain_words, texture_discard_ack, depths_mm, size)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def parts_critique(stage, piece, recipe="", transfer_dir="", piece_uv="", owner_poly="", mesh="", proposals=None, fixes="", weak=0.6, far_mm=30.0, min_faces=50, limit=12, turn=-90.0, by="agent"):
    """The auditor's critique of a transferred or segmented part set. flags: the rules first (weak-vote and far-transfer islands, parts with too few polygons or absent, a _L/_R part crossing the
    sagittal plane, left/right area asymmetry); render: the owner map in four views with the flagged islands magenta (Workbench, headless); judge: the packet for you to propose from (at most
    `limit` 1..20 flags, biggest first); write_fixes: your proposals [{target_part, islands | bbox_fbx, only_from_parts, reason, evidence}] validated and written to <piece>/parts/fixes.json (the exact
    shape apply_part_fixes reads); check: a dry run of those fixes against owner_tri.npy ({triangles, from} per fix) without writing an owner map. A fix between a metal part and a cloth/leather part is
    refused: that class comes from the user or the recipe, never from a render. Nothing here writes an owner map."""
    from .pipeline import parts_critique as _PC

    def _render(mesh_path, owner_path, recipe_path, prefix, turn_deg):
        res = RUN.run("render_owner", [_p(mesh_path), _p(owner_path), _p(recipe_path), prefix, "--turn", str(turn_deg)], _settings(), timeout=600)
        return [f"{prefix}_{v}.png" for v in ("front", "back", "left", "right")] if res.rc == 0 else []

    return _PC.run(str(_settings().project_root), stage, piece, _p(recipe) if recipe else "", _p(transfer_dir) if transfer_dir else "", _p(piece_uv) if piece_uv else "",
                   _p(owner_poly) if owner_poly else "", _p(mesh) if mesh else "", proposals, _p(fixes) if fixes else "", weak, far_mm, min_faces, limit, turn, _render, by)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def palette_fit(stage, piece, studio_base="", albedo="", masks="", classes=None, material="", name="", source="fit", metal_zero_on=None, statistic="median", space="srgb", min_texels=1000):
    """Fit the per-class Hue/Saturation/Value of the studio colours to the mesh-paint albedo, nudge it live, and hand pbr_merge its params. fit: per class the median HSV of the studio base under
    the class mask vs the albedo under the same mask (hue_shift, sat_mul, val_mul), measured in sRGB by default (the recorded chest fit is the sRGB median: reproduced to 0.02 on gold and plate, worst class 0.19; space=linear for a linear-light consumer), plus `residual` (mean |dRGB|
    after applying it) and a named reason for every skipped class (mask under min_texels); images of different size are resampled to the larger. apply_live: a COPY of `material` gets a
    Hue/Saturation/Value node per class mixed by its mask, labelled PAL: (idempotent). read_live: the sliders read back (the person's nudge is law). write_params: <piece>/pbr/live_material_params.json
    from source fit | live; refuses while a non-metal class (everything but gold and plate) is missing from metal_zero_on: "red is cloth: metallic must be 0 there"."""
    from .pipeline import palette_fit as _PF
    root = Path(str(_settings().project_root))
    base = root / piece / "pbr"
    order = list(classes or _PF.DEFAULT_CLASSES)
    if stage == "fit":
        res = _PF.fit(_p(studio_base), _p(albedo), _p(masks), order, statistic, space, int(min_texels))
        base.mkdir(parents=True, exist_ok=True)
        (base / "palette_fit.json").write_text(json.dumps(res, indent=1))
        return {**res, "path": str(base / "palette_fit.json")}
    if stage == "apply_live":
        from . import palette_live as _PL
        fitted = json.loads((base / "palette_fit.json").read_text())["palette"] if (base / "palette_fit.json").exists() else {}
        use = [c for c in order if c in fitted]
        if not use:
            raise LookupError("no fitted palette: run stage fit first")
        return _PL.apply(material, _p(masks), fitted, use, name)
    if stage == "read_live":
        from . import palette_live as _PL
        return {"ok": True, "palette": _PL.read(material, order if classes else None)}
    if stage == "write_params":
        if source == "live":
            from . import palette_live as _PL
            palette = _PL.read(material, order if classes else None)
        else:
            palette = json.loads((base / "palette_fit.json").read_text())["palette"]
        used = [c for c in order if c in palette]
        return _PF.write_params(palette, used, str(base / "live_material_params.json"), metal_zero_on if metal_zero_on is not None else ("red", "linen", "leather", "embroidery"))
    raise ValueError("stage must be fit | apply_live | read_live | write_params")


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def bake_maps(source, target, maps=None, size=2048, margin_px=None, cage_extrusion_m="auto", max_ray_m=None, samples=16, normal_green="gl", allow_overlap=False, out_dir="bake", overwrite=False,
              attach=True):
    """Bake a high-poly donor (`source`: a name or a list) into a UV-mapped low-poly `target`: maps from normal (tangent), albedo (Cycles COLOR pass only: no lighting, by construction) and ao;
    size a power of two 32..8192 (default 2048); margin_px default size/128 (at least 2); cage_extrusion_m 0..0.2 or auto (measured: the high-poly's greatest height above the target,
    and max_ray_m the cage plus its greatest depth below; an explicit cage under the median distance is refused), max_ray_m default twice an explicit cage; samples 1..512. Normals are
    16-bit, baked once in GL; normal_green=dx flips the green of that bake (never a second bake). Runs in a niced HEADLESS Cycles worker, never in the live scene (the pair is exported to a temporary .blend). Refused before anything runs, each with its fix: no UV (unwrap first),
    overlapping UVs, unapplied non-uniform scale, source == target, a pair not aligned (bbox centres > 2 % of the diagonal apart), an unsupported map, an existing map without overwrite=true.
    Returns the PNG paths under <root>/<out_dir>/, the black-texel fraction per map (a cage-too-small hint when > 0.5 %), the colour spaces (normal and ao Non-Color, albedo sRGB) and, with
    attach, a <target>_baked material wired with the maps and `lw_baked_from` on the target. Curvature, cavity, dust, bevel and position are not Cycles bake types and are refused by name."""
    from .features import bake as _BK
    return _BK.run(source, target, maps, size, margin_px, cage_extrusion_m, max_ray_m, samples, normal_green, allow_overlap, out_dir, overwrite, attach, str(_settings().project_root))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def pbr_pack(action, maps=None, convention="both", name="", metal_zero_masks=None, object="", new_base="", uv_hash=None):
    """One verb set for engine-ready PBR maps. pack: maps {base, normal, rough, metal, ao|null} (project paths) -> <root>/<name>/pbr_pack/ BaseColor (sRGB), ORM (R occlusion - 1 and a note when no AO -,
    G roughness, B metallic: Unreal order, linear), Normal_GL and/or Normal_DX (green flipped), Roughness, Metallic and merge.json; maps must be square powers of two; metal is forced to 0 under
    `metal_zero_masks` (cloth/leather masks); a flat normal is flagged; a set is never overwritten. audit: walks `object`'s Principled material - base colour must be sRGB, roughness/metallic/normal
    Non-Color, a Normal Map node present, and every channel reported linked or not. swap_base_color: replace only the base-colour image on a COPY of the material (roughness, metallic, normal kept);
    pass `uv_hash` (the producer's) and it is refused unless it equals the mesh's: the colour map must share this mesh's UV layout. For a patched mesh use pbr_merge."""
    from .pipeline import pbr_pack as _PP
    if action == "pack":
        m = {k: (_p(v) if v else None) for k, v in (maps or {}).items()}
        missing = [k for k in ("base", "normal", "rough", "metal") if not m.get(k)]
        if missing:
            raise ValueError(f"pack needs maps for: {missing} (ao is optional)")
        return _PP.pack(m, convention, name or object or "pbr", str(_settings().project_root), [_p(x) for x in metal_zero_masks or []])
    from .features import pbr_audit as _PA
    if action == "audit":
        return _PA.audit(object)
    if action == "swap_base_color":
        return _PA.swap_base_color(object, _p(new_base), uv_hash)
    raise ValueError("action must be pack | audit | swap_base_color")


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def armor_piece_pipeline(piece, mode="plan", from_step=1, to_step=15, paired=None, topology="Quad", v3_dir="", record_step=None, artefacts=None, mesh_hash=None, note=""):
    """Run one armour piece from V3 plates to an engine-ready export as 15 ordered, gated steps (the user's runbook mapped to Lampway's tools and the Tripo Studio actions). plan: every step with
    its tool, arguments, state (done | ready | waiting | needs_approval) and planned credits (mesh 100, Smart UV 20, texture 30, PBR 5 = 155 for a whole piece); start: the same, refused when
    from_step > 1 has no run record; record: append one step's result (artefacts with sha256, mesh_hash) to <piece>/pipeline/run.json - a geometry step after the texture makes the texture stale and
    the next run says to re-run step 13. Laws kept: texturing comes last (no texture or PBR without a recorded Smart UV step), Studio actions land on a saved copy, pose before rig. It never confirms a
    spend and never arms the Studio: needs_approval rows wait for the user's click in the Studios panel. A piece is one of Helmet1, Chest1, Waist1, Gauntlets1, Boots1 (paired: front and back views only)."""
    from .pipeline import armor_piece as _AP
    root = str(_settings().project_root)
    if mode == "record":
        if record_step is None:
            raise ValueError("record needs record_step (1..15)")
        return {"ok": True, "record": _AP.record(root, piece, record_step, [_p(a) for a in artefacts or []], mesh_hash, note)}
    if mode == "start":
        return _AP.start(root, piece, from_step, to_step, paired=paired, topology=topology, v3_dir=v3_dir)
    if mode == "plan":
        return _AP.plan(root, piece, from_step, to_step, paired=paired, topology=topology, v3_dir=v3_dir)
    raise ValueError("mode is plan | start | record")


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def fit_pose(kind, piece="", body="", armature="", dofs=None, chain=None, regions=None, out=""):
    """The closest pose of the body to a piece (canon 08). With dofs [{bone, axis (joint grammar: up | forward | lateral | {line} | {perp} |
    a vector), range [lo, hi] (<= 90 deg wide), step, expect (the first DOF's sign check: {joint, along, min_cm})}] and the scene's piece,
    skinned body and armature: a deterministic sweep (the grid over dofs, then each chain link in turn), rays from each skin sample's bone
    axis to the piece, regions {name: {bones, threshold_m}}; answers the pose in the replayable grammar, the A-pose and posed numbers, and
    writes pose.json to out. dofs="chest" is the canon's chest table (arms lowered 0..40 x swung -10..10, mirrored; then spine_01,
    spine_03, neck_01 pitch -8..8). Without dofs: chest is routed to pose_clearance; helmet, waist, boots, gauntlets answer needs_decision (the
    bones, axes and ranges are the user's to rule; the contract's proposals come with it, marked unverified)."""
    from . import posing as _PO
    if dofs == "chest":                                          # the canon's chest table (canon 08 B.4), by name
        t = _PO.CHEST
        dofs, chain, regions = t["dofs"], chain if chain is not None else t["chain"], regions or t["regions"]
    elif isinstance(dofs, str):
        raise ValueError(f"dofs is a list of DOFs or 'chest' (the canon's table); {dofs!r} names no table")
    if dofs:
        return _PO.solve_scene(kind, piece, body, armature, dofs, chain, regions, out, root=str(_settings().project_root))
    return _PO.fit_pose(kind)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def weight_audit(action, object, armature, intended=None, max_influences=4, side=None):
    """Read-only audit of a skinned mesh's weights, or a plan for how to bind it. audit: unweighted vertices, vertices over the influence cap, sums that are not 1, per-bone counts and mean weight, a rigid
    check (`intended` {rigid_bone}: vertices with any other influence), a side check (a *_l group on a right-side mesh; `side` left|right, else inferred from the mesh's x), and the competing-bone hotspots
    (vertices where two bones each carry >= 20 %); `pass` ignores hotspots. An object with no bone-named groups or no Armature modifier is told to bind first. plan: nearest-bone histogram of the
    geometry -> rigid (>= 90 % of the vertices on one bone) or deforming (it spans bones that rotate against each other), with the bone(s), joint_span and reason. Nothing is changed."""
    from .features import weights as _W
    if action == "audit":
        return _W.audit(object, armature, intended, max_influences, side)
    if action == "plan":
        return _W.plan(object, armature)
    raise ValueError("action is audit | plan")


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def weight_cleanup(object, armature, ops, mirror_from=None):
    """Fix weights on a COPY named <object>_wclean (the original stays). ops, in order: {op: normalize}, {op: limit, max_influences: 4}, {op: remove_influence, bone, region: {bbox: [[x0,y0,z0],[x1,y1,z1]]} |
    {vertex_group}} (refused when it would take one bone off more than 40 % of the vertices: that is a rebind, not a cleanup; never leaves a vertex with no weight), {op: smooth, iterations, factor, region},
    {op: rigid, bone, region} (full weight on one bone). Returns the ops applied with the vertices each changed and the weight_audit of the result. mirror_from is not built (it needs a verified symmetric mesh)."""
    from .features import weights as _W
    return _W.cleanup(object, armature, ops, mirror_from)


@tool(consumes={"mesh": Need(kind=("mesh",))})
def joints_from_views(mesh="", cameras="", keypoints="", calibration="", known="", detector="keypoints_json", rig=True, max_px=4.0, centre=True, hidden=None,
                      out="joints.json"):
    """Joints of a humanoid from orthographic views (canon 11): keypoints {keypoints_px: {joint: {view: [x, y(, confidence)]}}} made in
    the cameras {cameras: [{name, res, ortho, center, right, up, look}]} (pixels right and DOWN) are triangulated (exact for
    orthographic views; a view missing by more than max_px dropped while the rest fix the point; an AMBIGUOUS outlier - two views
    that alone fix a direction and disagree - refused, naming both), moved by the calibration measured on a body with known joints in
    the SAME cameras (rig=true needs it; known=<{joints_m}> writes one to out instead), and centred in the canonical mesh's limb
    cross-section (centre=true). One view per joint, a calibration from another camera framing, or a detector (rtmw_wholebody |
    rtmpose_hand: a model slot, decision 11-H1) are refused. Writes the receipt {joints: {name: {pos_m, views_used, residual_px,
    calibrated, centred, centred_cm}}} to out."""
    from .pipeline import joints_views as _JV
    root = str(_settings().project_root)
    if detector != "keypoints_json":
        _JV.detect(mesh, detector)
    if not cameras or not keypoints:
        raise ValueError("cameras and keypoints are required with detector=keypoints_json")
    if known:
        return _JV.calibrate(_p(cameras), _p(keypoints), _p(known), root, _p(out), max_px=max_px)
    vt = None
    if mesh and centre:
        from .features import rig as _rig
        vt = _rig._body_mesh(bpy.data.objects[mesh])
    res = _JV.run(_p(cameras), _p(keypoints), root, rig=rig, calibration=_p(calibration), max_px=max_px, hidden=tuple(hidden or ()), mesh=vt)
    if out:
        p = Path(_p(out))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(res, indent=1, sort_keys=True))
        res["out"] = out
    return res


@tool(consumes={"armature": Need(kind=("skeleton",), accept_raw=True)})
def normalize_rigged(armature, meshes=None, profile="ue5_body", turn_deg=0.0, dry_run=True):
    """An armature (and the meshes skinned to it) into a canonical skeleton and canonical rigged meshes (specs/canon/normalization
    contracts/normalize_rig.md): rig_inspect (convention, roster, units) then rig_normalize (unit and object scale, drift-checked),
    then the documents - bones with along = head -> the next joint (never the tail) and their frames; stamped lw_canon. Refused: a
    mixed convention, a roster incomplete against the profile (ue5_body | ue5_body_fingers | metahuman), units no known factor explains,
    a turn (the rig must face -Y). dry_run (default) changes nothing and answers the plan."""
    from .features import normalize_rigged as _NR
    return _NR.run(armature, meshes, profile, turn_deg, dry_run)


@tool(consumes={"input": Need(kind=("texture",), accept_raw=True)})
def normalize_texture(input, role="auto", normal_convention="auto", tiling_real_world_m=None, source_naming="none"):
    """An image (a datablock, or a file under the project root loaded raw) into a CANONICAL texture (lampway.canonical-asset/1): its
    role declared or read from the declared source's naming (source_naming ambientcg | polyhaven | lampway; tripo / none have no
    table, so role=auto refuses), the colour space bound to the role and set on the image (sRGB basecolor / emission / reference,
    Linear Rec.709 hdri, Non-Color every data map), a normal map's convention from the naming or declared (normal_convention gl | dx;
    never assumed), ORM packed r ao g roughness b metallic, size / bit depth / channels / alpha measured, the file's sha256; stamped
    lw_canon with a receipt. tiling_real_world_m [w, h] records a tileable's physical size."""
    from .features import normalize_texture as _NT
    return _NT.run(input, role, normal_convention, tiling_real_world_m, source_naming, root=str(_settings().project_root))


@tool(consumes={"input": Need(kind=("mesh",), accept_raw=True)})
def normalize_mesh(input, turn_deg=None, plate="", recipe="", generator="", want_scale="any", scale_evidence=None, weld="auto", weld_distance_m=None):
    """A raw mesh (an object, or a file under the project root imported raw) into a CANONICAL mesh (lampway.canonical-asset/1:
    metres, +Z up, front -Y, transform applied, the scale STATE recorded, a generated mesh welded by position, lw_source_face, pivot at
    the bounding box's bottom centre), stamped lw_canon, with a receipt under canon/receipts/. The facing is DECLARED: turn_deg
    (the piece's turn about Z; -90 for a +X-facing import) or a recipe's turn_deg; it is never guessed (refused: "frame undecided").
    generator: tripo_studio | tripo_api | meshy | hi3d | hyper3d | hunyuan | trellis | lampway_tool | captain_authored | unknown ...
    (Tripo / Hi3D files are generator_normalised; a generated mesh is welded at weld_distance_m, default 1e-5, refused above 5 %
    merged; weld=never for an authored mesh). want_scale=real needs scale_evidence {method, value, reference}. A skinned mesh is
    refused (normalize_rigged). Normalizing a canonical object again changes nothing (unchanged)."""
    from .features import normalize as _N
    return _N.run(input, turn_deg, plate, recipe, generator, want_scale, scale_evidence, weld, weld_distance_m, root=str(_settings().project_root))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def weight_transfer(object, source, max_distance=0.05, max_normal_angle=30.0, flip_normals=True, inpaint_mode="point", limit_groups=4, deform_only=True, name="", engine="algorithmic", weld_m=1e-5):
    """Copy skin weights from a rigged body onto a piece. Each piece vertex is matched to the closest point on the body's (deformed) surface and takes the barycentric weights when the distance <=
    max_distance (default 0.05 m, at most 0.5) and its normal is within max_normal_angle (default 30 degrees; a flipped normal also counts when flip_normals); every vertex with no trustworthy match is
    inpainted so armpits, crotch and chest-to-arm gaps blend without painting. engine algorithmic: a harmonic fill over the mesh graph (Blender's python); engine robust: the SIGGRAPH Asia 2023 method
    (robust Laplacian, biharmonic constrained solve) in the science python (needs LAMPWAY_PYTHON_SCIENCE with numpy scipy libigl robust_laplacian). limit_groups caps the influences (default 4, 0 = no cap).
    The source must carry vertex groups and exactly one Armature modifier; the piece must have no topology modifiers. Result: a NEW object <object>_wt (or `name`) with the body's groups and Armature; the
    original is untouched. Returns matched_fraction, inpainted_vertices, groups_written, the influence histogram and unweighted_vertices.
    weld_m (default 1e-5 m, canon 07 B.1): the piece's vertices are welded by position before matching and inpainting, so a seam-split smart
    mesh is one surface and both copies of a seam vertex carry the same row; 0 for an authored rig (a weld can invent identity there)."""
    from .features import weights as _W
    return _W.transfer(object, source, max_distance, max_normal_angle, flip_normals, inpaint_mode, limit_groups, deform_only, name, engine, weld_m=weld_m)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def garment_clearance(piece, body, armature, pose_set="rest", clearance_target_m=0.015, classes=None, body_open_band_m=None):
    """How far a piece sits from the body in rest and named poses: the signed distance of every piece vertex to the body posed by `armature` (positive outside, negative inside). pose_set is 'rest', 'wiki8'
    (the eight stress poses) or a list [{name, bone, rotate: [x, y, z degrees]} | {name, bones: [{bone, rotate}]}]; the poses are reset afterwards. Per pose: min_clearance_m, penetrating_vertices, max_depth_m,
    worst_region [x, y, z] and the body triangles that block most; `pass` when every vertex clears its target (clearance_target_m, default 0.015, or the target of the piece's vertex group named in
    `classes` {group: metres}: rigid and cloth parts differ). Also pass_pose_count and closest_pose. Refused: a body with no Armature modifier (the body needs an armature) and a piece more than 0.5 m
    from the body (run place_piece first). Canon 15: the sign is the angle-weighted pseudonormal's (never one face normal); an OPEN body (a headless
    body mesh) is refused unless body_open_band_m declares the band round its opening whose vertices stay unsigned (unsigned_near_opening)."""
    from .features import clearance as _CL
    return _CL.run(piece, body, armature, pose_set, clearance_target_m, classes, body_open_band_m)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def fit_validate(stage, piece="", bound="", original="", poses=None, roles=None, limits=None, body="", armature="", validation=None):
    """Measure a bound piece through poses against its ORIGINAL shell, and judge it (canon: specs/canon/05-fit-validation.md). stage measure (engine
    blender): `bound` the piece with an Armature modifier, `original` the pre-fit source shell (REQUIRED - measuring against a baked rest hides the
    distortion; same vertex count), `poses` - names from the vendored Titan set (rest, wrist_r_plus30, elbow_r_70, curl_r_full, ...) or
    [{name, bones: [{bone, axis: up | forward | lateral | {line: [a, b]} | {perp: [a, b], to} | [x, y, z], deg}], expect: {joint, along | closer_to,
    min_cm}} | {name, curl: {side, fraction}} | {name, bone, rotate: [x, y, z degrees]} (the Euler stress set)], `roles` {part: metal | leather | cloth |
    embroidery} (a part is the vertex group of that name, or the whole piece when there is one role). A pose's expect is measured on the posed JOINTS
    first: a wrong sign is REFUSED and nothing is measured; an expect on the commanded angle ({bone, axis, min_deg}) cannot fail and is refused. Per
    pose and part: rigid residual with the scale FIXED, edge strain (fraction, p95 and max), the source seam ledger's pairs (open over 2 mm, max cm),
    SURFACE crossings both ways and inside vertices of `body`; rest_fidelity of the whole piece and of every metal part; the crossing control (the
    piece pushed into the skin where it is nearest, capped at half its extent: no crossing seen = UNPROVEN). Limits default to Titan's armour limits
    adopted by the user (metal rigid < 0.5 mm, strain p95 < 1 %, no body crossing); leather, cloth and embroidery have none (UNVERIFIED), and a metric
    not measured is UNVERIFIED. stage judge: re-judge a validation (dict or file) under new `limits`."""
    from .features import validate_pose as _VP
    from .pipeline import validate as _V
    if stage == "measure":
        return _VP.measure(piece, bound, original, poses or [{"name": "rest"}], roles, limits, body or None, armature or None)
    if stage == "judge":
        v = json.loads(Path(_p(validation)).read_text()) if isinstance(validation, str) else dict(validation or {})
        if not v.get("poses"):
            raise ValueError("judge needs a validation with poses (the output of measure)")
        lim = limits or _V.DEFAULT_LIMITS
        judges = []
        for row in v["poses"]:
            if row.get("verdict") == "REFUSED":
                judges.append({"verdict": "REFUSED", "limits_status": lim.get("status", "proposed")})
                continue
            for part in row.get("pieces", {}).values():
                part["judge"] = _V.judge(part["role"], {"rigid_max_mm": part["rigid_max_mm"], "strain_p95": part["strain_p95"], "crossings": part.get("surface_crossings")}, lim)
                judges.append(part["judge"])
        v["limits"] = lim
        v["summary"] = _V.summarize(judges, (v.get("crossing_control") or {}).get("ok") is not False)
        return v
    raise ValueError("stage is measure | judge")


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def skeleton_export_check(armature="", fbx="", target=None, expect_unit_scale=1.0, allow_extra_bones=False):
    """Check an armature (in the scene) or an FBX (under the project root; give exactly one) against a reference skeleton: target {names_from: a reference FBX, e.g. a mannequin animation}. Reports leaf bones (`*_end`
    the reference does not have: export with add_leaf_bones off), missing and extra bones, parents that differ, the root, the unit scale (height ratio to the reference: a 100x export reads 100; expect_unit_scale
    default 1), the up axis and rest_vs_frame (rest_pose_is_frame_zero is true when bones are posed with no animation: the bind pose was taken from a posed scene). `pass` and the reasons. A profile name
    alone is refused: no profile table ships, pass a reference file."""
    from .features import export_checks as _EC
    return _EC.skeleton_check(armature, fbx, target, expect_unit_scale, allow_extra_bones, str(_settings().project_root))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def engine_import_check(package_dir, engine="unreal", collision=None, receipt=None):
    """Static check of an exported package (a folder with an FBX and Textures/) against the engine's import rules: the FBX header version (Unreal wants 7400+; FBX 2020.2 is 7700), mesh names and material
    slots, `UCX_<Render>_NN` collision meshes that must match a render mesh (`collision` lists the names expected), the textures the materials name that are missing from Textures/, textures nobody names, and an
    optional receipt from a hand-run import {engine_version, import_settings, wired_channels, notes} which is RECORDED, not judged. A package with no FBX is told to run export_piece first."""
    from .features import export_checks as _EC
    return _EC.engine_check(package_dir, engine, collision, receipt, str(_settings().project_root))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def fit_body(verb, armature="", mesh="", glb="", native_asset="", uproject="", sidecar="", out="fit/body"):
    """The body for fitting as one hashed package. build: writes <out>/<sha8>/ with joints.json (parents before children; head, tail and rest axes in metres), body.npz when `mesh` is given, body.glb, the
    NATIVE weights sidecar.json when `sidecar` names a file the user's UE editor leg wrote, and receipt.json with the sha256 of every file. verify (out = the package dir): recompute every hash, refused
    with 'the body asset changed: rebuild the package'. weights: refuses unless the package has a native sidecar ('weights come from the native asset'; a GLB body carries only 4 influences). Only the
    project-native body is accepted (native_asset under /Game/MetaHumans/); the editor leg itself (uproject) is not run from here."""
    from .features import fit_body as _FB
    if verb == "build":
        return _FB.build(armature, mesh, glb, native_asset, uproject, sidecar, out, str(_settings().project_root))
    if verb == "verify":
        return _FB.verify(_p(out))
    if verb == "weights":
        return _FB.need_weights(_p(out))
    if verb == "show":
        return json.loads((Path(_p(out)) / "receipt.json").read_text())
    raise ValueError("verb is build | verify | weights | show")


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def fit_export(object, armature, out_dir, body, textures=None, validation="", bind_check="", note="", allow_unverified=False, _bone_axis="Z"):
    """The rigged export of a fitted piece, behind gates, with a read-back. Refuses (each names its fix): a missing validation or one with FAIL/UNPROVEN, roles with no declared limits (unless
    allow_unverified=true, and then the README says 'limits: proposed; roles without limits: ...'), a bind_check that is not ok, textures whose merge.json mesh_sha256 is not this mesh (a geometry step
    discards the texture: re-run steps 13-14), vertex groups naming a bone the body package does not have, an existing out_dir. Writes <object>.fbx with the contract settings (primary bone axis Z, secondary X,
    leaf bones off, units applied), Textures/, README.md (files with sha256, conventions, validation counts, limits status, read-back) and export.json, then READS THE FBX BACK and compares every joint's
    position and axes with the body package (positions to 0.1 mm, axes to 0.5 degrees): a position-only check passed exports whose frames were 90 degrees off, so it is never the gate."""
    from .features import fit_export as _FE
    return _FE.run(object, armature, out_dir, _p(body), textures, validation, bind_check, note, allow_unverified, str(_settings().project_root), _bone_axis)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def fit_bind(stage, piece="", armature="", roles=None, bind_overrides=None, out_dir="fit/bind", body_object="", accept_seam_gap_mm=None):
    """Bind a finished piece to the body's skeleton by the user's weight laws. plan: per part (a vertex group of the piece) a role from `roles` {part: metal | leather | cloth | embroidery} - the user's or
    the recipe's, never a render's colour: a part without one is refused - and a mode: metal = rigid, ONE bone at full weight (the bone with most of its vertices nearest, or the override), anything else =
    restrict (weighted by position from the body's own weights, restricted to the bones its geometry spans); `bind_overrides` {part: {mode, bones, reason}} (metal as blend is refused: ask for a ruled cut;
    an unknown bone names the nearest). Parts that share a seam and a bone form a rigid group; two rigid parts of one shell on different bones OPEN the seam (seam_opens). Writes bind_plan.json and seams.json.
    weights: a copy <piece>_fit (the source is untouched) with the plan's weights; the body's weights come from `body_object` (a skinned body in the scene: an approximation, the native sidecar sampler is not built).
    A restrict part (canon 07) is welded by position, matched only on the body's own region for its bones (a closer surface of another region cannot
    capture it), within 30 degrees of normal (or flipped); a weight on a disallowed bone moves to its nearest allowed ancestor, else to the part's
    `fallback` (bind_overrides {part: {fallback}}), else the bone is refused by name; a vertex left with no weight is refused, never written empty.
    return: the metal parts' rest residual against the ORIGINAL shell. apply: refused while a seam opens unless accept_seam_gap_mm. report: the stages done and the files."""
    from .features import fit_bind as _FB
    root = str(_settings().project_root)
    if stage == "plan":
        return _FB.plan(piece, armature, roles, bind_overrides, out_dir, root)
    if stage == "weights":
        return _FB.weights(piece, armature, out_dir, body_object, root)
    if stage == "return":
        return _FB.return_report(piece, armature, out_dir, root)
    if stage == "apply":
        return _FB.apply(piece, armature, out_dir, accept_seam_gap_mm, root)
    if stage == "report":
        return _FB.report(out_dir, root)
    raise ValueError("stage is plan | weights | return | apply | report")


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def fit_glove(stage, piece="", side="r", labels=None, roles=None, overrides=None, by="agent"):
    """The glove's plate labels as a TYPED decision. stage labels: `labels` {plate: bone} for EVERY plate of the piece (its vertex groups; an unlabelled plate is named, never guessed), `roles` {plate: role},
    the glove's own side's bones only (a left-hand bone on the right glove is refused by name), finger caps and the bracer metal = one rigid bone each, a cloth plate (the upper arm) never rigid. Writes
    <piece>/fit/glove_labels.json, one decision row per plate to <piece>/fit/decisions.jsonl (decider `by`: agent proposals are recorded as such) and returns the bind_fragment to pass to fit_bind as
    bind_overrides. pose, bind and report need the hand-pose engine of the user's project and answer needs_decision with the open questions."""
    from .pipeline import fit_glove as _FG
    if stage == "labels":
        from .features import common as _C
        plates = [g.name for g in _C.need_object(piece).vertex_groups]
        return _FG.labels(str(_settings().project_root), piece, side, plates, labels or {}, roles or {}, overrides, by)
    if stage in ("pose", "bind", "report"):
        return _FG.not_built(stage)
    raise ValueError("stage is labels | pose | bind | report")


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def anim_reference_render(character, views=None, size="720x1280", background="#808080", camera=None, out_dir="anim/reference"):
    """The character at rest from a KNOWN orthographic camera on a plain grey background, front and side: the start images for the clip step. character: an object (its children are included) or a collection;
    views [front, side]; size WIDTHxHEIGHT (720x1280, 9:16); camera {ortho_scale, center, height_m} (default: fit-to-height with a 6 % margin each side, measured from the mesh; a perspective camera is refused). Writes
    <out_dir>/ref_<view>.png, ref_<view>_mask.png (the silhouette) and cameras.json (the recorded camera per view: orthographic scale, px_per_m, centre, axes) in a throw-away Workbench scene with anti-aliasing
    off: the grey is exact and two renders are byte-identical. The character faces -Y (Blender's front view); the side view shows it facing left. Refused: a posed character ('run pose_test reset'), no skinned model,
    a figure whose feet or head leave the frame. Free, no model."""
    from .features import anim_render as _AR
    return _AR.reference_render(character, views, size, background, camera, out_dir, str(_settings().project_root))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def animation_retarget(source, target, action=None, mapping="auto", method="matrix", root_motion="keep", scale="auto", frame_range=None, fps=None, check_objects=None, sample_frames=8, name=None,
                       dry_run=False, keep_source=False):
    """Bake an animation from one skeleton onto another (a NEW Action on the target; nothing is overwritten) and measure it. source: an armature in the scene or a project-relative .fbx/.bvh/.glb (imported in a
    hidden collection and removed after); target: the armature; action: a name, 'all', or the source's active one; mapping: 'auto' (bone names read to canonical labels and sides, exact names first), a preset
    name from anim/presets/ or [{source, target, mode: rotation|transform|none}]. method 'matrix' compensates the rest poses (the target bone turns by the source bone's world rotation, whatever either rest is);
    'constraints' is Copy Rotation + NLA bake and does NOT compensate (a warning says so). root_motion keep | in_place, scale 'auto' (pelvis height ratio) or 0.01..100, fps resamples. Refused: no action,
    a humanoid set not covered (the missing labels are listed; dry_run shows the mapping first), a file outside the project root. Returns the mapping, the unmapped bones, and metrics: world-direction error of
    what was baked, foot slide, and the edge stretch of check_objects. Writes anim/<action>.retarget.json and the reviewed mapping as a preset."""
    from .features import animation as _AN
    return _AN.retarget(source, target, action, mapping, method, root_motion, scale, frame_range, fps, check_objects, sample_frames, name, dry_run, str(_settings().project_root), keep_source)


def _gray_loader():
    """path -> 2-D float array 0..1: PIL when the interpreter has it, Blender's own image loader otherwise."""
    try:
        from PIL import Image
        import numpy as _np
        return lambda path: _np.asarray(Image.open(path).convert("L"), float) / 255.0
    except ImportError:
        import bpy
        import numpy as _np

        def load(path):
            from . import canon_io as _cio
            img = _cio.load_image(path)
            try:
                w, h = img.size
                px = _np.array(img.pixels[:], dtype=_np.float32).reshape(h, w, 4)[::-1]
                return px[..., :3].mean(axis=-1)
            finally:
                bpy.data.images.remove(img)
        return load


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def anim_multiview_fit(front="", side="", calibration=None, cameras="", fps=24.0, single_view=False, grid_frames=None, stage="fit", out="anim/multiview/fit.json",
                       frames=None, onnx="", armature="", mesh="", masks=None, bones=None, step_deg=8.0, rounds=5, key=False):
    """Motion from ONE split-screen clip (front + side), orthographic: triangulate per-panel 2D joints (JSON {keypoints: [[[u, v] x 15 joints] per frame], conf?}, joint order = pipeline.anim_mv.JOINTS) into 3D, the side
    view's near/far leg and arm labels put right from the FRONT view (heights, then continuity), pelvis-relative (a drifting camera is not travel), one floor row for both panels. calibration {px_per_m} or `cameras`
    (the cameras.json of anim_reference_render: the render cameras are the video cameras). Refused: panels out of sync ('re-generate'), a missing scale. Held (duplicate) frames are listed with the true motion rate.
    grid_frames: PNGs of the side-track grid clip: the floor's parallax gives the root speed. single_view=true is the control that cannot tell legs apart (it says so). Writes `out`. stage 'detect' (the RTMW 2D
    detector) is not wired: it answers needs_approval; supply the keypoints. Free, no model."""
    from .pipeline import anim_io as _IO
    if stage == "detect":
        # the RTMW detector: frames {front: [pngs] | dir, side: ...} -> <out dir>/front.json, side.json (the fit's input); weights from disk, never downloaded
        from .pipeline import rtmw as _RT
        if not isinstance(frames, dict) or set(frames) != {"front", "side"}:
            raise ValueError("stage detect needs frames {front: [png...] or a folder, side: ...} (the split panels) and onnx (the RTMW weights on disk)")
        try:
            backend = _RT.rtmw_backend(_p(onnx), run_tool=lambda n, a: RUN.run(n, a, timeout=3600))
        except _RT.DetectorUnavailable as exc:
            raise ValueError(str(exc)) from None
        res = {}
        for v, f in frames.items():
            fp = _p(f) if isinstance(f, str) else None
            paths = sorted(os.path.join(fp, x) for x in os.listdir(fp) if x.lower().endswith(".png")) if fp else [_p(x) for x in f]
            res[v] = _RT.detect(paths, os.path.join(os.path.dirname(_p(out)), f"{v}.json"), backend)
        return {"stage": "detect", "panels": res, "next": "stage fit with front/side = the two JSON files"}
    if stage == "refine":
        from .features import anim_abs as _ABS
        return _ABS.refine(armature, mesh, {k: _p(v) for k, v in (masks or {}).items()}, _p(cameras), _p(out), bones, step_deg, rounds, key)
    if stage != "fit":
        raise ValueError("stage is fit | detect | refine")
    grid = None
    if grid_frames:
        load = _gray_loader()
        grid = [load(_p(g)) for g in grid_frames]
    return _IO.multiview_fit(_p(front), _p(side), calibration, _p(cameras) or None, float(fps), bool(single_view), grid, _p(out))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def anim_check(poses, masks=None, rendered=None, cameras="", twist=None, claims=None, out="anim/check.json"):
    """Judge a tracked motion (the anim_multiview_fit file) against BOTH views' silhouette masks (dirs of PNG: {front, side}; a single view cannot settle which leg is in front: refused) and the ground. Gates with
    their numbers: G-OUT-front >= 0.80 and G-OUT-side >= 0.85 outline IoU, G-LEGS >= 85 % of lifted frames' lifted foot travelling forward, G-FOOT-SLIDE <= 1 cm, G-FOOT-PLANT <= 1 cm, G-TWIST <= 5 deg (when
    twist = [tracker yaws, refined yaws] radians is given, else unverified), G-CLAIMS (claims [{text, measurement}]). Controls run on THIS take: a fore-aft mirrored copy must read about 0 on G-LEGS and a dragged
    stance foot must fail the slide gate; a check whose controls cannot fail does not pass. rendered: dirs of posed silhouettes; without them a capsule stand-in is drawn through `cameras`. Thresholds are proposed.
    G-TOE is unverified. Writes `out`."""
    from .pipeline import anim_io as _IO
    load = _gray_loader()
    return _IO.check(_p(poses), {k: _p(v) for k, v in (masks or {}).items()}, {k: _p(v) for k, v in rendered.items()} if rendered else None, _p(cameras) or None,
                     twist, claims, load, _p(out))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def anim_loop_export(take, cycle="auto", fps=30.0, skeleton="metahuman_base_skel", check="", strides_note="", reference_bones=None, loop_tolerance_deg=None, out="anim/loop"):
    """Turn a checked multi-stride take into one seamless loop: the period found by autocorrelation and refined by least squares across strides (cycle 'auto' or 'strides:N'), strides averaged by PHASE into
    loop.json, and the export gates with their numbers: G-LOOP (<= 1 deg between strides, root offset one period), G-LOOP-WRAP, G-SPEED (planted-foot speed within 5 % of the root's), G-STRIDES (>= 4, or >= 2 with
    `strides_note`), G-SKEL (the bone set against `reference_bones`; unverified without it). `take` JSON: {quats [frame][bone][w,x,y,z], bones, root_y_m, fps, planted_foot_speed_mps}. Refused: a take that failed
    anim_check (`check` file), one stride, an export onto Manny. G-FIDELITY and G-ENGINE and the AnimSequence itself need the user's UE editor leg: reported not_run/unverified, never a pass."""
    from .pipeline import anim_io as _IO
    return _IO.loop_export(_p(take), float(fps), cycle, skeleton, loop_tolerance_deg, _p(check) or None, strides_note, reference_bones, _p(out))


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def anim_clip(reference_image, view="front", motion="walk", driver_video="", route="higgsfield", model="", duration=5, resolution="720p", aspect_ratio="9:16", generate_audio=False, has_camera_record=True):
    """Plan ONE character clip (the locked-camera prompt 'locked camera, no cuts, no zoom, the whole body and feet in frame, <motion> in place', Seedance 2.0, 720p 9:16 5 s) as a DRY RUN: the lampway_video_gen
    arguments, the list price (22.5 Higgsfield credits; $0.76, or $0.46 with the front clip as video reference, on OpenRouter: derived, not measured) and nothing spent. The side clip takes the front clip as
    driver_video. Refused: a 16:9 clip, under 4 s, a reference without its recorded camera. Run the plan with lampway_video_gen (the user confirms the cost), then gate the file with lampway_video_gate
    kind=clip: 24 fps all distinct, 720x1280, 5.0 s, figure >= 1000 px not touching the border, locked camera, >= 4 strides. A failed gate is NOT retried: every draw is a new charge."""
    from .pipeline import anim_plan as _AP
    return _AP.clip_plan(reference_image, view, motion, driver_video or None, route, model or None, duration, resolution, aspect_ratio, generate_audio, has_camera_record)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def anim_track(provider=None, shipping=True, clip="", mask_dir="", camera="", skeleton="metahuman_base_skel", stage="plan", frames_with_pose=None, total_frames=0):
    """Body tracking, video to the MetaHuman skeleton: the provider is the USER's decision, so stage plan answers needs_decision with the question and the model slots (GEM-X, hosted SAM 3D Body, Uthana: all
    needs_approval) and names anim_multiview_fit as the primary tracker that needs no provider. Refused: gvhmr with shipping=true (licence: research and non-profit only, needs SMPL-X; shipping=false tags the
    output prototype and not exportable), no mask_dir, mha_markerless off Windows. stage coverage: frames_with_pose / total_frames must reach 90 %. Nothing is run or spent."""
    from .pipeline import anim_plan as _AP
    if stage == "coverage":
        return _AP.coverage_gate(list(frames_with_pose or []), int(total_frames))
    if stage != "plan":
        raise ValueError("stage is plan | coverage")
    return _AP.track_plan(provider, shipping, clip, mask_dir, camera, skeleton)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def anim_from_video(character, motion="walk", views=None, stock_first=True, provider_track=None, route="higgsfield", out_package="", stock_inventory=None, anim_dir=""):
    """The animation-from-video pipeline as ONE dry-run plan: anim_reference_render (free) -> anim_clip (the only paid step: one spend card, '2 clips, 45 credits' at list price) -> anim_track (the provider
    decision stays open: needs_decision) -> anim_check -> anim_loop_export, with the decisions.jsonl path the run would write. stock_first refuses when a stock animation (stock_inventory names) already has the
    move: retarget it with animation_retarget. Nothing is run or spent; each step is the tool of that name, a failed gate stops the run, and a clip is never re-drawn without the user."""
    from .pipeline import anim_plan as _AP
    p = {"character": character, "motion": motion, "views": views, "stock_first": stock_first, "provider_track": provider_track, "route": route, "out_package": out_package,
         "stock_inventory": stock_inventory or []}
    if anim_dir:
        p["anim_dir"] = anim_dir
    return _AP.plan_steps(p)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def fit_state(stage="describe", **kw):
    """The descriptor / question / answer fit loop. Not built: answers needs_decision (is the Laya / fit-model route still the direction now that fit_validate measures the fit?). The question, the reason and a
    proposal are in the result."""
    from .pipeline import fit_glove as _FG
    return _FG.fit_state(stage)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def detail_normals(material, strengths=None, ambientcg_dir=""):
    """Micro depth for a textured_atlas material: per-material tiling detail normals, box-projected in object space (metals take their ambientCG
    NormalGL maps, cloth and leather a small bump from their colour), blended by the material's per-texel masks. Idempotent: its 'DN:' nodes are
    replaced on a re-run. strengths: {plate, gold, cloth, leather}; ambientcg_dir defaults to the settings' / LAMPWAY_AMBIENTCG_DIR."""
    from . import detail_normals as DN
    return DN.apply(material, strengths, ambientcg_dir or getattr(_settings(), "ambientcg_dir", None) or None)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def image_to_3d(images=None, size=1.0, resolution=64, mode="hull", depth=None, profile="round", name="", engine="algorithmic", detect_views="", views=None,
                paired=False, plate_check=True):
    """Mesh from images, no model: ``hull`` = visual hull of two or more cardinal views ({"Front": path, "Left": path, ...}, Front u=+X,
    Left u=-Y), ``extrude`` = rounded/slab extrusion of Front (+Back) for paired pieces, ``relief`` = luminance relief of one image.
    Reported by re-projection IoU, volume and boundary edges. detect_views = a turnaround sheet cut into panels named by ``views`` (left to right);
    paired = front and back only. engine=studio:tripo | studio:meshy | studio:hi3d answers with the action, its plan_args and price, after a plate check."""
    from .features import image3d_views as _IV
    s_ = _settings()
    detected = None
    if detect_views:
        sheet = _p(detect_views, s_.project_root)
        detected = _IV.detect_views(sheet, os.path.join(os.path.dirname(sheet), "views_" + os.path.splitext(os.path.basename(sheet))[0]), list(views or []))
        images = detected["views"]
    elif images:
        images = {v: _p(p, s_.project_root) for v, p in images.items()}
        if len(images) == 1 and _IV.looks_like_sheet(next(iter(images.values()))):
            raise ValueError("this looks like a turnaround sheet (more than 2:1): pass detect_views=<sheet> with views (the panel order) so the panels are not fused into one mesh")
    else:
        raise ValueError("give images {View: path} or detect_views (a turnaround sheet) with views")
    if paired and set(images) - {"Front", "Back"}:
        raise ValueError(f"a paired piece (gauntlets, boots) takes front and back only: drop {sorted(set(images) - {'Front', 'Back'})}")
    if engine != "algorithmic":
        if not plate_check:
            return _F_image3d.image_to_3d(images, size, resolution, mode, depth, profile, name, engine)
        return _IV.studio_plan(images, engine, paired)
    res = _F_image3d.image_to_3d(images, size, resolution, mode, depth, profile, name, engine)
    res["views_used"] = sorted(images)
    if detected:
        res["detected"] = {k: v for k, v in detected.items() if k != "views"}
    return res


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def splat_import(path, max_points=200000, name="lw_splat"):
    """Import a 3D Gaussian Splatting PLY (binary little endian: x y z f_dc_0..2 opacity scale_0..2) as ONE point object with colour,
    opacity and radius attributes and a geometry-nodes view; a splat is never converted to a mesh. max_points subsamples
    deterministically."""
    return _F_splat.splat_import(_p(path), max_points, name)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def render_video(object, out, kind="turntable", frames=48, width=640, height=360, fps=24, engine="workbench", waypoints=None):
    """Render a turntable or a keyframed camera path (``waypoints``: [{frame, location}]) of ``object`` to an H.264 mp4 under the project
    root with the light engines (workbench | eevee; never Cycles), in a throw-away scene. engine=model:<name> is the generative video
    slot: not wired."""
    return _F_video.render_video(object, _p(out), kind, frames, width, height, fps, engine, waypoints)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def project_views(object, views, size=1024, out="", occlusion=True):
    """Project cardinal-view images ({"Front": path, ...}, each framed to the subject) into the UV atlas by which way each texel faces
    (optional occlusion ray test) and apply it as the material ``<object>_proj``. Reports coverage and per-view share."""
    s_ = _settings()
    if not isinstance(views, dict) or not views or not all(isinstance(p, str) and p for p in views.values()):   # audit F12
        raise ValueError('views is an object {view: image path}, e.g. {"Front": "refs/front.png", "Back": "refs/back.png"}; '
                         f"the views are {', '.join(_F_texture.R.TO_CAMERA)}")
    return _F_texture.project_views(object, {v: _p(p, s_.project_root) for v, p in views.items()}, size,
                                    _p(out or f"{object}_atlas.png", s_.project_root), occlusion)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def texture_gen(object, prompt, out_dir="", views=("Front", "Back"), size=1024, engine="algorithmic", reference_image="", count=1, keep_original=True, record=True,
                piece="", delight=False, min_coverage=0.6):
    """Texture Gen: clay render of each view -> the server's image model paints it (count variants, best silhouette IoU kept; a material
    reference_image rides second) -> projection into the atlas of a copy <object>_tex (keep_original) -> a ledger row. Under min_coverage the run
    is refused before anything is paid. The object needs UVs. engine=studio:tripo is the Texture + PBR slot (30 + 5 credits: approval first)."""
    if engine != "algorithmic":
        return _F_texture.texture_gen(object, prompt, "", views, size, engine)
    if not out_dir:
        raise ValueError("texture_gen needs out_dir (a project folder for the clay renders, the painted views and the atlas)")
    return _F_texture.texture_gen(object, prompt, _p(out_dir), list(views), size, engine, reference_image=_p(reference_image), count=count,
                                  keep_original=keep_original, record=record, piece=piece, delight=delight, min_coverage=min_coverage)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def ai_render(object, prompt, view="Front", out="ai_render.png", size=768):
    """AI Render: a clay render of ``object`` from ``view`` is handed to the image model with the prompt; the result image is saved and
    loaded as a Blender image. It changes nothing in the scene (look development only)."""
    return _F_texture.ai_render(object, prompt, view, _p(out), size)


@tool(consumes=LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"))
def repair_texture(object, texture, view, patch, mask, out, feather=2):
    """Local texture repair: blend ``patch`` through ``mask`` (both framed like a clay render of ``view``) into the existing atlas where
    the surface faces that view; writes ``out``, never overwrites ``texture``."""
    s_ = _settings()
    return _F_texture.repair_texture(object, _p(texture, s_.project_root), view, _p(patch, s_.project_root), _p(mask, s_.project_root),
                                     _p(out, s_.project_root), feather)


# ---- Wave 6 tools (api_wave6.py): plain functions wrapped here, so they pass the same door with the same envelope

from . import api_wave6 as _W6                              # noqa: E402

# each wave 6 tool's declaration lives beside it (api_wave6.CONSUMES); a missing name fails the import
for _w6_name in _W6.TOOLS:
    globals()[_w6_name] = tool(consumes=_W6.CONSUMES[_w6_name])(getattr(_W6, _w6_name))


# ---- the orphan tools (STATUS.md ORPHANS): their own module, registered through tool() above

from .orphans_api import *  # noqa: E402,F401,F403
from .rig_api import *  # noqa: E402,F401,F403


# ---- the UE Renderer (specs/ue_parity): ue/ owns the behaviour, these are its doors

def _ue_profile(profile):
    from .ue import profile as _UEP
    return _UEP.load(_p(profile) if profile else _UEP.DEFAULT_PROFILE)


@tool(consumes=LEGACY("a material datablock: lampway_normalize_material is not built"))
def ue_material(material, mode="report", merge_json=None, master=None, on_loss="report", profile=None):
    """Translate a Principled material to UE's legacy Default Lit, deterministically: the UE material-instance parameters
    (BaseColor/Metallic/Roughness/Specular/Emissive, blend mode Opaque|Masked(0.3333)|Translucent, Two Sided = not backface
    culling, texture sRGB flags and compression), what is dropped or clamped, and translation_sha256. mode report changes nothing;
    preview builds '<material> [UE]' with the LW_UE_DefaultLit_v1 node group (Lambert added to single-scatter GGX, UE's F0 and its
    F90 = saturate(50 F0.g), the DirectX normal with Z rebuilt) beside the untouched original; export reads the pbr_pack
    merge_json for the texture colour spaces and the ORM channel order. on_loss refuse refuses any loss. profile: a
    lampway.ue-profile/1 file (default: the shipped engine-defaults profile). Free, no model."""
    from .ue import material_group as _UEG
    from .ue import material_map as _UEM
    prof = _ue_profile(profile)
    if mode == "preview":
        return _UEG.preview(material, prof)
    mat = bpy.data.materials.get(material)
    if mat is None:
        raise LookupError(f"no material named {material!r}; the materials are: {sorted(m.name for m in bpy.data.materials)}")
    merge, files = None, None
    if merge_json:
        mj = Path(_p(merge_json))
        merge = json.loads(mj.read_text(encoding="utf-8"))
        files = sorted(q.name for q in mj.parent.glob("*.png"))
    return _UEM.translate(_UEG.read_spec(mat), prof, mode, merge, files, master, on_loss)


@tool(consumes=LEGACY("acts on the whole open scene (scope=scene), not on named assets: the door checks named arguments only"))
def ue_look(action="status", profile=None, scope="scene", parity=False, receipt=None, cube=None, cube_meta=None):
    """The one-click UE Look mode, governed by one UE profile (lampway.ue-profile/1; default: the shipped engine-defaults
    profile) and its tonemapper cube, generated on the UE side and named by the profile's tonemap_cube / tonemap_cube_meta (or
    cube / cube_meta here; validated against the sidecar: sha256, grid, domain, engine version, tonemapper settings). action
    enable: validate the cube, write the UE view's OCIO config and the launcher's state (the next launch starts with the view;
    restart if this session lacks it). disable: clear the launcher's state. apply: the view, exposure = log2(k) + Bias - EV100,
    curves and white balance off, EEVEE fast GI and screen tracing as the profile's GI and reflection methods say (all off with
    parity=true, and dither 0), anisotropic filtering from r.MaxAnisotropy, soft falloff off on point/spot lights, every material
    in scope swapped to its '<name> [UE]' UE Default Lit preview; returns the receipt path (with the cube's sha256 and engine
    version), the lights' UE values and the per-class trust. revert: restores every recorded value exactly. status: active,
    profile hash, view, classes. generate: the view's OCIO config only. Refused: a missing or mismatched cube (fix: generate the
    cube on the UE side, then point UE Look at it), a session without the view, Standard ACES, a non-sRGB working space, auto
    exposure or engine defaults with parity, area or temperature lights in scope, a scene already in a UE look."""
    from .ue import launch as _UEL2
    from .ue import look as _UEL
    from .ue import ocio_view as _UEV
    scene = bpy.context.scene
    prof = _p(profile) if profile else None
    # the cube and its sidecar come from the UE side, usually outside the project root: they are only read and hashed, and
    # nothing of their content is returned, so they are the one exception to the project-root rule
    cube, cube_meta = (str(Path(cube).expanduser().resolve()) if cube else None), (str(Path(cube_meta).expanduser().resolve()) if cube_meta else None)
    if action == "status":
        return _UEL.status(scene)
    if action == "revert":
        return _UEL.revert(scene, _p(receipt) if receipt and not Path(receipt).is_absolute() else receipt)
    if action == "disable":
        return {"disabled": _UEL2.disable(), "message": "UE Look is off for the next launch (OCIO is left as it was)"}
    if action in ("generate", "enable"):
        _, pr = _UEL.load_profile(prof, cube, cube_meta)
        g = _UEV.generate(pr, bpy.utils.system_resource("DATAFILES", path="colormanagement"))
        if action == "generate":
            return g
        state = _UEL2.enable(g["config_path"], g["cube_path"], g["cube_sha256"], g["view_name"])
        restart = not _UEV.view_present(g["view_name"])
        return dict(g, state_path=state, restart=restart,
                    message="UE Look is on: restart Lampway (the launcher starts it with the UE view)" if restart else "UE Look is on")
    if action != "apply":
        raise ValueError("action is apply, status, revert, enable, disable or generate")
    return _UEL.apply(scene, prof, scope, bool(parity), cube, cube_meta)


@tool(consumes=LEGACY("armature and action need lampway_normalize_rigged / lampway_normalize_clip, not built (canon R1/R3/R4)"))
def ue_export(type, object="", armature=None, action=None, out_dir="", textures=None, body=None, frame_rate=None, hero=None, format="fbx",
              validation="", bind_check="", bake_receipt="", profile=None, allow_unverified=False, _bone_axis="Z"):
    """Export to UE by the ONE path its type allows: skinned_piece (FBX: armature + mesh, primary bone axis Z / secondary X, no
    leaf bones, units applied, tangents, triangles; fit_export's gates: body package, validation, bind_check, native bones, and
    the joint read-back), static_prop (the same without the armature), animation (FBX: the armature, every frame keyed at the
    scene rate, no simplification; frame_rate must equal the scene's) or texture_set (pbr_pack's BaseColor / ORM / Normal_DX with
    their DECLARED colour spaces). Canonical input only: a transform not applied, a negative scale or a scene not in metres is
    refused. Meshes are triangulated once (fixed method) on a temporary copy; bake_receipt's triangles_sha256 must match. Writes
    out_dir/<name>.fbx, Textures/, README.md, export.json (settings, content_sha256 with the timestamp zeroed, triangles_sha256,
    read-back, material translation, losses) and ue_import.json (the only import settings the UE editor leg may use). hero
    (default: the profile's export.precision) keeps UVs outside [0,1] and asks for high-precision tangents, UVs and weights. glTF
    for a skinned asset is refused. An existing out_dir is refused. Free, no model."""
    from .ue import export as _UEX
    s_ = _settings()
    if not out_dir:
        raise ValueError("out_dir is required: export/<asset>/<tag> under the project root")
    _p(out_dir, s_.project_root)                                          # refused outside the project root
    return _UEX.run(type, object, armature, action, out_dir, _p(textures) if textures else None, _p(body) if body else None, frame_rate, hero,
                    format, validation, bind_check, bake_receipt, _p(profile) if profile else None, str(s_.project_root), _bone_axis, allow_unverified)


@tool(consumes=LEGACY("builds its own standard scene and reads UE captures (image files): the door resolves datablocks and canon sidecars, not paths"))
def ue_parity(scene, profile=None, size=768, views=None, out_dir="", ue_captures=None, ue_linear_scale=None):
    """The parity harness, Lampway half: build a standard scene (chart | furnace | normals | lights) from its one JSON
    description in a throw-away scene, render each view (front | three_quarter | grazing) headless in EEVEE under ue_look
    parity=true to float EXR, and write out_dir/scene.json, lampway_<view>.exr, report.json and report.md (Blender and UE versions,
    profile, scene and file hashes, per-class verdicts). The UE half is needs_box until the captain's box time: given ue_captures
    (ue_<view>.exr from the UE editor leg) it compares per class against the tolerances (COL display <= 3 codes / linear < 1 %,
    SHD < 3 %, NRM sign agreement 100 % and mean dE2000 <= 2, LGT < 2 %, GEO IoU >= 0.995; PST and TEX reported). Refused: a
    profile with engine defaults, auto exposure, GI, reflections, SSAO, bloom, vignette or local exposure on; a mislabelled or
    .hdr capture; an armour scene without an ue_export receipt; an existing out_dir. Free, no model."""
    from .ue import parity as _UEP
    s_ = _settings()
    if not out_dir:
        raise ValueError("out_dir is required: parity/<scene>/<tag> under the project root")
    _p(out_dir, s_.project_root)
    return _UEP.run(scene, _p(profile) if profile else None, int(size), list(views or ["front"]), out_dir, ue_captures, ue_linear_scale,
                    str(s_.project_root))


# ---- the door the agent's scripts use

# Every @tool function, in definition order: derived, not listed by hand (a hand-kept list let 26 tools of Waves 2-4 be functions and Defs the agent could not run).
TOOL_FUNCS = tuple(_REGISTRY)


def call(name: str, payload: str = "{}") -> dict:
    """``api.call("qa_candidates", '{"draw": true}')``: a public tool function by name with its keyword arguments as a JSON
    object. The agent's scripts carry the arguments as one string literal, so no argument value can change the script."""
    if name not in TOOL_FUNCS:
        return {"ok": False, "error": f"no tool function {name!r}; the functions are {', '.join(TOOL_FUNCS)}",
                "help": ["Call `api.status()` to see what is configured"]}
    try:
        kwargs = json.loads(payload or "{}")
        if not isinstance(kwargs, dict):
            raise ValueError("the payload must be a JSON object")
    except ValueError as exc:
        return {"ok": False, "error": f"bad payload: {exc}", "help": ["Pass the arguments as one JSON object"]}
    try:
        return globals()[name](**kwargs)
    except TypeError as exc:
        return {"ok": False, "error": f"bad arguments for {name}: {exc}", "help": ["Check the tool's parameters"]}
