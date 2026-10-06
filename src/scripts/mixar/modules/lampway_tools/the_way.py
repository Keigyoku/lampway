# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Way (facelift contract 07): the tool sidebar as the captain's piece runbook. ``status.toml`` holds the steps in
his order and each tool's status word with the report that measured it; this module reads it, says where a piece is
(its done steps are a custom property on the object, written when a step's tool succeeds), and draws a tool's typed
form. No bpy."""

import os
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
DONE_KEY = "lampway_way_done"
WORD = {"live": "Live", "built": "Built", "partial": "Partial", "planned": "Planned"}
WORD_ICON = {"live": "CHECKMARK", "built": "TOOL_SETTINGS", "partial": "DECORATE_KEYFRAME", "planned": "TIME"}


def _table() -> dict:
    with open(os.path.join(HERE, "status.toml"), "rb") as fh:
        return tomllib.load(fh)


def steps() -> list:
    return list(_table()["step"])


def tool_status() -> dict:
    """Each tool's word: its own row in [tools], else its step's."""
    table = _table()
    out = {}
    for step in table["step"]:
        for tool in step.get("tools", []):
            out[tool] = {"status": step["status"], "source": step.get("source", ""), "when": step.get("when", "")}
    for tool, row in (table.get("tools") or {}).items():
        out[tool] = dict(out.get(tool, {}), **row)
    return out


def done_steps(obj) -> set:
    raw = obj.get(DONE_KEY, "") if obj is not None and hasattr(obj, "get") else ""
    return {s for s in str(raw).split(",") if s}


def mark_done(obj, step_id: str) -> None:
    if obj is not None:
        obj[DONE_KEY] = ",".join(sorted(done_steps(obj) | {step_id}))


def node(step_id: str, done: set) -> str:
    """The node preview for a step on this piece: lit (done), half (where the piece is: the first step not done), unlit."""
    if step_id in done:
        return "node_lit"
    first_open = next((s["id"] for s in steps() if s["id"] not in done), None)
    return "node_half" if step_id == first_open else "node"


def progress(done: set) -> str:
    total = steps()
    return f"{sum(1 for s in total if s['id'] in done)} of {len(total)} done"


def step_of(tool_name: str):
    return next((s["id"] for s in steps() if tool_name in s.get("tools", [])), None)


def draw_tool(layout, spec, status) -> None:
    """One tool on one line: its name, its word, and Run (which opens the typed form). A planned tool has no Run."""
    from .tool_specs import operator_id, title
    row = layout.row(align=True)
    word = status.get("status", "planned")
    if word == "planned":
        row.label(text=f"{title(spec)}: Planned, {status.get('when') or 'later'}", icon=WORD_ICON["planned"])
        return
    row.label(text=title(spec), icon=WORD_ICON[word])
    row.operator(operator_id(spec), text="Run", icon="PLAY")
