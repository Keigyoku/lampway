"""Server-side agent tools: the studio drivers.

They never go through Blender. The agent loop runs them here, as a subprocess under the browser python (the one with
patchright, ``LAMPWAY_PYTHON_BROWSER``), against the owner's logged-in tool browser. Safe by default: read-only commands,
and image/mesh generation run as a DRY RUN (every setting set and read back, nothing clicked) unless the call says
``dry_run: false``; a real generation additionally needs the owner's ``LAMPWAY_STUDIO_ARMED=1`` in THIS server's
environment, which no tool call can set (the driver refuses before it touches the browser otherwise).
Every path an argument names must stay inside the project root (``LAMPWAY_PROJECT_ROOT``).
"""

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .providers.base import ToolSpec

PKG_ROOT = str(Path(__file__).resolve().parents[2])           # the directory that holds lampway_server (for PYTHONPATH)
_BASE = "lampway_server.studios.tripo."


class BadToolCall(ValueError):
    pass


def project_root() -> Path:
    return Path(os.environ.get("LAMPWAY_PROJECT_ROOT") or Path.home() / ".local/share/lampway/projects")


def jail(path: str) -> str:
    root = project_root()
    full = Path(path) if Path(path).is_absolute() else root / path
    real_root, real = Path(os.path.realpath(root)), Path(os.path.realpath(full))
    if real != real_root and real_root not in real.parents:
        raise BadToolCall(f"{path} is outside the project root {root}")
    return str(full)


@dataclass
class A:
    name: str
    type: str = "string"
    desc: str = ""
    required: bool = False
    path: bool = False


@dataclass
class Local:
    name: str
    description: str
    module: str
    args: list = field(default_factory=list)
    timeout: float = 3600.0

    def spec(self) -> ToolSpec:
        props = {a.name: ({"type": "array", "items": {"type": "string"}, "description": a.desc} if a.type == "array"
                          else {"type": a.type, "description": a.desc}) for a in self.args}
        return ToolSpec(self.name, self.description, {"type": "object", "properties": props,
                        "required": [a.name for a in self.args if a.required], "additionalProperties": False})


_SPEND = (" Defaults to a DRY RUN: it sets and reads back every setting and clicks nothing. A real generation needs "
          "dry_run=false AND the owner's own LAMPWAY_STUDIO_ARMED=1 in the server's environment; it can spend credits, so never "
          "pass dry_run=false unless the user asked for exactly that generation.")

LOCALS = [
    Local("studio_tripo_state", "Read-only: the live state of the owner's Tripo Studio tab (credits, image quota, selected piece).",
          "tripo_image", [], 120),
    Local("studio_tripo_image", "Tripo Studio image generation (GPT Image 2.5, 4 images, 4K, free quota). Every setting is read back "
          "right before Generate and the run refuses on any mismatch, including a price that is not free." + _SPEND,
          "tripo_image", [A("out_dir", desc="New output directory", required=True, path=True),
                          A("prompt_file", desc="Text file holding the prompt", required=True, path=True),
                          A("refs", "array", "Reference images", path=True), A("model", desc="Default GPT Image 2.5"),
                          A("aspect", desc="Default 1:1"), A("count", desc="Always 4; fewer is refused"),
                          A("no_4k", "boolean", "Turn 4K off"), A("dry_run", "boolean", "Default true")], 900),
    Local("studio_tripo_mesh", "Tripo Studio Smart Mesh from the four cardinal views at the topology's maximum polycount, 4 variants; "
          "the price shown must equal the expected one or the run refuses." + _SPEND,
          "tripo_mesh", [A("out_dir", required=True, path=True), A("front", required=True, path=True), A("left", required=True, path=True),
                         A("right", required=True, path=True), A("back", required=True, path=True),
                         A("topology", desc="Quad (default) or Triangle"), A("polycount", desc="max (default)"),
                         A("expect_price", desc="Default 100"), A("dry_run", "boolean", "Default true")], 2400),
    Local("studio_tripo_fetch", "Download the variants of one Tripo Studio generation by its card stamp (read-only on Studio).",
          "tripo_fetch", [A("out_dir", required=True, path=True), A("stamp", desc="MM-DD HH:MM", required=True), A("expect", "integer")], 900),
    Local("studio_seed_catalog", "List the local catalog of every 3D seed with proportion scores and audit verdicts (no signed URLs are stored).",
          "seed_db", [A("piece"), A("by", desc="score (default) or created")], 60),
]
_TEX = (" Texturing comes LAST (the driver refuses unless the model's History holds a Smart UV step) and acts on the saved "
        "COPY the owner selected in Studio. Every setting is read back before Generate; the price must be the expected one."
        " Defaults to a DRY RUN (set + verify, nothing generated). A real run needs dry_run=false, an out_dir, AND the owner's own"
        " LAMPWAY_STUDIO_ARMED=1 in the server's environment; it spends credits (Texture 8K = 30, PBR = 5), so never pass"
        " dry_run=false unless the user asked for exactly that generation.")
LOCALS += [
    Local("studio_tripo_texture_state", "Read-only: the Texture panel's settings and price, and the selected model's History stamps.",
          "tripo_texture", [], 180),
    Local("studio_tripo_refs", "Replace the four reference images of the Texture tool (the generation plates by default) with the "
          "given ones, in Studio's slot order." + _TEX, "tripo_texture",
          [A("front", required=True, path=True), A("left", required=True, path=True), A("right", required=True, path=True),
           A("back", required=True, path=True)], 300),
    Local("studio_tripo_texture", "Tripo Studio Texture on the selected Smart UV clone, at a resolution, with or without Remove "
          "Lighting." + _TEX, "tripo_texture",
          [A("res", desc="2K | 4K | 8K (default 8K)"), A("remove_lighting", "boolean", "Default true"),
           A("expect_price", "integer", "Default 30"), A("out_dir", desc="Where the FBX and the extracted maps go (a real run)", path=True),
           A("dry_run", "boolean", "Default true")], 1500),
    Local("studio_tripo_pbr", "Tripo Studio PBR (normal / roughness / metallic) on the selected textured clone." + _TEX, "tripo_texture",
          [A("expect_price", "integer", "Default 5"), A("out_dir", desc="Where the FBX and the extracted maps go (a real run)", path=True),
           A("dry_run", "boolean", "Default true")], 1500),
    Local("studio_tripo_restore", "Make one History version of the selected model current again (free; the current one stays in "
          "History). The stamp is as Studio shows it, MM-DD HH:MM.", "tripo_texture", [A("stamp", required=True)], 180),
]
LOCALS.append(Local(
    "studio_image_generate", "Painted variants of a clay render (the mesh-paint step): through the configured image backend, "
    "`tripo` (Tripo Studio driver: GPT Image 2.5, 4 images, 4K, free quota) or `codex_cli` (the owner's own Codex login, only if "
    "the local-CLI setting is on) or `openrouter` (an OpenRouter image model; at most 4 images, each request costs money). refs in order: the clay render, a painted consistency view (optional), the design plate. "
    "Defaults to a dry run (tripo: settings read back, nothing clicked); `live: true` generates, and tripo additionally needs the "
    "owner's LAMPWAY_STUDIO_ARMED=1. Never pass live=true unless the user asked for exactly that.", "imagegen",
    [A("prompt_file", required=True, path=True), A("refs", "array", "Reference images in order", path=True),
     A("out_dir", required=True, path=True), A("backend", desc="tripo (default), codex_cli, or openrouter (an OpenRouter image model; paid, counted against the session spend ceiling, live=true only when asked)"), A("count", "integer", "Default 4"),
     A("live", "boolean", "Default false")], 3600))
BY_NAME = {d.name: d for d in LOCALS}
SPECS = [d.spec() for d in LOCALS]


def is_local(name: str) -> bool:
    return name in BY_NAME


def command(name: str, arguments: dict) -> list:
    d = BY_NAME.get(name)
    if d is None:
        raise BadToolCall(f"no server tool {name!r}")
    arguments = arguments if isinstance(arguments, dict) else {}
    missing = [a.name for a in d.args if a.required and arguments.get(a.name) in (None, "")]
    if missing:
        raise BadToolCall(f"{name} needs {', '.join(missing)}")
    py = os.environ.get("LAMPWAY_PYTHON_BROWSER") or sys.executable
    if name == "studio_image_generate":
        raise BadToolCall("studio_image_generate runs in-process, not as a subprocess")
    cmd = [py, "-m", _BASE + d.module]

    def val(key):
        v = arguments.get(key)
        a = next(x for x in d.args if x.name == key)
        return jail(v) if a.path else str(v)

    if name == "studio_tripo_image" or name == "studio_tripo_mesh" or name == "studio_tripo_fetch":
        if name == "studio_tripo_image":
            count = str(arguments.get("count") or "4")
            if count != "4":
                raise BadToolCall("never fewer than 4 images per generation")
            cmd += [val("out_dir"), val("prompt_file")]
            for r in arguments.get("refs") or []:
                cmd += ["--ref", jail(r)]
            cmd += ["--model", str(arguments.get("model") or "GPT Image 2.5"), "--aspect", str(arguments.get("aspect") or "1:1"), "--count", count]
            if arguments.get("no_4k"):
                cmd.append("--no-4k")
        elif name == "studio_tripo_mesh":
            cmd += [val("out_dir")]
            for view in ("front", "left", "right", "back"):
                cmd += [f"--{view}", val(view)]
            cmd += ["--topology", str(arguments.get("topology") or "Quad"), "--polycount", str(arguments.get("polycount") or "max"),
                    "--expect-price", str(arguments.get("expect_price") or "100")]
        else:
            cmd += [val("out_dir"), str(arguments["stamp"])]
            if arguments.get("expect"):
                cmd += ["--expect", str(int(arguments["expect"]))]
        if name != "studio_tripo_fetch" and arguments.get("dry_run", True) is not False:
            cmd.append("--dry-run")
    elif name in ("studio_tripo_texture_state", "studio_tripo_refs", "studio_tripo_texture", "studio_tripo_pbr", "studio_tripo_restore"):
        if name == "studio_tripo_texture_state":
            cmd += ["state"]
        elif name == "studio_tripo_refs":
            cmd += ["refs"] + [x for v in ("front", "left", "right", "back") for x in (f"--{v}", val(v))]
        elif name == "studio_tripo_restore":
            cmd += ["restore", "--stamp", str(arguments["stamp"])]
        else:
            if name == "studio_tripo_texture":
                cmd += ["texture", "--res", str(arguments.get("res") or "8K"), "--expect-price", str(int(arguments.get("expect_price") or 30))]
                if arguments.get("remove_lighting", True) is not False:
                    cmd.append("--remove-lighting")
            else:
                cmd += ["pbr", "--expect-price", str(int(arguments.get("expect_price") or 5))]
            if arguments.get("dry_run", True) is False:
                if not arguments.get("out_dir"):
                    raise BadToolCall(f"{name} with dry_run=false needs out_dir (where the FBX and maps go)")
                cmd += ["--go", "--out", val("out_dir")]
    elif name == "studio_seed_catalog":
        cmd += ["list"]
        if arguments.get("piece"):
            cmd += ["--piece", str(arguments["piece"])]
        if arguments.get("by") in ("score", "created"):
            cmd += ["--by", arguments["by"]]
    return cmd


def environment() -> dict:
    """The driver's environment: ours, plus PYTHONPATH to the server package. The arming variable is passed on exactly as the
    owner set it for this server process; nothing in a tool call can add to it."""
    env = dict(os.environ)
    env["PYTHONPATH"] = PKG_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _exec(cmd: list, env: dict, timeout: float):
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _run_imagegen(arguments: dict) -> tuple:
    from .. import imagegen as IG
    try:
        arguments = arguments if isinstance(arguments, dict) else {}
        for key in ("prompt_file", "out_dir"):
            if not arguments.get(key):
                raise BadToolCall(f"studio_image_generate needs {key}")
        res = IG.generate(arguments.get("backend") or IG.backend_name(), arguments["prompt_file"], arguments.get("refs") or [],
                          arguments["out_dir"], int(arguments.get("count") or 4), bool(arguments.get("live")))
    except (BadToolCall, IG.ImageGenError, ValueError) as exc:
        return str(exc), True
    lines = [f"backend: {res['backend']}", f"dry_run: {str(res['dry_run']).lower()}", f"images: {len(res['files'])}"] + [f"  {f}" for f in res["files"]]
    return "\n".join(lines) + ("\n" + res["output"][-1500:] if res["dry_run"] else ""), False


def run(name: str, arguments: dict) -> tuple:
    """(text for the model, is_error)."""
    if name == "studio_image_generate":
        return _run_imagegen(arguments)
    try:
        cmd = command(name, arguments)
    except BadToolCall as exc:
        return str(exc), True
    d = BY_NAME[name]
    try:
        rc, out = _exec(cmd, environment(), d.timeout)
    except subprocess.TimeoutExpired:
        return f"{name} timed out after {d.timeout:.0f} s", True
    except OSError as exc:
        return f"could not start {name}: {exc}", True
    out = out if len(out) <= 8000 else f"(truncated, {len(out)} chars)\n" + out[-8000:]
    return out, rc != 0
