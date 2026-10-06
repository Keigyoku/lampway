# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 14: one monoline icon set for privacy, money and agents (I1-I6), generated from one sheet."""

import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "scripts/dev/brand_art"
SHEET = ART / "icons/lampway_icons.svg"
ICONS_SVG = ROOT / "src/release/datafiles/icons_svg"
UI_ICONS = ROOT / "src/source/blender/editors/include/UI_icons.hh"
CMAKE = ROOT / "src/source/blender/editors/datafiles/CMakeLists.txt"
PREVIEWS = ROOT / "src/scripts/mixar/modules/common/lampway_icons"
NS = "{http://www.w3.org/2000/svg}"

# Contract 14 section 5 (the native set), section 14 (the cue glyphs) and the redrawn Generate.
REQUIRED = ["lamp", "wire", "coin", "cap", "receipt", "route", "shield", "shield-half", "shield-open", "shield-q", "hand",
            "spark", "worker", "pane", "compare", "vault", "gate", "node-lit", "node-half", "node",
            *[f"meter-{n}" for n in range(11)], "meter-near", "meter-over", "wire-dot-a", "wire-dot-b",
            "agent-idle", "agent-working", "agent-unread", "agent-blocked", "agent-paused", "agent-done", "agent-failed",
            "generate"]


def generator():
    sys.path.insert(0, str(ART))
    try:
        import lampway_icons
    finally:
        sys.path.remove(str(ART))
    return lampway_icons


def symbols():
    return {s.get("id"): s for s in ET.parse(SHEET).getroot().iter(NS + "symbol")}


def enums():
    return set(re.findall(r"DEF_ICON\w*\((LAMPWAY_\w+)\)", UI_ICONS.read_text(encoding="utf-8")))


def test_sheet_construction():
    """I3: 16 px viewBox, no gradient, raster or text, fills only currentColor or none."""
    bad = []
    for sid, sym in symbols().items():
        if sym.get("viewBox") != "0 0 16 16":
            bad.append((sid, "viewBox", sym.get("viewBox")))
        for el in sym.iter():
            tag = el.tag.replace(NS, "")
            if tag in ("linearGradient", "radialGradient", "image", "text"):
                bad.append((sid, tag))
            if el.get("fill") not in (None, "none", "currentColor"):
                bad.append((sid, "fill", el.get("fill")))
    assert not bad, bad


def test_sheet_has_every_required_icon():
    """I2."""
    assert sorted(set(REQUIRED) - set(symbols())) == []


def test_native_set_is_complete():
    """I4: every LAMPWAY icon has its SVG, its CMake line and its enum, and every Lampway SVG has an enum."""
    cmake = CMAKE.read_text(encoding="utf-8")
    native = generator().NATIVE
    assert set(native) <= set(REQUIRED)
    want = {f"LAMPWAY_{generator().native_name(n).upper()}" for n in native}
    assert enums() == want, sorted(enums() ^ want)
    for sid in native:
        name = "lampway_" + generator().native_name(sid)
        assert (ICONS_SVG / f"{name}.svg").is_file(), name
        assert re.search(rf"^\s+{name}$", cmake, re.M), f"{name} not compiled"
    for svg in ICONS_SVG.glob("lampway_*.svg"):
        assert f"LAMPWAY_{svg.stem[len('lampway_'):].upper()}" in enums(), svg.name


def test_retired_icons_are_gone():
    """I5: no sparkle, no Mixar credit badges, no reference to their enums; Generate is not a wand."""
    assert not (ICONS_SVG / "sparkle.svg").exists()
    assert not list(ICONS_SVG.glob("credits_*.svg"))
    header = UI_ICONS.read_text(encoding="utf-8")
    assert not re.search(r"DEF_ICON\w*\((SPARKLE|CREDITS_\w+)\)", header)
    offenders = []
    for path in list((ROOT / "src/source").rglob("*.c*")) + list((ROOT / "src/source").rglob("*.h*")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"ICON_(SPARKLE|CREDITS_\w+)\b", text):
            offenders.append(str(path.relative_to(ROOT)))
    for path in (ROOT / "src/scripts").rglob("*.py"):
        if re.search(r"icon\s*=\s*['\"](SPARKLE|CREDITS_\w+)['\"]", path.read_text(encoding="utf-8", errors="replace")):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
    assert (ICONS_SVG / "generate.svg").read_text(encoding="utf-8") == generator().native_svg(symbols()["generate"])


def test_every_lampway_icon_the_code_uses_exists():
    """I1 on the code: a Lampway icon named in Python or C++ is one the build has."""
    used = set()
    for path in (ROOT / "src/scripts").rglob("*.py"):
        used |= set(re.findall(r"icon\w*\s*=\s*['\"](LAMPWAY_[A-Z0-9_]+)['\"]",
                               path.read_text(encoding="utf-8", errors="replace")))
    for path in (ROOT / "src/source").rglob("*.cc"):
        used |= set(re.findall(r"\bICON_(LAMPWAY_[A-Z0-9_]+)", path.read_text(encoding="utf-8", errors="replace")))
    assert sorted(used - enums()) == []


def test_lampway_icons_are_in_the_svg_range():
    """``init_internal_icons`` registers SVG icons only below ``DEF_ICON_BLANK(LAST_SVG_ITEM)``; an icon defined after it
    has an enum value and no icon, and draws nothing ("no icon for icon ID")."""
    text = UI_ICONS.read_text(encoding="utf-8")
    boundary = text.index("DEF_ICON_BLANK(LAST_SVG_ITEM)")
    found = [m.start() for m in re.finditer(r"^DEF_ICON\(LAMPWAY_", text, re.M)]
    assert found and max(found) < boundary, "Lampway icons sit after LAST_SVG_ITEM and are never loaded"


def test_generated_files_are_committed(tmp_path):
    done = subprocess.run([sys.executable, str(ART / "lampway_icons.py"), "--out", str(tmp_path)], capture_output=True,
                          text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    for rel in ("src/source/blender/editors/include/UI_icons.hh",
                "src/source/blender/editors/datafiles/CMakeLists.txt", "src/release/datafiles/icons_svg/generate.svg"):
        assert (tmp_path / rel).read_bytes() == (ROOT / rel).read_bytes(), rel
    for svg in (tmp_path / "src/release/datafiles/icons_svg").glob("lampway_*.svg"):
        assert svg.read_bytes() == (ICONS_SVG / svg.name).read_bytes(), svg.name


def test_preview_icons_follow_the_theme(monkeypatch):
    """A Python surface gets the cue glyph in the current theme's colours: Night's set on a dark canvas, Paper's on a
    light one; every native glyph has both, the agent states also at 16 px; an unknown name says how to make it."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from mixar.modules.common import lampway_icons
    dark = SimpleNamespace(user_interface=SimpleNamespace(mixar_canvas=(0.05, 0.06, 0.09, 1)))
    light = SimpleNamespace(user_interface=SimpleNamespace(mixar_canvas=(0.96, 0.94, 0.89, 1)))
    assert (lampway_icons.theme_set(dark), lampway_icons.theme_set(light)) == ("night", "paper")
    gen = generator()
    for theme in ("night", "paper"):
        for sid in gen.NATIVE:
            lampway_icons.path(gen.native_name(sid), 32, theme)
            if sid.startswith("agent-"):
                lampway_icons.path(gen.native_name(sid), 16, theme)
    with pytest.raises(KeyError, match="lampway_icons.py"):
        lampway_icons.path("sparkle")
    loaded = {}

    class Collection(dict):
        def load(self, key, file, kind):
            loaded[key] = file
            self[key] = SimpleNamespace(icon_id=len(loaded))

    import bpy
    previews = SimpleNamespace(new=Collection, remove=MagicMock())
    monkeypatch.setitem(sys.modules, "bpy.utils.previews", previews)
    monkeypatch.setattr(bpy.utils, "previews", previews, raising=False)
    monkeypatch.setattr(lampway_icons, "_collections", {})
    assert lampway_icons.icon_id("agent_working", theme=light) == 1
    assert loaded == {"agent_working": str(PREVIEWS / "paper" / "agent_working.png")}


@pytest.mark.skipif(shutil.which("magick") is None, reason="the previews are rasterised with ImageMagick (librsvg)")
def test_previews_match_natives(tmp_path):
    """I6: each preview's alpha mask is the native SVG rendered at 32 px, within 2 percent of pixels."""
    from PIL import Image
    gen = generator()
    for theme in ("night", "paper"):
        for sid in gen.NATIVE:
            name = gen.native_name(sid)
            preview = Image.open(PREVIEWS / theme / f"{name}.png").convert("RGBA")
            native = tmp_path / f"{name}.png"
            sized = tmp_path / f"{name}.svg"
            sized.write_text((ICONS_SVG / f"lampway_{name}.svg").read_text(encoding="utf-8").replace(
                'width="1600" height="1600"', 'width="32" height="32"'), encoding="utf-8")
            subprocess.run(["magick", "-background", "none", str(sized), f"PNG32:{native}"], check=True)
            mask = Image.open(native).convert("RGBA")
            differ = sum(1 for a, b in zip(preview.getchannel("A").getdata(), mask.getchannel("A").getdata())
                         if abs(a - b) > 32)
            assert differ <= 0.02 * 32 * 32, (theme, name, differ)
