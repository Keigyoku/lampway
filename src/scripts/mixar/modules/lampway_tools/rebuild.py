# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The rebuild loop: a QA'd piece rebuilt from its source mesh and the captain's rulings.

Ported from the shelf's meshqa/rebuild_textured.sh (SPIKE 2026-10-04); the recipe he runs now is
``RES=4096 COLOR_FULL=1 ORNAMENT=600:24:0.25 rebuild_textured.sh <tag>``. Steps, in order:

  patch_holes     delete ruled faces, refill, patch ruled holes (curved fill, rim pinned), relabel   (Blender)
  uv_patches      patch UVs: the island puzzle first, the rest Smart-UV + packed with the originals locked (Blender)
  mesh_to_npz     the patched mesh to npz                                                           (Blender)
  maps            npz turned to -Y front, per-face texel overrides converted from SOURCE face ids to this mesh's
                  triangles                                                                         (numpy, in process)
  relief_project  V3 colour projection into the atlas                                               (science python)
  material_masks  material masks                                                                    (science python)

Outputs: ``<out_root>/patched/<piece>_<tag>*`` and ``<out_root>/<tag>/`` (masks, texel_face, ...). A tag is never
overwritten; ``resume`` skips the steps whose outputs already exist. Every step is niced by the runner.
"""

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import runner as RUN


class TagExists(RuntimeError):
    pass


@dataclass
class RebuildSpec:
    piece: str
    source_mesh: str
    owner: str
    recipe: str
    candidates: str
    decisions: str
    deletions: str
    relabels_orig: str
    texel_overrides: str
    relief_dir: str
    plates_dir: str
    out_root: str
    turn: float = -90.0
    relabel_rules: list = field(default_factory=list)      # FROM:TO:WITH, passed to patch_holes --relabel
    res: int = 2048
    color_full: bool = False
    ornament: str = ""                                      # max_tris:reach_px:min_share, e.g. 600:24:0.25 at 4096
    mesh_gold: bool = False
    no_flow: bool = False                                   # plates painted over the mesh's own render are aligned: no relief warp


@dataclass
class Step:
    name: str
    tool: Optional[str]
    args: list
    env: dict
    outputs: list


_TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _dirs(spec: RebuildSpec, tag: str, out_name: Optional[str] = None):
    return Path(spec.out_root) / "patched", Path(spec.out_root) / (out_name or tag)


def mask_env(spec: RebuildSpec, tag: str) -> dict:
    """The chest's material-mask recipe (rebuild_textured.sh): pixel-sized parameters scale with K = RES / 2048."""
    k = max(1, spec.res // 2048)
    P, _ = _dirs(spec, tag)
    return {
        "MM_GOLD_MIN_SAT": "0.66", "MM_GOLD_MIN_VAL": "0.48", "MM_BLUR": f"{k}.0",
        "MM_EMB_MIN_SAT": "0.55", "MM_EMB_MIN_VAL": "0.40", "MM_EMB_MIN_BLOB": str(60 * k * k),
        "MM_CLOTH_MEDIAN": str(2 * k + 1), "MM_NO_VOTE_CLASSES": "rigid-metal dangle",
        "MM_EXTRA_GOLD": "yoke_strap_collar,pauldron_lion_R,pauldron_lion_L", "MM_LINEN_FORCE": "2",
        "MM_HEIGHT_GOLD_MM": "0.5", "MM_PART_GOLD_SV": "pauldron_right:0.72:0.55,pauldron_left:0.72:0.55",
        "MM_PLATE_GOLD_MIN_BLOB": str(8 * k * k), "MM_PART_GOLD_BLOB": f"cuirass_*:{40 * k * k},tasset_*:{40 * k * k}",
        "MM_PLATE_GOLD_AND_MM": "0.5", "MM_PLATE_GOLD_CLOSE": str(2 * k), "MM_LEATHER_FORCE": "1",
        "MM_PART_HEIGHT_GOLD": "belt_studded:1.0:0.5", "MM_RIM_GOLD": "pauldron_right:9:60,pauldron_left:9:60",
        "MM_RIM_CLOSE": str(3 * k), "MM_STUD_GOLD": "pauldron_*|cuirass_*|tasset_*|yoke_strap_collar:30:22",
        "MM_SOFTEN_GOLD": "0.9", "MM_GOLD_FROM_MESH": f"0.6:{10 * k}" if spec.mesh_gold else "",
        "MM_ORNAMENT_GOLD": spec.ornament, "MM_FORCE_CLASS": str(P / f"{spec.piece}_{tag}_force_class_tri.json"),
    }


def plan(spec: RebuildSpec, tag: str, out_name: Optional[str] = None) -> list:
    if not _TAG.match(tag):
        raise ValueError(f"tag {tag!r} must be a plain name (letters, digits, _ . -)")
    P, O = _dirs(spec, tag, out_name)
    base = str(P / f"{spec.piece}_{tag}")
    patch_args = [spec.source_mesh, spec.owner, spec.recipe, spec.candidates, spec.decisions, base,
                  "--deletions", spec.deletions]
    for rule in spec.relabel_rules:
        patch_args += ["--relabel", rule]
    patch_args += ["--relabel-orig", spec.relabels_orig]
    front = f"{base}_uv_front-y.npz"
    return [
        Step("patch_holes", "patch_holes", patch_args, {}, [f"{base}.fbx", f"{base}_owner_poly.npy", f"{base}_orig_poly.npy", f"{base}_patch.json"]),
        Step("uv_patches", "uv_patches", [f"{base}.fbx", f"{base}_orig_poly.npy", f"{base}_uv.fbx"], {}, [f"{base}_uv.fbx"]),
        Step("mesh_to_npz", "mesh_to_npz", [f"{base}_uv.npz", "piece_uv", f"{base}_uv.fbx"], {}, [f"{base}_uv.npz"]),
        Step("maps", None, [str(P), spec.piece, tag, spec.texel_overrides], {}, [front, f"{base}_owner_tri.npy", f"{base}_force_class_tri.json"]),
        Step("relief_project", "relief_project", [front, spec.relief_dir, spec.plates_dir, str(O), str(spec.res)],
             {"RP_COLOR_FULL": "1" if spec.color_full else "0", **({"RP_NO_FLOW": "1"} if spec.no_flow else {}),
              "RP_MESH_HEIGHT": "25" if spec.mesh_gold else "0"},
             [str(O / "detail_height_u16.png")]),
        Step("material_masks", "material_masks", [str(O), f"{base}_owner_tri.npy", spec.recipe, str(O), front],
             mask_env(spec, tag), [str(O / "masks.json")]),
    ]


def check_fresh(spec: RebuildSpec, tag: str) -> None:
    P, _ = _dirs(spec, tag)
    if (P / f"{spec.piece}_{tag}.fbx").exists():
        raise TagExists(f"{P / (spec.piece + '_' + tag + '.fbx')} exists: a tag is never overwritten; pick a new tag or resume")


def make_maps(patched_dir: str, piece: str, tag: str, texel_overrides: str, turn: float = -90.0) -> dict:
    """npz turned to the -Y front, owner per triangle, and the texel overrides (source face ids) as triangle lists."""
    P = Path(patched_dir)
    d = np.load(P / f"{piece}_{tag}_uv.npz")
    th = math.radians(turn)
    R = np.array([[math.cos(th), -math.sin(th), 0], [math.sin(th), math.cos(th), 0], [0, 0, 1]])
    V = d["V"] @ R.T
    np.savez(P / f"{piece}_{tag}_uv_front-y.npz", V=V, T=d["T"], P=V[d["T"]], UV=d["UV"], POLY=d["POLY"])
    own = np.load(P / f"{piece}_{tag}_owner_poly.npy")
    orig = np.load(P / f"{piece}_{tag}_orig_poly.npy")
    if not (d["POLY"].max() + 1 == len(own) == len(orig)):
        raise ValueError(f"polygon counts disagree: npz {d['POLY'].max() + 1}, owner {len(own)}, orig {len(orig)}")
    np.save(P / f"{piece}_{tag}_owner_tri.npy", own[d["POLY"]])
    force = {}
    for r in json.load(open(texel_overrides))["force_class"]:
        tris = np.flatnonzero(np.isin(orig[d["POLY"]], r["faces_orig"])).tolist()
        force.setdefault(r["class"], []).extend(tris)
    json.dump(force, open(P / f"{piece}_{tag}_force_class_tri.json", "w"))
    return {"polys": int(len(own)), "force_class_triangles": {k: len(v) for k, v in force.items()}}


def run(spec: RebuildSpec, tag: str, settings, runner: Callable = RUN.run, resume: bool = False,
        maps: Callable = make_maps, log_dir=None, timeout: Optional[float] = None, only=None, out_name: Optional[str] = None) -> dict:
    """Run the plan; returns {'ok', 'steps': [{name, rc, seconds?}], 'skipped': [...], 'failed': name | None, 'out': ...}."""
    steps = plan(spec, tag, out_name)
    if only is not None:
        unknown = [n for n in only if n not in {s.name for s in steps}]
        if unknown:
            raise ValueError(f"unknown step(s) {unknown}; the steps are {[s.name for s in steps]}")
        steps = [s for s in steps if s.name in only]
    if not resume:
        check_fresh(spec, tag)
    P, O = _dirs(spec, tag, out_name)
    P.mkdir(parents=True, exist_ok=True)
    O.mkdir(parents=True, exist_ok=True)
    report = {"ok": True, "steps": [], "skipped": [], "failed": None, "patched": str(P), "out": str(O),
              "mesh": str(P / f"{spec.piece}_{tag}_uv.fbx")}
    for step in steps:
        if resume and all(Path(o).exists() for o in step.outputs):
            report["skipped"].append(step.name)
            continue
        if step.tool is None:
            try:
                info = maps(*step.args, turn=spec.turn)
                report["steps"].append({"name": step.name, "rc": 0, **info})
            except Exception as exc:
                report.update(ok=False, failed=step.name, error=str(exc))
                report["steps"].append({"name": step.name, "rc": 1, "error": str(exc)})
                break
            continue
        res = runner(step.tool, step.args, settings, env_extra=step.env, log_dir=log_dir, timeout=timeout)
        report["steps"].append({"name": step.name, "rc": res.rc, "tail": res.stdout[-600:], "log": res.log})
        if res.rc != 0:
            report.update(ok=False, failed=step.name)
            break
    return report
