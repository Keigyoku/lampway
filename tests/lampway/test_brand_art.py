# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The shipped art is Lampway's identity (scripts/dev/brand_art), not the placeholder lamp (rebrand defect 7).

``scripts/dev/lampway_placeholder_art.py`` writes every datafile the build embeds. Its splash must be the splash concept of ``scripts/dev/brand_art`` (Night
background, the lantern mark, the wordmark, the approved attribution sentence, the product version), and its icons the app-icon tile, in the brand's
Flame colour #EDB944. The old placeholder used a different amber (232,184,74), so a regression to it fails here.
"""

import importlib.util
import pathlib

import pytest
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[2]
FLAME = (0xED, 0xB9, 0x44)
NIGHT = (0x0E, 0x10, 0x16)


@pytest.fixture(scope="module")
def art(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("art", ROOT / "scripts/dev/lampway_placeholder_art.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path_factory.mktemp("art")
    mod.generate(out)
    return out


def _count(image, colour, tol=6):
    px = image.convert("RGB").getdata()
    return sum(1 for p in px if all(abs(p[i] - colour[i]) <= tol for i in range(3)))


def test_the_splash_is_the_brand_splash(art):
    splash = Image.open(art / "src/release/datafiles/splash.png")
    assert splash.size == (1672, 941)
    assert splash.convert("RGB").getpixel((5, 5)) == NIGHT
    assert _count(splash, FLAME) > 3000                     # the wordmark's "way" and the flame
    version = (ROOT / "VERSION").read_text().strip()
    assert version == "0.1.0"


def test_the_icons_are_the_app_icon_tile(art):
    ico = Image.open(art / "src/release/windows/icons/winmixar.ico")
    ico.size = (256, 256)
    big = ico.convert("RGBA")
    assert _count(big, FLAME) > 200 and _count(big, NIGHT) > 5000
    logo = Image.open(art / "src/release/datafiles/mixar_logo.png")
    assert _count(logo, FLAME) > 100


def test_the_freedesktop_svg_is_the_brand_icon(art):
    svg = (art / "src/release/freedesktop/icons/scalable/apps/mixar.svg").read_text()
    assert "#EDB944" in svg and "Lampway app icon" in svg
