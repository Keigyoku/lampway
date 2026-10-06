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


def verify(xml: Path, tmp_path: Path):
    report = tmp_path / (xml.stem + ".json")
    run = run_script(VERIFY, args=[xml, report])
    lines = [line for line in run.out.splitlines() if line.startswith("VERIFY")]
    return run, lines


@pytest.mark.parametrize("name", ["lampway_dark.xml", "lampway_light.xml"])
def test_theme_loads_through_the_preset_path_and_reads_back(name, tmp_path):
    run, lines = verify(THEME / name, tmp_path)
    assert run.rc == 0, run.out[-3000:]
    assert lines == ["VERIFY PASS 959 attributes, 0 problems"], lines


def test_a_planted_unknown_attribute_fails_the_loader(tmp_path):
    planted = tmp_path / "planted.xml"
    text = (THEME / "lampway_dark.xml").read_text(encoding="utf-8")
    planted.write_text(text.replace('menu_shadow_fac="0.5"', 'menu_shadow_fac="0.5"\n          lampway_not_a_property="1"', 1),
                       encoding="utf-8")
    run, lines = verify(planted, tmp_path)
    assert run.rc != 0
    assert lines and lines[0].startswith("VERIFY FAIL"), lines
