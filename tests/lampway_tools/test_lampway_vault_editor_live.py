# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""In the real binary, the MIXAR_ASSETS editor is called the Asset Vault in the Editor Type list."""

from blender_run import run_script

PROBE = r'''
import bpy, json
item = bpy.types.Area.bl_rna.properties["type"].enum_items["MIXAR_ASSETS"]
print("RESULT " + json.dumps({"name": item.name}))
'''


def test_the_editor_type_list_names_the_asset_vault():
    run = run_script(PROBE)
    assert run.rc == 0, run.out[-3000:]
    assert run.results[0]["name"] == "Asset Vault"
