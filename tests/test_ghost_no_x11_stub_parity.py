# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A Linux build with -DWITH_GHOST_X11=OFF must still link.

``space_agent_bubble.cc`` and ``wm_files.cc`` reference the ``Mixar_*`` window
helpers under ``__linux__`` whether or not the X11 backend is compiled. Without
a definition the link fails (observed: 34 undefined references). The no-X11
stub file therefore defines exactly the symbols the X11 backend defines, so the
two can never drift apart.
"""

import re
from pathlib import Path

GHOST = Path(__file__).resolve().parents[1] / "src" / "intern" / "ghost"
SYM = re.compile(r'extern "C"\s+[\w\s\*]+?\b(Mixar_\w+)\s*\(')


def _symbols(paths):
    out = set()
    for p in paths:
        out |= set(SYM.findall(p.read_text()))
    return out


def test_stub_defines_every_symbol_the_x11_backend_defines():
    x11 = _symbols(sorted((GHOST / "intern").glob("GHOST_MixarX11*.cc")))
    stub_path = GHOST / "intern" / "GHOST_MixarNoX11.cc"
    assert stub_path.is_file(), "no stub file for WITH_GHOST_X11=OFF"
    stub = _symbols([stub_path])
    assert x11, "X11 backend symbols not found - the regex is stale"
    assert x11 - stub == set(), f"undefined without X11: {sorted(x11 - stub)}"
    assert stub - x11 == set(), f"stub defines extras: {sorted(stub - x11)}"


def test_cmake_compiles_the_stub_only_without_x11():
    cmake = (GHOST / "CMakeLists.txt").read_text()
    assert "intern/GHOST_MixarNoX11.cc" in cmake
    i = cmake.index("intern/GHOST_MixarNoX11.cc")
    before = cmake[:i]
    # the nearest preceding conditional must be the else() of WITH_GHOST_X11
    assert before.rindex("else()") > before.rindex("add_definitions(-DWITH_GHOST_X11)")
