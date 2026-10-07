# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 02: the splash is the site's picture in the brand faces from the repo, shows the version once, and its menu
reads cached state only (recent files, the way in, and four glance cues for the setup)."""

import importlib.util
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "scripts/dev/lampway_placeholder_art.py"
SPLASH_PNG = ROOT / "src/release/datafiles/splash.png"
SPLASH_CC = ROOT / "src/source/blender/windowmanager/intern/wm_splash_screen.cc"
needs_tools = pytest.mark.skipif(shutil.which("magick") is None or shutil.which("fc-match") is None,
                                 reason="the splash is rendered with ImageMagick (librsvg) and fontconfig")


def art():
    spec = importlib.util.spec_from_file_location("lampway_placeholder_art", ART)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@needs_tools
def test_splash_art_uses_the_vendored_faces():
    """Every face the art names resolves to a font in the repo, by exact family; a face the repo lacks is refused
    (fontconfig would otherwise substitute one silently)."""
    tool = art()
    found = tool.splash_faces((tool.BRAND_DIR / "splash_v2.svg").read_text(encoding="utf-8"))
    assert found and {f for f, _file in found} == {"Fraunces", "IBM Plex Mono", "IBM Plex Sans"}
    assert all(Path(file).parent == tool.BRAND_DIR / "fonts" for _f, file in found)
    with pytest.raises(SystemExit, match="Comic Sans"):
        tool.splash_faces('<text font-family="Comic Sans">x</text>')


@needs_tools
def test_the_shipped_splash_is_the_render(tmp_path):
    from PIL import Image, ImageChops
    tool = art()
    fresh = tool.render_splash()
    shipped = Image.open(SPLASH_PNG).convert("RGBA")
    assert fresh.size == shipped.size == (1672, 941)
    diff = ImageChops.difference(fresh, shipped).convert("L").point(lambda v: 255 if v > 6 else 0)
    assert diff.histogram()[255] <= 0.01 * 1672 * 941, "splash.png is not the render of splash_v2.svg"
    # every text line is drawn in its face: its ink spans the width the face measures (tofu or a missing line does not)
    svg = (tool.BRAND_DIR / "splash_v2.svg").read_text(encoding="utf-8").replace("v0.1.0", f"v{tool.version()}")
    for x, y, family, size, weight, _fill, spacing, content in tool._texts(svg):
        band = shipped.crop((int(x) - 4, int(y - size), 1672, int(y + size * 0.35))).convert("L")
        background = band.getpixel((band.width - 2, band.height // 2))
        ink = band.point(lambda v, b=background: 255 if abs(v - b) > 40 else 0).getbbox()
        expected = tool._face(family, size, weight).getlength(content) + spacing * len(content)
        assert ink and abs((ink[2] - ink[0]) - expected) <= 0.03 * expected + 4, (content, ink, expected)


def test_splash_shows_one_version():
    """The art carries the version line; the C++ label over it is gone (it drew the version twice)."""
    assert "BKE_blender_version_string()" not in SPLASH_CC.read_text(encoding="utf-8").split(
        "static ui::Block *wm_block_splash_create", 1)[1].split("\n}\n", 1)[0]


class Recorder:
    def __init__(self, log=None):
        self.log = [] if log is None else log
        self.operator_context = self.emboss = None
        self.scale_y = 1.0

    def __getattr__(self, name):
        if name in ("row", "column", "split", "box"):
            return lambda *a, **k: Recorder(self.log)
        raise AttributeError(name)

    def label(self, text="", **kw):
        self.log.append(("label", text, kw.get("icon")))

    def operator(self, idname, text="", **kw):
        self.log.append(("op", idname, text))
        return SimpleNamespace()

    def menu(self, idname, text="", **kw):
        self.log.append(("menu", idname, text))

    def separator(self, **kw):
        pass

    def texts(self):
        return [e[2] if e[0] in ("op", "menu") else e[1] for e in self.log]


@pytest.fixture
def splash(monkeypatch, tmp_path):
    import bpy
    monkeypatch.setattr(sys.modules["bpy.types"], "Menu", object, raising=False)
    monkeypatch.delitem(sys.modules, "mixar.bootstrap.splash_menu", raising=False)
    import importlib
    splash_menu = importlib.import_module("mixar.bootstrap.splash_menu")  # not `from mixar.bootstrap import`: the package keeps a stale attribute
    recent = tmp_path / "recent-files.txt"
    files = []
    for name in ("lantern.blend", "gone.blend", "bench.blend", "rig.blend", "fifth.blend", "sixth.blend"):
        path = tmp_path / name
        if name != "gone.blend":
            path.write_bytes(b"BLENDER")
        files.append(str(path))
    recent.write_text("\n".join(files) + "\n", encoding="utf-8")
    monkeypatch.setattr(splash_menu, "_recent_files_path", lambda: str(recent))
    return splash_menu


def test_splash_menu_draw_is_pure_and_names_a_stopped_server(splash, monkeypatch):
    import urllib.request
    from mixar.modules.lampway_tools import statusbar_state as S
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network in draw")))
    S.reset()
    S.fail("the server could not be reached")
    layout = Recorder()
    splash.WM_MT_splash.draw(SimpleNamespace(layout=layout), SimpleNamespace())
    texts = layout.texts()
    assert "Lampway's server is not running" in texts
    assert [t for t in texts if t.endswith(".blend")] == ["lantern.blend", "bench.blend", "rig.blend", "fifth.blend"], \
        "four recent files, the missing one skipped"
    assert {"Start in Lamplight", "Start in Workshop", "New scene", "Recover last session"} <= set(texts)
    assert "Help" in texts


def test_splash_setup_cues_read_the_cache(splash):
    from mixar.modules.lampway_tools import statusbar_state as S
    S.update(egress={"routes": [{"id": "openrouter", "label": "OpenRouter", "enabled": True},
                                {"id": "fal", "label": "fal.ai", "enabled": True}],
                     "indicator": {"over_the_wire": False, "active": []}},
             spend={"scope": "day", "providers": [{"provider": "openrouter", "unit": "USD", "spent": 0.31,
                                                       "day_cap": 5.0}]},
             studio={"approvals": []})
    layout = Recorder()
    splash.WM_MT_splash.draw(SimpleNamespace(layout=layout), SimpleNamespace())
    texts = layout.texts()
    assert "server on this machine" in texts and "2 routes open" in texts and "spent today $0.31 of $5.00" in texts
    S.reset()
