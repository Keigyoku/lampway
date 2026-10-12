# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile maintained platform selection and X11 dock suppression boundaries."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'src/source/blender/editors/space_agent_bubble/space_agent_bubble.cc'
GHOST = ROOT / 'src/intern/ghost/intern/GHOST_MixarX11.cc'


def function(source, marker):
    start = source.index(marker)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def compile_run(tmp_path, program, flags=()):
    compiler = shutil.which('g++') or shutil.which('clang++')
    if compiler is None:
        pytest.skip('C++ compiler unavailable: native modal-dock controls UNVERIFIED')
    path = tmp_path / 'docks.cc'
    path.write_text(program)
    executable = tmp_path / 'docks'
    built = subprocess.run([compiler, '-std=c++17', *flags, str(path), '-o', str(executable)],capture_output=True,text=True)
    assert built.returncode == 0, built.stderr
    run = subprocess.run([str(executable)],capture_output=True,text=True)
    assert run.returncode == 0, run.stderr


def test_bubble_and_pill_mark_linux_docks_with_upstream_off_retained(tmp_path):
    source = SOURCE.read_text()
    marker = 'static void agent_bubble_mark_floating_dock('
    if marker in source:
        helper = function(source, marker)
        assert source.count('agent_bubble_mark_floating_dock(win->runtime->ghostwin);') == 3
        assert source.count('agent_bubble_mark_floating_dock(pill_win->runtime->ghostwin);') == 1
        cmake = (SOURCE.parent / 'CMakeLists.txt').read_text()
        assert cmake.index('blender_add_lib(bf_editor_space_agent_bubble') < cmake.index('target_compile_definitions(bf_editor_space_agent_bubble PRIVATE LAMPWAY)')
        assert 'if(LAMPWAY)\n  target_compile_definitions(bf_editor_space_agent_bubble PRIVATE LAMPWAY)\nendif()' in cmake
    else:
        # Compile the actual pre-fix callsite's Apple-only platform selection.
        marker = '#ifdef __APPLE__\n      Mixar_WindowMarkAsFloatingDock(win->runtime->ghostwin);\n#endif'
        assert marker in source
        helper = 'static void agent_bubble_mark_floating_dock(void *handle) {\n' + marker.replace('win->runtime->ghostwin','handle') + '\n}'
    program = '#include <cassert>\nint marks=0;\nvoid Mixar_WindowMarkAsFloatingDock(void *) { ++marks; }\n' + helper + '''
int main() {
  agent_bubble_mark_floating_dock(reinterpret_cast<void *>(1));
#if defined(__APPLE__) || (defined(__linux__) && defined(LAMPWAY))
  assert(marks==1);
#else
  assert(marks==0);
#endif
}
'''
    for flags in (('-DLAMPWAY',), (), ('-U__linux__','-D__APPLE__'), ('-U__linux__','-D_WIN32','-DLAMPWAY')):
        compile_run(tmp_path, program, flags)


def test_registered_x11_docks_hide_during_modal_and_restore_after_last_modal(tmp_path):
    source = GHOST.read_text()
    program = r'''
#include <cassert>
#include <vector>
#include <algorithm>
using Window=unsigned long;
using Atom=unsigned long;
constexpr Atom None=0, XA_ATOM=4; constexpr int False=0, PropModeReplace=0;
struct Display {} display;
struct GHOST_SystemX11 { Display *getXDisplay() { return &display; } } system_data;
struct MixarX11Dock { void *handle; Window xwin; };
std::vector<MixarX11Dock> s_x11_docks;
int s_x11_dock_suppress_depth=0;
std::vector<Window> s_x11_suppressed_docks;
bool mapped=true, alive=true;
GHOST_SystemX11 *mixar_x11_system() { return &system_data; }
void *mixar_x11_window(void *handle) { return alive ? handle : nullptr; }
bool mixar_x11_resolve(void *, Display **d, Window *w) { *d=&display;*w=7;return true; }
bool mixar_x11_is_viewable(Display *, Window) { return mapped; }
void XUnmapWindow(Display *, Window) { mapped=false; }
void XMapWindow(Display *, Window) { mapped=true; }
void XRaiseWindow(Display *, Window) {}
void XFlush(Display *) {}
Atom XInternAtom(Display *, const char *, int) { return 1; }
void XChangeProperty(Display *, Window, Atom, Atom, int, int, unsigned char *, int) {}
'''
    for marker in ('void mixar_x11_dock_register(', 'bool mixar_x11_dock_suppress_if_needed(', 'extern "C" void Mixar_WindowMarkAsFloatingDock(', 'extern "C" void Mixar_FloatingDocksSuppressForModal(', 'extern "C" void Mixar_FloatingDocksRestoreAfterModal('):
        program += function(source, marker) + '\n'
    program += r'''
int main() {
  void *handle=reinterpret_cast<void *>(1);
  Mixar_WindowMarkAsFloatingDock(handle);assert(s_x11_docks.size()==1);
  Mixar_WindowMarkAsFloatingDock(handle);assert(s_x11_docks.size()==1);
  Mixar_FloatingDocksSuppressForModal();assert(!mapped);
  Mixar_FloatingDocksSuppressForModal();assert(!mapped);
  Mixar_FloatingDocksRestoreAfterModal();assert(!mapped);
  Mixar_FloatingDocksRestoreAfterModal();assert(mapped);
  Mixar_FloatingDocksSuppressForModal();mapped=true;
  Mixar_WindowMarkAsFloatingDock(handle);assert(!mapped);
  Mixar_FloatingDocksRestoreAfterModal();assert(mapped);
}
'''
    compile_run(tmp_path, program)
