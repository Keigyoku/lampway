# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Plant one violation per finding code in a scratch repository and prove the check catches it.

An assertion that cannot fail is not an assertion: a rule earns its place only when a planted offender makes it fire. So this
builds a small fixture repository with a clean rail (and proves the check passes on it), then, in a fresh copy per plant, makes
exactly one kind of mistake and asserts its code is reported. The plant set is checked against ``railcore.CODES``: a code with no
plant fails the self-test, so the list of rules cannot grow past the list of demonstrations (enumeration is not a gate; this
comparison is). Controls (receipted edits, a receipted trigger, a move, a clean two-lane merge) must stay clean.

Scratch space comes from ``tempfile`` (honours ``TMPDIR``); nothing outside it is touched.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    from . import railcore as R
except ImportError:
    import railcore as R  # type: ignore

FM = ("---\n# SPDX-FileCopyrightText: 2026 Lampway contributors\n# SPDX-License-Identifier: GPL-3.0-or-later\n{extra}"
      "anneal_on_error: true\nanneal_on_success: true\nanneal_safety: gated\nverification-mode: mixed\n---\n\n")
LOG = ("## Anneal log\n\n| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |\n"
       "|---|---|---|---|---|---|\n| 2026-10-01 | adoption | fixture | none | the fixture rail | none |\n")
ROOT = FM.format(extra="") + ("# Fixture\n\nRoot contract.\n\n## Skills\n\n| skill | when |\n|---|---|\n"
                              "| [demo](rail/skills/demo/SKILL.md) | always |\n\n## Child DOX Index\n\n| path | owns |\n|---|---|\n"
                              "| [sub](sub/AGENTS.md) | the sub tree |\n\n## DOX closeout\n\n| tag | what annealed | evidence |\n|---|---|---|\n\n") + LOG
SUB = FM.format(extra="") + ("# Sub\n\n## Invariants\n\n- rule one\n- rule two\n\n## Test\n\n`true`\n\n## Owner\n\nthe fixture\n\n") + LOG
SKILL = FM.format(extra='name: demo\ndescription: "Use the demo tool."\n') + "# demo\n\nRun `python3 tool.py`.\n\n" + LOG
GIT_ENV = {"GIT_AUTHOR_NAME": "rail", "GIT_AUTHOR_EMAIL": "rail@example.invalid", "GIT_COMMITTER_NAME": "rail",
           "GIT_COMMITTER_EMAIL": "rail@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def sh(repo, *args) -> str:
    out = subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull, "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
                         cwd=repo, capture_output=True, env={**os.environ, **GIT_ENV})
    if out.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {out.stderr.decode()[:300]}")
    return out.stdout.decode()


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.is_symlink():
        p.unlink()
    p.write_text(text)


def commit(repo: Path, message: str) -> None:
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "--allow-empty", "-m", message)


def row(date="2026-10-02", what="edit") -> str:
    return f"| {date} | {what} | selftest | none | the change | none |\n"


def append_row(text: str, r: str) -> str:
    return text.rstrip("\n") + "\n" + r


def build(root: Path) -> Path:
    repo = root / "fixture"
    repo.mkdir()
    sh(repo, "init", "-q")
    write(repo, "README.md", "fixture\n")
    commit(repo, "seed")
    seed = sh(repo, "rev-parse", "HEAD").strip()
    write(repo, "AGENTS.md", ROOT)
    write(repo, "CLAUDE.md", "@AGENTS.md\n")
    write(repo, "sub/AGENTS.md", SUB)
    write(repo, "sub/CLAUDE.md", "@AGENTS.md\n")
    write(repo, "tool.py", "print('demo')\n")
    write(repo, "rail/skills/demo/SKILL.md", SKILL)
    write(repo, "rail/catalog.json", json.dumps({"schema": 1, "baseline": seed, "baseline_reason": "fixture",
                                                 "triggers": {"tool.py": {"owner": "rail/skills/demo/SKILL.md"}}, "exemptions": []}, indent=2) + "\n")
    R.sync(repo)
    commit(repo, "adopt the rail")
    return repo


# --------------------------------------------------------------------------- plants: (name, expected codes, fn(repo))

def _edit_sub(repo, body_from=None, body_to=None, new_row=True, message=None):
    text = (repo / "sub/AGENTS.md").read_text()
    if body_from is not None:
        text = text.replace(body_from, body_to, 1)
    if new_row:
        text = append_row(text, row())
    write(repo, "sub/AGENTS.md", text)
    if message:
        commit(repo, message)


def p_drift(repo):
    write(repo, ".agents/skills/demo/SKILL.md", SKILL + "hand edit\n")


def p_extras(repo):
    write(repo, ".claude/skills/ghost/SKILL.md", SKILL.replace("demo", "ghost"))


def p_catalog(repo):
    c = json.loads((repo / "rail/catalog.json").read_text())
    c["triggers"]["gone.py"] = {"owner": "rail/skills/demo/SKILL.md"}
    write(repo, "rail/catalog.json", json.dumps(c))


def p_frontmatter(repo):
    _edit_sub(repo, "anneal_safety: gated", "anneal_safety: auto", message="weaken the anneal contract")


def p_log(repo):
    write(repo, "sub/AGENTS.md", (repo / "sub/AGENTS.md").read_text().replace("- rule two", "- rule 2") + "| 2026-10-02 | five | cells | only | here |\n")


def p_stub(repo):
    write(repo, "sub/CLAUDE.md", "@AGENTS.md\n@../AGENTS.md\n")


def p_unpaired(repo):
    (repo / "sub/CLAUDE.md").unlink()


def p_index(repo):
    write(repo, "other/AGENTS.md", SUB)
    write(repo, "other/CLAUDE.md", "@AGENTS.md\n")


def p_skill_index(repo):
    write(repo, "rail/skills/extra/SKILL.md", SKILL.replace("name: demo", "name: extra"))
    R.sync(repo)


def p_section(repo):
    _edit_sub(repo, "## Owner\n\nthe fixture\n\n", "", message="drop the owner")


def p_no_row(repo):
    _edit_sub(repo, "- rule two", "- rule two, changed", new_row=False, message="a body change with no receipt")


def p_edited_row(repo):
    text = (repo / "sub/AGENTS.md").read_text().replace("| adoption |", "| rewritten |").replace("- rule two", "- rule 2")
    write(repo, "sub/AGENTS.md", append_row(text, row()))
    commit(repo, "rewrite history")


def p_receipt_for_nothing(repo):
    _edit_sub(repo, message="a row with no body change")


def p_trigger(repo):
    write(repo, "tool.py", "print('changed')\n")
    commit(repo, "change the tool, not its skill")


def p_delete(repo):
    shutil.rmtree(repo / "sub")
    root = (repo / "AGENTS.md").read_text().replace("| [sub](sub/AGENTS.md) | the sub tree |\n", "")
    write(repo, "AGENTS.md", append_row(root, row(what="remove sub")))
    commit(repo, "delete a rail and its history")


def p_baseline(repo):
    c = json.loads((repo / "rail/catalog.json").read_text())
    c["baseline"] = "0" * 40
    write(repo, "rail/catalog.json", json.dumps(c))


def p_exemption(repo):
    c = json.loads((repo / "rail/catalog.json").read_text())
    c["exemptions"] = [{"code": "RAIL-006", "path": "sub/CLAUDE.md", "reason": "an exemption nothing needs"}]
    write(repo, "rail/catalog.json", json.dumps(c))


def p_symlink(repo):
    (repo / "sub/CLAUDE.md").unlink()
    os.symlink("AGENTS.md", repo / "sub/CLAUDE.md")


def _two_lanes(repo):
    """Lane a edits rule one, lane b edits the Test section (lines apart, so the bodies combine cleanly); each receipted. Returns after checking out main with both branches made."""
    sh(repo, "checkout", "-q", "-b", "lane-a")
    _edit_sub(repo, "- rule one", "- rule one (a)", new_row=False)
    write(repo, "sub/AGENTS.md", append_row((repo / "sub/AGENTS.md").read_text(), row("2026-10-03", "lane a")))
    commit(repo, "lane a")
    sh(repo, "checkout", "-q", "main")
    sh(repo, "checkout", "-q", "-b", "lane-b")
    _edit_sub(repo, "`true`", "`true` (b)", new_row=False)
    write(repo, "sub/AGENTS.md", append_row((repo / "sub/AGENTS.md").read_text(), row("2026-10-04", "lane b")))
    commit(repo, "lane b")
    sh(repo, "checkout", "-q", "main")
    sh(repo, "merge", "-q", "--no-ff", "--no-edit", "lane-a")
    subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull, "merge", "-q", "--no-ff", "--no-edit", "lane-b"], cwd=repo,
                   capture_output=True, env={**os.environ, **GIT_ENV})   # conflicts in the table: resolved by the plant


def _resolved(lost_row=False, extra_body=""):
    text = SUB.replace("- rule one", "- rule one (a)").replace("`true`", "`true` (b)" + extra_body)
    rows = [row("2026-10-03", "lane a"), row("2026-10-04", "lane b")]
    if lost_row:
        rows = rows[1:]
    return text.rstrip("\n") + "\n" + "".join(rows)


def p_merge_lost_row(repo):
    _two_lanes(repo)
    write(repo, "sub/AGENTS.md", _resolved(lost_row=True))
    commit(repo, "merge lane b, losing lane a's row")


def p_merge_unreceipted(repo):
    _two_lanes(repo)
    write(repo, "sub/AGENTS.md", _resolved(extra_body="\n- a rule only the merge wrote"))
    commit(repo, "merge lane b and author a rule with no receipt")


def c_receipted_edit(repo):
    _edit_sub(repo, "- rule two", "- rule two, changed", message="a receipted change")


def c_trigger_receipted(repo):
    write(repo, "tool.py", "print('changed')\n")
    skill = (repo / "rail/skills/demo/SKILL.md").read_text().replace("Run `python3 tool.py`.", "Run `python3 tool.py`; it prints changed.")
    write(repo, "rail/skills/demo/SKILL.md", append_row(skill, row()))
    R.sync(repo)
    commit(repo, "tool and skill together")


def c_move(repo):
    sh(repo, "mv", "sub", "moved")
    write(repo, "moved/AGENTS.md", append_row((repo / "moved/AGENTS.md").read_text().replace("# Sub", "# Moved"), row(what="move")))
    root = (repo / "AGENTS.md").read_text().replace("[sub](sub/AGENTS.md) | the sub tree", "[moved](moved/AGENTS.md) | the moved tree")
    write(repo, "AGENTS.md", append_row(root, row(what="index the move")))
    commit(repo, "move a rail with its log")


def c_merge_clean(repo):
    _two_lanes(repo)
    write(repo, "sub/AGENTS.md", _resolved())
    commit(repo, "merge both lanes: rows from both, sorted by date")


PLANTS = [
    ("drift", {"RAIL-001"}, p_drift),
    ("extras", {"RAIL-002"}, p_extras),
    ("dead catalog trigger", {"RAIL-003"}, p_catalog),
    ("weakened frontmatter", {"RAIL-004"}, p_frontmatter),
    ("five-cell anneal row", {"RAIL-005"}, p_log),
    ("two-import stub", {"RAIL-006"}, p_stub),
    ("AGENTS.md without its stub", {"RAIL-007"}, p_unpaired),
    ("nested rail missing from the index", {"RAIL-008"}, p_index),
    ("skill missing from the Skills table", {"RAIL-008"}, p_skill_index),
    ("rail without its Owner section", {"RAIL-009"}, p_section),
    ("body change with no row", {"RAIL-010"}, p_no_row),
    ("prior row rewritten", {"RAIL-011"}, p_edited_row),
    ("row with no body change", {"RAIL-012"}, p_receipt_for_nothing),
    ("trigger without its owner", {"RAIL-013"}, p_trigger),
    ("rail deleted with its history", {"RAIL-014"}, p_delete),
    ("baseline not an ancestor", {"RAIL-015"}, p_baseline),
    ("stale exemption", {"RAIL-016"}, p_exemption),
    ("symlinked stub", {"RAIL-017"}, p_symlink),
    ("merge loses a lane's row", {"RAIL-011"}, p_merge_lost_row),
    ("merge authors an unreceipted rule", {"RAIL-010"}, p_merge_unreceipted),
]
CONTROLS = [
    ("clean fixture", lambda repo: None),
    ("receipted rail edit", c_receipted_edit),
    ("receipted trigger", c_trigger_receipted),
    ("rail moved with its log", c_move),
    ("two lanes merged, rows sorted by date", c_merge_clean),
]


def run(names=None) -> dict:
    rows, failures = [], []
    with tempfile.TemporaryDirectory(prefix="rail-selftest-") as tmp:
        tmp = Path(tmp)
        fixture = build(tmp)
        for i, (name, expected, fn) in enumerate([(n, set(), f) for n, f in CONTROLS] + PLANTS):
            if names and name not in names:
                continue
            repo = tmp / f"case{i}"
            shutil.copytree(fixture, repo, symlinks=True)
            fn(repo)
            got = {f["code"] for f in R.check(repo)["findings"]}
            ok = (got == set()) if not expected else expected <= got
            rows.append({"case": name, "expect": ",".join(sorted(expected)) or "clean", "got": ",".join(sorted(got)) or "clean", "ok": ok})
            if not ok:
                failures.append(name)
    planted = {c for _, codes, _ in PLANTS for c in codes}
    unplanted = sorted(set(R.CODES) - planted)
    if unplanted and not names:
        failures.append("codes with no plant: " + ", ".join(unplanted))
    return {"verdict": "FAIL" if failures else "PASS", "cases": rows, "failures": failures, "codes": len(R.CODES), "planted": len(planted)}
