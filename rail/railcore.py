# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The rail's IO half: read the tree and its history, generate the harness registrations, and judge both.

One entry point a caller needs, ``check(repo)``: the inventory (rails, stubs, the Child DOX Index, the catalog, the generated
registrations) plus the anneal rule over every commit that descends from the adoption baseline, plus the uncommitted worktree.
``sync(repo)`` regenerates the registrations; ``closeout(repo, tag)`` reads the root rail's DOX closeout row for a tag.

Nothing here writes outside ``sync``. Findings carry stable codes (``CODES``); ``rail/selftest.py`` plants a violation for every
code and fails if a code has no plant, so a rule cannot exist without a demonstration that it fires.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

try:
    from . import anneal as A
except ImportError:                       # run as a script: rail/ is on sys.path
    import anneal as A                    # type: ignore

VERSION = "1.0.0"
CATALOG = "rail/catalog.json"
MANIFEST = ".agents/skills/LAMPWAY-RAIL.generated.json"
REGISTRATIONS = (".agents/skills", ".claude/skills")
STUB = "@AGENTS.md\n"
ROOT_SECTIONS = ("Skills", "Child DOX Index", "DOX closeout", "Anneal log")
NESTED_SECTIONS = ("Invariants", "Test", "Owner", "Anneal log")
CATALOG_KEYS = {"schema", "baseline", "baseline_reason", "triggers", "exemptions", "generated"}
SKIP_PARTS = {"upstream", "source", "build", "node_modules", ".git", "__pycache__", ".venv"}

CODES = {
    "RAIL-001": "a generated registration differs from its canonical skill (run `python3 rail/rail.py sync`)",
    "RAIL-002": "a registration directory or file has no canonical source (extras)",
    "RAIL-003": "the catalog is invalid: a trigger or owner path that does not exist, or an unknown key",
    "RAIL-004": "rail frontmatter: the gated anneal contract, verification-mode, or a skill's name/description",
    "RAIL-005": "a malformed Anneal log",
    "RAIL-006": "a CLAUDE.md that is not exactly the one line `@AGENTS.md`",
    "RAIL-007": "an AGENTS.md without its CLAUDE.md stub, or a CLAUDE.md without an AGENTS.md",
    "RAIL-008": "the root Child DOX Index and the nested AGENTS.md files on disk disagree",
    "RAIL-009": "a rail missing a required section",
    "RAIL-010": "a rail changed with no new anneal row",
    "RAIL-011": "a prior anneal row edited, deleted or reordered",
    "RAIL-012": "an anneal row appended with no body change (a receipt for nothing)",
    "RAIL-013": "a trigger changed without its owner's anneal row and body change",
    "RAIL-014": "a rail deleted with no successor carrying its anneal log",
    "RAIL-015": "the adoption baseline is not an ancestor commit (or the history is too shallow to judge)",
    "RAIL-016": "an exemption that is malformed or no longer matches a finding",
    "RAIL-017": "a symlink where a rail, stub or registration must be a regular file",
    "RAIL-018": "a generated document is stale, or its generator's check could not run",
}


class GitError(RuntimeError):
    pass


def _finding(code, path, message, commit=None, trigger=None):
    out = {"code": code, "path": path, "message": message}
    if trigger and trigger != path:
        out["trigger"] = trigger
    if commit:
        out["commit"] = commit
    return out


# --------------------------------------------------------------------------- git and the tree

def git(repo, *args, input: Optional[bytes] = None) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, input=input)
    if result.returncode:
        raise GitError(f"git {' '.join(args[:3])}: {result.stderr.decode(errors='replace').strip()[:300]}")
    return result.stdout


def _skipped(path: str) -> bool:
    parts = path.split("/")
    return parts[0] in SKIP_PARTS or any(p in ("__pycache__", "node_modules", ".venv") for p in parts)


def worktree_files(repo: Path) -> List[str]:
    """Tracked files plus untracked ones git does not ignore, that exist on disk (a deleted tracked file is gone)."""
    raw = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard").decode()
    return sorted({p for p in raw.split("\0") if p and not _skipped(p) and (os.path.lexists(repo / p))})


def load_catalog_text(text: str) -> dict:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate JSON key {key!r}")
            out[key] = value
        return out
    return json.loads(text, object_pairs_hook=pairs)


def _relevant(path: str, triggers: set) -> bool:
    return A.is_agents(path) or path.startswith(A.SKILLS_DIR) or path == CATALOG or path in triggers


def snapshot_commit(repo: Path, commit: str, extra_triggers: set = frozenset()) -> Dict[str, str]:
    paths = [p for p in git(repo, "ls-tree", "-r", "-z", "--name-only", "--full-tree", commit).decode().split("\0") if p and not _skipped(p)]
    catalog_triggers = set(extra_triggers)
    if CATALOG in paths:
        try:
            catalog_triggers |= set(load_catalog_text(git(repo, "show", f"{commit}:{CATALOG}").decode()).get("triggers", {}))
        except (ValueError, GitError):
            pass
    wanted = [p for p in paths if _relevant(p, catalog_triggers)]
    if not wanted:
        return {}
    query = "".join(f"{commit}:{p}\n" for p in wanted).encode()
    out = git(repo, "cat-file", "--batch", input=query)
    snap, pos = {}, 0
    for path in wanted:
        header_end = out.index(b"\n", pos)
        header = out[pos:header_end].decode().split()
        size = int(header[2])
        data = out[header_end + 1: header_end + 1 + size]
        pos = header_end + 1 + size + 1
        snap[path] = data.decode("utf-8", errors="replace")
    return snap


def snapshot_worktree(repo: Path, extra_triggers: set = frozenset()) -> Dict[str, str]:
    files = worktree_files(repo)
    catalog_triggers = set(extra_triggers)
    if (repo / CATALOG).is_file():
        try:
            catalog_triggers |= set(load_catalog_text((repo / CATALOG).read_text()).get("triggers", {}))
        except ValueError:
            pass
    snap = {}
    for p in files:
        if _relevant(p, catalog_triggers) and (repo / p).is_file():
            snap[p] = (repo / p).read_bytes().decode("utf-8", errors="replace")
    return snap


# --------------------------------------------------------------------------- the inventory

def _catalog(repo: Path, findings: list) -> dict:
    path = repo / CATALOG
    if not path.is_file():
        findings.append(_finding("RAIL-003", CATALOG, "the catalog is missing"))
        return {"triggers": {}, "exemptions": []}
    try:
        catalog = load_catalog_text(path.read_text())
    except ValueError as exc:
        findings.append(_finding("RAIL-003", CATALOG, f"the catalog is not valid JSON: {exc}"))
        return {"triggers": {}, "exemptions": []}
    unknown = set(catalog) - CATALOG_KEYS
    if catalog.get("schema") != 1 or unknown or not isinstance(catalog.get("triggers"), dict) or not isinstance(catalog.get("exemptions"), list):
        findings.append(_finding("RAIL-003", CATALOG, f"the catalog needs schema 1, a triggers map and an exemptions list; unknown keys: {sorted(unknown)}"))
        return {"triggers": {}, "exemptions": [], **{k: v for k, v in catalog.items() if k == "baseline"}}
    generated = catalog.get("generated", [])
    if not isinstance(generated, list):
        findings.append(_finding("RAIL-003", CATALOG, "generated must be a list of {doc, script, args}"))
        catalog["generated"] = []
    for row in catalog.get("generated", []):
        ok = isinstance(row, dict) and isinstance(row.get("doc"), str) and isinstance(row.get("script"), str) and isinstance(row.get("args", []), list)
        if not ok or not (repo / row["script"]).is_file():
            findings.append(_finding("RAIL-003", CATALOG, f"generated row {row!r}: needs doc, an existing script and an args list"))
    for trigger, row in sorted(catalog["triggers"].items()):
        owner = row.get("owner") if isinstance(row, dict) else None
        if not (repo / trigger).is_file():
            findings.append(_finding("RAIL-003", CATALOG, f"trigger {trigger} does not exist (a moved file leaves a dead row)"))
        if not isinstance(owner, str) or not A.is_rail(owner) or not (repo / owner).is_file():
            findings.append(_finding("RAIL-003", CATALOG, f"trigger {trigger}: owner {owner!r} must be an existing AGENTS.md or rail/skills/<name>/SKILL.md"))
        if A.is_rail(trigger) or A.skill_of(trigger):
            findings.append(_finding("RAIL-003", CATALOG, f"trigger {trigger} is itself part of a rail; rails are judged directly"))
    return catalog


def _check_rail_text(path: str, text: str, findings: list, skill_name=None, required=()) -> None:
    try:
        A.check_frontmatter(text, skill_name)
    except A.RailError as exc:
        findings.append(_finding(exc.code, path, str(exc)))
    try:
        A.anneal_rows(text)
    except A.RailError as exc:
        findings.append(_finding(exc.code, path, str(exc)))
    have = A.sections(text)
    for name in required:
        if have.count(name) != 1:
            findings.append(_finding("RAIL-009", path, f"needs exactly one '## {name}' section (found {have.count(name)})"))


def _linked(text: str, heading: str, target: str) -> set:
    """Every link to a ``target``-named file inside one section of the root rail (normalised, repository-relative)."""
    match = re.search(r"(?ms)^## " + re.escape(heading) + r"[ \t]*\n(.*?)(?=^## |\Z)", text)
    if not match:
        return set()
    return {os.path.normpath(m).replace(os.sep, "/") for m in re.findall(r"\]\(([^)#\s]+" + re.escape(target) + r")\)", match.group(1))}


def inventory(repo: Path, files: List[str]) -> (List[dict], dict):
    findings: List[dict] = []
    catalog = _catalog(repo, findings)
    agents = [p for p in files if A.is_agents(p)]
    claudes = [p for p in files if p == "CLAUDE.md" or p.endswith("/CLAUDE.md")]
    for path in agents + claudes:
        if (repo / path).is_symlink():
            findings.append(_finding("RAIL-017", path, "a rail or stub must be a regular file (a git symlink checks out as a text line on Windows)"))
    for path in agents:
        sibling = path[: -len("AGENTS.md")] + "CLAUDE.md"
        if sibling not in claudes:
            findings.append(_finding("RAIL-007", path, f"needs its stub {sibling} containing exactly `@AGENTS.md`"))
        if (repo / path).is_symlink():
            continue
        text = (repo / path).read_text(encoding="utf-8", errors="replace")
        _check_rail_text(path, text, findings, required=ROOT_SECTIONS if path == "AGENTS.md" else NESTED_SECTIONS)
    for path in claudes:
        sibling = path[: -len("CLAUDE.md")] + "AGENTS.md"
        if sibling not in agents:
            findings.append(_finding("RAIL-007", path, f"a CLAUDE.md with no {sibling}: the contract lives in AGENTS.md and CLAUDE.md only imports it"))
        elif not (repo / path).is_symlink() and (repo / path).read_bytes() != STUB.encode():
            findings.append(_finding("RAIL-006", path, "must be exactly the one line `@AGENTS.md` (pinned against the literal, never against its siblings)"))
    if "AGENTS.md" in agents:
        root_text = (repo / "AGENTS.md").read_text(encoding="utf-8", errors="replace")
        listed = _linked(root_text, "Child DOX Index", "AGENTS.md")
        nested = {p for p in agents if p != "AGENTS.md"}
        for path in sorted(nested - listed):
            findings.append(_finding("RAIL-008", path, "a nested rail the root Child DOX Index does not list"))
        for path in sorted(listed - nested):
            findings.append(_finding("RAIL-008", "AGENTS.md", f"the Child DOX Index lists {path}, which does not exist"))
    else:
        findings.append(_finding("RAIL-009", "AGENTS.md", "the repository has no root AGENTS.md"))
    skills_dir = repo / A.SKILLS_DIR
    skills = {}
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            rel = f"{A.SKILLS_DIR}{child.name}/SKILL.md"
            if child.is_symlink() or (repo / rel).is_symlink():
                findings.append(_finding("RAIL-017", rel, "a canonical skill must be a regular directory and file"))
                continue
            if not child.is_dir():
                findings.append(_finding("RAIL-004", f"{A.SKILLS_DIR}{child.name}", "rail/skills holds skill directories only"))
                continue
            if not (repo / rel).is_file():
                findings.append(_finding("RAIL-004", rel, "a skill directory needs its SKILL.md"))
                continue
            text = (repo / rel).read_text(encoding="utf-8", errors="replace")
            _check_rail_text(rel, text, findings, skill_name=child.name)
            skills[child.name] = child
    if "AGENTS.md" in agents:
        listed = _linked(root_text, "Skills", "SKILL.md")
        canonical = {f"{A.SKILLS_DIR}{n}/SKILL.md" for n in skills}
        for path in sorted(canonical - listed):
            findings.append(_finding("RAIL-008", path, "a canonical skill the root Skills table does not list"))
        for path in sorted(listed - canonical):
            findings.append(_finding("RAIL-008", "AGENTS.md", f"the Skills table lists {path}, which is not a canonical skill"))
    return findings, {"catalog": catalog, "skills": skills, "rails": len(agents) + len(skills)}


# --------------------------------------------------------------------------- the registrations

def plan(repo: Path, skills: dict) -> Dict[str, bytes]:
    """Every generated file and its bytes: full copies of each canonical skill directory under each registration root."""
    outputs: Dict[str, bytes] = {}
    sources = {}
    for name, directory in sorted(skills.items()):
        for f in sorted(p for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
            rel = f.relative_to(directory).as_posix()
            data = f.read_bytes()
            sources[f.relative_to(repo).as_posix()] = hashlib.sha256(data).hexdigest()
            for root in REGISTRATIONS:
                outputs[f"{root}/{name}/{rel}"] = data
    manifest = {"schema": 1, "generator": "rail/rail.py sync", "sources": sources,
                "outputs": {p: hashlib.sha256(d).hexdigest() for p, d in sorted(outputs.items())}}
    outputs[MANIFEST] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    return outputs


def registration_findings(repo: Path, outputs: Dict[str, bytes]) -> List[dict]:
    findings = []
    for rel, data in sorted(outputs.items()):
        path = repo / rel
        if path.is_symlink():
            findings.append(_finding("RAIL-017", rel, "a registration must be a regular file"))
        elif not path.is_file() or path.read_bytes() != data:
            findings.append(_finding("RAIL-001", rel, "differs from its canonical source or is missing: run `python3 rail/rail.py sync`"))
    for root in REGISTRATIONS:
        base = repo / root
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*")):
            rel = f.relative_to(repo).as_posix()
            if (f.is_file() or f.is_symlink()) and rel not in outputs:
                findings.append(_finding("RAIL-002", rel, "no canonical source generates this: delete it, or add the skill under rail/skills"))
    return findings


def sync(repo) -> dict:
    repo = Path(repo).resolve()
    findings, info = inventory(repo, worktree_files(repo))
    blocking = [f for f in findings if f["code"] in ("RAIL-004", "RAIL-005", "RAIL-017") and f["path"].startswith(A.SKILLS_DIR)]
    if blocking:
        return {"written": 0, "refused": blocking}
    outputs = plan(repo, info["skills"])
    previous = {}
    if (repo / MANIFEST).is_file():
        previous = json.loads((repo / MANIFEST).read_text()).get("outputs", {})
    written, removed = 0, 0
    for rel, data in outputs.items():
        path = repo / rel
        if path.is_symlink():
            path.unlink()
        if path.is_file() and path.read_bytes() == data:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            tmp.write(data)
        os.replace(tmp.name, path)
        written += 1
    for rel in sorted(set(previous) - set(outputs)):  # a retired skill's generated copies: this generator wrote them, so it removes them
        if (repo / rel).is_file():
            (repo / rel).unlink()
            removed += 1
    return {"written": written, "removed": removed, "skills": len(info["skills"])}


# --------------------------------------------------------------------------- the history

def _merge3(base: str, ours: str, theirs: str) -> Optional[str]:
    with tempfile.TemporaryDirectory(prefix="rail-merge3-") as tmp:
        files = []
        for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            p = Path(tmp) / name
            p.write_text(text)
            files.append(str(p))
        result = subprocess.run(["git", "merge-file", "-p", "-q", *files], capture_output=True)
        if result.returncode != 0:
            return None
        return result.stdout.decode("utf-8", errors="replace")


def _pre_adoption(commit, parents, before, after, triggers, lineage) -> List[dict]:
    """What a merge took unchanged from a parent that does not descend from the adoption baseline: work authored before the rail
    reached its branch. It is inherited (the rule binds commits that could see it), and listed so a reviewer sees it."""
    def version(s, p):
        return A.full(s, p) if A.is_rail(p) else s.get(p)
    out = []
    for path in sorted(set(triggers) | A.rails_in(after, *before)):
        mine = version(after, path)
        if any(version(b, path) == mine for b, p in zip(before, parents) if p in lineage):
            continue
        for b, p in zip(before, parents):
            if p not in lineage and version(b, path) == mine:
                out.append({"commit": commit[:12], "path": path, "from": p[:12]})
                break
    return out


def maintain(repo: Path, catalog: dict, quick: bool = False) -> dict:
    baseline = catalog.get("baseline")
    if not isinstance(baseline, str) or not re.fullmatch(r"[0-9a-f]{40}", baseline):
        return {"commits": 0, "findings": [_finding("RAIL-015", CATALOG, "baseline must be the full SHA of the adoption commit")], "inherited": []}
    try:
        git(repo, "cat-file", "-e", baseline + "^{commit}")
        git(repo, "merge-base", "--is-ancestor", baseline, "HEAD")
    except GitError:
        shallow = git(repo, "rev-parse", "--is-shallow-repository").decode().strip() == "true"
        why = " (this clone is shallow: `git fetch --unshallow`)" if shallow else ""
        return {"commits": 0, "findings": [_finding("RAIL-015", CATALOG, f"baseline {baseline[:12]} is not an ancestor of HEAD{why}")], "inherited": []}
    commits = git(repo, "rev-list", "--reverse", "--topo-order", "--ancestry-path", f"{baseline}..HEAD").decode().split()
    triggers_all = set()
    cache: Dict[str, Dict[str, str]] = {}

    def snap(commit):
        if commit not in cache:
            cache[commit] = snapshot_commit(repo, commit, triggers_all)
        return cache[commit]

    def triggers_of(*snaps) -> Dict[str, str]:
        out = {}
        for s in snaps:
            if CATALOG in s:
                try:
                    for path, row in load_catalog_text(s[CATALOG]).get("triggers", {}).items():
                        if isinstance(row, dict) and isinstance(row.get("owner"), str):
                            out[path] = row["owner"]
                except ValueError:
                    pass
        return out

    # every trigger path any catalog in range ever named, so a snapshot carries it even before its catalog row existed
    for commit in [baseline, *commits]:
        try:
            triggers_all |= set(load_catalog_text(git(repo, "show", f"{commit}:{CATALOG}").decode()).get("triggers", {}))
        except (GitError, ValueError):
            pass
    findings, inherited = [], []
    lineage = {baseline, *commits}
    if quick:                                                   # only what no remote-tracking ref holds: what this push brings
        unpushed = set(git(repo, "rev-list", "HEAD", "--not", "--remotes").decode().split())
        commits = [c for c in commits if c in unpushed]
    steps = [(c, git(repo, "rev-list", "--parents", "-n", "1", c).decode().split()[1:]) for c in commits]
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    merge_head = repo / ".git" / "MERGE_HEAD"
    try:
        gitdir = Path(git(repo, "rev-parse", "--absolute-git-dir").decode().strip())
        merge_head = gitdir / "MERGE_HEAD"
    except GitError:
        pass
    worktree = snapshot_worktree(repo, triggers_all)
    work_parents = [head] + (merge_head.read_text().split() if merge_head.is_file() else [])
    for commit, parents in steps + ([] if quick else [("WORKTREE", work_parents)]):
        after = worktree if commit == "WORKTREE" else snap(commit)
        before = [snap(p) for p in parents]
        triggers = triggers_of(after, *before)
        if len(parents) == 1:
            result = A.assess(before[0], after, triggers)
        else:
            base = None
            if len(parents) == 2:
                try:
                    bases = git(repo, "merge-base", parents[0], parents[1]).decode().split()
                    base = snap(bases[0]) if bases else None
                except GitError:
                    base = None
            result = A.assess_merge(before, after, triggers, base, _merge3)
            inherited += _pre_adoption(commit, parents, before, after, triggers, lineage)
        for f in result:
            findings.append(_finding(f["code"], f["path"], f["message"], commit=commit if commit == "WORKTREE" else commit[:12], trigger=f.get("trigger")))
    return {"commits": len(commits), "findings": findings, "inherited": inherited, "baseline": baseline}


# --------------------------------------------------------------------------- the verdict

def _apply_exemptions(findings: List[dict], exemptions: list) -> (List[dict], List[dict]):
    kept, exempted, problems = [], [], []
    used = set()
    for i, ex in enumerate(exemptions):
        if not isinstance(ex, dict) or not {"code", "path", "reason"} <= set(ex) or ex.get("code") not in CODES or not str(ex.get("reason", "")).strip():
            problems.append(_finding("RAIL-016", CATALOG, f"exemption {i} needs code (a known RAIL code), path and a reason"))
    for f in findings:
        match = next((i for i, ex in enumerate(exemptions) if isinstance(ex, dict) and ex.get("code") == f["code"] and ex.get("path") == f["path"]
                      and ex.get("commit", f.get("commit")) == f.get("commit")), None)
        if match is None:
            kept.append(f)
        else:
            used.add(match)
            exempted.append(dict(f, reason=exemptions[match].get("reason")))
    for i, ex in enumerate(exemptions):
        if isinstance(ex, dict) and i not in used and {"code", "path"} <= set(ex):
            problems.append(_finding("RAIL-016", CATALOG, f"exemption {ex.get('code')} {ex.get('path')} matches no finding: delete it (exemptions only shrink)"))
    return kept + problems, exempted


def server_python(repo: Path) -> str:
    """The interpreter a generator runs under: $LAMPWAY_SERVER_PYTHON, else the server's own venv, else this one."""
    env = os.environ.get("LAMPWAY_SERVER_PYTHON")
    if env:
        return env
    venv = repo / "server" / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def generated_findings(repo: Path, catalog: dict) -> List[dict]:
    """Run each generated document's own --check. A generator that cannot run (a missing dependency) is red, never skipped."""
    findings = []
    for row in catalog.get("generated", []) or []:
        if not (isinstance(row, dict) and isinstance(row.get("script"), str) and (repo / row["script"]).is_file()):
            continue                                            # already a RAIL-003 from the catalog
        cmd = [server_python(repo), str(repo / row["script"]), *[str(a) for a in row.get("args", [])]]
        try:
            result = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=600)
            rc, tail = result.returncode, (result.stdout + result.stderr).strip().splitlines()[-1:]
        except (OSError, subprocess.TimeoutExpired) as exc:
            rc, tail = -1, [str(exc)]
        if rc != 0:
            findings.append(_finding("RAIL-018", row.get("doc", row["script"]),
                                     f"`{row['script']} {' '.join(map(str, row.get('args', [])))}` exited {rc}: {(tail or [''])[0][:240]}"))
    return findings


def check(repo, quick: bool = False) -> dict:
    """The gate. ``quick`` (the pre-push hook) judges only commits no remote-tracking ref holds yet, skips the worktree and the
    generated documents (their generators need the server's dependencies); CI runs the full check."""
    repo = Path(repo).resolve()
    files = worktree_files(repo)
    findings, info = inventory(repo, files)
    outputs = plan(repo, info["skills"])
    findings += registration_findings(repo, outputs)
    history = maintain(repo, info["catalog"], quick=quick)
    findings += history["findings"]
    if not quick:
        findings += generated_findings(repo, info["catalog"])
    findings, exempted = _apply_exemptions(findings, info["catalog"].get("exemptions") or [])
    return {"verdict": "FAIL" if findings else "PASS", "mode": "quick" if quick else "full", "skills": len(info["skills"]),
            "rails": info["rails"], "commits": history["commits"], "baseline": (history.get("baseline") or "")[:12],
            "findings": findings, "exempted": exempted, "inherited_pre_adoption": history["inherited"]}


def closeout(repo, tag: str) -> dict:
    if not tag or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", tag):
        raise ValueError("--tag needs the planned release tag")
    text = (Path(repo) / "AGENTS.md").read_text()
    match = re.search(r"(?ms)^## DOX closeout[ \t]*\n(.*?)(?=^## |\Z)", text)
    rows = [l for l in (match.group(1) if match else "").splitlines() if l.strip().startswith("|")][2:]
    hits = [r for r in rows if A.cells(r)[0] == tag]
    if len(hits) != 1 or len(A.cells(hits[0])) != 3 or not all(A.cells(hits[0])):
        raise ValueError(f"the root AGENTS.md DOX closeout table needs one complete row `| {tag} | what annealed | evidence |`")
    return {"tag": tag, "closeout": hits[0].strip()}
