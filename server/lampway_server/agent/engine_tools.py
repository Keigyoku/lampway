"""The agent's engine-project tool (engine_projects/): which engine project a folder belongs to and what may be offered about it. Read-only: command descriptions are returned as inert data
and nothing here starts a process. Paths must lie under the project root or an enrolled root (LAMPWAY_ENGINE_PROJECT_ROOTS); engine installs come from LAMPWAY_UE_ENGINE_DIRS."""

import json
import os
from pathlib import Path

from ..engine_projects import registry as R
from ..engine_projects.contracts import ProjectError
from . import server_tools as ST
from .providers.base import ToolSpec

NAMES = {"lampway_engine_project"}


def specs() -> list:
    return [ToolSpec("lampway_engine_project", "Which game-engine project is a folder (or an export package) going to, in what version? action detect: every adapter that matches (Unreal: the nearest "
                     "ancestor with one .uproject, engine association, default map, modules, enabled plugins; Godot; a generic fallback) sorted by confidence. action capabilities (adapter): files, command "
                     "DESCRIPTIONS (open | run: never executed by any tool), artifacts and context documents. Read-only. The path must be under the project root or an enrolled engine project root.",
                     {"type": "object", "additionalProperties": False, "required": ["action", "path"], "properties": {
                         "action": {"type": "string", "description": "detect | capabilities"}, "path": {"type": "string"}, "adapter": {"type": "string"}, "run_script": {"type": "string"}}})]


def _roots() -> list:
    roots = [str(ST.project_root())]
    roots += [p for p in os.environ.get("LAMPWAY_ENGINE_PROJECT_ROOTS", "").split(os.pathsep) if p]
    return roots


async def call(name: str, arguments: dict) -> tuple:
    a = arguments if isinstance(arguments, dict) else {}
    engines = [p for p in os.environ.get("LAMPWAY_UE_ENGINE_DIRS", "").split(os.pathsep) if p]
    try:
        path = a.get("path") or ""
        full = path if os.path.isabs(path) else str(Path(ST.project_root()) / path)
        if a.get("action") == "detect":
            return json.dumps({"matches": R.detect(full, _roots(), engines)}), False
        if a.get("action") == "capabilities":
            return json.dumps(R.capabilities(full, a.get("adapter") or "unreal", _roots(), engines, a.get("run_script") or None)), False
        return "action is detect | capabilities", True
    except ProjectError as exc:
        return str(exc), True
    except OSError as exc:
        return f"{type(exc).__name__}: {exc}", True
