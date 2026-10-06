"""A skill pack that proves itself when unpacked somewhere else: build refuses symlinks and forbidden names; verify checks duplicates, escaping or backslash names, the manifest checksums, the two skill
layouts being identical, and that every relative Markdown link in a SKILL.md resolves inside the extracted tree."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path

from . import mirror as MIR
from .roots import FORBIDDEN

LINK = re.compile(r"\]\(([^)#\s]+)\)")


class PackError(ValueError):
    pass


def _forbidden(name: str) -> bool:
    return bool(FORBIDDEN.search(name.rsplit("/", 1)[-1])) or name.rsplit("/", 1)[-1] in ("job.json", "result.json", "upload.json")


def _links_ok(base: Path, skill_md: Path) -> list:
    bad = []
    for m in LINK.finditer(skill_md.read_text(errors="replace")):
        t = m.group(1)
        if "://" in t or t.startswith(("mailto:", "/")):
            continue
        if not (skill_md.parent / t).resolve().is_file():
            bad.append(f"{skill_md.relative_to(base).as_posix()} links to {t}, which is not in the pack")
    return bad


def build(project, out, check_links=True) -> dict:
    project = Path(project)
    files = {}
    for sub in (".agents/skills", ".claude/skills"):
        root = project / sub
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(project).as_posix()
            if p.is_symlink():
                raise PackError(f"{rel} is a symlink: pack resources must be real files")
            if p.is_file() and not any(x.startswith(".") for x in p.relative_to(root).parts):
                if _forbidden(rel):
                    raise PackError(f"{rel} has a forbidden name (credentials, tokens, job state)")
                files[rel] = p
    lic = project / "LICENSES"
    if lic.is_dir():
        for p in sorted(lic.rglob("*")):
            if p.is_file() and not p.is_symlink():
                files["LICENSES/" + p.relative_to(lic).as_posix()] = p
    if check_links:
        with tempfile.TemporaryDirectory() as d:
            for rel, p in files.items():
                t = Path(d) / rel
                t.parent.mkdir(parents=True, exist_ok=True)
                t.write_bytes(p.read_bytes())
            bad = [b for rel in files if rel.endswith("SKILL.md") for b in _links_ok(Path(d), Path(d) / rel)]
        if bad:
            raise PackError("; ".join(bad))
    manifest = {"skills": sorted({r.split("/")[2] for r in files if r.startswith(".agents/skills/")}), "files": {r: hashlib.sha256(p.read_bytes()).hexdigest() for r, p in files.items()}}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=1, sort_keys=True))
        for rel, p in files.items():
            z.writestr(rel, p.read_bytes())
    return {"ok": True, "path": str(out), "files": len(files), "skills": manifest["skills"]}


def verify(zip_path) -> dict:
    problems = []
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        seen = set()
        for n in names:
            if n in seen:
                problems.append(f"duplicate entry {n}")
            seen.add(n)
            if "\\" in n or n.startswith("/") or ".." in Path(n).parts:
                problems.append(f"bad entry name {n!r}")
            elif _forbidden(n):
                problems.append(f"forbidden file name {n}")
        try:
            manifest = json.loads(z.read("manifest.json"))
        except (KeyError, ValueError):
            return {"ok": False, "problems": problems + ["manifest.json is missing or unreadable"]}
        for rel, h in manifest.get("files", {}).items():
            if rel not in seen:
                problems.append(f"{rel} is in the manifest but not in the pack")
            elif hashlib.sha256(z.read(rel)).hexdigest() != h:
                problems.append(f"checksum mismatch for {rel}")
        extra = [n for n in names if n not in manifest.get("files", {}) and n != "manifest.json" and not n.endswith("/")]
        problems += [f"{n} is in the pack but not in the manifest" for n in dict.fromkeys(extra) if not any(p.startswith("bad") or "forbidden" in p for p in problems if n in p)]
        if not problems or all("duplicate" not in p for p in problems):
            with tempfile.TemporaryDirectory() as d:                                  # outside the project: the pack must stand on its own
                safe = [n for n in names if "\\" not in n and not n.startswith("/") and ".." not in Path(n).parts]
                for n in dict.fromkeys(safe):
                    if n.endswith("/"):
                        continue
                    t = Path(d) / n
                    t.parent.mkdir(parents=True, exist_ok=True)
                    t.write_bytes(z.read(n))
                MIR_check = MIR.check(Path(d))
                if not MIR_check["ok"]:
                    problems.append("the .agents and .claude skill copies differ: " + ", ".join(MIR_check["missing"] + MIR_check["differing"]))
                for skill in Path(d).rglob("SKILL.md"):
                    problems += _links_ok(Path(d), skill)
    return {"ok": not problems, "problems": problems}
