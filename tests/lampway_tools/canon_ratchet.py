# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The LEGACY ratchet's history check (tests/lampway_tools/test_canon_doors.py).

The count (the file's first token) may only fall, with ONE exception (the coordinator's ruling A, 2026-10-06, the rail's
"pre-rail merges are listed, not judged"): a MERGE commit may raise it when that same commit adds a record line

    rebaseline <new count> merged=<sha of the merged-in parent> reason=<why>

whose number is the new count, whose sha is one of the merge's non-first parents (7+ hex characters, a prefix), and whose reason
is not empty. Any other rise - a plain commit, a merge without the record, a record re-used by a later commit - is a violation.
In the working tree a rise is accepted only during a merge (MERGE_HEAD) whose record names MERGE_HEAD."""

import re
import subprocess

RECORD = re.compile(r"^rebaseline\s+(\d+)\s+merged=([0-9a-f]{7,40})\s+reason=(.*)$", re.M)


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def _text_at(root, rev, rel):
    show = _git(root, "show", f"{rev}:{rel}")
    return show.stdout if show.returncode == 0 and show.stdout.strip() else None


def _count(text):
    return int(text.split()[0]) if text else None


def _record_ok(text, before, count, merged):
    """The text adds (relative to every text in ``before``) a whole record for ``count`` naming one of ``merged``."""
    old = set()
    for b in before:
        old |= {m.group(0) for m in RECORD.finditer(b or "")}
    for m in RECORD.finditer(text):
        if m.group(0) in old:
            continue
        if int(m.group(1)) == count and m.group(3).strip() and any(p.startswith(m.group(2)) for p in merged):
            return True
    return False


def violations(root, rel, worktree_text=None):
    """[str]: every unrecorded rise of the count, in the file's full history and in the working tree against HEAD."""
    out = []
    rows = _git(root, "log", "--full-history", "--format=%H %P", "--", rel).stdout.splitlines()
    first = rows[-1].split()[0] if rows else None
    for row in rows:
        sha, *parents = row.split()
        text = _text_at(root, sha, rel)
        if text is None:
            continue
        ptexts = [_text_at(root, p, rel) for p in parents]
        have = [_count(t) for t in ptexts if t is not None]
        if not have:
            if sha != first:
                out.append(f"{sha[:10]} re-creates the ratchet file at {_count(text)} (only its first commit may set a baseline)")
            continue
        new, low = _count(text), min(have)
        if new <= low:
            continue
        if len(parents) < 2:
            out.append(f"the ratchet rose {low} -> {new} in a plain commit (a rise is accepted only in a merge commit that records it)")
        elif not _record_ok(text, ptexts, new, parents[1:]):
            out.append(f"the ratchet rose {low} -> {new} in merge {sha[:10]} without a record "
                       f"'rebaseline {new} merged=<the merged sha> reason=<why>' added in that merge")
    if worktree_text is not None:
        head = _text_at(root, "HEAD", rel)
        new, old = _count(worktree_text), _count(head)
        if old is not None and new > old:
            mh = _git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").stdout.strip()
            if not (mh and _record_ok(worktree_text, [head], new, [mh])):
                out.append(f"the ratchet rose {old} -> {new} in the working tree (lower the file when you migrate a tool; a merge records "
                           f"'rebaseline {new} merged=<MERGE_HEAD> reason=<why>')")
    return out
