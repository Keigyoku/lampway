# SPDX-FileCopyrightText: 2024 Mixar Authors
#
# SPDX-License-Identifier: GPL-2.0-or-later

"""Root-level pytest conftest: pre-stub bpy and related Blender modules so
that tests can be run outside of Blender without import errors."""
import sys
from unittest.mock import MagicMock


def _install_bpy_stubs():
    """Install minimal bpy stub hierarchy into sys.modules."""
    bpy_mock = MagicMock(name='bpy')
    # Register top-level and all known sub-modules that Mixar code imports.
    stub_names = [
        'bpy', 'bpy.types', 'bpy.props', 'bpy.utils', 'bpy.app',
        'bpy.app.handlers', 'bpy.app.timers', 'bpy.context', 'bpy.data',
        'bpy.ops', 'bpy.ops.mixar',
        # The rest of what Blender puts on sys.path. Without these, a module
        # is untestable purely because it imports one of them at module
        # scope, which pushes its logic into source-level assertions that
        # cannot actually run it. Stubbing them costs nothing: nothing here
        # can import the real ones anyway.
        'bpy_extras', 'bpy_extras.view3d_utils', 'bpy_extras.object_utils',
        'mathutils', 'mathutils.geometry',
        'gpu', 'gpu.state', 'gpu.shader', 'gpu.texture',
        'gpu_extras', 'gpu_extras.batch', 'gpu_extras.presets',
        'blf', 'bmesh', 'addon_utils', 'idprop', 'aud',
    ]
    for name in stub_names:
        if name not in sys.modules:
            sys.modules[name] = MagicMock(name=name)
    # @persistent must stay a transparent decorator, or every decorated
    # handler imports as a MagicMock and can never be exercised in tests.
    sys.modules['bpy.app.handlers'].persistent = lambda func: func
    # Ensure top-level 'bpy' is the same mock (not two separate ones)
    if 'bpy' not in sys.modules:
        sys.modules['bpy'] = bpy_mock


_install_bpy_stubs()


def _preload_real_optional_modules():
    """Import the real Pillow/numpy before any test module can stub them.

    ``mixar.modules.testing.mock_bpy`` stubs "third-party modules that may not
    be available" only when they are ABSENT from ``sys.modules``, so whichever
    test imports it first decides whether PIL is real for the whole session.
    Collection order then silently decided whether the image tests ran against
    Pillow or against a MagicMock that hands back empty bytes. Importing the
    real packages here — conftest runs before any test module — makes the mock
    the fallback it was meant to be.
    """
    import importlib

    # ``requests`` too: a dozen test files stub it with a MagicMock when it is absent, and a MagicMock is not a package,
    # so ``from requests.adapters import HTTPAdapter`` in common/api failed for every later file (test_lampway_brand).
    for name in ("numpy", "PIL", "PIL.Image", "PIL.ImageOps", "requests", "requests.adapters", "urllib3", "urllib3.util.retry"):
        try:
            importlib.import_module(name)
        except ImportError:
            pass


_preload_real_optional_modules()


# ---------------------------------------------------------------------------------------------------------- isolation
# No test may read or write the person's real home (a relative test home once copied their real ~/.mixar into the repository). For the whole
# session every home-shaped variable points inside the basetemp; each test starts with them there (tests/lampway/test_test_isolation.py).
import os as _os  # noqa: E402

import pytest as _pytest  # noqa: E402

ISOLATED_VARS = {"HOME": "home", "XDG_CONFIG_HOME": "config", "XDG_DATA_HOME": "data", "XDG_STATE_HOME": "state", "XDG_CACHE_HOME": "cache",
                 "LAMPWAY_HOME": "lampway", "LAMPWAY_LEGACY_HOME": "legacy-mixar", "LAMPWAY_TEST_ROOT": ".."}       # the test root is the whole basetemp


@_pytest.fixture(scope="session", autouse=True)
def _isolated_homes(tmp_path_factory):
    base = tmp_path_factory.getbasetemp() / "isolated-home"
    saved = {k: _os.environ.get(k) for k in ISOLATED_VARS}
    for var, sub in ISOLATED_VARS.items():
        d = (base / sub).resolve()
        d.mkdir(parents=True, exist_ok=True)
        _os.environ[var] = str(d)
    yield base
    for k, v in saved.items():
        if v is None:
            _os.environ.pop(k, None)
        else:
            _os.environ[k] = v


@_pytest.fixture(autouse=True)
def _homes_stay_inside_the_basetemp(_isolated_homes, tmp_path_factory):
    base = str(tmp_path_factory.getbasetemp().resolve())
    for var in ISOLATED_VARS:
        real = _os.path.realpath(_os.environ.get(var, ""))
        assert _os.path.commonpath([real, base]) == base, f"{var}={_os.environ.get(var)!r} points outside the test basetemp {base}"


# ---------------------------------------------------------------------------------------------------- environment
# Tests that need the reference test environment (scripts/lampway/test_env.sh: upstream/ at its pin, the MCP 2.x SDK, jsonschema).
# Outside test_all (a contributor's partial checkout) they SKIP with the reason and the count is printed as one ENV-SKIPPED line;
# inside test_all (LAMPWAY_TEST_ALL=1, the environment already verified) nothing is skipped: a missing piece there is a failure.
import importlib as _importlib  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_ROOT = _Path(__file__).resolve().parent
_ENV_SKIPPED = []
_UPSTREAM_NEEDED = ("tests/lampway/test_lampway_theme.py", "tests/test_open_mixie_shortcut.py")
_UPSTREAM_FILES = ("upstream/release/datafiles/userdef/userdef_default_theme.c", "upstream/scripts/presets/keyconfig/keymap_data/blender_default.py")


def _mcp_sdk_ok() -> bool:
    try:
        return hasattr(_importlib.import_module("mcp"), "Client") and _importlib.import_module("jsonschema") is not None
    except Exception:  # noqa: BLE001
        return False


def _in_test_all() -> bool:
    return _os.environ.get("LAMPWAY_TEST_ALL") == "1"


def pytest_ignore_collect(collection_path, config):
    rel = _Path(str(collection_path)).resolve()
    try:
        rel = rel.relative_to(_ROOT).as_posix()
    except ValueError:
        return None
    if rel.startswith("tests/mcp/") and rel.endswith(".py") and _Path(rel).name.startswith("test_") and not _in_test_all() and not _mcp_sdk_ok():
        _ENV_SKIPPED.append(f"{rel} (needs the MCP 2.x SDK and jsonschema: scripts/lampway/test_env.sh)")
        return True
    return None


def pytest_collection_modifyitems(config, items):
    if _in_test_all() or all((_ROOT / f).is_file() for f in _UPSTREAM_FILES):
        return
    mark = _pytest.mark.skip(reason="needs upstream/ checked out at its pin: run scripts/lampway/test_env.sh")
    for item in items:
        if item.nodeid.split("::")[0] in _UPSTREAM_NEEDED:
            item.add_marker(mark)
            _ENV_SKIPPED.append(item.nodeid + " (needs upstream/)")


def pytest_terminal_summary(terminalreporter):
    if _ENV_SKIPPED:
        terminalreporter.write_line(f"ENV-SKIPPED {len(_ENV_SKIPPED)}: tests that need the reference test environment (scripts/lampway/test_env.sh)")
