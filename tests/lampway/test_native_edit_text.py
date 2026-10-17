# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile the maintained text selector; these controls do not build Blender."""
from pathlib import Path
import shutil
import subprocess

SOURCE = Path(__file__).resolve().parents[2] / 'src/source/blender/editors/interface/interface_qa_inspect.cc'


def selector():
    source = SOURCE.read_text()
    marker = 'static std::string qa_button_visible_text('
    if marker not in source:
        # Exercise the pre-fix maintained decision, so RED is a behavior failure.
        decision = 'const std::string &text = but->drawstr.empty() ? but->str : but->drawstr;'
        assert decision in source
        return 'static std::string qa_button_visible_text(const ui::Button *but, bool secret) {' + decision + 'return secret ? std::string() : text;}'
    start = source.index(marker)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    assert 'json_str(out, "text", qa_button_visible_text(but, secret));' in source
    return source[start:end]


def test_active_edit_buffer_and_secret_redaction(tmp_path):
    compiler = shutil.which('g++') or shutil.which('clang++')
    assert compiler, 'C++ compiler required for native observation controls'
    program = r'''
#include <string>
#include <cassert>
namespace ui { struct Button { std::string str, drawstr; const char *editstr = nullptr; }; }
''' + selector() + r'''
int main() {
  ui::Button button{"committed", "drawn", "helmet-suite.mixar"};
#ifdef LAMPWAY
  assert(qa_button_visible_text(&button,false)=="helmet-suite.mixar");
  button.editstr=""; assert(qa_button_visible_text(&button,false).empty());
  button.editstr="héłmet.mixar"; assert(qa_button_visible_text(&button,false)=="héłmet.mixar");
#else
  assert(qa_button_visible_text(&button,false)=="drawn");
#endif
  assert(qa_button_visible_text(&button,true).empty());
  button.editstr=nullptr; assert(qa_button_visible_text(&button,false)=="drawn");
  button.drawstr.clear(); assert(qa_button_visible_text(&button,false)=="committed");
  assert(qa_button_visible_text(&button,true).empty());
}
'''
    path = tmp_path / 'text.cc'
    path.write_text(program)
    for enabled in (True, False):
        executable = tmp_path / ('on' if enabled else 'off')
        command = [compiler, '-std=c++17', str(path), '-o', str(executable)]
        if enabled:
            command.append('-DLAMPWAY')
        built = subprocess.run(command, capture_output=True, text=True)
        assert built.returncode == 0, built.stderr
        run = subprocess.run([str(executable)], capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
