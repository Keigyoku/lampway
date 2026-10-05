# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The withheld `paint/procedural_materials` package is replaced, so Lampway starts without import
errors and the paint UI imports. These run the REAL binary (see blender_run.py)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script


def test_startup_logs_no_failed_import():
    run = run_script("print('RESULT {}')")
    assert run.rc == 0, run.out[-2000:]
    assert "Failed to import" not in run.out
    assert "procedural_materials" not in run.out


def test_the_paint_ui_module_imports():
    run = run_script("from mixar.modules.paint.ui import ui\nprint('RESULT {\"ok\": true}')")
    assert run.rc == 0, run.out[-2000:]
    assert run.results == [{"ok": True}]


def test_paint_registers_its_layer_properties():
    run = run_script(
        "import bpy\n"
        "print('RESULT', __import__('json').dumps({'mp': hasattr(bpy.types.Material, 'mp') or hasattr(bpy.types.ShaderNodeTree, 'mp')}))"
    )
    assert run.rc == 0, run.out[-2000:]
    assert run.results == [{"mp": True}]


def test_a_material_script_builds_its_node_group_in_the_sandbox():
    run = run_script(
        "import bpy\n"
        "from mixar.modules.paint.procedural_materials import material_registry as r\n"
        "r.register_material(r.ProceduralMaterial(material_id='demo', name='Demo', category='test', node_group_name='DemoGroup',\n"
        "    script=\"g = bpy.data.node_groups.new('DemoGroup', 'ShaderNodeTree')\\n\"))\n"
        "g = r.get_node_group('demo')\n"
        "print('RESULT', __import__('json').dumps({'name': g.name if g else None, 'custom': r.is_custom_material('demo')}))\n"
    )
    assert run.rc == 0, run.out[-2000:]
    assert run.results == [{"name": "DemoGroup", "custom": True}]


def test_a_material_script_cannot_escape_the_sandbox():
    run = run_script(
        "from mixar.modules.paint.procedural_materials import material_registry as r\n"
        "r.register_material(r.ProceduralMaterial(material_id='bad', name='Bad', category='test', script='x = ().__class__.__bases__'))\n"
        "try:\n"
        "    r.get_node_group('bad'); out = 'ran'\n"
        "except Exception as e:\n"
        "    out = str(e)\n"
        "print('RESULT', __import__('json').dumps({'msg': out}))\n"
    )
    assert run.rc == 0, run.out[-2000:]
    assert "blocked" in run.results[0]["msg"].lower()
