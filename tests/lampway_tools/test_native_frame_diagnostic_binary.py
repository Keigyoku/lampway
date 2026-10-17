# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual Blender read-only diagnostic on the complete native identity graph."""
from pathlib import Path

from blender_run import run_script
from test_native_complete_topology import PRE, BUILD

SCRIPT = Path(__file__).parents[2] / "scripts/lampway/read_native_frame_diagnostics.py"


def test_native_diagnostic_retains_scene_and_records_loaded_source(tmp_path):
    r = run_script(PRE + BUILD + "DIAG_SCRIPT=" + repr(str(SCRIPT)) + r'''
import importlib.util
from mixar.modules.lampway_tools.features import rig_tools as RT, normalize_rigged as NR
spec=importlib.util.spec_from_file_location('native_diag',DIAG_SCRIPT)
diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)
before={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones}
keys=list(arm.keys());objects=sorted(o.name for o in bpy.data.objects)
receipt=diag.collect(bpy,RT,NR,arm.name)
path=os.path.join(root,'private-frames.json');diag.write_exclusive(path,receipt)
res({'schema':receipt['schema'],'count':receipt['bone_count'],
     'source':{k:len(v['sha256']) for k,v in receipt['loaded_modules'].items()},
     'function':receipt['bones_function_source'].startswith('def _bones('),
     'json_matches':json.load(open(path))==receipt,
     'unchanged':before=={b.name:[list(row) for row in b.matrix_local] for b in arm.data.bones}
                 and keys==list(arm.keys()) and objects==sorted(o.name for o in bpy.data.objects)})
''', env={"LW_KEEP_ROOT": str(tmp_path)}, timeout=300)
    assert r.rc == 0, r.out[-2000:]
    result = r.results[-1]
    assert result["schema"] == "lampway.native-frame-diagnostic/1" and result["count"] == 342
    assert result["source"] == {"rig_tools": 64, "normalize_rigged": 64, "rig_core": 64}
    assert result["function"] and result["json_matches"] and result["unchanged"]
