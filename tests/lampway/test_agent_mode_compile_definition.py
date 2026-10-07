# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the real agent-bubble target's ON/OFF macro scope with its shipped chip header.

The CMake target definition and chip fitter are real. A small blender_add_lib
fixture omits unrelated Blender sources/dependencies; this is not a Blender build.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
TARGET = 'bf_editor_space_agent_bubble'
OVERLAY = ROOT / 'src/source/blender/editors/space_agent_bubble'


@pytest.mark.parametrize('enabled', [False, True], ids=['OFF', 'ON'])
def test_agent_mode_target_compiles_guarded_chip_only_when_enabled(tmp_path, enabled):
    cmake = shutil.which('cmake')
    compiler = shlex.split(os.environ.get('CXX') or 'c++')
    assert cmake, 'CMake is required for the agent mode target-definition regression'
    assert shutil.which(compiler[0]), 'a C++ compiler is required for the shipped chip-header regression'
    fixture = tmp_path / 'fixture'; fixture.mkdir()
    (fixture / 'chip.cc').write_text('''
#include "agent_ui_chip_fit.hh"
extern "C" int mode_chip_is_compiled() {
#ifdef LAMPWAY
  blender::AgentChipRowInputs inputs;
  inputs.agent_mode_available = true;
  inputs.agent_byoa = true;
  return blender::AGENT_CHIP_SLOT_AGENT_MODE >= 0 && inputs.agent_byoa;
#else
  return 0;
#endif
}
''')
    (fixture / 'caller.cc').write_text('''
extern "C" int mode_chip_is_compiled();
int main() {
#ifdef LAMPWAY
  return 99; // PRIVATE definitions must not reach this linked consumer.
#else
  return mode_chip_is_compiled();
#endif
}
''')
    # Include the production CMakeLists verbatim; only Blender's helper and RNA
    # dependency are supplied by the fixture. A definition on another target,
    # an unconditional definition, or PUBLIC propagation cannot pass this test.
    (fixture / 'CMakeLists.txt').write_text(f'''
cmake_minimum_required(VERSION 3.20)
project(agent_mode_target_scope LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(PROBE_SOURCE "${{CMAKE_CURRENT_SOURCE_DIR}}/chip.cc")
function(blender_add_lib name sources includes system_includes libraries)
  add_library(${{name}} STATIC "${{PROBE_SOURCE}}")
  target_include_directories(${{name}} PRIVATE "{OVERLAY.as_posix()}")
endfunction()
add_custom_target(bf_rna)
include("{(OVERLAY / 'CMakeLists.txt').as_posix()}")
add_executable(mode_chip_caller caller.cc)
target_link_libraries(mode_chip_caller PRIVATE {TARGET})
''')
    build = tmp_path / 'build'
    configured = subprocess.run([cmake, '-S', str(fixture), '-B', str(build),
        '-DCMAKE_CXX_COMPILER=' + compiler[0], '-DLAMPWAY=' + ('ON' if enabled else 'OFF')],
        capture_output=True, text=True)
    assert configured.returncode == 0, configured.stdout + configured.stderr
    commands = json.loads((build / 'compile_commands.json').read_text())
    chip = next(row['command'] for row in commands if Path(row['file']).name == 'chip.cc')
    caller = next(row['command'] for row in commands if Path(row['file']).name == 'caller.cc')
    assert ('-DLAMPWAY' in shlex.split(chip)) == enabled, (
        f'{TARGET} must compile its own guarded mode chip exactly when LAMPWAY is ON; command: {chip}')
    assert '-DLAMPWAY' not in shlex.split(caller), 'the mode-chip definition must remain PRIVATE'
    compiled = subprocess.run([cmake, '--build', str(build), '--parallel', '1'], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run([str(build / 'mode_chip_caller')], capture_output=True, text=True)
    assert result.returncode == int(enabled), result.stderr
