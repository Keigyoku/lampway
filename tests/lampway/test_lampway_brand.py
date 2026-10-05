# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""User-facing identity: product name, agent name, website.

One Python constant each (``mixar.config.brand``), mirrored by one C++
header (``BLI_lampway_brand.h``) and one guarded mirror in the header the
chip-fit harness compiles alone. Internal identifiers (``mixar.*``
packages, ``mixie_chat`` ids, keyring names, bundle ids) are NOT renamed.
"""

import ast
import pathlib
import re

from mixar.config import brand

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
MODULES = SRC / "scripts/mixar/modules"
CPP = SRC / "source/blender"


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _define(source, name):
    match = re.search(rf'#\s*define {name} "([^"]*)"', source)
    assert match, name
    return match.group(1)


def _string_literals(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def test_identity_constants():
    assert brand.PRODUCT_NAME == "Lampway"
    assert brand.AGENT_NAME == "Lampway Agent"
    assert brand.REPO_URL == "https://github.com/Keigyoku/lampway" and brand.WEBSITE_URL == "https://lampway.dev"
    assert brand.website_url("/docs") == brand.docs_url() == "https://lampway.dev/docs/"
    assert brand.website_url("docs#connect-ai-apps") == "https://lampway.dev/docs/#connect-ai-apps" == brand.docs_url("connect-ai-apps")
    assert brand.website_url("/bug-report") == "https://lampway.dev/bug-report/" and brand.website_url("/downloads") == "https://lampway.dev/downloads/"
    assert brand.website_url("/legal/privacy-policy") == brand.docs_url("privacy") == "https://lampway.dev/legal/privacy-policy/"
    assert brand.website_url() == brand.WEBSITE_URL


def test_cpp_brand_header_mirrors_python():
    header = _read("src/source/blender/blenlib/BLI_lampway_brand.h")
    assert _define(header, "LAMPWAY_PRODUCT_NAME") == brand.PRODUCT_NAME
    assert _define(header, "LAMPWAY_AGENT_NAME") == brand.AGENT_NAME
    assert _define(header, "LAMPWAY_WEBSITE_URL") == brand.WEBSITE_URL


def test_chip_fit_header_mirrors_the_agent_name():
    """The harness compiles this header alone, so it carries its own guarded
    copy of the define; the two must agree or the chip is measured for one
    label and painted with another."""
    source = _read("src/source/blender/editors/space_agent_bubble/agent_ui_chip_fit.hh")
    assert _define(source, "LAMPWAY_AGENT_NAME") == brand.AGENT_NAME
    assert "#ifndef LAMPWAY_AGENT_NAME" in source
    assert '"Mixie"' not in source


def test_native_agent_surfaces_use_the_agent_name():
    for rel in (
        "editors/space_agent_bubble/agent_ui_controls_paint.cc",
        "editors/space_agent_bubble/agent_ui_draw.cc",
        "editors/space_mixie_chat/mixie_chat_rules_rows.cc",
    ):
        source = (CPP / rel).read_text(encoding="utf-8")
        assert "LAMPWAY_AGENT_NAME" in source, rel
        # String literals only: identifiers such as `MixieCatPose` are internal.
        code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        literals = re.findall(r'"[^"\n]*\bMixie\b[^"\n]*"', code)
        assert literals == [], (rel, literals)


def test_window_title_and_platform_dialogs_use_the_product_name():
    window = (CPP / "windowmanager/intern/wm_window.cc").read_text(encoding="utf-8")
    assert "LAMPWAY_PRODUCT_NAME" in window
    assert '"Mixar"' not in window and "- Mixar" not in window
    support = (CPP / "windowmanager/intern/wm_platform_support.cc").read_text(encoding="utf-8")
    assert "LAMPWAY_PRODUCT_NAME" in support
    assert "Mixar" not in support.split("namespace blender", 1)[1]


def test_profile_card_links_to_our_website():
    source = (CPP / "editors/interface/interface_mixar_profile_card.cc").read_text(encoding="utf-8")
    assert 'LAMPWAY_WEBSITE_URL "/docs"' in source
    assert 'LAMPWAY_WEBSITE_URL "/bug-report"' in source


def test_model_chip_fallback_is_the_agent_name():
    from mixar.modules.byok.core import model_menu
    assert model_menu.RESET_TEXT == brand.AGENT_NAME


_AGENT_FILES = (
    "agent_bubble/ui/operators/open_mixie_op.py",
    "space_mixie_chat/ui/operators/quick_prompt_ops.py",
    "space_mixie_chat/ui/operators/auth_ops.py",
    "space_mixie_chat/ui/operators/session_ops.py",
    "space_mixie_chat/ui/operators/rules_ops.py",
    "space_mixie_chat/core/credits_notice.py",
    "space_mixie_chat/ui/properties/chat_props.py",
    "context_folder/ui/menus/attach_menu.py",
    "onboarding/core/tour/script.py",
    "byok/core/model_menu.py",
)


def test_user_facing_python_strings_use_the_agent_name():
    for rel in _AGENT_FILES:
        path = MODULES / rel
        source = path.read_text(encoding="utf-8")
        assert "AGENT_NAME" in source, rel
        offenders = [s for s in _string_literals(path) if re.search(r"\bMixie\b", s)]
        assert offenders == [], (rel, offenders)


_PRODUCT_FILES = (
    "space_mixie_chat/ui/login_panel.py",
    "space_mixie_chat/ui/topbar.py",
    "common/ui/panels/privacy_panel.py",
    "common/ui/panels/theme_panel.py",
    "common/ui/operators/theme_ops.py",
)


def test_user_facing_python_strings_use_the_product_name():
    for rel in _PRODUCT_FILES:
        path = MODULES / rel
        source = path.read_text(encoding="utf-8")
        assert "PRODUCT_NAME" in source, rel
        offenders = [s for s in _string_literals(path) if re.search(r"\bMixar\b", s)]
        assert offenders == [], (rel, offenders)
    analytics = (SRC / "scripts/mixar/bootstrap/analytics_module.py").read_text(encoding="utf-8")
    assert "PRODUCT_NAME" in analytics and "improve Mixar" not in analytics


def test_web_links_go_through_the_website_constant():
    from mixar.modules.common.notifications import constants as notifications
    from mixar.modules.common.updates import constants as updates
    from mixar.modules.mcp_bridge import constants as mcp
    from mixar.modules.common.job_queue.ui.lists import queue_uilist

    assert not hasattr(notifications, "CREDITS_BANNER_REFERRAL_URL") and not hasattr(notifications, "CREDITS_BANNER_CREATOR_URL")  # Mixar commerce, deleted
    assert updates.DOWNLOADS_PAGE_URL == brand.website_url("/downloads")
    assert mcp.SETUP_GUIDE_URL == brand.website_url("/docs#connect-ai-apps")
    assert queue_uilist._BUG_REPORT_URL == brand.website_url("/bug-report")


def test_help_and_app_menus_are_lampway():
    topbar = _read("src/scripts/startup/bl_ui/space_topbar.py")
    help_menu = topbar[topbar.index("class TOPBAR_MT_help"):topbar.index("class TOPBAR_MT_file_context_menu")]
    assert "youtube.com/@Mixar3D" not in help_menu
    assert '"/creator-program"' not in help_menu and '"/docs"' in help_menu and '"/bug-report"' in help_menu
    app_menu = topbar[topbar.index("class TOPBAR_MT_blender"):topbar.index("class TOPBAR_MT_blender", topbar.index("class TOPBAR_MT_blender") + 1)]
    assert 'bl_label = "Lampway"' in app_menu
    assert 'text="Mixar"' not in topbar


def test_desktop_identity_files_name_lampway():
    desktop = _read("src/release/freedesktop/mixar.desktop")
    assert "Name=Lampway" in desktop
    metainfo = _read("src/release/freedesktop/org.mixar.Mixar.metainfo.xml")
    assert "<name>Lampway</name>" in metainfo and "mixar.app" not in metainfo
    plist = _read("src/release/darwin/Mixar.app/Contents/Info.plist")
    assert "Lampway File" in plist and "Mixar File" not in plist
    rc = _read("src/release/windows/icons/winmixar.rc")
    assert '"ProductName", "Lampway"' in rc and '"Mixar"' not in rc
