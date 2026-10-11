# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile the maintained readback dispatcher with controlled GPU boundaries.

This verifies routing/context restoration, not the full native GPU build. The
isolated real operator pixel regression still needs the rebuilt application.
"""
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
DRAW = ROOT / 'src/source/blender/windowmanager/intern/wm_draw.cc'
CMAKE = ROOT / 'src/source/blender/windowmanager/CMakeLists.txt'


def dispatcher(source):
    start = source.index('uint8_t *WM_window_pixels_read(bContext *C, wmWindow *win, int r_size[2])')
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


@pytest.mark.parametrize('fork', [True, False])
def test_compiled_window_readback_routes_and_restores_context(tmp_path, fork):
    compiler = shutil.which('g++') or shutil.which('clang++')
    assert compiler, 'a C++ compiler is required to verify the native dispatcher'
    harness = r'''
#include <cstdint>
#include <cassert>
struct bContext {};
struct wmWindow {};
struct wmWindowManager {};
static wmWindowManager manager;
static uint8_t front[4], offscreen[4];
static bool capability, switch_context, fail_offscreen;
static int front_reads, offscreen_reads, pushes, pops;
constexpr int WM_CAPABILITY_GPU_FRONT_BUFFER_READ = 1;
int WM_capabilities_flag() { return capability ? 1 : 0; }
wmWindowManager *CTX_wm_manager(bContext *) { return &manager; }
bool Mixar_window_gpu_context_push(const wmWindowManager *, wmWindow *) {
  pushes++; return switch_context;
}
void Mixar_window_gpu_context_pop(const wmWindowManager *) { pops++; }
uint8_t *WM_window_pixels_read_from_frontbuffer(const wmWindowManager *, wmWindow *, int size[2]) {
  front_reads++; size[0] = 3; size[1] = 2; return front;
}
uint8_t *WM_window_pixels_read_from_offscreen(bContext *, wmWindow *, int size[2]) {
  offscreen_reads++; size[0] = 3; size[1] = 2;
  return fail_offscreen ? nullptr : offscreen;
}
''' + dispatcher(DRAW.read_text()) + r'''
int main() {
  bContext context; wmWindow window;
  for (bool cap : {false, true}) {
    for (bool changed : {false, true}) {
      for (bool failed : {false, true}) {
        capability = cap; switch_context = changed; fail_offscreen = failed;
        front_reads = offscreen_reads = pushes = pops = 0;
        int size[2] = {};
        uint8_t *pixels = WM_window_pixels_read(&context, &window, size);
#ifdef LAMPWAY
        assert(front_reads == 0 && offscreen_reads == 1);
        assert(pushes == 1 && pops == int(changed));
        assert(pixels == (failed ? nullptr : offscreen));
#else
        assert(front_reads == int(cap) && offscreen_reads == int(!cap));
        assert(pushes == 0 && pops == 0);
        assert(pixels == (cap ? front : failed ? nullptr : offscreen));
#endif
        assert(size[0] == 3 && size[1] == 2);
      }
    }
  }
}
'''
    harness = '#include <initializer_list>\n' + harness
    source = tmp_path / 'readback.cc'
    source.write_text(harness)
    executable = tmp_path / 'readback'
    compile_args = [compiler, '-std=c++17', str(source), '-o', str(executable)]
    if fork:
        compile_args.insert(1, '-DLAMPWAY')
    compiled = subprocess.run(compile_args, capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    run = subprocess.run([str(executable)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr


def assert_target_definition(source):
    source = re.sub(r'#[^\n]*', '', source)
    target = source.index('blender_add_lib_nolist(bf_windowmanager')
    owned = re.search(r'if\(LAMPWAY\)\s*target_compile_definitions\(bf_windowmanager PRIVATE LAMPWAY\)\s*endif\(\)', source)
    assert owned, 'readback fork branch must compile only in Lampway windowmanager'
    assert owned.start() > target
    assert len(re.findall(r'target_compile_definitions\(bf_windowmanager\s+[^)]*\bLAMPWAY\b[^)]*\)', source)) == 1


def test_windowmanager_target_owns_the_fork_definition():
    assert_target_definition(CMAKE.read_text())
    assert '#  include "WM_mixar.hh"' in DRAW.read_text(), 'context helpers require their public declarations'


@pytest.mark.parametrize('corruption', ['missing', 'wrong_target', 'public', 'unconditional', 'before_target'])
def test_windowmanager_definition_rejects_broken_scope(corruption):
    target = 'blender_add_lib_nolist(bf_windowmanager "${SRC}" "${INC}" "${INC_SYS}" "${LIB}")\n'
    guarded = 'if(LAMPWAY)\n  target_compile_definitions(bf_windowmanager PRIVATE LAMPWAY)\nendif()\n'
    source = target + guarded
    if corruption == 'missing':
        source = target
    elif corruption == 'wrong_target':
        source = source.replace('target_compile_definitions(bf_windowmanager', 'target_compile_definitions(mixar')
    elif corruption == 'public':
        source = source.replace('PRIVATE', 'PUBLIC')
    elif corruption == 'unconditional':
        source += 'target_compile_definitions(bf_windowmanager PRIVATE LAMPWAY)\n'
    else:
        source = guarded + target
    with pytest.raises(AssertionError):
        assert_target_definition(source)
