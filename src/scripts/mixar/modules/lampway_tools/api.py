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
import json
from pathlib import Path

import bpy

from . import TOOLS_VERSION
from . import jobs
from . import live_load
from . import rebuild as RB
from . import runner as RUN
from . import settings as S
from .meshqa import decisions as D
from .meshqa import live as L
from .meshqa import marks as M
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


def tool(fn):
    """Return {'ok': True, ...} from the function's dict, or {'ok': False, 'error', 'help'} for a refusal."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            out = fn(*a, **kw)
            return {"ok": True, **out} if isinstance(out, dict) else {"ok": True, "result": out}
        except Exception as exc:
            help_ = next((h for t, h in _HELP.items() if isinstance(exc, t)), ["See the error"])
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}" if not isinstance(exc, (LookupError, S.PathOutsideProject,
                    FileNotFoundError, ValueError, RUN.ToolUnavailable)) else str(exc).strip("'\""), "help": help_}
    return wrapper


def _settings() -> S.Settings:
    return S.load()


def _p(path, root=None) -> str:
    """A path argument resolved inside the project root ('' stays '')."""
    if path in (None, ""):
        return ""
    return str(S.resolve_in_root(path, root or _settings().project_root))


# ---- settings and status

@tool
def settings_get():
    s = _settings()
    return {"settings": {k: (str(getattr(s, k)) if getattr(s, k) is not None else None) for k in S._FIELDS},
            "interpreters": S.interpreter_report(s)}


@tool
def settings_set(**kw):
    s = _settings()
    for k, v in kw.items():
        if k not in S._FIELDS:
            raise ValueError(f"unknown setting {k!r}; the settings are {', '.join(S._FIELDS)}")
        setattr(s, k, int(v) if k == "nice" else Path(v))
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
            "rulings_dir": cfg.rulings_dir, "candidates": cfg.candidates_path.exists()}


@tool
def status():
    s = _settings()
    return {"version": TOOLS_VERSION, "project_root": str(s.project_root), "interpreters": S.interpreter_report(s),
            "qa": _qa_summary(), "jobs": jobs.status(), "tools": tools()}


# ---- mesh QA

@tool
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


@tool
def qa_tag_layers():
    ann = M.create_tag_layers()
    return {"layers": [l.info for l in ann.layers]}


@tool
def qa_candidates(draw=False):
    cfg = L.load_config(bpy.context.scene)
    out = L.compute_candidates(cfg)
    if draw:
        out["drawn"] = L.draw_candidates(cfg)["drawn"]
    return out


@tool
def qa_draw():
    return L.draw_candidates(L.load_config(bpy.context.scene))


@tool
def qa_read_tags(apply=True, close_round=False, mislabel_to=None):
    cfg = L.load_config(bpy.context.scene)
    targets = {int(k): v for k, v in (mislabel_to or {}).items()}
    return L.read_tags(cfg, apply=apply, close_round=close_round, mislabel_to=targets)


@tool
def qa_rulings():
    cfg = L.load_config(bpy.context.scene)
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


@tool
def rebuild_setup(source_mesh, source_owner, relief_dir, plates_dir, template_material, out_root="", relabel_rules=(),
                  turn=-90.0, lift=0.0, previous=()):
    """What a rebuild needs besides the rulings: the SOURCE mesh and its owner map (rebuilds always start from the
    source), the relief views and plates, the live material to copy, where the outputs go, the objects to hide."""
    cfg = L.load_config(bpy.context.scene)
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


@tool
def rebuild(tag, res=2048, color_full=False, ornament="", mesh_gold=False, read_tags=True, close_round=False,
            mislabel_to=None, resume=False):
    """Read his tags, write the rulings, rebuild, and load the result beside the previous version.

    The rebuild runs as a background job (minutes); this returns its id at once. When it finishes the app's timer loads
    the new mesh textured next to the old one, hides the old, and points mesh QA at the new object so the loop continues.
    ``api.job_status(<id>)`` reports it."""
    cfg = L.load_config(bpy.context.scene)
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
        cfg2 = L.load_config(bpy.context.scene)
        cfg2.object = res_["name"]
        cfg2.offset = (0.0, 0.0, float(setup["lift"]))
        cfg2.owner = str(patched / f"{piece}_{tag}_owner_poly.npy")
        cfg2.orig_poly = str(patched / f"{piece}_{tag}_orig_poly.npy")
        cfg2.turn = float(setup["turn"])
        L.save_config(bpy.context.scene, cfg2)

    job = jobs.start("rebuild", work, on_done=land)
    jobs.ensure_timer()
    return {"job": job.id, "tag": tag, "reading": reading, "next": f"api.job_status('{job.id}')"}


@tool
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

@tool
def run_tool(name, args=(), timeout=3600):
    """Run any ported tool (``api.tools()``) as a batch job: every argument that names a path stays inside the project root."""
    s = _settings()
    if name not in RUN.TOOLS:
        raise RUN.ToolUnavailable(f"no tool {name!r}; the tools are: {', '.join(sorted(RUN.TOOLS))}")
    jailed = []
    for a in args:
        a = str(a)
        jailed.append(str(S.resolve_in_root(a, s.project_root)) if ("/" in a and not a.startswith("--")) or a.startswith(("..", "~")) else a)
    res = RUN.run(name, jailed, s, timeout=float(timeout), log_dir=s.project_root / "logs")
    return {"rc": res.rc, "output": res.stdout, "log": res.log, "timed_out": res.timed_out, "ok_run": res.rc == 0}
