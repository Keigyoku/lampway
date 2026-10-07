<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Lampway themes: Night (dark) and Paper (light)

v2, the calm pass: `lampway_dark.xml` and `lampway_light.xml` are complete Blender 5.2 theme presets (959 attributes each, every attribute the 0.1.0 build's schema has). `python3 build_theme.py` writes them and ships the same bytes as `src/scripts/presets/interface_theme/Lampway_Night.xml` and `Lampway_Paper.xml` (`tests/lampway/test_lampway_theme.py` fails if a shipped copy or any other generated file drifts); pick them from Preferences, Themes, or the Quick Setup theme row. The facelift spec's contract 01 (tokens and theme) covers making Night the default.

| file | what |
|---|---|
| `tokens.json` | the token source (colour, worker rings, radii, spacing, type, motion); mirrored in `../DESIGN.md` 2.1 |
| `build_theme.py` | generates both XMLs and their provenance from the tokens over the build's default theme; refuses a colour with no rule |
| `check_theme.py` | the gate, T1-T6 (tokens = DESIGN.md, schema-complete, every colour accounted for, no Mixar green, readable text, the fork's own contrast pairs); `--self-test` plants one offender per check |
| `verify_in_blender.py` | loads a theme through the real preset path in a headless build and reads every attribute back |
| `check_cues.py` | the glance-cue gate (C1-C4): one glyph per state per family, only live egress moves, only waiting-on-you glows, colour distances under deuteranopia and protanopia; writes `cues_report.md` |
| `lampway.wezterm.lua` | Lampway's own WezTerm config (contract 16), generated from the same tokens |
| `check_wezterm.py` | runs the WezTerm config under a stub with luajit (W1-W5): tokens, no update check, isolation from the user's config, a viewport only (no tab bar, no tab title or status from state), the image link |
| `dump_theme.py` | re-dumps the build's default theme and schema into `base/` after a DNA/RNA theme change |
| `dump_theme_dna.py` | measures, in the built binary, where each theme XML attribute lives in DNA (`base/theme_dna_0.1.0.json`: the compiled default as DNA, and the RNA-to-DNA map with each field's kind). `build_theme.py` uses it to write the compiled defaults below; re-run it after a DNA/RNA theme change |
| compiled defaults | `build_theme.py` also writes Lampway Night into `src/release/datafiles/userdef/userdef_default_theme.c` (with upstream's own writer, `upstream/tools/utils/blender_theme_as_c.py`), the fork's slot fallbacks (`interface_mixar_theme.cc`), its zen palette (`UI_mixar_tokens.hh`) and RNA's reset defaults (`rna_userdef.cc`). The colours RNA hides from presets take their rules from the same table; these four files need a native rebuild |
| `base/` | the 0.1.0 build's default theme and schema (dumped 2026-10-05), and upstream Blender 5.2's light preset (the source of the domain colours) |
| `*.provenance.json` | per attribute: `token:<name>[@alpha]`, `domain:upstream`, `kept:<literal>` or `metric` |

```
python3 build_theme.py                 # writes both themes
python3 check_theme.py                 # 0 findings, or exit 1
python3 check_theme.py --self-test     # 6 of 6 caught
python3 check_cues.py && python3 check_cues.py --self-test         # 0 findings; 4 of 4 caught
python3 check_wezterm.py && python3 check_wezterm.py --self-test   # 0 findings; 4 of 4 caught (needs luajit)
<build>/bin/lampway --background --factory-startup --python verify_in_blender.py -- lampway_dark.xml report.json
<build>/bin/lampway --background --factory-startup --python verify_in_blender.py -- lampway_dark.xml report.json --as-default
<build>/bin/lampway --background --factory-startup --python dump_theme_dna.py -- lampway_dark.xml base/theme_dna_0.1.0.json
```

Measured 2026-10-05 against the 0.1.0 Linux build (Blender 5.2.0 schema): both files PASS, 959 attributes, 0 problems; a planted unknown attribute fails. Run the build with `HOME` and the XDG dirs in an empty scratch folder; never against a live session.
