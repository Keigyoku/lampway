# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon_judge: the normalizer's TYPED JUDGE slot (the captain, 2026-10-06: "System One models aren't stochastic judgement so much as
they are typed judgement, and fast inference of it").

* A judge answers one judgment FIELD with one value of that field's schema enum (facing: an axis; side: L | R | centre; texture
  role: the schema's role enum; bone map: a reference bone name or none; piece kind: the schema's kind enum). Constrained output:
  anything else is a ``SchemaError``, never accepted. Computable facts (units, axes, transforms, welds, scale, colour space from
  role, bone direction) are not fields: asking for one raises ``NotAJudgment``.
* Pinned and repeatable: the model id and version ride on every judgment, with its latency; the golden harness re-runs each case.
* A deterministic CROSS-CHECK, where one exists (facing vs the plate silhouettes, the bone map vs chain lengths and hierarchy, a role vs
  pixel statistics), decides: disagreement refuses and records both. Without one the value is accepted only at or above the
  ``confidence_threshold`` setting - which nobody has numbered yet, so it refuses.
* OFF by default (``enabled``): on only once a judge's goldens beat refusal - and refusal is never wrong, so a judge that is ever wrong
  does not beat it. Routing when a judge exists: local first (the Vault's bundled models), else a ZDR or plan route, never ``:free``,
  through egress consent, resolved as the Choices purpose ``normalize.judge`` once that hub lands. No judge model is installed today:
  the Vault's CLIP is an image tower only (no text tower for zero-shot) and its weights are a user's fetch away."""

import json
import time
from pathlib import Path

FIELDS = ("facing", "side", "texture_role", "bone_map", "piece_kind")
FACTS = ("units", "axes", "transform", "weld", "scale", "colour_space", "bone_direction")
SETTINGS = {
    "enabled": {"value": False, "why": "on only once its goldens beat refusal (never wrong), field by field"},
    "confidence_threshold": {"value": None, "needs_decision": True, "why": "a named pref, unset: the confidence a judged field without a cross-check needs (no number has been decided; needs_decision)"},
    "purpose": {"value": "normalize.judge", "why": "the Choices hub purpose once it lands; until then no route is configured"},
}


class SchemaError(ValueError):
    pass


class NotAJudgment(ValueError):
    pass


def _schema_enum(*path):
    s = json.loads((Path(__file__).parent / "canon" / "canonical-asset.schema.json").read_text())
    node = s
    for p in path:
        node = node[p]
    return tuple(node["enum"])


def allowed(field, reference=()):
    """The enum a judge must answer ``field`` from."""
    if field in FACTS:
        raise NotAJudgment(f"{field} is a computable fact: deterministic code decides it, never a judge")
    if field == "facing":
        return ("+X", "-X", "+Y", "-Y")
    if field == "side":
        return ("L", "R", "centre")
    if field == "texture_role":
        return _schema_enum("$defs", "TextureBody", "properties", "role")
    if field == "piece_kind":
        return _schema_enum("properties", "kind")
    if field == "bone_map":
        return tuple(reference) + ("none",)
    raise NotAJudgment(f"{field!r} is not a judgment field ({', '.join(FIELDS)})")


def ask(judge, field, inputs, reference=()):
    """{field, value, confidence, model_id, model_version, latency_ms}: one typed judgment; an answer outside the enum raises."""
    enum = allowed(field, reference)
    t0 = time.perf_counter()
    value, confidence = judge.propose(field, inputs, enum)
    ms = (time.perf_counter() - t0) * 1000
    if value not in enum:
        raise SchemaError(f"the judge answered {value!r} for {field}, outside {list(enum)}: refused")
    if not (isinstance(confidence, (int, float)) and 0 <= confidence <= 1):
        raise SchemaError(f"the judge's confidence {confidence!r} is not in 0..1")
    return {"field": field, "value": value, "confidence": float(confidence), "model_id": judge.model_id, "model_version": judge.model_version,
            "latency_ms": round(ms, 3)}


def decide(judgment, cross_check=None, threshold=None):
    """The decision on a judgment: the cross-check decides where there is one; else the threshold; an unset threshold refuses."""
    out = dict(judgment, proposal=judgment["value"], cross_check=cross_check, accepted=False)
    if cross_check is not None:
        if cross_check == judgment["value"]:
            out.update(accepted=True, why="the judge and the deterministic check agree")
        else:
            out.update(value=None, why=f"the judge ({judgment['value']}) and the deterministic check ({cross_check}) disagree: refused, ask the user")
        return out
    t = threshold if threshold is not None else SETTINGS["confidence_threshold"]["value"]
    if t is None:
        out.update(value=None, why="no confidence threshold is set (needs_decision) and there is no cross-check: refused")
    elif judgment["confidence"] >= t:
        out.update(accepted=True, why=f"confidence {judgment['confidence']:.3f} >= threshold {t}")
    else:
        out.update(value=None, why=f"confidence {judgment['confidence']:.3f} < threshold {t}: refused, ask the user")
    return out


def active():
    """The judge the normalizer consults, or None (the slot is off, or no judge is installed)."""
    if not SETTINGS["enabled"]["value"]:
        return None
    return None                                                        # no judge model is installed yet (see the module docstring)


def golden(judge, field, cases, repeats=3, reference=()):
    """{accuracy, wrong, decided, refusal_accuracy, repeatable, beats_refusal, latency_ms}: a judge on golden cases [{..inputs, want}]."""
    right = wrong = 0
    repeatable, times = True, []
    for case in cases:
        answers = []
        for _ in range(repeats):
            j = ask(judge, field, case, reference)
            answers.append(j["value"])
            times.append(j["latency_ms"])
        repeatable &= len(set(answers)) == 1
        right += answers[0] == case["want"]
        wrong += answers[0] != case["want"]
    n = max(len(cases), 1)
    return {"field": field, "model_id": judge.model_id, "model_version": judge.model_version, "cases": len(cases), "accuracy": right / n,
            "wrong": wrong, "decided": right + wrong, "refusal_accuracy": 0.0, "repeatable": repeatable,
            "beats_refusal": bool(repeatable and wrong == 0 and right > 0),
            "latency_ms": {"max": max(times) if times else 0.0, "mean": sum(times) / len(times) if times else 0.0}}
