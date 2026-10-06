# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 14 in the real binary: the native Lampway icons are icons the build knows, the retired ones are gone,
and a Python surface can load a cue preview."""

import sys
from pathlib import Path

from blender_run import ROOT, run_script

sys.path.insert(0, str(ROOT / "scripts/dev/brand_art"))
import lampway_icons as gen  # noqa: E402

PROBE = r'''
import bpy, json
items = set(bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys())
from mixar.modules.common import lampway_icons
lampway_icons.icon_id("agent_blocked")   # an icon id needs a window; headless, the image itself is what loads
preview = next(iter(lampway_icons._collections.values()))["agent_blocked"]
print("RESULT " + json.dumps({"icons": sorted(i for i in items if i.startswith(("LAMPWAY_", "SPARKLE", "CREDITS_", "GENERATE"))),
                              "preview": list(preview.image_size)}))
'''


def test_the_build_knows_every_lampway_icon_and_none_retired():
    run = run_script(PROBE)
    assert run.rc == 0, run.out[-3000:]
    found = run.results[0]
    want = {f"LAMPWAY_{gen.native_name(s).upper()}" for s in gen.NATIVE}
    assert want <= set(found["icons"]), sorted(want - set(found["icons"]))
    assert not [i for i in found["icons"] if i.startswith(("SPARKLE", "CREDITS_"))], found["icons"]
    assert "GENERATE" in found["icons"]
    assert found["preview"] == [32, 32]
