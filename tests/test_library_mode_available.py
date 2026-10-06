# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Library mode is available again, on the Asset Vault (the captain, 2026-10-06: "yeah bring LIBRARY mode back").

``scene.mixie_chat_mode`` is a static ``EnumProperty`` and every mode dropdown enumerates it (the C++ chat footer, the agent bubble's footer panel and the bubble menu all
bind that one property), so listing the item shows it everywhere at once. It takes back value 4, the value it always had, so a .blend saved in Library mode before the mode
was retired opens in Library mode again. ``bpy`` is a MagicMock in this suite, so these are source-level contracts; the real-binary test is
``tests/lampway_tools/test_chat_library_vault.py``.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / "src/scripts/mixar/modules/space_mixie_chat"
BUBBLE = ROOT / "src/scripts/mixar/modules/agent_bubble"

CHAT_PROPS = CHAT / "ui/properties/chat_props.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _mode_items(props: str) -> str:
    return props.split("mixie_chat_mode = EnumProperty")[1].split("default=")[0]


def test_library_is_a_mode_enum_item_on_its_own_value():
    items = _mode_items(_read(CHAT_PROPS))
    assert "('LIBRARY'," in items and "'ASSET_MANAGER', 4)" in items
    for identifier in ("('AGENT',", "('GENERATE',", "('ADDON_PROJECT',"):
        assert identifier in items


def test_enum_value_2_stays_reserved():
    """Reusing the legacy ASK value would silently reopen old .blend files in whatever mode inherited it."""
    items = _mode_items(_read(CHAT_PROPS))
    assert ", 2)," not in items
    assert "'FILE_SCRIPT', 3)" in items


def test_every_mode_dropdown_binds_the_same_property():
    """Nothing may draw its own hand-rolled mode list, or listing the item in one place would leave Library missing in another."""
    bubble_footer = _read(BUBBLE / "ui/panels/footer_panel.py")
    bubble_menu = _read(BUBBLE / "ui/menus/agent_bubble_menu.py")

    assert 'prop(scene, "mixie_chat_mode"' in bubble_footer
    assert 'prop(scene, "mixie_chat_mode"' in bubble_menu


def test_the_quick_prompt_routes_still_only_enter_the_prompt_modes():
    """A quick prompt is text for the agent or a generation; Library is entered from the mode dropdown."""
    special_ops = _read(CHAT / "ui/operators/chat_special_ops.py")
    props = _read(CHAT_PROPS)

    assert "in {'AGENT', 'GENERATE'}" in special_ops
    quick_prompt_enum = props.split("mixie_chat_quick_prompt_mode")[1]
    assert "'LIBRARY'" not in quick_prompt_enum.split("]")[0]


def test_files_saved_in_library_mode_load_in_library_mode():
    """The load sanitizer keeps LIBRARY (value 4 is back in range) and still resets an out-of-range value (the old ASK 2) to AGENT."""
    handlers = _read(CHAT / "core/file_handlers.py")

    assert "'AGENT', 'GENERATE', 'ADDON_PROJECT', 'LIBRARY'" in handlers
    assert "scene.mixie_chat_mode = 'AGENT'" in handlers


def test_the_send_and_the_mode_switch_reach_the_vault():
    """Enter in Library mode runs the Library send, and switching into the mode shows the Vault's first page."""
    chat_ops = _read(CHAT / "ui/operators/chat_ops.py")
    library_browse = _read(CHAT / "core/library_browse.py")
    props = _read(CHAT_PROPS)

    assert "scene.mixie_chat_mode == 'LIBRARY'" in chat_ops and "execute_library_mode" in chat_ops
    assert "library_browse.schedule_show_all()" in props
    assert "library_vault_chat.start(ctx, \"\")" in library_browse
    assert "library_vault_chat.start(context, query)" in library_browse
