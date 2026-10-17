# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Install paths must not carry a version.

Restart-to-update assumes a release replaces the previous one. A
version-stamped install directory (Windows) or bundle name (macOS) breaks
that quietly: the new build lands beside the old one and the user keeps
launching whichever shortcut they had. These are cheap source-level
guards on the two places that decide those names.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGING_CMAKE = ROOT / "src" / "build_files" / "cmake" / "packaging.cmake"
WIX_TEMPLATE = ROOT / "src" / "release" / "windows" / "installer_wix" / "WIX.template"
CREATOR_CMAKE = ROOT / "src" / "source" / "creator" / "CMakeLists.txt"


def _cmake() -> str:
    return PACKAGING_CMAKE.read_text(encoding="utf-8")


def _windows_block() -> str:
    """The if(WIN32) section — an earlier generic assignment is overridden."""
    block = _cmake()
    return block[block.index("if(WIN32)"):]


def test_windows_install_directory_has_no_version():
    match = re.search(
        r'set\(CPACK_PACKAGE_INSTALL_DIRECTORY\s+"([^"]*)"\)', _windows_block(),
    )
    assert match, "CPACK_PACKAGE_INSTALL_DIRECTORY not found"
    assert match.group(1) == "Lampway"
    assert "MAJOR_VERSION" not in match.group(1)


def test_windows_upgrade_code_is_version_independent():
    """The UpgradeCode is the product identity — deriving it from a version
    turns every minor release into a side-by-side install."""
    block = _cmake()
    guid_call = block[block.index("string(UUID CPACK_WIX_UPGRADE_GUID"):]
    guid_call = guid_call[:guid_call.index(")")]

    assert 'NAME "Lampway"' in guid_call
    assert "VERSION" not in guid_call


def test_lampway_installs_never_remove_a_mixar_install():
    """Lampway has no installs made under an older scheme, and a Mixar install is somebody else's product: no legacy upgrade rows are generated."""
    block = _cmake()

    assert "LEGACY_UPGRADE" not in block and "OnlyDetect" not in block and "Mixar/Mixar" not in block
    assert "LEGACY_UPGRADE_MARKER" not in WIX_TEMPLATE.read_text(encoding="utf-8")


def test_macos_dmg_bundle_name_has_no_version():
    # CPack packages the installed bundle; there is no separate package.sh.
    assert re.search(r'if\(APPLE\)\s+set\(CPACK_GENERATOR "DragNDrop"\)', _cmake())
    source = CREATOR_CMAKE.read_text(encoding="utf-8")
    mac = source[source.index("elseif(APPLE)", source.index("# Install Targets (Platform Specific)")):]
    assert "set_target_properties(mixar PROPERTIES OUTPUT_NAME Mixar)" in mac
    destinations = re.findall(r'DESTINATION\s+"([^"\n]*Mixar\.app[^"\n]*)"', mac)
    assert destinations, "the DMG must contain the installed application bundle"
    assert all(path.startswith(("Mixar.app/", "./Mixar.app/")) for path in destinations)
    assert all("VERSION" not in path for path in destinations)
