# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Cloud audit F17 (2026-10-06): what an AI app reads from observe on the startup window. Most controls are icon-only, so
their text is empty; the label falls back to the tooltip. Observe pages with ``offset`` (it returned the first 100 of up to
153 with no way to the rest). Facts only: nothing is acted on."""

import json


def setup(bpy):
    pass


def facts(bpy, dump):
    from mixar.modules.common.ui_control.core import observe as O
    from mixar.modules.common.ui_control.core import schema
    every, _ = O.observe("visual-harness", {"limit": 200})
    first, _ = O.observe("visual-harness", {"limit": 5})
    second, _ = O.observe("visual-harness", {"limit": 5, "offset": 5})
    try:
        schema.validate("mixar_ui_observe", {"limit": 5, "offset": 5})
        offset_schema = "ok"
    except Exception as exc:  # noqa: BLE001
        offset_schema = str(exc)[:200]
    targets = every["targets"]
    key = lambda t: json.dumps([t.get("rect"), t.get("op"), t.get("prop"), t.get("text")])  # noqa: E731
    return {
        "total": every["total_targets"], "shown": len(targets),
        "empty_text": sum(1 for t in targets if not t.get("text")),
        "empty_label": sum(1 for t in targets if not t.get("label")),
        "tip_fallbacks_right": all(t.get("label") == (t.get("text") or t.get("tip") or "") for t in targets),
        "pages": [[key(t) for t in first["targets"]], [key(t) for t in second["targets"]]],
        "page_handles": [[t["target"] for t in first["targets"]], [t["target"] for t in second["targets"]]],
        "same_as_every": [key(t) for t in targets[:10]],
        "offset_echo": second.get("offset"), "offset_schema": offset_schema,
    }


def surfaces(bpy, dump):
    return {}


def regions(bpy):
    return {}
