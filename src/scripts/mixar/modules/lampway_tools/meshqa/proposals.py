# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Proposals: what the RULES or an agent THINK each Mesh QA candidate is, kept apart from the rulings.

``<rulings_dir>/<piece>_proposals.json`` is a list of {id, kind, verdict, reason, by, at, target?}; ``by`` is ``rule:<name>`` for a rule
(rules.py) or the proposer's name (``agent``). A verdict is delete | hole | mislabel | keep. It only recolours the markers and fills the
review panel. Nothing here writes a ruling or a decision row: those come from the captain's own tags (``read_tags``) or typed answers,
never from a proposal. A rule never overwrites a row somebody else wrote.
"""

import datetime
import json
from pathlib import Path

VERDICTS = ("delete", "hole", "mislabel", "keep")


def path_for(rulings_dir, piece) -> Path:
    return Path(rulings_dir) / f"{piece}_proposals.json"


def load_rows(rulings_dir, piece) -> list:
    p = path_for(rulings_dir, piece)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):                                   # the first shape: {piece, proposals: {id: {...}}}
        data = [{"id": k, **v, "reason": v.get("reason") or v.get("note", "")} for k, v in (data.get("proposals") or {}).items()]
    return data


def as_map(rows) -> dict:
    return {r["id"]: r for r in rows}


def validate(proposals, candidates_by_id, by="agent") -> list:
    """Rows from an explicit ``{id: {verdict, reason?, target?}}``. A refusal names the bad id or verdict and writes nothing."""
    if not isinstance(proposals, dict) or not proposals:
        raise ValueError("proposals must be an object {candidate id: {verdict: delete|hole|mislabel|keep, reason?}}")
    rows = []
    for cid, p in proposals.items():
        if cid not in candidates_by_id:
            raise ValueError(f"no candidate {cid!r} for this piece; the candidates are: {sorted(candidates_by_id)[:40]}")
        p = p or {}
        verdict = str(p.get("verdict", "")).lower()
        if verdict not in VERDICTS:
            raise ValueError(f"{cid}: verdict {verdict!r} is not one of {list(VERDICTS)}")
        rows.append(_row(cid, candidates_by_id[cid]["kind"], verdict, p.get("reason") or p.get("note") or "", by, p.get("target")))
    return rows


def _row(cid, kind, verdict, reason, by, target=None) -> dict:
    row = {"id": cid, "kind": kind, "verdict": verdict, "reason": str(reason)[:300], "by": by,
           "at": datetime.datetime.now().isoformat(timespec="seconds")}
    if target:
        row["target"] = str(target)
    return row


def rule_rows(verdicts) -> list:
    return [_row(v["id"], v["kind"], v["verdict"], v["reason"], f"rule:{v['rule']}") for v in verdicts]


def _is_rule(row) -> bool:
    return str(row.get("by", "")).startswith("rule:")


def merge(existing: list, new_rows: list, rules_run: bool = False) -> list:
    """``existing`` + ``new_rows``; a new row replaces the old row for its id. On a rules run the old RULE rows are replaced wholesale (the
    rules' fresh answer), and a rule row never replaces one somebody else wrote: an agent's judgement of an ambiguous candidate survives
    a re-run of the rules."""
    out = {r["id"]: r for r in existing if not (rules_run and _is_rule(r))}
    for r in new_rows:
        if _is_rule(r) and r["id"] in out and not _is_rule(out[r["id"]]):
            continue
        out[r["id"]] = r
    return list(out.values())


def save(rulings_dir, piece, rows) -> Path:
    path = path_for(rulings_dir, piece)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return path


def counts(rows) -> dict:
    out = {v: 0 for v in VERDICTS}
    for r in rows:
        out[r["verdict"]] += 1
    return out
