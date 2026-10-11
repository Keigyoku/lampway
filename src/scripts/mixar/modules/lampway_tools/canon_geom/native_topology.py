# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Measured native MetaHuman identities/edges, not substring anatomy guesses."""
import json
from pathlib import Path

PROFILE = json.loads((Path(__file__).parents[1] / "canon/metahuman342-topology.json").read_text())
PARENTS = PROFILE["parents"]
AUXILIARY = frozenset(PROFILE["auxiliary"])
TERMINALS = frozenset(PROFILE["canonical_terminals"])
CHILDREN = {n: frozenset(b for b, p in PARENTS.items() if p == n) for n in PARENTS}


def terminal_children(bone, children):
    return bool(bone in TERMINALS and children and set(children).issubset(CHILDREN[bone]))


def audit(parents):
    """All unsupported rows at once. Core-only rigs may omit anatomical ancestors.

    Native auxiliary edges never collapse or move. Missing rows are reported,
    rather than a core minimum falsely proving a complete native reference.
    """
    errors = []
    for n, parent in sorted(parents.items()):
        if n not in PARENTS:
            errors.append(f"unknown native bone {n}")
            continue
        expected = PARENTS[n]
        if n not in AUXILIARY:
            while expected is not None and expected not in parents:
                expected = PARENTS[expected]
        if parent != expected:
            errors.append(f"{n}: parent {parent!r}, expected {expected!r}")
    if errors:
        raise ValueError("native topology refused: " + "; ".join(errors))
    missing = sorted(set(PARENTS) - set(parents))
    return {"complete": not missing, "missing": missing}
