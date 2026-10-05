# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The mesh-QA decision log: one typed decision per row, so the rows can train a decision model later.

Shape (the shelf's meshqa/decisions.jsonl, itself shaped like the project's fit_state tool's decision log): the
candidate's descriptor (the drawing segments dropped) beside its sha256 over canonical JSON, the question and its
options, the answer, the decider ('captain'), the session, and how it was decided (his words, a rule, the stroke
ids). The LATEST answer per candidate wins, so a correction is a new row, never an edit. Pure Python.
"""

import hashlib
import json
from pathlib import Path

DECIDERS = ("captain", "model", "oracle")


def _clean(descriptor: dict) -> dict:
    return {k: v for k, v in descriptor.items() if k != "segments_m"}


def descriptor_sha256(descriptor: dict) -> str:
    return hashlib.sha256(json.dumps(_clean(descriptor), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def row(session, source, descriptor, question, options, answer, decider="captain", how=None,
        captain_words=None, region_rule=None, strokes=None) -> dict:
    if decider not in DECIDERS:
        raise ValueError(f"decider must be one of {DECIDERS}, got {decider!r}")
    d = _clean(descriptor)
    out = {"session": session, "source": str(source), "descriptor": d, "descriptor_sha256": descriptor_sha256(d),
           "question": question, "options": list(options), "answer": answer, "decider": decider}
    for key, val in (("how", how), ("captain_words", captain_words), ("region_rule", region_rule), ("strokes", strokes)):
        if val is not None:
            out[key] = val
    return out


def append_rows(path, rows) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    return len(rows)


def read_rows(path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def latest_answers(rows, kind="open_loop", session=None) -> dict:
    """{candidate id: the latest answer} for descriptors of ``kind`` (patch_holes.py reads 'open_loop' -> 'hole')."""
    latest = {}
    for r in rows:
        d = r.get("descriptor", {})
        if d.get("kind") == kind and (session is None or r.get("session") == session):
            latest[d["id"]] = r.get("answer")
    return latest


_HOW = {"circled": "yellow annotation (Hole layer) circling it", "along": "yellow annotation (Hole layer) running along it"}


def rows_from_tags(tagged, candidates, session, source, close_round=False, decider="captain") -> list:
    """Decision rows for one reading of the tag layers (``marks.interpret`` output; Delete strokes carry
    ``orig_faces`` once mapped to source faces). ``close_round`` also answers every candidate nobody named: keep
    (the captain's "everything else looks pretty good / intentional")."""
    by_id = {c["id"]: c for c in candidates}
    rows, named = [], set()

    def hole_row(c, how, strokes):
        return row(session, source, c, "open_loop_defect", ["hole", "keep"], "hole", decider, how=how, strokes=strokes)

    loops = {}
    for s in tagged.get("hole", []):
        for cid, mode in s.get("loops", {}).items():
            if cid in by_id:
                loops.setdefault(cid, (mode, []))[1].append(s["stroke"])
    for cid, (mode, strokes) in loops.items():
        rows.append(hole_row(by_id[cid], _HOW[mode], strokes))
        named.add(cid)
    for s in tagged.get("hole", []):
        if s.get("orphan"):
            rows.append(row(session, source, {"kind": "captain_finding", "stroke": s["stroke"], "centre_m": s["centre_m"],
                                              "n_points": s.get("n_points")},
                            "open_loop_defect", ["hole", "keep"], "hole", decider, how="yellow annotation that met no candidate",
                            strokes=[s["stroke"]]))
    for s in tagged.get("delete", []):
        hit = set(s.get("orig_faces", []))
        for c in candidates:
            if c.get("kind") == "loose_shell" and c["id"] not in named and hit & set(c.get("orig_polys", [])):
                rows.append(row(session, source, c, "loose_shell_defect", ["delete", "keep"], "delete", decider,
                                how="red annotation (Delete layer)", strokes=[s["stroke"]]))
                named.add(c["id"])
    if close_round:
        for c in candidates:
            if c["id"] not in named:
                q = "open_loop_defect" if c["kind"] == "open_loop" else "loose_shell_defect"
                rows.append(row(session, source, c, q, ["hole", "keep"] if c["kind"] == "open_loop" else ["delete", "keep"],
                                "keep", decider, how="everything_else_intentional"))
    return rows


def new_rows(existing, rows) -> list:
    """The rows that change something: a row repeating the LATEST answer already logged for the same descriptor
    and question is dropped (re-reading the same marks must not grow the log)."""
    last = {}
    for r in existing:
        last[(r.get("descriptor_sha256"), r.get("question"))] = r.get("answer")
    out = []
    for r in rows:
        key = (r["descriptor_sha256"], r["question"])
        if last.get(key) == r["answer"] and key in last:
            continue
        last[key] = r["answer"]
        out.append(r)
    return out
