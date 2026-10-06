# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The typed tool forms of the Way (facelift contract 07). ``tool_specs.json`` is generated from the agent's own tool
definitions (scripts/lampway/facelift/tool_specs.py), so the sidebar form and the agent's schema are one thing. No bpy:
``argv`` builds a batch tool's command line exactly as the server's ``_args_for`` does for the agent."""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load() -> dict:
    with open(os.path.join(HERE, "tool_specs.json"), encoding="utf-8") as fh:
        return {t["name"]: t for t in json.load(fh)["tools"]}


def operator_id(spec) -> str:
    return "lampway.tool_" + (spec.get("batch") or spec.get("api"))


def argv(spec, values: dict) -> list:
    """Positional parameters first, then the flags; a False flag and an empty value are left out."""
    out = []
    for p in (q for q in spec["params"] if q.get("flag") is None):
        v = values.get(p["name"])
        if v is None or v == "":
            continue
        out += [str(x) for x in v] if isinstance(v, list) else [str(v)]
    for p in (q for q in spec["params"] if q.get("flag") is not None):
        v = values.get(p["name"])
        if v is None or v is False or v == "" or v == []:
            continue
        if v is True:
            out.append(p["flag"])
        elif isinstance(v, list):
            vals = [str(x) for x in v]
            out += [x for val in vals for x in (p["flag"], val)] if p.get("repeat") else [p["flag"], ",".join(vals)]
        else:
            out += [p["flag"], str(v)]
    return out


def title(spec) -> str:
    """'lampway_pose_clearance' -> 'Pose clearance'."""
    name = spec["name"].removeprefix("lampway_").replace("_", " ")
    return name[:1].upper() + name[1:]
