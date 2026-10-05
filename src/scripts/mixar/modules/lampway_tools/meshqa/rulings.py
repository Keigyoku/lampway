# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The rulings files the rebuild reads. All ids are SOURCE face ids (the original mesh's polygon index), so a ruling
survives every rebuild; a live face of a rebuilt mesh maps back through that rebuild's ``orig_poly`` array
(``-1`` marks a patch face, which has no source). Files, per piece, in one directory (the shelf's meshqa/):

    <piece>_deletions.json          {"polys": [...], "decisions": [{what, decider, date, note?}], "refill": [...]}
    <piece>_relabels_orig.json      {"relabels": [{"faces_orig": [...], "to": part, "why": ...}]}
    <piece>_texel_overrides_orig.json  {"force_class": [{"faces_orig": [...], "class": ..., "why": ...}]}
    <piece>_candidates_merged.json  {mesh, owner, recipe, turn, ..., "candidates": [...]}  (rounds merged)

Pure Python (no bpy). Every writer is idempotent: adding what is already ruled changes nothing.
"""

import datetime
import json
from pathlib import Path


def _today():
    return datetime.date.today().isoformat()


def _read(path, default):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def merge_candidates(base: dict, extra: dict, prefix: str = "B-") -> dict:
    """``base`` plus ``extra``'s candidates, every extra id carrying ``prefix`` (a later round's L110 is 'B-L110', as in
    the shelf's merged file, so no round can shadow another). The base's meta (mesh, owner, recipe, turn, ...) is kept."""
    out = {k: v for k, v in base.items() if k != "candidates"}
    cands = list(base["candidates"])
    ids = {c["id"] for c in cands}
    for c in extra["candidates"]:
        c = dict(c)
        c["id"] = prefix + c["id"]
        if c["id"] in ids:
            raise ValueError(f"candidate id {c['id']} already merged")
        ids.add(c["id"])
        cands.append(c)
    out["candidates"] = cands
    return out


class Rulings:
    def __init__(self, directory, piece, parts=None):
        self.dir = Path(directory)
        self.piece = piece
        self.parts = list(parts) if parts is not None else None

    def path(self, kind):
        return self.dir / f"{self.piece}_{kind}.json"

    # ---- deletions
    def add_deletions(self, polys, what, decider="captain", date=None, note=None) -> int:
        """Union ``polys`` into the deletions; records one decision when something new was added. Returns how many are new."""
        p = self.path("deletions")
        data = _read(p, {"polys": [], "decisions": []})
        have = set(data.get("polys", []))
        new = sorted(set(int(x) for x in polys) - have)
        if not new:
            return 0
        data["polys"] = sorted(have | set(new))
        rec = {"what": what, "decider": decider, "date": date or _today()}
        if note:
            rec["note"] = note
        data.setdefault("decisions", []).append(rec)
        _write(p, data)
        return len(new)

    # ---- relabels and texel overrides
    def _check_part(self, to):
        if self.parts is not None and to not in self.parts:
            raise ValueError(f"unknown part {to!r}; the recipe has {self.parts}")

    def add_relabel(self, faces_orig, to, why) -> None:
        self._check_part(to)
        p = self.path("relabels_orig")
        data = _read(p, {"relabels": []})
        entry = {"faces_orig": sorted(set(int(x) for x in faces_orig)), "to": to, "why": why}
        if entry not in data["relabels"]:
            data["relabels"].append(entry)
            _write(p, data)

    def add_force_class(self, faces_orig, cls, why) -> None:
        p = self.path("texel_overrides_orig")
        data = _read(p, {"force_class": []})
        entry = {"faces_orig": sorted(set(int(x) for x in faces_orig)), "class": cls, "why": why}
        if entry not in data["force_class"]:
            data["force_class"].append(entry)
            _write(p, data)

    # ---- candidates
    def save_merged(self, base: dict, extra: dict = None, prefix: str = "B-") -> dict:
        merged = merge_candidates(base, extra, prefix) if extra else base
        _write(self.path("candidates_merged"), merged)
        return merged

    # ---- tags -> rulings
    def apply_tags(self, tagged, candidates, orig_poly, what="red annotation (Delete layer)", date=None,
                   expand_shell=True, mislabel_to=None, why="green annotation (Mislabel layer)") -> dict:
        """Turn one reading of the tag layers into rulings.

        Delete: the tagged faces (source ids), plus the whole floating shell each sits on when ``expand_shell``.
        Patch faces (``orig_poly`` -1) have no source id: counted and skipped.
        Mislabel: a stroke with a target part in ``mislabel_to`` ({stroke index: part}) becomes a relabel; one without
        is returned in ``relabels_needing_a_target`` with its faces and Smart UV islands - the target is a decision
        (a person's or a model's), never guessed here."""
        report = {"deleted": 0, "patch_faces_skipped": 0, "shells": [], "relabelled": 0, "relabels_needing_a_target": []}
        mislabel_to = mislabel_to or {}

        def to_orig(faces):
            out, skipped = [], 0
            for f in faces:
                o = int(orig_poly[f])
                if o < 0:
                    skipped += 1
                else:
                    out.append(o)
            return out, skipped

        dele = set()
        for s in tagged.get("delete", []):
            faces, skipped = to_orig(s["faces"])
            dele |= set(faces)
            report["patch_faces_skipped"] += skipped
        if dele and expand_shell:
            for c in candidates:
                if c.get("kind") == "loose_shell" and dele & set(c.get("orig_polys", [])):
                    dele |= set(c["orig_polys"])
                    report["shells"].append(c["id"])
        if dele:
            report["deleted"] = len(dele)
            self.add_deletions(sorted(dele), what=what, date=date)
        for s in tagged.get("mislabel", []):
            faces, _ = to_orig(s["faces"])
            if not faces:
                continue
            target = mislabel_to.get(s["stroke"])
            if target:
                self.add_relabel(faces, target, why)
                report["relabelled"] += len(faces)
            else:
                report["relabels_needing_a_target"].append({"stroke": s["stroke"], "faces_orig": sorted(set(faces)),
                                                            "islands": s.get("islands", [])})
        return report
