# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 01: the Night and Paper themes are generated from one token file and gated (T1-T6, T10)."""

import filecmp
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
THEME = ROOT / "scripts/lampway/facelift/theme"
PRESETS = ROOT / "src/scripts/presets/interface_theme"


def run(script, *args, cwd=None):
    return subprocess.run([sys.executable, str(THEME / script), *args], capture_output=True, text=True, cwd=cwd)


def test_theme_gate_has_no_findings():
    done = run("check_theme.py")
    assert done.returncode == 0, done.stdout + done.stderr


def test_theme_gate_catches_each_planted_offender():
    done = run("check_theme.py", "--self-test")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "MISSED" not in done.stdout


def test_cue_gate_passes_and_catches_its_plants():
    assert run("check_cues.py").returncode == 0
    done = run("check_cues.py", "--self-test")
    assert done.returncode == 0, done.stdout + done.stderr


def test_shipped_presets_are_the_generated_files(tmp_path):
    done = run("build_theme.py", "--out", str(tmp_path))
    assert done.returncode == 0, done.stdout + done.stderr
    for shipped, generated in (("Lampway_Night.xml", "lampway_dark.xml"), ("Lampway_Paper.xml", "lampway_light.xml")):
        assert (PRESETS / shipped).is_file(), shipped
        assert filecmp.cmp(PRESETS / shipped, tmp_path / generated, shallow=False), shipped
        assert filecmp.cmp(THEME / generated, tmp_path / generated, shallow=False), generated


def test_every_generated_file_is_committed_as_generated(tmp_path):
    """The provenance maps and the WezTerm config are generator outputs too: a hand edit or a stale copy fails."""
    done = run("build_theme.py", "--out", str(tmp_path))
    assert done.returncode == 0, done.stdout + done.stderr
    for name in ("lampway_dark.provenance.json", "lampway_light.provenance.json", "lampway.wezterm.lua"):
        assert filecmp.cmp(THEME / name, tmp_path / name, shallow=False), name


@pytest.mark.skipif(shutil.which("luajit") is None, reason="check_wezterm.py runs the config under luajit")
def test_wezterm_gate_passes_and_catches_its_plants():
    assert run("check_wezterm.py").returncode == 0
    done = run("check_wezterm.py", "--self-test")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "MISSED" not in done.stdout


def test_quick_setup_theme_row_names_lampway_night(monkeypatch):
    """A fresh profile has picked no preset (the menu label is upstream's "Presets"): the row names the default."""
    import bpy
    monkeypatch.setitem(sys.modules, "bpy.app.translations", SimpleNamespace(pgettext_iface=lambda text, *_: text))
    monkeypatch.setattr(bpy.types, "USERPREF_MT_interface_theme_presets", SimpleNamespace(bl_label="Presets"),
                        raising=False)
    monkeypatch.setattr(bpy.types, "PREFERENCES_OT_copy_prev", None, raising=False)
    monkeypatch.setattr(sys.modules["bpy.types"], "Menu", object, raising=False)  # a real base keeps its draw
    monkeypatch.delitem(sys.modules, "mixar.bootstrap.splash_quick_setup", raising=False)
    from mixar.bootstrap.splash_quick_setup import WM_MT_splash_quick_setup

    layout = MagicMock()
    context = SimpleNamespace(window_manager=MagicMock())
    WM_MT_splash_quick_setup.draw(SimpleNamespace(layout=layout), context)
    themed = [c for c in layout.mock_calls if c[0].endswith(".menu") and c[1][:1] == ("USERPREF_MT_interface_theme_presets",)]
    assert [c[2].get("text") for c in themed] == ["Lampway Night"]


# ------------------------------------------------------------------------------------------- the compiled defaults
# Contract 01 6.3/6.4 and T8: Lampway Night is the default theme. The compiled tables are generated from the same
# tokens: the default theme (userdef_default_theme.c, through the DNA map measured in base/theme_dna_0.1.0.json),
# the fork's slot fallbacks, its zen palette and RNA's reset defaults.
NATIVE = {
    "userdef_default_theme.c": ROOT / "src/release/datafiles/userdef/userdef_default_theme.c",
    "interface_mixar_theme.cc": ROOT / "src/source/blender/editors/interface/interface_mixar_theme.cc",
    "UI_mixar_tokens.hh": ROOT / "src/source/blender/editors/include/UI_mixar_tokens.hh",
    "rna_userdef.cc": ROOT / "src/source/blender/makesrna/intern/rna_userdef.cc",
    "interface_mixar_liquid_glass_tokens.cc": ROOT / "src/source/blender/editors/interface/interface_mixar_liquid_glass_tokens.cc",
}
UPSTREAM_USERDEF = ROOT / "upstream/release/datafiles/userdef/userdef_default_theme.c"


def c_fields(text):
    """{path: value} for every leaf initialiser of `U_theme_default` (designators and array indices as the path)."""
    body = text.split("const bTheme U_theme_default = {", 1)[1]
    stack, counters, out = [], [0], {}
    for raw in body.splitlines():
        s = raw.strip()
        if s.startswith("."):
            name, _, value = s[1:].partition(" = ")
            if value == "{":
                stack.append(name)
                counters.append(0)
            else:
                out[tuple(stack + [name])] = value.rstrip(",")
        elif s == "{":
            stack.append(counters[-1])
            counters[-1] += 1
            counters.append(0)
        elif s in ("},", "};") and stack:
            stack.pop()
            counters.pop()
    return out


def c_hex(value):
    """RGBA(0x2f592fff) -> '2f592fff'; an omitted colour is zero."""
    return value.split("0x", 1)[1].rstrip(")") if value else None


def xml_values(path):
    """provenance key -> value for every attribute below <Theme>, keyed as build_theme.py keys them."""
    import xml.etree.ElementTree as ET
    counters, out = {}, {}

    def walk(el, stack):
        if el.tag[0].isupper() and el.tag not in ("Theme", "ThemeStyle"):
            key = "/".join(t for t in stack if t[0].islower())
            idx = counters.get(key, 0)
            counters[key] = idx + 1
            for attr, val in el.attrib.items():
                out[f"{key}[{idx}].{attr}"] = val
        for ch in el:
            walk(ch, stack + [ch.tag])

    walk(ET.parse(path).getroot().find("Theme"), [])
    return out


def dna_map():
    import json
    return json.loads((THEME / "base/theme_dna_0.1.0.json").read_text(encoding="utf-8"))


def test_compiled_defaults_are_the_generated_files(tmp_path):
    done = run("build_theme.py", "--out", str(tmp_path))
    assert done.returncode == 0, done.stdout + done.stderr
    for name, committed in NATIVE.items():
        assert (tmp_path / name).is_file(), name
        assert filecmp.cmp(committed, tmp_path / name, shallow=False), f"{name}: rebuild with build_theme.py"


def test_default_theme_c_closes_every_block():
    """The first native build of the generated file stopped at `.strip_color = {` left open: every block closes."""
    text = NATIVE["userdef_default_theme.c"].read_text(encoding="utf-8")
    body = text.split("const bTheme U_theme_default = {", 1)[1]
    depth = 1
    for no, line in enumerate(body.splitlines(), 1):
        depth += line.count("{") - line.count("}")
        assert depth >= 0, f"line {no} closes a block that was never opened"
        if depth == 0:
            assert line.strip() == "};", (no, line)
            break
    assert depth == 0, f"{depth} blocks left open at the end of U_theme_default"


def test_the_measured_dna_is_the_compiled_default():
    """base/theme_dna_0.1.0.json is a measurement of a built binary; it must be the build of the committed C file
    (re-run dump_theme_dna.py after a rebuild), or the map would be read against a theme that no longer exists."""
    def norm(value):
        if isinstance(value, str) and value.startswith(("RGBA(", "RGB(")):
            return c_hex(value)
        if isinstance(value, str) and value.startswith('"'):
            return value.strip('"')
        if isinstance(value, str) and len(value) in (6, 8) and all(c in "0123456789abcdef" for c in value):
            return value  # a measured colour; "303330ff" is not a number
        try:
            return round(float(str(value).rstrip("f")), 5)
        except ValueError:
            return value

    compiled = {k: norm(v) for k, v in c_fields(NATIVE["userdef_default_theme.c"].read_text(encoding="utf-8")).items()}
    measured = {tuple(p): norm(v) for p, v in dna_map()["baseline"]
                if v not in (0, 0.0, "") and not (isinstance(v, str) and set(v) == {"0"})}
    assert compiled == measured, sorted(set(compiled.items()) ^ set(measured.items()), key=str)[:10]


def test_default_theme_is_lampway_night_field_by_field():
    """T8: every attribute of lampway_dark.xml is what userdef_default_theme.c compiles in, through the DNA map."""
    fields = c_fields(NATIVE["userdef_default_theme.c"].read_text(encoding="utf-8"))
    want = xml_values(THEME / "lampway_dark.xml")
    assert fields[("name",)] == '"Lampway Night"'
    wrong = []
    for key, m in dna_map()["map"].items():
        if m.get("hidden"):
            continue
        path, xml = tuple(m["path"]), want[key]
        got = fields.get(path)
        if m["kind"] == "colour":
            have = c_hex(got) or "0" * 8
            ok = have[:6] == xml[1:7] and (len(xml) < 9 or len(have) < 8 or have[6:8] == xml[7:9])
        elif m["kind"] == "channel":
            ok = int((c_hex(got) or "0" * 8)[2 * m["channel"]:2 * m["channel"] + 2], 16) == round(float(xml) * 255)
        elif m["kind"] == "flag":
            ok = (int(got or 0) & m["mask"]) == (m["bit"] if xml == "TRUE" else 0)
        elif m["kind"] == "enum":
            ok = int(got or 0) == m["values"][xml]
        else:  # RNA can scale what DNA stores; the probe measured the line
            dna_value = m["scale"] * float(xml) + m["offset"]
            ok = abs(float((got or "0").rstrip("f")) - dna_value) <= 1e-6 * max(1.0, abs(dna_value))
        if not ok:
            wrong.append((key, path, xml, got))
    assert not wrong, f"{len(wrong)} compiled defaults differ from Lampway Night, e.g. {wrong[:5]}"


def test_colours_no_preset_can_carry_follow_the_rules():
    """The colours RNA hides from presets (the five Mixar slots, the chat and moodboard extras) have no XML; the
    compiled default is their only source, so it must come from the same rules as everything else."""
    sys.path.insert(0, str(THEME))
    try:
        import build_theme
    finally:
        sys.path.remove(str(THEME))
    fields = c_fields(NATIVE["userdef_default_theme.c"].read_text(encoding="utf-8"))
    hidden = {k: m for k, m in dna_map()["map"].items() if m.get("hidden")}
    assert {"user_interface[0].mixar_pane_pill_dim", "user_interface[0].mixar_pane_pill_on",
            "user_interface[0].mixar_cinema_pill_fill", "user_interface[0].mixar_profile_fill",
            "user_interface[0].mixar_cinema_gate_fill"} <= set(hidden)
    wrong = []
    for key, m in hidden.items():
        container, attr = key.split("[0].")
        spec = build_theme.RULES[container][attr]
        want = build_theme.resolve(spec, attr, container, 0, "dark", 4, {})[0]
        if (c_hex(fields.get(tuple(m["path"]))) or "0" * 8) != want[1:]:
            wrong.append((key, spec, want, fields.get(tuple(m["path"]))))
    assert not wrong, wrong


def _greens_allowed():
    import json
    import re
    tokens = json.loads((THEME / "tokens.json").read_text(encoding="utf-8"))["colour"]
    allowed = {tokens[n]["dark"][1:7].lower() for n in ("go", "go_bed")}
    allowed |= {h.lower() for h in re.findall(r'="#([0-9a-fA-F]{6})', (THEME / "lampway_dark.xml").read_text())}
    allowed |= {c_hex(v)[:6] for v in c_fields(UPSTREAM_USERDEF.read_text(encoding="utf-8")).values()
                if v.startswith("RGB")}
    return allowed


def _is_green(rgb):
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    return 70 <= h * 360 <= 175 and s > 0.25 and v > 0.15


def _colour_literals(text):
    import re
    for no, line in enumerate(text.splitlines(), 1):
        for m in re.finditer(r"RGBA?\(0x([0-9a-fA-F]{6})", line):
            yield no, tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
        for m in re.finditer(r"\{\s*(\d{1,3}),\s*(\d{1,3}),\s*(\d{1,3}),\s*\d{1,3}\s*\}", line):
            yield no, tuple(int(x) for x in m.groups())
        over = r"(\d+(?:\.\d+)?)f\s*/\s*255\.0f"
        for m in re.finditer(rf"{over},\s*{over},\s*{over}", line):
            yield no, tuple(round(float(x)) for x in m.groups())


def test_no_mixar_green_is_compiled_into_the_theme_tables():
    """T4 on the compiled side: the tables this contract owns hold no green unless the theme itself keeps it
    (a `go` token, or a Blender domain colour that upstream's own default theme has)."""
    allowed = _greens_allowed()
    found = []
    for name, path in NATIVE.items():
        text = path.read_text(encoding="utf-8")
        if name == "rna_userdef.cc":  # only the theme's reset defaults, not every float array RNA declares
            text = "\n".join(line for line in text.splitlines()
                             if "255.0f" in line or line.lstrip().startswith(("{\"mixar_", "{\"agent_")))
        for no, rgb in _colour_literals(text):
            if _is_green(rgb) and "%02x%02x%02x" % rgb not in allowed:
                found.append(f"{name}:{no} #%02x%02x%02x" % rgb)
    assert not found, f"{len(found)} Mixar greens compiled in: {found[:12]}"
