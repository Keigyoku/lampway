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
from . import albedo as AB
from . import live_load
from . import meshpaint as MP
from . import rebuild as RB
from . import runner as RUN
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
def qa_candidates(draw=False, piece="", collection="", prefix=None):
    """Candidates for ``piece`` (default: the active piece); with ``draw`` they are drawn into ``collection`` (default
    ``QA_<piece>``) with marker names starting ``prefix`` (default ``<piece>_``)."""
    cfg = L.load_config(bpy.context.scene, piece or None)
    out = L.compute_candidates(cfg)
    if draw:
        out["drawn"] = L.draw_candidates(cfg, collection or None, prefix)["drawn"]
    return out


@tool
def qa_draw(piece="", collection="", prefix=None):
    return L.draw_candidates(L.load_config(bpy.context.scene, piece or None), collection or None, prefix)


def _qa_candidates_by_id(cfg) -> dict:
    if not cfg.candidates_path.exists():
        raise FileNotFoundError(f"{cfg.candidates_path} does not exist: compute the candidates first")
    return {c["id"]: c for c in json.loads(cfg.candidates_path.read_text(encoding="utf-8"))["candidates"]}


@tool
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


@tool
def qa_proposals(piece=""):
    """The proposals so far for the piece (rows {id, kind, verdict, reason, by}), with counts per verdict."""
    cfg = L.load_config(bpy.context.scene, piece or None)
    rows = QP.load_rows(cfg.rulings_dir, cfg.piece)
    return {"piece": cfg.piece, "counts": QP.counts(rows), "proposals": QP.as_map(rows)}


@tool
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


@tool
def qa_read_tags(apply=True, close_round=False, mislabel_to=None, piece=""):
    cfg = L.load_config(bpy.context.scene, piece or None)
    targets = {int(k): v for k, v in (mislabel_to or {}).items()}
    return L.read_tags(cfg, apply=apply, close_round=close_round, mislabel_to=targets)


@tool
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


@tool
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


@tool
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
    jailed = S.jail_args(args, s.project_root)
    # The tool's working directory is the root, so a bare file name it writes lands inside it too.
    res = RUN.run(name, jailed, s, timeout=float(timeout), log_dir=s.project_root / "logs", cwd=str(s.project_root))
    return {"rc": res.rc, "output": res.stdout, "log": res.log, "timed_out": res.timed_out, "ok_run": res.rc == 0}


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


@tool
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


@tool
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
from .features import workflows as _F_wf                   # noqa: E402


@tool
def retopo(object, target_faces=2000, method="quadriflow", engine="algorithmic", symmetry=False):
    """A new all-quad mesh ``<object>_retopo`` near ``target_faces`` (QuadriFlow, voxel fallback) with a measured report;
    the original is untouched. ``engine="studio:tripo"`` answers with the action and price for approval and clicks nothing."""
    return _F_retopo.retopo(object, target_faces, method, engine, symmetry)


@tool
def uv_unwrap(object, method="smart", angle_limit=66.0, margin=0.005, texel_density=None, texture_size=2048, engine="algorithmic"):
    """A new mesh ``<object>_uv`` with a packed UV layout (smart project, angle-based or conformal with seams at sharp edges) and
    a measured report: islands, coverage, overlap, texel-density spread. The original keeps its UVs. engine=studio:tripo is the
    Smart UV slot: it answers with the action and price for approval."""
    return _F_uv.uv_unwrap(object, method, angle_limit, margin, texel_density, texture_size, engine)


@tool
def segment_mesh(object, method="shells", angle=40.0, min_faces=1, engine="algorithmic"):
    """Split a mesh into part objects in the collection ``<object>_parts`` (largest first): connected ``shells``, regions bounded by
    ``sharp`` edges (dihedral > angle), or ``uv_islands``; regions under min_faces merge into a neighbour. The original is hidden,
    never deleted. engine=studio:tripo is the part-detection slot."""
    return _F_segment.segment_mesh(object, method, angle, min_faces, engine)


@tool
def auto_rig(object, kind="humanoid", engine="algorithmic", weights="auto", facing="-Y", copy=True):
    """A UE-named humanoid armature ``<object>_rig`` placed from landmarks measured on a T-pose mesh, the mesh parented with heat-map
    weights (proximity fallback for the vertices heat cannot solve). ``_l``/``_r`` are the figure's own sides. engine=studio:tripo
    is the Auto Rig slot (answers with action and price). The source mesh is never touched: ``<object>_rigged`` is the rigged copy (copy=false rigs in place)."""
    return _F_rig.auto_rig(object, kind, engine, weights, facing, copy)


@tool
def bind_to_armature(object, armature, mode="rigid", bone="", source=""):
    """Bind a piece to an armature: ``rigid`` = one bone at full weight (plates), ``transfer`` = weights copied from ``source`` (the
    aligned body; deforming pieces), ``auto`` = heat-map weights."""
    return _F_rig.bind_to_armature(object, armature, mode, bone, source)


@tool
def pose_test(armature, object, poses, clearance_body="", seam_radius_m=0.02):
    """Rotate bones ([{name, bone, rotate: [x, y, z] degrees}] or {name, bones: [{bone, rotate}]}) and measure the evaluated mesh: max/min edge
    stretch, the largest vertex displacement, the seam gap growth between shells, and with ``clearance_body`` the clearance to that posed body;
    every pose is reset afterwards."""
    return _F_rig.pose_test(armature, object, poses, clearance_body, seam_radius_m)


@tool
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


@tool
def mesh_prep(object, merge_distance=1e-5):
    """Workflow: a branch ``<object>_prep`` of a generated mesh with its source hash recorded, loose and doubled vertices removed and
    inverted normals fixed; a before/after report. The source is untouched."""
    return _F_wf.mesh_prep(object, merge_distance)


@tool
def asset_acceptance(object, reference="", tolerance=0.1, source_hash=""):
    """Workflow: identity, orientation, geometry and materials gates for a candidate asset (against an optional reference), each with
    reasons, and an overall accepted flag. Identity fails unless the object records the source it came from and that matches the
    reference (or ``source_hash``). It lists what it did not check (engine import, collision, skeleton)."""
    return _F_wf.asset_acceptance(object, reference, tolerance, source_hash)


@tool
def rig_armor(object, armature, bone="", body="", poses=None, max_stretch=None, clearance_body="", min_clearance_m=0.0, seam_limit_m=0.01):
    """Workflow: fit a copy ``<object>_fit`` of a piece to an armature (bone=one bone at full weight for rigid plates, body=weights
    transferred from the aligned body, else heat map), then measure edge stretch over a pose set. The original is never bound."""
    return _F_wf.rig_armor(object, armature, bone, body, poses, max_stretch, clearance_body, min_clearance_m, seam_limit_m)


@tool
def asset_lineage(action, object, source="", transform="", anchors=None, changed_region=None, tolerance_m=0.01, parent="", piece=""):
    """Where a derivative came from. record: store the source's geometry/UV/material hashes, the transformation and exactly THREE identity anchors
    ([{name, point: [x, y, z]}] in object space, landmarks that must not move) on the object and in <root>/<piece>/lineage.jsonl; verify: each anchor's
    nearest-point distance to the derivative must stay within tolerance_m (default 1 cm); show: the lineage and its parent chain. A second record on a
    derived object needs parent=<its lineage id>."""
    return _F_lineage.run(action, object, str(_settings().project_root), source, transform, anchors, changed_region, tolerance_m, parent, piece)


@tool
def workflow_graph(action, name="", graph=None, inputs=None, from_node="", version="", template="", description=""):
    """A typed DAG of Lampway tool calls as data. define (graph = {nodes: [{id, tool, args, after, spend, studio_action, credits}], outputs}; args may use
    {{inputs}} and @node.key for an upstream output) | plan (order, cached?, credits_planned) | run | rerun (from_node: it and what follows re-execute) |
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
    raise WG.GraphError("action is define|plan|run|rerun|version|rollback|template_save|template_use|show")


@tool
def plate_pick(stage, piece="", view="Front", paired=False, v3_dir="", variants_dir="", design_words="", palette="", pick=None, bg_threshold=0.06, opening_iters=3, min_px=1024):
    """Plates stage of the piece pipeline. prompt: the library template (plate-4k-crisper) and its variables for one view (render it, generate 4 images per view); score: rank
    the 4 regenerations (variants_dir/1..4) against the approved V3 plate (v3_dir/<View>.png, RGBA): silhouette IoU x DoG structure x (1 - colour error); cut: the pick's alpha
    (luminance threshold, opening, fill holes, 1 px feather); run: score + cut + checks (margins, aspect, view correspondence) -> <piece>/plates_4k_alpha/<View>.png + alpha.json;
    status. A the user's `pick` (1-4) overrides the best score. Paired pieces: Front and Back only. Free, local, never overwrites."""
    from .pipeline import plates as PL
    return PL.tool(stage, str(_settings().project_root), piece, view, paired, _p(v3_dir), _p(variants_dir), design_words, palette, pick, bg_threshold, opening_iters, min_px)


@tool
def uv_score(objects=None, files=None, res=1024, out="uv_score.json", gates=None):
    """Score UV layouts on measurements, not by eye: utilization (rasterised at res, 256..4096), overlap, UV-connected islands, stretch p90/p10, the fraction of area off by 2x, flipped
    (mirrored) faces, seam length and a composite score (the shelf's uv_score). objects: mesh objects in the scene; files: .fbx/.glb attempts inside the project root, measured in a
    headless Blender (the live scene is untouched). Each row carries gates {pass, failed} (overlap <= 0.005, flipped <= 0.02, off-density <= 0.05, overridable). `best` is advice: the user picks."""
    from .features import uv_score as _UVS
    return _UVS.run(objects, files, res, out, str(_settings().project_root), gates)


@tool
def uv_texel_density(object, texture_size=2048, target="auto", weights=None, mode="island", repack=True, margin=0.005, name="", discard_texture=False):
    """Set and equalise texel density per UV island on a NEW object `<object>_td` (the source keeps its UVs), then repack and report the density actually achieved. target: px/metre,
    'N px/cm' or 'auto' (the current mean: only the spread changes); weights: {material | vertex group | island:N: factor 0.1..4}; mode island | all; texture_size a power of two.
    The layout is only ever shrunk to fit 0..1 (`shortfall` = achieved/requested says so). Refuses a textured object (a UV change discards the texture) unless discard_texture."""
    from .features import uv_texel as _UVT
    return _UVT.run(object, texture_size, target, weights, mode, repack, margin, name, discard_texture, str(_settings().project_root))


@tool
def mesh_defect_scan(object, piece="", kinds=None, thin_threshold_m=0.002, max_candidates=100):
    """A read-only clay inspection: typed defect candidates for the user's decisions, never an edit. kinds (default all): open_loop (boundary loops), floating_shell (a small shell
    >3 mm from the body), intersection (faces crossing faces, by BVH), thin (thinner than thin_threshold_m inward, default 2 mm, an unverified default), flipped_shell (a shell pointing
    into itself, closed or open), degenerate (zero-area faces), isolated_tri. Each candidate: id, kind, descriptor {faces, area_m2, centroid, bbox, normal, rim_length_m}, rule_verdict
    (keep | delete | hole | ambiguous), rule, severity. More than max_candidates (1..500): the first N plus truncated and total."""
    from .features import defect_scan as _DS
    return _DS.run(object, piece, kinds, thin_threshold_m, max_candidates)


@tool
def silhouette_compare(a, b, piece="", views=None, size=512, min_iou=0.9, landmarks=None):
    """Did the piece drift? Render the approved source `a` and the candidate `b` (a mesh, or a plate image with an alpha or a flat background) from the SAME orthographic cameras
    (Front/Back/Left/Right, framed on `a`) and report per view the silhouette IoU, area ratio, centroid shift and, with landmarks [{name, point}] in world space, the drift to b's
    surface; `pass` = worst IoU >= min_iou (0.9 is a placeholder, unverified). Side-by-side PNGs go to <root>/<piece>/compare/. A mirrored candidate fails the view that sees the mirror."""
    from .features import silhouette as _SIL
    return _SIL.run(a, b, str(_settings().project_root), piece, views, size, min_iou, landmarks)


@tool
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


@tool
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


@tool
def fit_openings(stage, object, axis=None, plane_origin=None, limb="", pose=None, answers=None, flange_mm=None, lip_mm=4.0, clearance_mm=15.0, piece="", captain_words="",
                 texture_discard_ack=False, depths_mm=None, size=384):
    """The openings decision at fit: every cap a seed put across a limb, neck or waist opening gets keep | gasket | delete, logged append-only in <piece>/fit/decisions.jsonl. detect: the capped
    sites along `axis` (pointing out of the piece); propose: proposals only (the user rules); apply: answers {"OP000": "gasket"}. A GASKET cuts the POSED limb's cross-section (`limb`, an
    object) plus clearance_mm (5..40, default 15) into the cap plane and forms a COLLAR - a tubular flange into the piece whose free edge rolls outward into a lip (an exhaust/intake manifold
    port, not a raw hole); its depth `flange_mm` (2..60) is the user's number: without it apply answers needs_decision, and `variants` builds and renders three depths (depths_mm) to pick.
    Needs `pose` (the fit_pose result): never the rest pose. Result `<object>_openings`; the source is untouched. Discards a studio texture (texture_discard_ack). keep changes no geometry."""
    from .features import opening as _OP
    return _OP.run(stage, object, str(_settings().project_root), axis, plane_origin, limb, pose, answers, flange_mm, lip_mm, clearance_mm, piece, captain_words, texture_discard_ack, depths_mm, size)


@tool
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


@tool
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


@tool
def bake_maps(source, target, maps=None, size=2048, margin_px=None, cage_extrusion_m="auto", max_ray_m=None, samples=16, normal_green="gl", allow_overlap=False, out_dir="bake", overwrite=False,
              attach=True):
    """Bake a high-poly donor (`source`: a name or a list) into a UV-mapped low-poly `target`: maps from normal (tangent), albedo (Cycles COLOR pass only: no lighting, by construction) and ao;
    size a power of two 32..8192 (default 2048); margin_px default size/128 (at least 2); cage_extrusion_m 0..0.2 or auto (2 % of the target's diagonal), max_ray_m default half of it; samples
    1..512. Runs in a niced HEADLESS Cycles worker, never in the live scene (the pair is exported to a temporary .blend). Refused before anything runs, each with its fix: no UV (unwrap first),
    overlapping UVs, unapplied non-uniform scale, source == target, a pair not aligned (bbox centres > 2 % of the diagonal apart), an unsupported map, an existing map without overwrite=true.
    Returns the PNG paths under <root>/<out_dir>/, the black-texel fraction per map (a cage-too-small hint when > 0.5 %), the colour spaces (normal and ao Non-Color, albedo sRGB) and, with
    attach, a <target>_baked material wired with the maps and `lw_baked_from` on the target. Curvature, cavity, dust, bevel and position are not Cycles bake types and are refused by name."""
    from .features import bake as _BK
    return _BK.run(source, target, maps, size, margin_px, cage_extrusion_m, max_ray_m, samples, normal_green, allow_overlap, out_dir, overwrite, attach, str(_settings().project_root))


@tool
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


@tool
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


@tool
def fit_pose(kind, **kw):
    """The closest pose of the body to a piece. chest: routed to pose_clearance (arms lowered and swung, then the spine and neck pitch chain). helmet, waist, boots, gauntlets: answers needs_decision -
    the bones, axes and ranges to sweep are the user's to rule; the contract's proposals come with it, marked unverified."""
    from . import posing as _PO
    return _PO.fit_pose(kind)


@tool
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


@tool
def weight_cleanup(object, armature, ops, mirror_from=None):
    """Fix weights on a COPY named <object>_wclean (the original stays). ops, in order: {op: normalize}, {op: limit, max_influences: 4}, {op: remove_influence, bone, region: {bbox: [[x0,y0,z0],[x1,y1,z1]]} |
    {vertex_group}} (refused when it would take one bone off more than 40 % of the vertices: that is a rebind, not a cleanup; never leaves a vertex with no weight), {op: smooth, iterations, factor, region},
    {op: rigid, bone, region} (full weight on one bone). Returns the ops applied with the vertices each changed and the weight_audit of the result. mirror_from is not built (it needs a verified symmetric mesh)."""
    from .features import weights as _W
    return _W.cleanup(object, armature, ops, mirror_from)


@tool
def weight_transfer(object, source, max_distance=0.05, max_normal_angle=30.0, flip_normals=True, inpaint_mode="point", limit_groups=4, deform_only=True, name="", engine="algorithmic"):
    """Copy skin weights from a rigged body onto a piece. Each piece vertex is matched to the closest point on the body's (deformed) surface and takes the barycentric weights when the distance <=
    max_distance (default 0.05 m, at most 0.5) and its normal is within max_normal_angle (default 30 degrees; a flipped normal also counts when flip_normals); every vertex with no trustworthy match is
    inpainted so armpits, crotch and chest-to-arm gaps blend without painting. engine algorithmic: a harmonic fill over the mesh graph (Blender's python); engine robust: the SIGGRAPH Asia 2023 method
    (robust Laplacian, biharmonic constrained solve) in the science python (needs LAMPWAY_PYTHON_SCIENCE with numpy scipy libigl robust_laplacian). limit_groups caps the influences (default 4, 0 = no cap).
    The source must carry vertex groups and exactly one Armature modifier; the piece must have no topology modifiers. Result: a NEW object <object>_wt (or `name`) with the body's groups and Armature; the
    original is untouched. Returns matched_fraction, inpainted_vertices, groups_written, the influence histogram and unweighted_vertices."""
    from .features import weights as _W
    return _W.transfer(object, source, max_distance, max_normal_angle, flip_normals, inpaint_mode, limit_groups, deform_only, name, engine)


@tool
def garment_clearance(piece, body, armature, pose_set="rest", clearance_target_m=0.015, classes=None):
    """How far a piece sits from the body in rest and named poses: the signed distance of every piece vertex to the body posed by `armature` (positive outside, negative inside). pose_set is 'rest', 'wiki8'
    (the eight stress poses) or a list [{name, bone, rotate: [x, y, z degrees]} | {name, bones: [{bone, rotate}]}]; the poses are reset afterwards. Per pose: min_clearance_m, penetrating_vertices, max_depth_m,
    worst_region [x, y, z] and the body triangles that block most; `pass` when every vertex clears its target (clearance_target_m, default 0.015, or the target of the piece's vertex group named in
    `classes` {group: metres}: rigid and cloth parts differ). Also pass_pose_count and closest_pose. Refused: a body with no Armature modifier (the body needs an armature) and a piece more than 0.5 m
    from the body (run place_piece first)."""
    from .features import clearance as _CL
    return _CL.run(piece, body, armature, pose_set, clearance_target_m, classes)


@tool
def fit_validate(stage, piece="", bound="", original="", poses=None, roles=None, limits=None, body="", armature="", validation=None):
    """Measure a bound piece through poses against its ORIGINAL shell, and judge it. stage measure (engine blender): `bound` the piece with an Armature modifier, `original` the pre-fit source shell (REQUIRED
    - measuring against a baked rest hides the distortion; same vertex count), `poses` [{name, bone, rotate: [x, y, z degrees], expect: {bone, axis, min_deg}} | {name, bones: [...]}], `roles` {part: metal |
    leather | cloth | embroidery} (from the user or the recipe, never a render's colour; a part is the vertex group of that name, or the whole piece when there is one role). Per pose and part: rigid residual
    with the scale FIXED (a breathing pose fails), edge strain, the seam gap, crossings of `body`; rest_fidelity (the source similarity: scale, rms, max mm); a crossing control when `body` is given (the piece
    is pushed 1 cm into the skin: a counter that cannot see it makes the run UNPROVEN). A pose whose expect fails is REFUSED and not measured. Verdicts: PASS | FAIL | UNVERIFIED (no limits for the role: cloth,
    leather, embroidery have none) | REFUSED | UNPROVEN; limits default to PROPOSED metal limits (1 mm rigid, 1 % strain, 1 mm seam: unverified placeholders) and the status rides along; ok only when nothing is
    unverified. stage judge: re-judge a validation (dict or file) under new `limits`."""
    from .features import validate_pose as _VP
    from .pipeline import validate as _V
    if stage == "measure":
        return _VP.measure(piece, bound, original, poses or [{"name": "rest"}], roles, limits, body or None, armature or None)
    if stage == "judge":
        v = json.loads(Path(_p(validation)).read_text()) if isinstance(validation, str) else dict(validation or {})
        if not v.get("poses"):
            raise ValueError("judge needs a validation with poses (the output of measure)")
        lim = limits or _V.PROPOSED
        judges = []
        for row in v["poses"]:
            for part in row.get("pieces", {}).values():
                part["judge"] = _V.judge(part["role"], {"rigid_residual_mm": part["rigid_residual_mm"], "strain_max_pct": part["strain_max"], "seam_gap_mm_max": part["seam_gap_mm_max"], "crossings_body": part.get("crossings_body")}, lim)
                judges.append(part["judge"])
        v["limits"] = lim
        v["summary"] = _V.summarize(judges, (v.get("crossing_control") or {}).get("ok") is not False)
        return v
    raise ValueError("stage is measure | judge")


@tool
def skeleton_export_check(armature="", fbx="", target=None, expect_unit_scale=1.0, allow_extra_bones=False):
    """Check an armature (in the scene) or an FBX (under the project root; give exactly one) against a reference skeleton: target {names_from: a reference FBX, e.g. a mannequin animation}. Reports leaf bones (`*_end`
    the reference does not have: export with add_leaf_bones off), missing and extra bones, parents that differ, the root, the unit scale (height ratio to the reference: a 100x export reads 100; expect_unit_scale
    default 1), the up axis and rest_vs_frame (rest_pose_is_frame_zero is true when bones are posed with no animation: the bind pose was taken from a posed scene). `pass` and the reasons. A profile name
    alone is refused: no profile table ships, pass a reference file."""
    from .features import export_checks as _EC
    return _EC.skeleton_check(armature, fbx, target, expect_unit_scale, allow_extra_bones, str(_settings().project_root))


@tool
def engine_import_check(package_dir, engine="unreal", collision=None, receipt=None):
    """Static check of an exported package (a folder with an FBX and Textures/) against the engine's import rules: the FBX header version (Unreal wants 7400+; FBX 2020.2 is 7700), mesh names and material
    slots, `UCX_<Render>_NN` collision meshes that must match a render mesh (`collision` lists the names expected), the textures the materials name that are missing from Textures/, textures nobody names, and an
    optional receipt from a hand-run import {engine_version, import_settings, wired_channels, notes} which is RECORDED, not judged. A package with no FBX is told to run export_piece first."""
    from .features import export_checks as _EC
    return _EC.engine_check(package_dir, engine, collision, receipt, str(_settings().project_root))


@tool
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


@tool
def fit_export(object, armature, out_dir, body, textures=None, validation="", bind_check="", note="", allow_unverified=False, _bone_axis="Z"):
    """The rigged export of a fitted piece, behind gates, with a read-back. Refuses (each names its fix): a missing validation or one with FAIL/UNPROVEN, roles with no declared limits (unless
    allow_unverified=true, and then the README says 'limits: proposed; roles without limits: ...'), a bind_check that is not ok, textures whose merge.json mesh_sha256 is not this mesh (a geometry step
    discards the texture: re-run steps 13-14), vertex groups naming a bone the body package does not have, an existing out_dir. Writes <object>.fbx with the contract settings (primary bone axis Z, secondary X,
    leaf bones off, units applied), Textures/, README.md (files with sha256, conventions, validation counts, limits status, read-back) and export.json, then READS THE FBX BACK and compares every joint's
    position and axes with the body package (positions to 0.1 mm, axes to 0.5 degrees): a position-only check passed exports whose frames were 90 degrees off, so it is never the gate."""
    from .features import fit_export as _FE
    return _FE.run(object, armature, out_dir, _p(body), textures, validation, bind_check, note, allow_unverified, str(_settings().project_root), _bone_axis)


@tool
def fit_bind(stage, piece="", armature="", roles=None, bind_overrides=None, out_dir="fit/bind", body_object="", accept_seam_gap_mm=None):
    """Bind a finished piece to the body's skeleton by the user's weight laws. plan: per part (a vertex group of the piece) a role from `roles` {part: metal | leather | cloth | embroidery} - the user's or
    the recipe's, never a render's colour: a part without one is refused - and a mode: metal = rigid, ONE bone at full weight (the bone with most of its vertices nearest, or the override), anything else =
    restrict (weighted by position from the body's own weights, restricted to the bones its geometry spans); `bind_overrides` {part: {mode, bones, reason}} (metal as blend is refused: ask for a ruled cut;
    an unknown bone names the nearest). Parts that share a seam and a bone form a rigid group; two rigid parts of one shell on different bones OPEN the seam (seam_opens). Writes bind_plan.json and seams.json.
    weights: a copy <piece>_fit (the source is untouched) with the plan's weights; the body's weights come from `body_object` (a skinned body in the scene: an approximation, the native sidecar sampler is not built).
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


@tool
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


@tool
def fit_state(stage="describe", **kw):
    """The descriptor / question / answer fit loop. Not built: answers needs_decision (is the Laya / fit-model route still the direction now that fit_validate measures the fit?). The question, the reason and a
    proposal are in the result."""
    from .pipeline import fit_glove as _FG
    return _FG.fit_state(stage)


@tool
def detail_normals(material, strengths=None, ambientcg_dir=""):
    """Micro depth for a textured_atlas material: per-material tiling detail normals, box-projected in object space (metals take their ambientCG
    NormalGL maps, cloth and leather a small bump from their colour), blended by the material's per-texel masks. Idempotent: its 'DN:' nodes are
    replaced on a re-run. strengths: {plate, gold, cloth, leather}; ambientcg_dir defaults to the settings' / LAMPWAY_AMBIENTCG_DIR."""
    from . import detail_normals as DN
    return DN.apply(material, strengths, ambientcg_dir or getattr(_settings(), "ambientcg_dir", None) or None)


@tool
def image_to_3d(images, size=1.0, resolution=64, mode="hull", depth=None, profile="round", name="", engine="algorithmic"):
    """Mesh from images, no model: ``hull`` = visual hull of two or more cardinal views ({"Front": path, "Left": path, ...}, Front u=+X,
    Left u=-Y), ``extrude`` = rounded/slab extrusion of Front (+Back) for paired pieces, ``relief`` = luminance relief of one image.
    Reported by re-projection IoU, volume and boundary edges. engine=studio:tripo is the Smart Mesh slot (100 credits: approval first)."""
    if engine == "algorithmic":
        s_ = _settings()
        images = {v: _p(p, s_.project_root) for v, p in images.items()}
    return _F_image3d.image_to_3d(images, size, resolution, mode, depth, profile, name, engine)


@tool
def splat_import(path, max_points=200000, name="lw_splat"):
    """Import a 3D Gaussian Splatting PLY (binary little endian: x y z f_dc_0..2 opacity scale_0..2) as ONE point object with colour,
    opacity and radius attributes and a geometry-nodes view; a splat is never converted to a mesh. max_points subsamples
    deterministically."""
    return _F_splat.splat_import(_p(path), max_points, name)


@tool
def render_video(object, out, kind="turntable", frames=48, width=640, height=360, fps=24, engine="workbench", waypoints=None):
    """Render a turntable or a keyframed camera path (``waypoints``: [{frame, location}]) of ``object`` to an H.264 mp4 under the project
    root with the light engines (workbench | eevee; never Cycles), in a throw-away scene. engine=model:<name> is the generative video
    slot: not wired."""
    return _F_video.render_video(object, _p(out), kind, frames, width, height, fps, engine, waypoints)


@tool
def project_views(object, views, size=1024, out="", occlusion=True):
    """Project cardinal-view images ({"Front": path, ...}, each framed to the subject) into the UV atlas by which way each texel faces
    (optional occlusion ray test) and apply it as the material ``<object>_proj``. Reports coverage and per-view share."""
    s_ = _settings()
    return _F_texture.project_views(object, {v: _p(p, s_.project_root) for v, p in views.items()}, size,
                                    _p(out or f"{object}_atlas.png", s_.project_root), occlusion)


@tool
def texture_gen(object, prompt, out_dir="", views=("Front", "Back"), size=1024, engine="algorithmic"):
    """Texture Gen: clay render of each view -> the server's image model paints it -> projection into the atlas -> material applied.
    The object needs UVs. engine=studio:tripo is the Texture + PBR slot (30 + 5 credits: approval first)."""
    if engine != "algorithmic":
        return _F_texture.texture_gen(object, prompt, "", views, size, engine)
    if not out_dir:
        raise ValueError("texture_gen needs out_dir (a project folder for the clay renders, the painted views and the atlas)")
    return _F_texture.texture_gen(object, prompt, _p(out_dir), list(views), size, engine)


@tool
def ai_render(object, prompt, view="Front", out="ai_render.png", size=768):
    """AI Render: a clay render of ``object`` from ``view`` is handed to the image model with the prompt; the result image is saved and
    loaded as a Blender image. It changes nothing in the scene (look development only)."""
    return _F_texture.ai_render(object, prompt, view, _p(out), size)


@tool
def repair_texture(object, texture, view, patch, mask, out, feather=2):
    """Local texture repair: blend ``patch`` through ``mask`` (both framed like a clay render of ``view``) into the existing atlas where
    the surface faces that view; writes ``out``, never overwrites ``texture``."""
    s_ = _settings()
    return _F_texture.repair_texture(object, _p(texture, s_.project_root), view, _p(patch, s_.project_root), _p(mask, s_.project_root),
                                     _p(out, s_.project_root), feather)


# ---- the door the agent's scripts use

TOOL_FUNCS = ("meshpaint", "chat_transcript", "qa_propose", "qa_proposals", "qa_descriptors", "mesh_prep", "asset_acceptance", "rig_armor", "status", "settings_get", "settings_set", "qa_setup", "qa_tag_layers", "qa_candidates", "qa_draw", "qa_read_tags",
              "qa_rulings", "rebuild_setup", "rebuild", "job_status", "run_tool", "export_piece", "retopo", "uv_unwrap", "segment_mesh", "auto_rig", "bind_to_armature", "pose_test", "image_to_3d", "splat_import", "render_video", "project_views", "texture_gen", "ai_render", "repair_texture", "detail_normals", "asset_lineage", "workflow_graph", "plate_pick", "uv_score", "uv_texel_density", "mesh_defect_scan", "silhouette_compare", "seed_audit", "fit_place", "fit_openings")


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
