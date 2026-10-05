# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canonical bone labels for retargeting: a deterministic, side-aware reading of a bone name (Mixamo, Rigify, UE Manny/MetaHuman, 3ds Bip01 and the like) into
(label, side, number). Written from the naming conventions themselves, not copied from any project's vocabulary table. A name it cannot read is None: never guessed."""

import re

PREFIXES = ("mixamorig", "cc", "base", "def", "org", "mch")
SIDE_TOKENS = {"left": "l", "l": "l", "lft": "l", "right": "r", "r": "r", "rgt": "r"}
SKIP = ("twist", "ik", "pole", "helper", "corrective", "roll", "end", "target", "ctrl", "control", "tip", "nub")
FINGERS = ("thumb", "index", "middle", "ring", "pinky", "little")
KEYS = {
    "pelvis": "pelvis", "hips": "pelvis", "hip": "pelvis", "root": "root",
    "spine": "spine", "chest": "spine", "upperchest": "spine", "neck": "neck", "head": "head",
    "clavicle": "clavicle", "shoulder": "clavicle", "collar": "clavicle", "collarbone": "clavicle",
    "upperarm": "upperarm", "arm": "upperarm", "uparm": "upperarm",
    "forearm": "lowerarm", "lowerarm": "lowerarm", "lowarm": "lowerarm",
    "hand": "hand", "wrist": "hand",
    "thigh": "thigh", "upleg": "thigh", "upperleg": "thigh", "upleg": "thigh",
    "calf": "calf", "shin": "calf", "leg": "calf", "lowerleg": "calf", "lowleg": "calf",
    "foot": "foot", "ankle": "foot", "toe": "ball", "toes": "ball", "toebase": "ball", "ball": "ball",
}


def _tokens(name: str) -> list:
    s = name.split(":")[-1] if name.lower().startswith("mixamorig:") else name
    s = re.sub(r"(?i)^bip0*1[\s_.]*", "", s)                           # 3ds Bip01 / Bip001 prefix
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)                        # CamelCase
    s = re.sub(r"([A-Za-z])(\d)", r"\1 \2", s)
    s = re.sub(r"[\s_.:\-]+", " ", s).strip().lower()
    return [t for t in s.split(" ") if t and t not in PREFIXES]


def label(name: str):
    """(label, side, number) or None. side is 'l', 'r' or None; number is the digits in the name (spine 2, neck 1, finger joint 3) or None."""
    toks = _tokens(name)
    if not toks or any(t in SKIP for t in toks):
        return None
    side = None
    rest = []
    for t in toks:
        if t in SIDE_TOKENS and side is None and len(toks) > 1:
            side = SIDE_TOKENS[t]
        else:
            rest.append(t)
    nums = [int(t) for t in rest if t.isdigit()]
    words = [t for t in rest if not t.isdigit()]
    number = nums[0] if nums else None
    fingers = [w for w in words if w in FINGERS]
    if fingers:
        return ("finger_" + ("pinky" if fingers[0] == "little" else fingers[0]), side, number)
    key = "".join(words)
    if key in KEYS:
        return (KEYS[key], side, number)
    for w in words:                                                    # a decorated name: the last word that reads
        if w in KEYS:
            return (KEYS[w], side, number)
    return None
