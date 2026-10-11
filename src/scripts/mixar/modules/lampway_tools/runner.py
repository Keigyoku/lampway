# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run a ported tool under the interpreter it needs, niced, with Lampway's configuration in its environment.

The ported tools are batch programs from the owner's shelf (scripts/). They are kept as command-line tools (AXI:
content first, refusals on stdout, unknown flags exit 2) and run as subprocesses, so a crash in a mesh tool never
takes the app down and the user can run the same file by hand.

    kind 'blender'  blender -b --python-exit-code 1 -P <tool> -- <args>   (this app's own binary unless one is configured)
    kind 'numpy'    <python> <tool> <args>   numpy / Pillow only: the configured science python, else the app's bundled one
    kind 'science'  <python> <tool> <args>   scipy / OpenCV: the configured science python, nothing else will do

Every run is niced (he works live while they run) and gets LAMPWAY_BRIDGE_PORT=0 so a batch Lampway never takes the
port a live window listens on.
"""

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import settings as S
from .canon_door import LEGACY, NONE, validate_declaration

SCRIPTS = Path(__file__).resolve().parent / "scripts"


class ToolUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    kind: str          # blender | numpy | science
    script: str        # relative to scripts/
    summary: str
    consumes: object   # REQUIRED (the normalization door): {arg: Need}, NONE("why") or, during migration, LEGACY("issue")
    opens_blend: bool = False   # the first argument is a .blend Blender opens before the script (``blender -b <blend> -P ...``)

    def __post_init__(self):
        validate_declaration(self.consumes)


def _t(name, kind, script, summary, consumes, opens_blend=False):
    return name, Tool(name, kind, script, summary, consumes, opens_blend)


TOOLS = dict([
    _t("mesh_qa", "blender", "meshqa/mesh_qa.py", "mesh QA candidates (open loops, floating shells) with review renders", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("patch_holes", "blender", "partseg/patch_holes.py", "apply mesh QA rulings: delete ruled faces, patch ruled holes, relabel", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("uv_patches", "blender", "partseg/uv_patches.py", "UV islands for patch faces, packed with the originals locked", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("delete_caps", "blender", "partseg/delete_caps.py", "delete a cap that closes an opening by ray-casting its footprint", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("bake_maps", "blender", "bake/bake_maps.py", "headless Cycles bake of high-poly donors onto a UV-mapped target: normal, colour-only albedo, AO", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("material_bake", "blender", "bake/material_bake.py", "headless Cycles bake of a material's channels (base colour, roughness, metallic, normal, AO, emission) with an ORM pack", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("asset_catalog_export", "blender", "library/catalog_export.py", "write Asset Vault assets into a Blender asset library .blend, marked with their catalogues", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("rtmw_detect", "science", "anim/rtmw_detect.py", "RTMW whole-body 2D keypoints per frame (rtmlib + onnxruntime, weights from disk)", LEGACY("reads video frames: a frame sequence has no kind in lampway.canonical-asset/1 yet")),
    _t("robust_weight_transfer", "science", "rig/robust_weight_transfer.py", "biharmonic inpainting of unmatched vertices' skin weights (robust skin-weight transfer)", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("render_owner", "blender", "partseg/render_owner.py", "render a mesh coloured by part owner, four views plus legend", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("mesh_to_npz", "blender", "proportion/mesh_to_npz.py", "export a mesh or the MetaHuman body to npz", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("proportion_fit", "blender", "proportion/proportion_fit.py", "clearance-fit overlays (fragile as a ranking)", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("mesh_compare", "blender", "proportion/mesh_compare.py", "compare candidate meshes with a reference, matcap renders", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("pose_clearance", "blender", "proportion/pose_clearance.py", "the MetaHuman's closest pose and residual blocking surfaces", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("render_textured", "blender", "texlib/render_textured.py", "textured look of a parts set on its shared atlas", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)"),
       opens_blend=True),
    _t("clay_view", "blender", "texlib/clay_view.py", "orthographic clay render of a mesh from a cardinal view (the mesh-paint input)", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("mesh_paint_set", "numpy", "texlib/mesh_paint_set.py", "projection plate set from mesh-paint results: picked painted views with their clay-render alpha", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("split_relief", "science", "partseg/split_relief.py", "split a raised relief out of its part as a material-only part", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("transfer_parts", "science", "partseg/transfer_parts.py", "carry an approved part set onto a new seed", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("apply_part_fixes", "numpy", "partseg/apply_part_fixes.py", "apply an auditor's part fixes to an owner map", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("relief_project", "science", "texlib/relief_project.py", "project view reliefs and plate colour into the UV atlas", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("material_masks", "science", "texlib/material_masks.py", "material masks from the projected colour and each part's class", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("pbr_merge", "science", "texlib/pbr_merge.py", "engine-ready PBR set: studio maps kept, patches filled, palette and metal fixes baked in", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("proportion_ratios", "numpy", "proportion/proportion_ratios.py", "scale-free landmark ratios against the body (the primary proportion score)", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("uv_score", "blender", "texlib/uv_score.py", "score UV layouts of files on measurements (utilization, overlap, islands, stretch, flipped, seams)", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("piece_ratios", "numpy", "proportion/piece_ratios.py", "proportion scores of helmet / waist / boots / gauntlets against the body (NEW, unvalidated)", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("place_piece", "numpy", "proportion/place_piece.py", "place a torso piece on the body the way the audits do", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
    _t("export_parts", "blender", "partseg/export_parts.py", "export a finished part set as Parts Library candidates: one GLB + part.json per part, versions never overwritten", LEGACY("runner argv: a mesh FILE path (npz/glb); the door resolves datablocks and canon sidecars, and mesh_to_npz does not yet write the npz canon header (migration group 1)")),
    _t("verify_set", "numpy", "partseg/verify_set.py", "independent check of an exported part set: every part GLB corner by corner against the source, every face once", LEGACY("runner argv: a source mesh FILE path; npz canon headers come with migration group 1 (mesh_to_npz)")),
    _t("render_final", "blender", "partseg/render_final.py", "render a finished part set: the assembly, the unassigned faces, each part isolated and in context", LEGACY("runner argv: a mesh FILE path; npz canon headers come with migration group 1 (mesh_to_npz)")),
    _t("judge_pack", "blender", "partseg/judge_pack.py", "the review pack for a parts regroup: two segmentations reconciled into candidates and decisions, with renders", LEGACY("runner argv: a mesh FILE path; npz canon headers come with migration group 1 (mesh_to_npz)")),
    _t("gen_parts_table", "numpy", "libwiki/gen_parts_table.py", "write a part set's table and held notes into the mesh wiki's entity spec from the exported files", NONE("reads the exported SET and part.json files, no geometry")),
    _t("index_delta", "numpy", "texlib/index_delta.py", "a texture library's next INDEX as a delta against a baseline listing (added, changed, removed; never overwritten)", NONE("compares two library listings (paths, sizes, sha256), no asset")),
    _t("libwiki", "numpy", "libwiki/libwiki.py", "publish a library inventory as an LLM wiki: build, lint, drift (deterministic; pages generated, never hand-edited)", NONE("reads a library listing (paths, sizes, sha256), no asset")),
    _t("pauldron_symmetry", "numpy", "proportion/pauldron_symmetry.py", "left versus mirrored-right shoulder height maps", LEGACY("canon N2 rollout: declare Need/NONE (specs/canon/normalization contracts/canon_migration.md)")),
])

_NOISE = re.compile(r"\[INFO\]|\[WARNING\]|\[agent_bubble\]|empty keymap|^register_class\(|^Info: Registering|^Warning: '.*' does not contain"
                    r"|^\[TD |^Library not found|^Blender quit|^Blender \d|HIPEW|libcurl|^$")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _python_for(tool: Tool, s: S.Settings) -> str:
    if s.python_science:
        return str(s.python_science)
    if tool.kind == "numpy":
        return sys.executable
    raise ToolUnavailable(
        f"{tool.name} needs a python with scipy and OpenCV: set LAMPWAY_PYTHON_SCIENCE (or python_science in "
        f"{S.lampway_home() / 'settings.json'}) to one, for example a venv with numpy scipy pillow opencv-python")


def command(name: str, args, s: Optional[S.Settings] = None) -> list:
    s = s or S.load()
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolUnavailable(f"no tool {name!r}; the tools are: {', '.join(sorted(TOOLS))}")
    script = str(SCRIPTS / tool.script)
    nice = ["nice", "-n", str(s.nice)]
    if tool.kind == "blender":
        blender = S.blender_binary(s)
        if blender is None:
            raise ToolUnavailable("no Blender to run under: set LAMPWAY_BLENDER (inside the app this is the app's own binary)")
        args = list(map(str, args))
        opened = [args.pop(0)] if tool.opens_blend and args else []
        return nice + [str(blender), "-b", *opened, "--python-exit-code", "1", "-P", script, "--", *args]
    return nice + [_python_for(tool, s), script, *map(str, args)]


@dataclass
class Result:
    rc: int
    stdout: str
    log: Optional[str]
    cmd: list
    timed_out: bool = False


def _env(s: S.Settings) -> dict:
    env = dict(os.environ)
    env["LAMPWAY_BRIDGE_PORT"] = "0"
    env["LAMPWAY_PROJECT_ROOT"] = str(s.project_root)
    for var, val in (("LAMPWAY_TILES_DIR", s.tiles_dir), ("LAMPWAY_AMBIENTCG_DIR", s.ambientcg_dir), ("LAMPWAY_HDRI", s.hdri)):
        if val:
            env[var] = str(val)
    return env


def run(name: str, args, s: Optional[S.Settings] = None, timeout: Optional[float] = None, max_chars: int = 6000,
        log_dir=None, env_extra=None, cwd=None) -> Result:
    """Run a tool; the result's ``stdout`` is its output with Blender's start-up noise dropped and cut to the LAST
    ``max_chars`` (a tool's summary comes last), the whole of it kept in ``log`` when ``log_dir`` is given.
    The truncation hint is separate from that body limit and retains the complete log path, whose length is unbounded."""
    s = s or S.load()
    cmd = command(name, args, s)
    env = _env(s)
    env.update(env_extra or {})
    timed_out = False
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
        rc, text = p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as exc:
        rc, timed_out = -1, True
        text = ((exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")) \
            + f"\nerror: {name} timed out after {timeout} s and was killed"
    log = None
    if log_dir is not None:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        log = str(Path(log_dir) / f"{name}.log")
        Path(log).write_text(text, encoding="utf-8")
    lines = [ln for ln in _ANSI.sub("", text).splitlines() if not _NOISE.search(ln)] if TOOLS[name].kind == "blender" \
        else text.splitlines()
    out = "\n".join(lines)
    if len(out) > max_chars:
        hint = f"(truncated, {len(out)} chars total" + (f" - full log: {log}" if log else "") + ")"
        out = hint + "\n" + out[-max_chars:]
    return Result(rc, out, log, cmd, timed_out)


def run_exe(cmd, timeout, cwd=None, nice=15, env=None) -> dict:
    """Run a configured executable niced in its OWN process group, with LAMPWAY_BRIDGE_PORT=0 and a hard timeout that kills the whole group. Returns {rc, log, timed_out, seconds}.
    The executable path comes from settings, never from an agent's arguments; stdout and stderr are merged into ``log`` (lines)."""
    import signal
    import time
    e = dict(os.environ)
    e.update({"LAMPWAY_BRIDGE_PORT": "0"})
    e.update(env or {})
    t0 = time.time()
    proc = subprocess.Popen(["nice", "-n", str(int(nice))] + [str(c) for c in cmd], cwd=cwd, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    timed_out = False
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, _ = proc.communicate()
    return {"rc": None if timed_out else proc.returncode, "log": (out or "").splitlines(), "timed_out": timed_out, "seconds": round(time.time() - t0, 3)}
