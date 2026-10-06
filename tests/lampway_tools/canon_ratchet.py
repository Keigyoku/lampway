# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The LEGACY ratchet's history check (tests/lampway_tools/test_canon_doors.py).

The count (the file's first token) may only fall, with ONE exception (the coordinator's ruling A, 2026-10-06, the rail's
"pre-rail merges are listed, not judged"): a MERGE commit may raise it when that same commit's file records

    rebaseline <N> merge <parent1> <parent2>: <reason>                 (lane orphans' form, 5a993b5 - THE form)
    rebaseline <N> merged=<parent2> reason=<reason>                    (the form lp/canon's 09dec65 used; accepted, not to be written)

with N the new count, the sha(s) (7+ hex, prefixes) the commit's OWN merge parents, and a reason of at least 10 characters. A rise is
measured against the HIGHEST parent count: each parent's count was itself checked, so merging a lane whose rise was recorded there
needs no second record, and a merge that adds rises of its own does. During an uncommitted merge the working tree's parents are HEAD
and MERGE_HEAD."""

import re
import subprocess

FORMS = (re.compile(r"^rebaseline (\d+) merge ([0-9a-f]{7,40}) ([0-9a-f]{7,40}): (.*)$", re.M),
         re.compile(r"^rebaseline\s+(\d+)\s+merged=([0-9a-f]{7,40})\s+reason=(.*)$", re.M))


def _count(text):
    return int(text.split()[0]) if text and text.strip() else None


def _recorded(text, n, parents):
    """True when ``text`` records a rebaseline to ``n`` naming merge parents of this commit (all of them it names) and a reason."""
    if len(parents) < 2:
        return False
    for form in FORMS:
        for m in form.finditer(text):
            *shas, reason = m.groups()[1:]
            if int(m.group(1)) == n and len(reason.strip()) >= 10 and all(any(p.startswith(s) for p in parents) for s in shas):
                return True
    return False


def ratchet_problems(rows, text_at):
    """[str]: rows = [(sha, [parent shas], file text)] OLDEST FIRST; ``text_at(sha)`` -> the file's text at a parent, or None where it
    is absent. Only the oldest row whose parents all lack the file (the file's creation) may set a count from nothing."""
    out, created = [], False
    for sha, parents, text in rows:
        n = _count(text)
        before = [c for c in (_count(text_at(p)) for p in parents) if c is not None]
        if not before:
            if created:
                out.append(f"{sha[:12]}: the ratchet file is re-created at {n} (only its first commit sets a baseline)")
            created = True
            continue
        if n is None or n <= max(before):
            continue
        if not _recorded(text, n, parents):
            kind = "a plain commit" if len(parents) < 2 else "a merge without its record"
            out.append(f"{sha[:12]}: the ratchet rose {max(before)} -> {n} in {kind} (a rise is accepted only in the merge commit that records "
                       f"'rebaseline {n} merge <parent1> <parent2>: <reason>')")
    return out


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def violations(root, rel, worktree_text=None):
    """[str]: every unrecorded rise in the file's full history, and in the working tree (its parents HEAD and MERGE_HEAD)."""
    def text_at(rev):
        show = _git(root, "show", f"{rev}:{rel}")
        return show.stdout if show.returncode == 0 else None
    rows = []
    for line in reversed(_git(root, "log", "--full-history", "--format=%H %P", "--", rel).stdout.splitlines()):      # oldest first
        sha, *parents = line.split()
        t = text_at(sha)
        if t is not None:
            rows.append((sha, parents, t))
    if worktree_text is not None and worktree_text != text_at("HEAD"):
        heads = [_git(root, "rev-parse", "-q", "--verify", h).stdout.strip() for h in ("HEAD", "MERGE_HEAD")]
        rows.append(("working-tree", [h for h in heads if h], worktree_text))
    return ratchet_problems(rows, text_at)
