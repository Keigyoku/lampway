# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The native startup login gate is compiled out of Lampway builds.

Source-level pins (the C++ is built by the build crew, not here):
* ``creator.cc`` only calls ``show_startup_dialog()`` when ``LAMPWAY`` is
  undefined, so a build without a keyring token does not exit;
* ``LAMPWAY`` is a CMake option, ON by default in our builds, that defines
  the macro for the creator target;
* the token exchange reads the backend from ``LAMPWAY_BACKEND_URL`` at
  runtime before the baked macro and, under ``LAMPWAY``, accepts plain
  http only for loopback hosts.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
CREATOR = ROOT / "src/source/creator"


def _read(path):
    return path.read_text(encoding="utf-8")


def test_startup_gate_is_compiled_out_for_lampway():
    source = _read(CREATOR / "creator.cc")
    guarded = re.search(r"#ifndef LAMPWAY(.*?)#endif", source, flags=re.S)
    assert guarded, "the gate is not behind #ifndef LAMPWAY"
    assert "show_startup_dialog()" in guarded.group(1)
    assert "// LAMPWAY:" in source
    # The ONLY call site of the gate is the guarded one.
    assert source.count("show_startup_dialog()") == 1


def test_lampway_is_a_cmake_option_defaulting_on():
    overrides = _read(ROOT / "cmake/mixar_overrides.cmake")
    assert re.search(r'set\(LAMPWAY ON CACHE BOOL', overrides)
    cmake = _read(CREATOR / "CMakeLists.txt")
    block = re.search(r"if\(LAMPWAY\)(.*?)endif\(\)", cmake, flags=re.S)
    assert block and "add_definitions(-DLAMPWAY)" in block.group(1)


def test_base_url_comes_from_runtime_config_first():
    source = _read(CREATOR / "creator_startup.cc")
    body = source[source.index("const char* get_mixar_base_url()"):]
    body = body[:body.index("\n}") + 2]
    assert 'getenv("LAMPWAY_BACKEND_URL")' in body
    assert body.index("getenv") < body.index("return MIXAR_BASE_URL")


def test_loopback_http_is_allowed_only_under_lampway():
    source = _read(CREATOR / "creator_startup.cc")
    exchange = source[source.index("static bool exchange_desktop_code"):]
    exchange = exchange[:exchange.index("#ifdef _WIN32")]
    assert "#ifdef LAMPWAY" in exchange
    assert '"http://127.0.0.1' in exchange and '"http://localhost' in exchange
    # The https requirement survives for every non-loopback URL.
    assert 'strncmp(url, "https://", 8)' in exchange
    assert "refusing non-HTTPS URL" in exchange
