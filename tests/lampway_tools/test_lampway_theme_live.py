# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 01 in the real binary (headless): Blender itself parses the themes.

T7: Lampway Night and Lampway Paper load through the Theme menu's own path (`script.execute_preset`) and every one of
their attributes reads back from RNA. A text comparison cannot fake this: an attribute the 5.2 schema does not have,
or a struct the preset importer skips, fails here.
"""

from pathlib import Path

import pytest

from blender_run import ROOT, run_script

THEME = ROOT / "scripts/lampway/facelift/theme"
VERIFY = (THEME / "verify_in_blender.py").read_text(encoding="utf-8")


def verify(xml: Path, tmp_path: Path, *flags):
    report = tmp_path / (xml.stem + ".json")
    run = run_script(VERIFY, args=[xml, report, *flags])
    lines = [line for line in run.out.splitlines() if line.startswith("VERIFY")]
    return run, lines


@pytest.mark.parametrize("name", ["lampway_dark.xml", "lampway_light.xml"])
def test_theme_loads_through_the_preset_path_and_reads_back(name, tmp_path):
    run, lines = verify(THEME / name, tmp_path)
    assert run.rc == 0, run.out[-3000:]
    assert lines == ["VERIFY PASS 959 attributes, 0 problems"], lines


def test_a_new_profile_starts_in_lampway_night(tmp_path):
    """T8 in the binary: with nothing loaded, the factory theme reads back as lampway_dark.xml, attribute by
    attribute (938 below <Theme>; the style is not part of the compiled theme)."""
    run, lines = verify(THEME / "lampway_dark.xml", tmp_path, "--as-default")
    assert lines == ["VERIFY PASS 938 attributes, 0 problems"], lines + [run.out[-2000:]]


def test_the_theme_menu_offers_night_and_paper_and_not_forest():
    run = run_script(
        "import bpy, json, os\n"
        "names = sorted(n for d in bpy.utils.preset_paths('interface_theme') for n in os.listdir(d))\n"
        "print('RESULT ' + json.dumps({'presets': names, 'name': bpy.context.preferences.themes[0].name}))\n")
    assert run.rc == 0, run.out[-2000:]
    found = run.results[0]
    assert {"Lampway_Night.xml", "Lampway_Paper.xml"} <= set(found["presets"]), found
    assert not [n for n in found["presets"] if "forest" in n.lower() or n == "Mixar_theme.xml"], found
    assert found["name"] == "Lampway Night", found


OFFER = r'''
import bpy, json, sys
boot = sys.modules["bootstrap"]  # UI modules register in timer batches; a headless run has no event loop to drain them
for _ in range(100000):
    if boot._ui_loading_complete:
        break
    boot._load_ui_batch_tick()
assert boot._ui_loading_complete
from mixar.config import config
from mixar.modules.common.core import lampway_night as night
from mixar.modules.common.notifications.store import get_notification_store
forest = sys.argv[sys.argv.index("--") + 1]
assert bpy.ops.script.execute_preset(filepath=forest, menu_idname="USERPREF_MT_interface_theme_presets") == {"FINISHED"}
theme = bpy.context.preferences.themes[0]
path = night.preset_path(bpy.utils.preset_paths("interface_theme"))
store = get_notification_store()
first = night.offer_once(theme, path, config, store)
shown = store.contains(night.TOAST_ID)
second = night.offer_once(theme, path, config, store)
applied = sorted(bpy.ops.lampway.apply_night_theme())
print("RESULT " + json.dumps({"first": first, "shown": shown, "second": second, "applied": applied,
                              "wears_night": night.wears(theme, path), "canvas": list(theme.user_interface.mixar_canvas)}))
'''


def test_an_existing_profile_is_offered_night_once_and_the_button_applies_it():
    """F2 in the binary: a profile that kept Mixar's Forest gets the toast once; its button switches to Night."""
    run = run_script(OFFER, args=[ROOT / "src/release/datafiles/userdef/Mixar_theme.xml"])
    assert run.rc == 0, run.out[-3000:]
    found = run.results[0]
    assert (found["first"], found["shown"], found["second"]) == ("offered", True, "already-offered"), found
    assert found["applied"] == ["FINISHED"] and found["wears_night"] is True, found


def test_a_planted_unknown_attribute_fails_the_loader(tmp_path):
    planted = tmp_path / "planted.xml"
    text = (THEME / "lampway_dark.xml").read_text(encoding="utf-8")
    planted.write_text(text.replace('menu_shadow_fac="0.5"', 'menu_shadow_fac="0.5"\n          lampway_not_a_property="1"', 1),
                       encoding="utf-8")
    run, lines = verify(planted, tmp_path)
    assert run.rc != 0
    assert lines and lines[0].startswith("VERIFY FAIL"), lines
