# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Lampway tool configuration: where things live. Pure Python (no bpy), so the command-line tools and the tests
read it the same way the add-on does.

Resolution order for every value: the environment variable, then ``<lampway home>/settings.json``, then the default.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def lampway_home(environ=None) -> Path:
    """The Lampway profile directory: ``$LAMPWAY_HOME``, else ``$XDG_DATA_HOME/lampway``, else ``~/.local/share/lampway``."""
    env = os.environ if environ is None else environ
    if env.get("LAMPWAY_HOME"):
        return Path(env["LAMPWAY_HOME"])
    base = env.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "lampway"


class PathOutsideProject(ValueError):
    pass


_FIELDS = ("project_root", "python_science", "python_browser", "blender", "nice", "tiles_dir", "ambientcg_dir", "hdri", "python_server", "server_dir",
           "image_backend", "autoremesher_bin")
_TEXT_FIELDS = ("image_backend",)          # plain strings; everything else but nice is a path


@dataclass
class Settings:
    """project_root     where pieces live: meshes, rulings, rebuilds (every tool path must stay inside it)
    python_science   a python with numpy + scipy + Pillow + OpenCV, for the texture and part-transfer tools
    python_browser   a python with patchright, for the Tripo Studio drivers (the SERVER runs those, never the app)
    blender          the Blender the headless tools run under; unset = this very app (its own binary)
    nice             the CPU niceness of every batch run (he works live while they run)
    tiles_dir        the folder of <Name>_BaseColor_Tile1024 colour tiles render_textured.py uses
    ambientcg_dir    the ambientCG material folders (Metal009, Metal048C) the metal normals and colours come from
    hdri             the studio .hdr the textured render is lit with
    python_server    a python that can run lampway_server (the mesh-paint image backend runs there, not in the app)
    server_dir       the directory holding the lampway_server package (the repo's server/)
    image_backend    the mesh-paint image backend: tripo | openrouter (unset = the backend's own default)
    autoremesher_bin the lampway-quadremesh executable (native/quadremesh/build.sh) that retopo method=autoremesher runs: the app never downloads one"""

    project_root: Path = None
    python_science: Optional[Path] = None
    python_browser: Optional[Path] = None
    blender: Optional[Path] = None
    nice: int = 15
    tiles_dir: Optional[Path] = None
    ambientcg_dir: Optional[Path] = None
    hdri: Optional[Path] = None
    python_server: Optional[Path] = None
    server_dir: Optional[Path] = None
    image_backend: Optional[str] = None
    autoremesher_bin: Optional[Path] = None


def _settings_file(home=None) -> Path:
    return (home or lampway_home()) / "settings.json"


def load(environ=None) -> Settings:
    env = os.environ if environ is None else environ
    home = lampway_home(env)
    s = Settings(project_root=home / "projects")
    try:
        data = json.loads(_settings_file(home).read_text(encoding="utf-8"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    for name in _FIELDS:
        raw = env.get(f"LAMPWAY_{name.upper()}") or data.get(name)
        if raw in (None, ""):
            continue
        setattr(s, name, int(raw) if name == "nice" else str(raw) if name in _TEXT_FIELDS else Path(raw))
    return s


def save(s: Settings, environ=None) -> Path:
    """Write the settings that are set (the environment is never written back)."""
    home = lampway_home(environ)
    home.mkdir(parents=True, exist_ok=True)
    data = {}
    for name in _FIELDS:
        v = getattr(s, name)
        if v is not None:
            data[name] = v if name == "nice" else str(v)
    path = _settings_file(home)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return path


def resolve_in_root(path, root) -> Path:
    """``path`` (relative to ``root``, or absolute inside it) as an absolute path; anything that resolves outside
    the root (``..``, an absolute path elsewhere, a symlink out) raises PathOutsideProject."""
    root = Path(root)
    p = Path(path)
    full = p if p.is_absolute() else root / p
    real_root = Path(os.path.realpath(root))
    real = Path(os.path.realpath(full))
    if real != real_root and real_root not in real.parents:
        raise PathOutsideProject(f"{path} is outside the project root {root}")
    return full


_PATH_TOKEN = __import__("re").compile(r"(?:(?<=^)|(?<=[=:,]))((?:\.\.?/|~/|/|\.\.$|~$)[^:,=]*|[^:,=/]+/[^:,=]*)")


def jail_args(args, root) -> list:
    """A batch tool's arguments with every path-like token resolved inside ``root``: positional paths, the value of a
    ``--flag=path``, and the path in a ``name=path:turn`` form. A token is path-like when it contains a slash or is
    ``..``/``~``; a bare file name is left alone (the tool runs with ``root`` as its working directory, so it lands
    there). A token that resolves outside the root raises PathOutsideProject."""
    out = []
    for raw in args:
        text = str(raw)
        if text == "-" or (text.startswith("--") and "=" not in text):
            out.append(text)
            continue

        def _sub(m):
            return str(resolve_in_root(Path(m.group(1)).expanduser(), root))

        out.append(_PATH_TOKEN.sub(_sub, text))
    return out


def blender_binary(s: Settings) -> Optional[Path]:
    if s.blender:
        return s.blender
    try:
        import bpy
        binary = bpy.app.binary_path
        return Path(binary) if isinstance(binary, str) and binary else None
    except Exception:
        return None


def interpreter_report(s: Settings) -> dict:
    out = {}
    for name, path in (("python_science", s.python_science), ("python_browser", s.python_browser),
                       ("blender", blender_binary(s))):
        out[name] = {"path": str(path) if path else None, "exists": bool(path and Path(path).exists())}
    return out
