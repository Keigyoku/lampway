# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Audit F19 (2026-10-06), through the REAL ScriptExecutor in the real binary: writing into a Blender text block is not a file write
(``bpy.data.texts.new(...).write(...)`` was refused, its content judged as a path), and the shared temp directory is not the
sandbox's: a script writes only into its own per-session folder (``tempfile.gettempdir()`` inside the sandbox names it)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

DRIVER = r'''
import json, os, tempfile
from mixar.modules.space_mixie_chat.core.executor import ScriptExecutor
ex = ScriptExecutor()
shared = tempfile.gettempdir()
out = {"shared": os.path.realpath(shared)}
def run(name, src):
    res = ex.execute(src.replace("%SHARED%", repr(shared)), push_undo=False)
    out[name] = {"success": res.success, "error": (res.error or "")[:240], "result": res.return_value}
run("text_write", "t = bpy.data.texts.new('notes')\nt.write('hello from the agent')\n__RESULT__ = t.as_string()")
run("shared_tmp", "f = open(%SHARED% + '/agent_note.txt', 'w')\nf.write('x')\nf.close()")
run("session_tmp", "import tempfile\np = tempfile.gettempdir() + '/ok.txt'\nf = open(p, 'w')\nf.write('x')\nf.close()\n__RESULT__ = p")
print("RESULT", json.dumps(out))
'''


def test_text_blocks_are_writable_and_only_the_session_temp_folder_is():
    r = run_script(DRIVER)
    assert r.rc == 0 and r.results, r.out[-3000:]
    o = r.results[0]
    assert o["text_write"]["success"] is True and o["text_write"]["result"] == "hello from the agent", o["text_write"]
    assert o["shared_tmp"]["success"] is False, o["shared_tmp"]
    s = o["session_tmp"]
    assert s["success"] is True, s
    assert s["result"].startswith(o["shared"] + "/") and Path(s["result"]).parent.as_posix() != o["shared"], s
