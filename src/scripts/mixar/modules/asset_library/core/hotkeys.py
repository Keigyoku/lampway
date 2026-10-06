# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Vault editor's hotkeys (specs/asset_library/asset_ui_editor.md section 6.8): the key table, and what each key asks for on the active asset. Pure Python.

The keys are registered in the add-on keyconfig's "User Interface" keymap (the keyconfig-reload rule: Python side, never only C), bound to one operator whose poll
passes only over a Vault area, so a key pressed anywhere else falls through untouched. The space's C++ region carries only UI handlers (ED_KEYMAP_UI), so a space keymap
is not expected to be polled [not measured]; the "User Interface" keymap is (measured). Measured in a windowed run with Blender's event simulation: 4, X, F, C, P reach the operator over a Vault area
in the Layout workspace. In the Zen Mode workspace no key shortcut fired at all, Blender's own ctrl+Space included."""

KEYMAP = [{"type": t, "action": a} for t, a in (("ONE", "RATE_1"), ("TWO", "RATE_2"), ("THREE", "RATE_3"), ("FOUR", "RATE_4"), ("FIVE", "RATE_5"), ("X", "REJECT"),
                                                 ("P", "PICK"), ("SPACE", "PLAY"), ("SLASH", "SEARCH"), ("F", "FIND"), ("C", "COMPARE"), ("RET", "PLACE"))]
ACTIONS = tuple(k["action"] for k in KEYMAP)


def plan(action: str, vm):
    """(verb, arguments) the key asks for, or None when it needs a selected asset and there is none."""
    if action == "PLAY":
        return ("play", {})
    if action == "SEARCH":
        return ("search", {})
    aid = vm.active
    if aid is None:
        return None
    if action.startswith("RATE_"):
        return ("rate", {"asset_id": aid, "stars": int(action[-1])})
    if action in ("REJECT", "PICK"):
        return ("rate", {"asset_id": aid, "flag": action.lower()})
    if action == "FIND":
        name = next((i.get("name") for i in vm.items if i["id"] == aid), aid)
        return ("find", {"asset_id": aid, "name": name})
    if action == "COMPARE":
        return ("compare", {"asset_id": aid})
    if action == "PLACE":
        return ("place", {"asset_id": aid})
    raise ValueError(f"unknown hotkey action {action!r}")
