"""Unreal: the nearest ancestor with exactly one .uproject. Two in one folder are two matches at 0.5 with the reason. The engine association resolves by version string against the
configured engine install folders; a GUID association is reported as unresolved (the Linux registry of installed engines is not read)."""
import json
import os
import re
from pathlib import Path

from .contracts import MAX_FILES, SKIP_DIRS, ancestors, ini_section, match, walk_files

ID, LABEL = "unreal", "Unreal Engine project"
GUID = re.compile(r"^\{?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}?$")
EXES = ("Engine/Binaries/Linux/UnrealEditor", "Engine/Binaries/Win64/UnrealEditor.exe", "Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor")


def _engine_dir(assoc, dirs):
    for d in dirs or []:
        try:
            v = json.loads((Path(d) / "Engine" / "Build" / "Build.version").read_text())
        except (OSError, ValueError):
            continue
        if f"{v.get('MajorVersion')}.{v.get('MinorVersion')}" == assoc:
            return str(d)
    return None


def _describe(uproject: Path, ctx):
    data = json.loads(uproject.read_text())
    assoc = str(data.get("EngineAssociation") or "")
    kind = "guid" if GUID.match(assoc) else "version" if re.fullmatch(r"\d+\.\d+", assoc) else "custom" if assoc else "none"
    engine_dir = _engine_dir(assoc, ctx.get("ue_engine_dirs")) if kind == "version" else None
    ini = uproject.parent / "Config" / "DefaultEngine.ini"
    default_map = ini_section(ini.read_text(errors="replace"), "/Script/EngineSettings.GameMapsSettings").get("GameDefaultMap") if ini.is_file() else None
    content = sorted(p.name for p in (uproject.parent / "Content").iterdir()) if (uproject.parent / "Content").is_dir() else []
    return {"engine_association": assoc, "engine_association_kind": kind, "engine_dir": engine_dir,
            "engine_note": "a GUID association is unresolved: the registry of installed engines is not read here" if kind == "guid" else ("" if engine_dir or kind != "version" else "no configured engine folder matches this version"),
            "default_map": default_map, "modules": [m.get("Name") for m in data.get("Modules", [])], "plugins_enabled": [p.get("Name") for p in data.get("Plugins", []) if p.get("Enabled", True)],
            "content_roots": [f"Content/{c}" for c in content if (uproject.parent / "Content" / c).is_dir()], "uproject": uproject.name}


def detect(start, ctx):
    for d in ancestors(Path(start), ctx.get("stop")):
        found = sorted(d.glob("*.uproject"))
        if len(found) == 1:
            return [match(ID, d, 0.95, f"{found[0].name} found", found[0].stem, _describe(found[0], ctx))]
        if len(found) > 1:
            return [match(ID, d, 0.5, "two .uproject files here: pass the one you mean", f.stem, _describe(f, ctx)) for f in found]
    return None


def _content_counts(root: Path):
    out = []
    content = root / "Content"
    for dp, dn, fn in os.walk(content):
        dn[:] = sorted(dn)
        ua, um = sum(1 for f in fn if f.endswith(".uasset")), sum(1 for f in fn if f.endswith(".umap"))
        if ua or um:
            out.append({"path": Path(dp).relative_to(root).as_posix(), "uasset": ua, "umap": um})
    return out


def capabilities(m, ctx):
    root = Path(m["root"])
    up = root / m["metadata"]["uproject"]

    def allow(rel):
        parts = Path(rel).parts
        return rel == m["metadata"]["uproject"] or (parts[0] == "Config" and rel.endswith(".ini")) or (parts[0] == "Source" and rel.endswith(".Build.cs") and len(parts) <= 4)
    files = [f for f in walk_files(root, 5, allow) if not f["path"].startswith("Content/")]
    cmds = []
    ed = m["metadata"].get("engine_dir")
    if ed:
        for rel in EXES:
            exe = Path(ed) / rel
            if exe.is_file() and os.access(exe, os.X_OK):
                cmds.append({"id": "ue-editor", "label": "Open in the Unreal editor", "executable": str(exe), "cwd": str(root), "args": [str(up)], "safety": "open", "metadata": {}})
                if ctx.get("run_script"):
                    cmds.append({"id": "ue-run-script", "label": f"Run {ctx['run_script']} in the editor", "executable": str(exe), "cwd": str(root),
                                 "args": [str(up), f"-ExecutePythonScript={ctx['run_script']}"], "safety": "run", "metadata": {"reason": "runs the named script with the editor's full authority over the project"}})
                break
    arts = [{"path": m["metadata"]["uproject"]}] + ([{"default_map": m["metadata"]["default_map"]}] if m["metadata"].get("default_map") else [])
    ctxdocs = [{"path": n} for n in ("AGENTS.md", "README.md") if (root / n).is_file()]
    return {"files": files[:MAX_FILES], "content_counts": _content_counts(root), "commands": cmds, "artifacts": arts, "context": ctxdocs}
