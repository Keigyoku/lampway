# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 03, the window's native chrome: the glass retinted from Mixar green to night and lamplight with no moving
sheen, the island's credit ring gone (F6), the account card that shows no e-mail until asked, workspace tabs as text
with an amber underline, and Cinema without its pill border."""

import colorsys
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDITORS = ROOT / "src/source/blender/editors"
GLASS = EDITORS / "interface/interface_mixar_liquid_glass_tokens.cc"
NIGHT = ROOT / "scripts/lampway/facelift/theme/lampway_dark.xml"
PAPER = ROOT / "scripts/lampway/facelift/theme/lampway_light.xml"


def glass_rows():
    """{row name: {field: [floats]}} from the glass material table."""
    text = GLASS.read_text(encoding="utf-8")
    table = text.split("const MixarGlassTokens g_glass_tokens[] = {", 1)[1].split("\n};", 1)[0]
    rows = {}
    for name, body in re.findall(r"/\* (MIXAR_GLASS_\w+).*?\*/\s*\{(.*?)\n    \},", table, re.S):
        fields = {}
        for field, value in re.findall(r"/\*\s*(\w+)\s*\*/\s*(\{[^}]*\}|[-\d.]+f)", body):
            fields[field] = [float(v.rstrip("f")) for v in re.findall(r"[-\d.]+f?", value)]
        rows[name] = fields
    return rows


def _green(rgb):
    h, s, v = colorsys.rgb_to_hsv(*rgb[:3])
    return 70 <= h * 360 <= 175 and s > 0.25 and v > 0.15


def test_glass_has_no_green_and_no_sheen():
    rows = glass_rows()
    assert len(rows) == 9, sorted(rows)
    green = [(n, f) for n, fields in rows.items() for f in ("tint_top", "tint_bottom", "rim", "glaze") if _green(fields[f])]
    assert green == []
    assert {n: fields["specular_alpha"][0] for n, fields in rows.items() if fields["specular_alpha"][0] != 0.0} == {}


def test_glass_is_generated_from_the_tokens():
    """The four panes the contract names take their tint from `surface` and their rim from `line_hi`, at the row's alphas."""
    import json
    tokens = json.loads((ROOT / "scripts/lampway/facelift/theme/tokens.json").read_text(encoding="utf-8"))["colour"]
    rgb = lambda name: [round(int(tokens[name]["dark"][i:i + 2], 16) / 255, 3) for i in (1, 3, 5)]  # noqa: E731
    rows = glass_rows()
    for name in ("MIXAR_GLASS_CARD", "MIXAR_GLASS_ISLAND", "MIXAR_GLASS_PANEL", "MIXAR_GLASS_PILL"):
        assert rows[name]["tint_top"][:3] == rgb("surface"), name
        assert rows[name]["rim"][:3] == rgb("line_hi"), name


def test_the_island_card_has_no_credit_meter():
    """F6: one 0..1 ring cannot say which provider's credits; the status bar carries spend."""
    draw = (EDITORS / "space_agent_bubble/agent_ui_draw.cc").read_text(encoding="utf-8")
    call = re.search(r"draw_card_border_meter\((.*?)\);", draw, re.S)[1]
    assert "credits_remaining" not in call


def test_the_account_card_hides_the_address_until_asked():
    card = (EDITORS / "interface/interface_mixar_profile_card.cc").read_text(encoding="utf-8")
    assert 'read_bool(&wm_ptr, "lampway_show_identity")' in card
    header = card.split("void add_header", 1)[1].split("\nvoid ", 1)[0]
    assert "show_identity" in header and "Local account" in header


def test_workspace_tabs_are_text_with_an_amber_underline():
    widgets = (EDITORS / "interface/interface_widgets.cc").read_text(encoding="utf-8")
    tab = widgets.split("static void widget_tab(", 1)[1].split("\n}\n", 1)[0]
    assert "wcol->item" in tab and "is_active" in tab.split("UNUSED_VARS", 1)[0]
    for xml, bed in ((NIGHT, "canvas"), (PAPER, "canvas")):
        tab_theme = ET.parse(xml).getroot().find(".//wcol_tab/ThemeWidgetColors").attrib
        assert tab_theme["inner"] == tab_theme["inner_sel"], (xml.name, "no pill behind the active tab")
        assert tab_theme["item"].lower().startswith("#edb944") or xml is PAPER, tab_theme["item"]


def test_cinema_has_no_pill_border():
    ui = ET.parse(NIGHT).getroot().find(".//user_interface/ThemeUserInterface").attrib
    assert ui["mixar_cinema_pill_border"].endswith("00"), ui["mixar_cinema_pill_border"]
