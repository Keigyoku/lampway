# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The file-system gate through the REAL ScriptExecutor in the real binary: one small script per refused class, each
asserting the refusal and that nothing was written outside the sandbox's roots."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

DRIVER = '''
import json, os
from mixar.modules.space_mixie_chat.core.executor import ScriptExecutor
outside = os.environ["LW_OUTSIDE"]
ex = ScriptExecutor()
out = {}
def run(name, src):
    res = ex.execute(src.replace("%OUT%", repr(outside)), push_undo=False)
    out[name] = {"success": res.success, "error": (res.error or "")[:300],
                 "wrote": sorted(os.listdir(outside))}
run("save_blend_outside", "bpy.ops.wm.save_as_mainfile(filepath=%OUT% + '/x.blend', copy=True)")
run("numpy_pickle_load", "import tempfile\\np = tempfile.gettempdir() + '/a.npy'\\nnumpy.save(p, numpy.zeros(1))\\nnumpy.load(p, allow_pickle=True)")
run("numpy_save_outside", "numpy.save(%OUT% + '/a.npy', numpy.zeros(1))")
run("read_outside", "open(%OUT% + '/../secret.txt').read()")
run("python_file_run", "bpy.ops.script.python_file_run(filepath=%OUT% + '/x.py')")
run("write_in_temp_still_works", "import tempfile\\nf = open(tempfile.gettempdir() + '/ok.txt', 'w'); f.write('x'); f.close()\\n__RESULT__ = {'ok': True}")
print("RESULT", json.dumps(out))
'''


@pytest.fixture(scope="module")
def outcomes(tmp_path_factory):
    base = tmp_path_factory.mktemp("gate")
    (base / "outside").mkdir()
    (base / "tmp").mkdir()
    (base / "secret.txt").write_text("not for scripts")
    r = run_script(DRIVER, env={"LW_OUTSIDE": str(base / "outside"), "TMPDIR": str(base / "tmp")})
    assert r.rc == 0 and r.results, r.out[-3000:]
    return r.results[0]


@pytest.mark.parametrize("name", ["save_blend_outside", "numpy_pickle_load", "numpy_save_outside", "read_outside",
                                  "python_file_run"])
def test_the_script_is_refused_and_writes_nothing_outside(outcomes, name):
    got = outcomes[name]
    assert got["success"] is False, f"{name} was not refused: {got}"
    assert got["wrote"] == [], f"{name} wrote outside the roots: {got}"


def test_a_write_inside_the_temp_dir_still_works(outcomes):
    assert outcomes["write_in_temp_still_works"]["success"] is True, outcomes["write_in_temp_still_works"]


# ---- the datablock methods and RNA path properties the gate must also cover (Security #1 residual of the first pass)

DRIVER2 = '''
import json, os
from mixar.modules.space_mixie_chat.core.executor import ScriptExecutor
outside = os.environ["LW_OUTSIDE"]
ex = ScriptExecutor()
out = {}
def run(name, src):
    res = ex.execute(src.replace("%OUT%", repr(outside)), push_undo=False)
    out[name] = {"success": res.success, "error": (res.error or "")[:200], "wrote": sorted(os.listdir(outside))}
run("images_load_outside", "bpy.data.images.load(%OUT% + '/../secret.png')")
run("image_save_via_filepath_raw", "im = bpy.data.images.new('x', 4, 4)\\nim.filepath_raw = %OUT% + '/x.png'\\nim.file_format = 'PNG'\\nim.save()")
run("image_save_render_outside", "im = bpy.data.images.new('y', 4, 4)\\nim.save_render(%OUT% + '/y.png')")
run("libraries_write_outside", "bpy.data.libraries.write(%OUT% + '/z.blend', {bpy.data.objects[0]} if len(bpy.data.objects) else set())")
run("image_reload_from_outside", "im = bpy.data.images.new('w', 4, 4)\\nim.filepath = %OUT% + '/../secret.png'\\nim.reload()")
run("sounds_load_outside", "bpy.data.sounds.load(%OUT% + '/../secret.png')")
print("RESULT", json.dumps(out))
'''


def test_datablock_loads_saves_and_reloads_outside_the_roots_are_refused(tmp_path_factory):
    base = tmp_path_factory.mktemp("gate2")
    (base / "outside").mkdir()
    (base / "tmp").mkdir()
    from PIL import Image
    Image.new("RGB", (4, 4)).save(base / "secret.png")
    r = run_script(DRIVER2, env={"LW_OUTSIDE": str(base / "outside"), "TMPDIR": str(base / "tmp")})
    assert r.rc == 0 and r.results, r.out[-3000:]
    for name, got in r.results[0].items():
        assert got["success"] is False and got["wrote"] == [], f"{name} was not refused: {got}"
        assert "sandbox" in got["error"] or "not available" in got["error"], f"{name} failed for another reason: {got}"
