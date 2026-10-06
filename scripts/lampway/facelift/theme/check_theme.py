#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The theme-token gate (contract 01, test T1-T6). Pure Python, no Blender.

    python3 check_theme.py               # exit 1 on any finding
    python3 check_theme.py --self-test   # plants one offender per check and proves each check fails

T1  DESIGN.md's colour table and tokens.json agree, token by token, dark and light.
T2  each shipped XML carries exactly the base theme's attributes (the 0.1.0 / Blender 5.2 schema): none missing, none extra.
T3  every colour in the XML equals what its provenance says: the token (with its alpha), the upstream domain value, or
    a KEPT literal; a colour with no provenance fails.
T4  no Mixar green survives: a token- or literal-sourced colour with hue 70-175 and saturation > 0.25 fails unless it
    is the `go` family (domain colours copied from upstream are Blender's conventions, not brand, and are exempt).
T5  readable-text pairs clear WCAG 4.5:1 in both variants; the pairs are read from the XML, not from the tokens.
T6  the existing fork test's pairs (tests/test_mixar_theme_colors.py:103-114) hold on the Lampway values too, so
    making this theme the default does not turn that test red.
"""
import colorsys
import copy
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN = os.path.join(HERE, "..", "DESIGN.md")
sys.path.insert(0, HERE)
import build_theme  # noqa: E402  (the KEPT reasons and the upstream reader live with the builder)


def lum(hx):
    hx = hx.lstrip("#")[:6]
    rgb = [int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda v: v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2])


def contrast(a, b):
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def design_tokens(text):
    out = {}
    for m in re.finditer(r"^\|\s*`([a-z_]+)`\s*\|\s*`?(#[0-9A-Fa-f]{6})`?\s*\|\s*`?(#[0-9A-Fa-f]{6})`?\s*\|", text, re.M):
        out[m.group(1)] = {"dark": m.group(2).upper(), "light": m.group(3).upper()}
    return out


def flat(path):
    """{(container key, index, attr): value} for a theme XML."""
    root = ET.parse(path).getroot()
    out, counters = {}, {}

    def walk(el, stack):
        if el.tag[0].isupper() and el.tag not in ("Theme", "ThemeStyle"):
            key = build_theme.container_key(stack)
            idx = counters.get(key, 0)
            counters[key] = idx + 1
            for k, v in el.attrib.items():
                out[(key, idx, k)] = v
        for ch in el:
            walk(ch, stack + [ch.tag])

    walk(root.find("Theme"), [])
    for ch in root.find("ThemeStyle"):
        for k, v in ch.find("ThemeFontStyle").attrib.items():
            out[("style/" + ch.tag, 0, k)] = v
    return out


def check(tokens, design_text, xmls, provs):
    findings = []
    # T1
    dt = design_tokens(design_text)
    if not dt:
        findings.append("T1: no colour table found in DESIGN.md")
    for name, tok in tokens["colour"].items():
        row = dt.get(name)
        if row is None:
            findings.append(f"T1: token {name} is in tokens.json but not in DESIGN.md")
            continue
        for v in ("dark", "light"):
            if row[v] != tok[v].upper():
                findings.append(f"T1: {name} {v}: DESIGN.md {row[v]} != tokens.json {tok[v]}")
    for name in dt:
        if name not in tokens["colour"]:
            findings.append(f"T1: token {name} is in DESIGN.md but not in tokens.json")
    base = flat(build_theme.BASE)
    upstream = build_theme.load_upstream()
    for variant, xml_vals in xmls.items():
        prov = provs[variant]
        # T2
        missing = set(base) - set(xml_vals)
        extra = set(xml_vals) - set(base)
        for k in sorted(missing)[:10]:
            findings.append(f"T2 {variant}: missing {k}")
        for k in sorted(extra)[:10]:
            findings.append(f"T2 {variant}: not in the 5.2 schema {k}")
        # T3, T4
        for (key, idx, attr), val in xml_vals.items():
            if not val.startswith("#"):
                continue
            src = prov.get(f"{key}[{idx}].{attr}")
            if src is None:
                findings.append(f"T3 {variant}: {key}[{idx}].{attr} = {val} has no provenance")
                continue
            kind, _, ref = src.partition(":")
            if kind == "token":
                name, _, alpha = ref.partition("@")
                tok = tokens["colour"].get(name)
                if tok is None:
                    findings.append(f"T3 {variant}: {key}.{attr} names unknown token {name}")
                    continue
                exp = build_theme.fmt(tok[variant] + alpha.lower(), (len(val) - 1) // 2)
                if val.lower() != exp:
                    findings.append(f"T3 {variant}: {key}.{attr} = {val}, token {ref} says {exp}")
            elif kind == "kept":
                if ref not in build_theme.KEPT:
                    findings.append(f"T3 {variant}: {key}.{attr} literal {ref} has no KEPT reason")
            elif kind == "domain":
                up = (upstream.get((key, idx)) or {}).get(attr)
                if key == "nla_editor" and attr == "sound_strips":
                    up = upstream.get(("sequence_editor", 0)).get("audio_strip")
                if up is None or val.lower()[:7] != up.lower()[:7]:
                    findings.append(f"T3 {variant}: {key}[{idx}].{attr} = {val} is not upstream's {up}")
                continue
            r, g, b = [int(val[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            alpha = int(val[7:9], 16) if len(val) == 9 else 255
            is_go = kind == "token" and ref.split("@")[0] in ("go", "go_bed")
            if 70 <= h * 360 <= 175 and s > 0.25 and v > 0.15 and alpha > 0 and not is_go:
                findings.append(f"T4 {variant}: {key}.{attr} = {val} is in the forbidden green family (the upstream brand's)")
        # T5 (read from the XML)
        ui = lambda a: xml_vals[("user_interface", 0, a)]  # noqa: E731
        w = lambda c, a: xml_vals[("user_interface/" + c, 0, a)]  # noqa: E731
        sp = lambda e, a: xml_vals[(e + "/space", 0, a)]  # noqa: E731
        pairs = [
            ("panel text on panel", ui("panel_text"), ui("panel_back")),
            ("panel title on header", ui("panel_title"), ui("panel_header")),
            ("button text", w("wcol_regular", "text"), w("wcol_regular", "inner")),
            ("selected button text", w("wcol_regular", "text_sel"), w("wcol_regular", "inner_sel")),
            ("toggle on", w("wcol_toggle", "text_sel"), w("wcol_toggle", "inner_sel")),
            ("text field", w("wcol_text", "text"), w("wcol_text", "inner")),
            ("menu item hover", w("wcol_menu_item", "text_sel"), w("wcol_menu_item", "inner_sel")),
            ("list row selected", w("wcol_list_item", "text_sel"), w("wcol_list_item", "inner_sel")),
            ("tab active", w("wcol_tab", "text_sel"), w("wcol_tab", "inner_sel")),
            ("tooltip", w("wcol_tooltip", "text"), w("wcol_tooltip", "inner")),
            ("outliner text", sp("outliner", "text"), sp("outliner", "back")),
            ("header text", sp("properties", "header_text"), sp("properties", "header")),
            ("chat user bubble", xml_vals[("mixie_chat", 0, "chat_user_text")], xml_vals[("mixie_chat", 0, "chat_user_bubble")]),
            ("chat label", xml_vals[("mixie_chat", 0, "chat_label_color")], sp("mixie_chat", "back")),
        ]
        for label, fg, bg in pairs:
            c = contrast(fg, bg)
            if c < 4.5:
                findings.append(f"T5 {variant}: {label} {fg} on {bg} = {c:.2f}:1 (< 4.5)")
        # T6: the fork's own pinned pairs (tests/test_mixar_theme_colors.py:103-114)
        for fg, bg in (("mixar_text", "mixar_canvas"), ("mixar_text_secondary", "mixar_panel"), ("mixar_text_strong", "mixar_primary"),
                       ("mixar_brand_text", "mixar_brand"), ("mixar_ink", "mixar_gradient_start"), ("mixar_ink", "mixar_gradient_end"),
                       ("mixar_viewport_label", "mixar_viewport_fill")):
            c = contrast(ui(fg), ui(bg))
            if c < 4.5:
                findings.append(f"T6 {variant}: {fg} on {bg} = {c:.2f}:1 (< 4.5, tests/test_mixar_theme_colors.py would fail)")
    return findings


def load():
    tokens = json.load(open(os.path.join(HERE, "tokens.json")))
    design = open(DESIGN, encoding="utf-8").read() if os.path.exists(DESIGN) else ""
    xmls = {v: flat(os.path.join(HERE, f"lampway_{v}.xml")) for v in ("dark", "light")}
    provs = {v: json.load(open(os.path.join(HERE, f"lampway_{v}.provenance.json"))) for v in ("dark", "light")}
    return tokens, design, xmls, provs


def self_test():
    tokens, design, xmls, provs = load()
    assert not check(tokens, design, xmls, provs), "the shipped files must be clean before the self-test"
    plants = []
    t = copy.deepcopy(tokens); t["colour"]["accent"]["dark"] = "#EDB945"
    plants.append(("T1 token drift", (t, design, xmls, provs), "T1"))
    x = copy.deepcopy(xmls); x["dark"].pop(next(iter(x["dark"])))
    plants.append(("T2 missing attribute", (tokens, design, x, provs), "T2"))
    x = copy.deepcopy(xmls); x["dark"][("user_interface", 0, "panel_back")] = "#123456ff"
    plants.append(("T3 off-token colour", (tokens, design, x, provs), "T3"))
    x = copy.deepcopy(xmls); p = copy.deepcopy(provs)
    x["dark"][("user_interface", 0, "mixar_selected")] = "#2f592fff"; p["dark"]["user_interface[0].mixar_selected"] = "kept:#2f592fff"
    build_theme.KEPT["#2f592fff"] = "planted"
    plants.append(("T4 upstream green", (tokens, design, x, p), "T4"))
    x = copy.deepcopy(xmls); x["dark"][("user_interface/wcol_regular", 0, "text")] = "#2a2a2a"
    plants.append(("T5 unreadable button text", (tokens, design, x, provs), "T5"))
    x = copy.deepcopy(xmls); x["dark"][("user_interface", 0, "mixar_primary")] = "#edb944ff"
    plants.append(("T6 fork contrast pair", (tokens, design, x, provs), "T6"))
    ok = True
    for label, a, tag in plants:
        got = check(*a)
        hit = any(f.startswith(tag) for f in got)
        print(("caught  " if hit else "MISSED  ") + label)
        ok &= hit
    build_theme.KEPT.pop("#2f592fff", None)
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if self_test() else 1)
    findings = check(*load())
    for f in findings:
        print(f)
    print(f"check_theme: {len(findings)} finding(s)")
    sys.exit(1 if findings else 0)
