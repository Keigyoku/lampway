# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Proposals: what an agent (or the swarm) THINKS each Mesh QA candidate is, kept apart from the rulings.

``<rulings_dir>/<piece>_proposals.json``  {piece, session, proposals: {candidate id: {verdict, note, target?, by, at}}}

A verdict is delete | hole | mislabel | keep. It only recolours the markers and fills the review panel. Nothing here writes a
ruling or a decision row: those come from the captain's own tags (``read_tags``) or typed answers, never from a proposal.
"""

import datetime
import json
from pathlib import Path

VERDICTS = ("delete", "hole", "mislabel", "keep")


def path_for(rulings_dir, piece) -> Path:
    return Path(rulings_dir) / f"{piece}_proposals.json"


def load(rulings_dir, piece) -> dict:
    p = path_for(rulings_dir, piece)
    if not p.exists():
        return {"piece": piece, "proposals": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def merge(rulings_dir, piece, session, proposals: dict, candidate_ids, by="agent") -> dict:
    """Validate ``proposals`` ({id: {verdict, note?, target?}}) against the candidate ids, merge them into the file, return it.
    A refusal names the bad id or verdict and writes nothing."""
    known = set(candidate_ids)
    if not isinstance(proposals, dict) or not proposals:
        raise ValueError("proposals must be an object {candidate id: {verdict: delete|hole|mislabel|keep, note?}}")
    clean = {}
    for cid, p in proposals.items():
        if cid not in known:
            raise ValueError(f"no candidate {cid!r} for this piece; the candidates are: {sorted(known)[:40]}")
        verdict = str((p or {}).get("verdict", "")).lower()
        if verdict not in VERDICTS:
            raise ValueError(f"{cid}: verdict {verdict!r} is not one of {list(VERDICTS)}")
        row = {"verdict": verdict, "by": by, "at": datetime.datetime.now().isoformat(timespec="seconds")}
        if p.get("note"):
            row["note"] = str(p["note"])[:300]
        if p.get("target"):
            row["target"] = str(p["target"])
        clean[cid] = row
    data = load(rulings_dir, piece)
    data.update({"piece": piece, "session": session})
    data["proposals"].update(clean)
    path = path_for(rulings_dir, piece)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data


def counts(data: dict) -> dict:
    out = {v: 0 for v in VERDICTS}
    for p in data.get("proposals", {}).values():
        out[p["verdict"]] += 1
    return out
