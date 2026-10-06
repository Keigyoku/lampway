# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Vault editor's hotkeys (specs/asset_library/asset_ui_editor.md section 6.8): 1-5 rate, X reject, P pick, Space play/pause, / search, F find like this, C compare,
Enter place. The table and what each key does to the active asset are pure; the keymap and the area gate are Blender's (the windowed probe presses them)."""

from mixar.modules.asset_library.core import hotkeys as H
from mixar.modules.asset_library.core.viewmodel import VaultViewModel


class Clock:
    t = 1.0

    def __call__(self):
        return self.t


def vm_with(active="a1"):
    vm = VaultViewModel(clock=Clock())
    vm.submit(); r = vm.due()
    vm.receive(r["token"], {"items": [{"id": "a1", "kind": "mesh", "name": "Greaves"}, {"id": "a2", "kind": "mesh", "name": "Helm"}], "total": 2, "facets": {}, "cursor": None})
    if active:
        vm.select(active)
    return vm


def test_the_table_is_the_contracts():
    keys = {k["type"]: k["action"] for k in H.KEYMAP}
    assert keys == {"ONE": "RATE_1", "TWO": "RATE_2", "THREE": "RATE_3", "FOUR": "RATE_4", "FIVE": "RATE_5", "X": "REJECT", "P": "PICK", "SPACE": "PLAY",
                    "SLASH": "SEARCH", "F": "FIND", "C": "COMPARE", "RET": "PLACE"}
    assert all(not k.get("ctrl") and not k.get("shift") and not k.get("alt") for k in H.KEYMAP)


def test_what_each_key_asks_for_on_the_active_asset():
    vm = vm_with()
    assert H.plan("RATE_4", vm) == ("rate", {"asset_id": "a1", "stars": 4})
    assert H.plan("REJECT", vm) == ("rate", {"asset_id": "a1", "flag": "reject"})
    assert H.plan("PICK", vm) == ("rate", {"asset_id": "a1", "flag": "pick"})
    assert H.plan("FIND", vm) == ("find", {"asset_id": "a1", "name": "Greaves"})
    assert H.plan("PLACE", vm) == ("place", {"asset_id": "a1"})
    assert H.plan("PLAY", vm) == ("play", {}) and H.plan("SEARCH", vm) == ("search", {})
    H.plan("COMPARE", vm)
    assert H.plan("COMPARE", vm) == ("compare", {"asset_id": "a1"})


def test_with_nothing_selected_only_the_selection_free_keys_act():
    vm = vm_with(active=None)
    for action in ("RATE_1", "REJECT", "PICK", "FIND", "COMPARE", "PLACE"):
        assert H.plan(action, vm) is None, action
    assert H.plan("SEARCH", vm) == ("search", {}) and H.plan("PLAY", vm) == ("play", {})
