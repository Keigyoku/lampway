# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""G9: the allow-list is the cheapest way to turn a brand gate green, so it is itself gated.

Every entry names path, text, reason and a known category; its path exists and still contains its text (a stale exemption fails); and the count equals
the number recorded in ``brand_allowlist.ratchet`` -- adding an entry means editing that number in the same commit, where a reviewer sees it, and
removing one means lowering it.
"""

import brandgate


def problems(entries, root=brandgate.ROOT):
    out = []
    for i, e in enumerate(entries):
        for field in ("path", "text", "reason", "category"):
            if not str(e.get(field, "")).strip():
                out.append(f"entry {i}: empty {field}")
        if e.get("category") not in brandgate.CATEGORIES:
            out.append(f"entry {i}: category {e.get('category')!r} is not one of {brandgate.CATEGORIES}")
        p = root / e.get("path", "")
        if not p.is_file():
            out.append(f"entry {i}: {e.get('path')} does not exist")
        elif e.get("text", "") not in p.read_text(encoding="utf-8", errors="replace"):
            out.append(f"entry {i}: {e.get('path')} no longer contains {e.get('text')!r}")
        if len(str(e.get("reason", ""))) < 30:
            out.append(f"entry {i}: reason is too short to say why")
    return out


def test_every_entry_is_complete_and_still_matches():
    assert problems(brandgate.load()) == []


def test_the_count_is_the_recorded_baseline():
    recorded = int((brandgate.HERE / "brand_allowlist.ratchet").read_text().strip())
    assert len(brandgate.load()) == recorded, "edit brand_allowlist.ratchet in the same commit as the list"


def test_the_gate_sees_planted_bad_entries(tmp_path):
    (tmp_path / "f.txt").write_text("hello\n")
    bad = [{"path": "f.txt", "text": "absent", "reason": "x", "category": "nonsense"}, {"path": "missing.txt", "text": "t", "reason": "", "category": "native-lookup"}]
    found = problems(bad, root=tmp_path)
    assert any("no longer contains" in f for f in found) and any("category" in f for f in found) and any("does not exist" in f for f in found) and any("empty reason" in f for f in found)
    good = [{"path": "f.txt", "text": "hello", "reason": "the line that looks it up is f.txt:1, see the test", "category": "native-lookup"}]
    assert problems(good, root=tmp_path) == []
