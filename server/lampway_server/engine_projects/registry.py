"""The registry: every adapter runs, failures become 'no match', results sort by confidence then id; the generic fallback always matches. Paths must lie inside an enrolled root (symlinks are
resolved first). There is deliberately no method here that runs a command."""
import os
from pathlib import Path

from . import generic, godot, unreal
from .contracts import ProjectError

ADAPTERS = {"unreal": unreal, "godot": godot, "generic": generic}


def _inside(path, roots):
    real = Path(os.path.realpath(path))
    for r in roots or []:
        rr = Path(os.path.realpath(r))
        if real == rr or rr in real.parents:
            return real, rr
    raise ProjectError(f"{path} is outside the enrolled roots: enrol the folder first: engine_project_roots")


def detect(path, roots, ue_engine_dirs=(), run_script=None) -> list:
    real, root = _inside(path, roots)
    ctx = {"stop": root, "ue_engine_dirs": list(ue_engine_dirs or []), "run_script": run_script}
    out = []
    for adapter in ADAPTERS.values():
        try:
            ms = adapter.detect(real, ctx)
        except Exception:  # noqa: BLE001 - a failing adapter is "no match", never a failed detection
            continue
        out.extend(ms or [])
    return sorted(out, key=lambda m: (-m["confidence"], m["adapter_id"], m["name"]))


def capabilities(path, adapter_id, roots, ue_engine_dirs=(), run_script=None, which=None) -> dict:
    if adapter_id not in ADAPTERS:
        raise ProjectError(f"Unknown project adapter {adapter_id!r}; the adapters are {sorted(ADAPTERS)}")
    ms = [m for m in detect(path, roots, ue_engine_dirs, run_script) if m["adapter_id"] == adapter_id]
    if not ms:
        return {"matches": []}
    m = ms[0]
    _real, root = _inside(path, roots)
    caps = ADAPTERS[adapter_id].capabilities(m, {"stop": root, "ue_engine_dirs": list(ue_engine_dirs or []), "run_script": run_script})
    return {"adapter_id": adapter_id, "label": ADAPTERS[adapter_id].LABEL, "project": m, **caps}
