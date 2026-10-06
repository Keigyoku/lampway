# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The anneal rule over explicit before/after snapshots: pure, no IO, no git.

A snapshot is ``{path: text}`` holding the rails (every ``AGENTS.md``, every canonical ``rail/skills/<name>/SKILL.md`` and the
files beside it) and the triggers the catalog names. ``assess`` judges one ordinary commit against its one parent; ``assess_merge``
judges a merge against all its parents, given a three-way text merge it can call (``merge3(base, ours, theirs)`` -> merged text, or
None on a conflict). Both return findings ``{code, path, trigger, message}``; an empty list is a clean increment.

The rule, stated once (docs/rail.md has the long form):

* A rail that changes appends at least one anneal row, keeps every prior row unchanged and in order, and changes its body too.
  A row with no body change is a receipt for nothing; a body change with no row is an unreceipted change.
* A trigger (a file the catalog assigns to an owning rail) that changes owes its owner an appended row AND a body change in the
  same commit.
* A deleted rail is a move only when a rail new in the same commit carries its rows as a prefix and appends its own.
* At a merge, a file equal to one parent's version is inherited, and so is a clean three-way combination of two parents; only
  what the merge itself authored owes a receipt. Every parent's rows survive, unchanged and in relative order.
"""

from __future__ import annotations

import datetime
import json
import re
from typing import Callable, Dict, List, Optional

ANNEAL_HEADING = "## Anneal log"
ANNEAL_HEADER = ["date", "change-shape", "trigger", "failure-mode", "fix-into-directive", "promote-candidate"]
ANNEAL_FIELDS = {"anneal_on_error": True, "anneal_on_success": True, "anneal_safety": "gated"}
VERIFICATION_MODES = ("deterministic", "judgment", "mixed")
SKILLS_DIR = "rail/skills/"
SIBLING_MARK = "\n===== rail sibling: {} =====\n"
_PIPE = re.compile(r"(?<!\\)\|")


class RailError(ValueError):
    """A rail that cannot be read: carries the finding code it maps to."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- reading one rail

def is_skill(path: str) -> bool:
    parts = path.split("/")
    return path.startswith(SKILLS_DIR) and len(parts) == 4 and parts[3] == "SKILL.md"


def is_agents(path: str) -> bool:
    return path == "AGENTS.md" or path.endswith("/AGENTS.md")


def is_rail(path: str) -> bool:
    return is_agents(path) or is_skill(path)


def skill_of(path: str) -> Optional[str]:
    """The SKILL.md a file beside it belongs to (a sibling is part of the skill), else None."""
    parts = path.split("/")
    if path.startswith(SKILLS_DIR) and len(parts) >= 4 and not is_skill(path):
        return "/".join(parts[:3]) + "/SKILL.md"
    return None


def frontmatter(text: str) -> Dict[str, object]:
    """The flat ``key: value`` block between the opening ``---`` lines. ``#`` lines are comments (the SPDX header lives there)."""
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise RailError("RAIL-004", "missing frontmatter: the file must open with a --- block")
    fields: Dict[str, object] = {}
    for line in text[4:].split("\n---\n", 1)[0].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1].isspace():
            raise RailError("RAIL-004", f"nested frontmatter is not supported: {line.strip()!r}")
        key, sep, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not sep or not key or key in fields:
            raise RailError("RAIL-004", f"invalid or duplicate frontmatter field: {line.strip()!r}")
        try:
            fields[key] = json.loads(value) if value.startswith('"') or value in ("true", "false") else value
        except json.JSONDecodeError as exc:
            raise RailError("RAIL-004", f"frontmatter {key}: {exc}") from None
    return fields


def check_frontmatter(text: str, skill_name: Optional[str] = None) -> Dict[str, object]:
    fields = frontmatter(text)
    for key, want in ANNEAL_FIELDS.items():
        if fields.get(key) != want:
            raise RailError("RAIL-004", f"frontmatter {key} must be {json.dumps(want)} (the gated anneal contract)")
    if fields.get("verification-mode") not in VERIFICATION_MODES:
        raise RailError("RAIL-004", "frontmatter verification-mode must be deterministic, judgment or mixed")
    if skill_name is not None:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", skill_name) or len(skill_name) > 64 or fields.get("name") != skill_name:
            raise RailError("RAIL-004", f"frontmatter name must equal the skill's directory, {skill_name!r}")
        if not isinstance(fields.get("description"), str) or not str(fields["description"]).strip():
            raise RailError("RAIL-004", "a skill needs a trigger description (frontmatter description)")
    return fields


def split_anneal(text: str):
    """(body, log) where body is the file without its Anneal log section and log is that section's lines."""
    marker = ANNEAL_HEADING + "\n"
    starts = [m.start() for m in re.finditer(r"(?m)^## Anneal log[ \t]*$", text)]
    if len(starts) != 1 or text.count(marker) != 1:
        raise RailError("RAIL-005", "a rail needs exactly one '## Anneal log' section")
    before, rest = text.split(marker, 1)
    log, sep, after = rest.partition("\n## ")
    return before + (sep + after if sep else ""), log


def cells(row: str) -> List[str]:
    return [c.strip() for c in _PIPE.split(row.strip().strip("|"))]


def anneal_rows(text: str) -> List[str]:
    """The receipt rows, validated: the six-column header, a separator, complete rows, ISO dates in order, nothing but the table."""
    _, log = split_anneal(text)
    lines = [l for l in log.splitlines() if l.strip()]
    stray = [l for l in lines if not l.strip().startswith("|")]
    if stray:
        raise RailError("RAIL-005", f"the Anneal log holds only its table; move this into the body: {stray[0].strip()[:80]!r}")
    if len(lines) < 3 or cells(lines[0]) != ANNEAL_HEADER:
        raise RailError("RAIL-005", "the Anneal log needs the six-column header (" + " | ".join(ANNEAL_HEADER) + ") and at least one row")
    if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells(lines[1])) or len(cells(lines[1])) != 6:
        raise RailError("RAIL-005", "the Anneal log table needs a six-column separator row")
    previous = None
    rows = []
    for line in lines[2:]:
        values = cells(line)
        if len(values) != 6 or not all(values):
            raise RailError("RAIL-005", f"an anneal row needs six non-empty cells: {line.strip()[:80]!r}")
        try:
            date = datetime.date.fromisoformat(values[0])
        except ValueError:
            raise RailError("RAIL-005", f"an anneal row starts with an ISO date: {values[0]!r}") from None
        if previous and date < previous:
            raise RailError("RAIL-005", f"anneal rows are in date order: {values[0]} follows {previous.isoformat()}")
        previous = date
        rows.append(line.strip())
    return rows


def sections(text: str) -> List[str]:
    return [m.group(1).strip() for m in re.finditer(r"(?m)^## (.+)$", text)]


def body(snapshot: Dict[str, str], path: str) -> Optional[str]:
    """A rail's body: the file without its Anneal log; a skill's body includes every file beside its SKILL.md."""
    text = snapshot.get(path)
    if text is None:
        return None
    out = split_anneal(text)[0] if ANNEAL_HEADING + "\n" in text else text
    if is_skill(path):
        prefix = path[: -len("SKILL.md")]
        for other in sorted(p for p in snapshot if p.startswith(prefix) and p != path):
            out += SIBLING_MARK.format(other[len(prefix):]) + snapshot[other]
    return out


def full(snapshot: Dict[str, str], path: str) -> Optional[str]:
    """Everything that makes a rail what it is (the text, and for a skill its siblings): two equal fulls are the same rail."""
    text = snapshot.get(path)
    if text is None or not is_skill(path):
        return text
    prefix = path[: -len("SKILL.md")]
    return text + "".join(SIBLING_MARK.format(p[len(prefix):]) + snapshot[p] for p in sorted(snapshot) if p.startswith(prefix) and p != path)


def _rows(snapshot, path) -> List[str]:
    text = snapshot.get(path)
    return anneal_rows(text) if text is not None and ANNEAL_HEADING + "\n" in text else []


def _finding(code, path, trigger, message):
    return {"code": code, "path": path, "trigger": trigger, "message": message}


def _subsequence_positions(old: List[str], new: List[str]) -> Optional[List[int]]:
    positions, cursor = [], 0
    for row in old:
        while cursor < len(new) and new[cursor] != row:
            cursor += 1
        if cursor == len(new):
            return None
        positions.append(cursor)
        cursor += 1
    return positions


# --------------------------------------------------------------------------- ordinary commits

def rails_in(*snapshots) -> set:
    return {p for s in snapshots for p in s if is_rail(p)}


def assess(before: Dict[str, str], after: Dict[str, str], triggers: Dict[str, str]) -> List[dict]:
    """Findings for one single-parent increment. ``triggers`` maps a trigger path to its owner rail's path."""
    findings: List[dict] = []
    judged: Dict[str, Optional[dict]] = {}

    def judge(path: str) -> Optional[dict]:
        """The rail's own verdict (None = a clean, receipted change); memoised so an owner is judged once."""
        if path in judged:
            return judged[path]
        verdict = None
        try:
            if path not in after:
                verdict = _judge_deletion(path, before, after)
            else:
                new_rows = anneal_rows(after[path])
                old_rows = _rows(before, path)
                if new_rows[: len(old_rows)] != old_rows:
                    verdict = _finding("RAIL-011", path, path, "a prior anneal row was edited, deleted or reordered: rows are append-only")
                elif len(new_rows) <= len(old_rows):
                    verdict = _finding("RAIL-010", path, path, "the rail changed with no new anneal row: append one in the same commit")
                elif body(after, path) == body(before, path):
                    verdict = _finding("RAIL-012", path, path, "an anneal row was appended but the body did not change: a receipt for nothing")
        except RailError as exc:
            verdict = _finding(exc.code, path, path, str(exc))
        judged[path] = verdict
        return verdict

    changed_rails = sorted(p for p in rails_in(before, after) if full(before, p) != full(after, p))
    for path in changed_rails:
        verdict = judge(path)
        if verdict:
            findings.append(verdict)
    owners_of_siblings = {skill_of(p): p for p in set(before) | set(after) if skill_of(p) and before.get(p) != after.get(p)}
    owed = dict((p, o) for p, o in triggers.items() if before.get(p) != after.get(p))
    owed.update({sibling: owner for owner, sibling in owners_of_siblings.items()})
    for trigger, owner in sorted(owed.items()):
        if full(before, owner) == full(after, owner) or owner not in after:
            findings.append(_finding("RAIL-013", owner, trigger, f"{trigger} changed: its owner {owner} owes an appended anneal row and a body change in the same commit"))
        elif judge(owner) is not None:
            findings.append(_finding("RAIL-013", owner, trigger, f"{trigger} changed but its owner {owner} is not cleanly receipted ({judge(owner)['code']})"))
    return findings


def _judge_deletion(path, before, after) -> Optional[dict]:
    text = before.get(path, "")
    if ANNEAL_HEADING + "\n" not in text:
        return _finding("RAIL-014", path, path, "a rail was deleted that never carried an anneal log")
    old_rows = anneal_rows(text)
    for other in sorted(p for p in after if is_rail(p) and p not in before and p != path):
        try:
            rows = anneal_rows(after[other])
        except RailError:
            continue
        if rows[: len(old_rows)] == old_rows and len(rows) > len(old_rows):
            return None
    return _finding("RAIL-014", path, path, "a rail was deleted with no successor carrying its anneal rows and appending its own (a move keeps the log)")


# --------------------------------------------------------------------------- merges

Merge3 = Callable[[str, str, str], Optional[str]]


def assess_merge(parents: List[Dict[str, str]], after: Dict[str, str], triggers: Dict[str, str],
                 base: Optional[Dict[str, str]] = None, merge3: Optional[Merge3] = None) -> List[dict]:
    """Findings for a merge. ``base`` is the merge base snapshot (two-parent merges); ``merge3`` the text merge used to recognise a
    clean combination of both parents, which is inherited and owes nothing."""
    findings: List[dict] = []
    paths = rails_in(after, *parents)

    def combined(get, path) -> Optional[str]:
        if base is None or merge3 is None or len(parents) != 2:
            return None
        a, b, o = get(parents[0], path), get(parents[1], path), get(base, path)
        if a is None or b is None:
            return None
        return merge3(o or "", a, b)

    def inherited(path, get) -> bool:
        mine = get(after, path)
        return any(get(p, path) == mine for p in parents) or (mine is not None and combined(get, path) == mine)

    verdicts: Dict[str, Optional[dict]] = {}
    authored = set()
    for path in sorted(paths):
        verdict = None
        try:
            if path not in after:
                if any(path not in p for p in parents):
                    continue                                    # one side already deleted (or moved) it: inherited
                authored.add(path)
                verdict = _judge_deletion(path, parents[0], after)
            elif not inherited(path, full):
                rows = anneal_rows(after[path])
                inherited_at = []
                for parent in parents:
                    positions = _subsequence_positions(_rows(parent, path), rows)
                    if positions is None:
                        verdict = _finding("RAIL-011", path, path, "the merge lost, edited or reordered a parent's anneal row: every parent's rows survive in order")
                        break
                    inherited_at += positions
                if verdict is None:
                    novel = sorted(set(range(len(rows))) - set(inherited_at))
                    mine = body(after, path)
                    body_inherited = any(body(p, path) == mine for p in parents) or combined(body, path) == mine
                    if not body_inherited:
                        authored.add(path)
                    if body_inherited and novel:
                        verdict = _finding("RAIL-012", path, path, "the merge appended an anneal row but authored no body change: a receipt for nothing")
                    elif not body_inherited and not novel:
                        verdict = _finding("RAIL-010", path, path, "the merge authored a body change to this rail with no new anneal row")
                    elif novel and inherited_at and min(novel) < max(inherited_at):
                        verdict = _finding("RAIL-011", path, path, "a merge-owned anneal row sits before an inherited row: append it after them")
        except RailError as exc:
            verdict = _finding(exc.code, path, path, str(exc))
        verdicts[path] = verdict
        if verdict:
            findings.append(verdict)
    owed = {}
    for trigger, owner in triggers.items():
        if not inherited(trigger, lambda s, p: s.get(p)):
            owed[trigger] = owner
    for path in set(after).union(*parents):
        owner = skill_of(path)
        if owner and not inherited(path, lambda s, p: s.get(p)):
            owed[path] = owner
    for trigger, owner in sorted(owed.items()):
        if owner not in authored or owner not in after or verdicts.get(owner) is not None:
            findings.append(_finding("RAIL-013", owner, trigger, f"the merge authored a change to {trigger}: its owner {owner} owes a merge-owned anneal row and body change"))
    return findings
