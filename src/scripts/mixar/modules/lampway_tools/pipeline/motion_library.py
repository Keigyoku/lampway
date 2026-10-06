# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""motion_generate, the pure layer: a deterministic ranker over an index of owned clips, and the model slots (specs/resources/motion_generate.md).

A clip's words are its tags plus its name's tokens (split on _ and case; fwd/bwd/l/r expanded; the MM_/MF_ prefixes and numbers dropped). A prompt's words
drop a few stop words. score = the share of the prompt's words the clip has; ties go to the clip whose duration is nearest the asked duration, then to the
name. A best match with no shared word, or under MIN_SCORE, is refused rather than returned. The model engines (Kimodo, UniMate) are slots: until the captain
names a provider they answer needs_provider and send nothing (no network code exists here)."""

import hashlib
import json
import re

from ..meshqa import decisions as D

MIN_SCORE = 0.25
STOP = {"a", "an", "the", "with", "of", "to", "and", "in", "on", "some", "my", "his", "her", "do", "does", "heavy", "quick", "slow", "please"}
ABBR = {"fwd": "forward", "bwd": "backward", "l": "left", "r": "right", "atk": "attack"}
DROP = {"mm", "mf", "ue", "anim", "a"}
MODELS = ("model:kimodo", "model:unimate")


class MotionError(ValueError):
    pass


def _words(text):
    parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(text)).replace("_", " ").replace("-", " ").lower().split()
    out = []
    for p in parts:
        p = ABBR.get(p, p)
        if p.isdigit() or p in DROP:
            continue
        out.append(p)
    return out


def _check(prompt, duration):
    if not 1 <= len(str(prompt or "").strip()) <= 300:
        raise MotionError("the prompt is 1..300 characters")
    if not 0.5 <= float(duration) <= 10:
        raise MotionError("duration is 0.5..10 seconds")


def rank(prompt, rows, duration=3.0):
    want = [w for w in _words(prompt) if w not in STOP]
    out = []
    for r in rows:
        have = set(_words(r["name"])) | {t.lower() for t in r.get("tags") or []}
        hit = sum(1 for w in set(want) if w in have)
        score = hit / max(len(set(want)), 1)
        dur = (r["frames"] / r["fps"]) if r.get("frames") and r.get("fps") else None
        out.append({"name": r["name"], "file": r.get("file"), "score": round(score, 4), "hits": hit,
                    "duration_gap": abs(dur - float(duration)) if dur is not None else 1e9})
    out.sort(key=lambda x: (-x["score"], x["duration_gap"], x["name"]))
    return out


def pick(prompt, rows, duration=3.0):
    _check(prompt, duration)
    if not rows:
        raise MotionError("the clip index is empty: run motion_generate action=index on the library folder first")
    ranked = rank(prompt, rows, duration)
    best = ranked[0]
    if best["hits"] == 0 or best["score"] < MIN_SCORE:
        tags = sorted({w for r in rows for w in _words(r["name"])} | {t for r in rows for t in r.get("tags") or []})
        raise MotionError(f"no clip matches {prompt!r}; the library has {len(rows)} clips: {', '.join(tags)}; add one to anims/index.json or pick an engine")
    return best, ranked


def model_slot(engine):
    if engine not in MODELS:
        raise MotionError(f"engine is library | {' | '.join(MODELS)}")
    return {"ok": False, "needs_provider": True, "engine": engine,
            "error": "no GPU provider is configured for text-to-motion; nothing was run and nothing was sent",
            "help": ["the captain names a host for text-to-motion (a rented GPU worker, a Studio that adds it, or none: the Seedance/video route)",
                     "use engine=library meanwhile, never a silent fallback"]}


def decision_row(prompt, ranked, picked, source):
    desc = {"prompt": prompt, "candidates": [{"name": r["name"], "score": r["score"]} for r in ranked[:5]]}
    return D.row("motion_generate", source, desc, "which clip answers the prompt", [r["name"] for r in ranked[:5]], picked, decider="model",
                 how="token overlap of the prompt with the clip's name and tags; ties by duration")


def index_rows(names_files, existing):
    """Rows for the files found, keeping any existing row's tags, fps, frames and root_motion (the captain's)."""
    old = {r["name"]: r for r in existing or []}
    rows = []
    for name, f in sorted(names_files):
        r = dict(old.get(name) or {"name": name, "tags": [], "fps": None, "frames": None, "root_motion": None})
        r["file"] = f
        rows.append(r)
    return rows


def sha(rows) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
