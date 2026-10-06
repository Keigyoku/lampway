"""Godot: the second engine that proves the seam (off unless a project.godot is enrolled)."""
import re
import shutil
from pathlib import Path

from .contracts import ancestors, ini_section, match, walk_files

ID, LABEL = "godot", "Godot project"
EXT = {".gd", ".tscn", ".tres", ".godot", ".glb", ".gltf", ".png", ".svg", ".import", ".cfg", ".md", ".json"}


def detect(start, ctx):
    for d in ancestors(Path(start), ctx.get("stop")):
        f = d / "project.godot"
        if f.is_file():
            app = ini_section(f.read_text(errors="replace"), "application")
            feats = re.findall(r'"([^"]*)"', app.get("config/features", ""))
            return [match(ID, d, 0.9, "project.godot found", app.get("config/name") or d.name,
                          {"main_scene": app.get("run/main_scene"), "features": feats, "icon": app.get("config/icon")})]
    return None


def capabilities(m, ctx):
    root = Path(m["root"])
    cmds = []
    for exe in ("godot", "godot4"):
        path = shutil.which(exe)
        if path:
            cmds += [{"id": "godot-editor", "label": "Open in the Godot editor", "executable": path, "cwd": str(root), "args": ["--editor", "--path", str(root)], "safety": "open", "metadata": {}},
                     {"id": "godot-run", "label": "Run the project", "executable": path, "cwd": str(root), "args": ["--path", str(root)], "safety": "run", "metadata": {"reason": "runs project scripts"}}]
            break
    return {"files": walk_files(root, 2, lambda r: Path(r).suffix in EXT or r == "project.godot"), "commands": cmds, "artifacts": [{"path": "project.godot"}], "context": []}
