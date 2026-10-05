# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every upstream brand asset is replaced by generated PLACEHOLDER art.

The 15 files the upstream REUSE.toml licensed as brand assets, plus the
two visibly branded datafiles (``splash.png``, ``mixar_logo.png``), are
produced by ``scripts/dev/lampway_placeholder_art.py`` and licensed with
the source. Formats and dimensions must stay what the build consumes.
"""

import pathlib
import struct
import tomllib

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[2]

ICNS = "src/release/darwin/Mixar.app/Contents/Resources/"
BRAND_FILES = (
    ICNS + "Mixar_Legacy_Document_Icon.icns",
    ICNS + "mixar_icon.icns",
    "src/release/datafiles/blender_icons16/icon16_mixar_icon.dat",
    "src/release/datafiles/blender_icons32/icon32_mixar_icon.dat",
    "src/release/datafiles/icons_svg/mixar_icon.svg",
    "src/release/datafiles/icons_svg/credits_upgrade.svg",
    "src/release/datafiles/icons_svg/credits_slide.svg",
    "src/release/datafiles/icons_svg/credits_refer.svg",
    "src/release/datafiles/icons_svg/credits_creator.svg",
    "src/release/datafiles/mixar_icons.svg",
    "src/scripts/mixar/modules/common/notifications/assets/mixie_mascot.webp",
    "src/release/freedesktop/icons/scalable/apps/mixar.svg",
    "src/release/freedesktop/icons/symbolic/apps/mixar-symbolic.svg",
    "src/release/windows/icons/winmixar.ico",
    "src/release/windows/icons/winmixarfile.ico",
    "src/release/datafiles/splash.png",
    "src/release/datafiles/mixar_logo.png",
)
PLACEHOLDER_MARK = "Lampway placeholder"


def _annotation_for(reuse, rel):
    for block in reuse["annotations"]:
        paths = block["path"]
        if isinstance(paths, str):
            paths = [paths]
        if rel in paths:
            return block
    raise AssertionError(f"{rel} has no explicit REUSE annotation")


def test_generator_is_checked_in():
    assert (ROOT / "scripts/dev/lampway_placeholder_art.py").is_file()


def test_every_brand_file_is_placeholder_licensed_with_the_source():
    reuse = tomllib.loads((ROOT / "REUSE.toml").read_text(encoding="utf-8"))
    for rel in BRAND_FILES:
        assert (ROOT / rel).is_file(), rel
        block = _annotation_for(reuse, rel)
        assert block["SPDX-License-Identifier"] == "GPL-3.0-or-later", rel
        assert "Lampway" in block["SPDX-FileCopyrightText"], rel
        assert block["precedence"] == "override", rel


def test_icon_dat_headers_are_what_the_build_expects():
    for rel, header in (
        ("src/release/datafiles/blender_icons16/icon16_mixar_icon.dat", (16, 16, 257, 320, 602, 640)),
        ("src/release/datafiles/blender_icons32/icon32_mixar_icon.dat", (32, 32, 514, 640, 1204, 1280)),
    ):
        data = (ROOT / rel).read_bytes()
        assert struct.unpack("<6i", data[:24]) == header, rel
        assert len(data) == 24 + header[0] * header[1] * 4, rel
        # Not blank: the placeholder glyph has opaque pixels.
        assert any(data[24 + 3::4]), rel


def test_raster_formats_and_dimensions():
    with Image.open(ROOT / "src/release/datafiles/splash.png") as splash:
        assert splash.size == (1672, 941) and splash.mode == "RGBA"
    with Image.open(ROOT / "src/release/datafiles/mixar_logo.png") as logo:
        assert logo.size == (256, 256) and logo.mode == "RGBA"
    mascot = ROOT / "src/scripts/mixar/modules/common/notifications/assets/mixie_mascot.webp"
    assert mascot.stat().st_size < 400_000
    with Image.open(mascot) as art:
        assert art.size == (632, 725) and art.mode == "RGBA"
        assert art.getchannel("A").getextrema() == (0, 255)
    for rel in ("src/release/windows/icons/winmixar.ico", "src/release/windows/icons/winmixarfile.ico"):
        with Image.open(ROOT / rel) as ico:
            assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(ico.info["sizes"]), rel
    for rel in (ICNS + "mixar_icon.icns", ICNS + "Mixar_Legacy_Document_Icon.icns"):
        with Image.open(ROOT / rel) as icns:
            assert icns.format == "ICNS" and icns.size[0] >= 512, rel


def test_svgs_are_marked_placeholders():
    for rel in BRAND_FILES:
        if not rel.endswith(".svg"):
            continue
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert PLACEHOLDER_MARK in text, rel
        assert "SPDX-License-Identifier: GPL-3.0-or-later" in text, rel
        assert "<svg" in text
    sheet = (ROOT / "src/release/datafiles/mixar_icons.svg").read_text(encoding="utf-8")
    assert 'width="602"' in sheet and 'height="640"' in sheet
