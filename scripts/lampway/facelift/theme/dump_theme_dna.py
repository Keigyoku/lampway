# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Dump the build's compiled default theme as DNA, and where each theme XML attribute lives in it (headless).

    HOME=<scratch> <lampway binary> --background --factory-startup --python dump_theme_dna.py -- <theme.xml> <out.json>

The theme XML speaks RNA (`view_3d.object_selected`); `userdef_default_theme.c` speaks DNA (`.space_view3d.select`).
Blender keeps that map in C (rna_userdef.cc), so it is measured here instead of being copied by hand: every colour
attribute gets a unique colour in one pass, every other attribute is nudged one at a time, and the preferences are
saved and read back as DNA with upstream's own reader (tools/utils/blender_theme_as_c.py, the tool that writes the C
file). Writes:
  baseline: the factory theme as DNA, in DNA order ([path, value] pairs; colours as hex), which is the C file's content
  map:      provenance key ("view_3d[0].object_selected") -> DNA path, with the DNA kind
            (colour / float or int with the measured scale and offset RNA applies / flag with its mask and bit /
            enum with each item's value / channel: one byte of a colour)
  unmapped: attributes whose nudge changed no DNA field or more than one (refused by the C emitter)
base/theme_dna_0.1.0.json was produced this way from the 0.1.0 Linux build. Re-run after any DNA/RNA theme change,
with HOME and the XDG dirs in an empty scratch folder (it saves preferences there).
"""
import json
import os
import sys
import xml.etree.ElementTree as ET

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "upstream", "tools", "utils"))
sys.path.insert(0, HERE)
import blender_theme_as_c as theme_as_c  # noqa: E402  (upstream; appends tools/modules for blendfile)
from build_theme import container_key  # noqa: E402

xml_path, out_path = sys.argv[sys.argv.index("--") + 1:][:2]
config = bpy.utils.user_resource('CONFIG', create=True)
bpy.context.preferences.use_preferences_save = True


def path_str(key):
    return [k.decode("ascii") if isinstance(k, bytes) else k for k in (key if isinstance(key, tuple) else (key,))]


def dna():
    """The current theme as DNA: {path tuple: value} in DNA order."""
    for name in os.listdir(config):
        if name.endswith("userpref.blend"):
            os.remove(os.path.join(config, name))
    bpy.ops.wm.save_userpref()
    found = [n for n in os.listdir(config) if n.endswith("userpref.blend")]
    assert len(found) == 1, found
    blend, theme = theme_as_c.theme_data(os.path.join(config, found[0]))
    out = {}
    for key, value in theme.items_recursive_iter(use_nil=False):
        p = tuple(path_str(key))
        if theme_as_c.is_ignore_dna_name(p[-1].encode("ascii")):
            continue
        out[p] = value
    blend.close()
    return out


def entries():
    """(provenance key, rna owner, attribute, xml value) for every attribute below <Theme>, keyed as build_theme.py."""
    counters, acc = {}, []

    def walk(el, rna, stack):
        if el.tag[0].isupper() and el.tag != "Theme":
            key = container_key(stack)
            idx = counters.get(key, 0)
            counters[key] = idx + 1
            for attr, val in el.attrib.items():
                acc.append((f"{key}[{idx}].{attr}", rna, attr, val))
            # colours RNA hides from presets (PROP_HIDDEN): no XML carries them, the compiled table still does
            for p in rna.bl_rna.properties:
                if (p.is_hidden and p.type == "FLOAT" and getattr(p, "array_length", 0) in (3, 4)
                        and p.identifier not in el.attrib and not p.is_readonly):
                    acc.append((f"{key}[{idx}].{p.identifier}", rna, p.identifier, "#hidden"))
        for ch in el:
            if ch.tag[0].islower():
                sub = getattr(rna, ch.tag)
                structs = [c for c in ch if c.tag[0].isupper()]
                for i, s in enumerate(structs):
                    target = sub[i] if (hasattr(sub, "__len__") and not hasattr(sub, "bl_rna")) else sub
                    walk(s, target, stack + [ch.tag, s.tag])

    walk(ET.parse(xml_path).getroot().find("Theme"), bpy.context.preferences.themes[0], [])
    return acc


def hexval(v):
    return "".join(f"{b:02x}" for b in v)


items = entries()
base = dna()
colour_items = [(k, r, a, v) for k, r, a, v in items if v.startswith("#")]
other_items = [(k, r, a, v) for k, r, a, v in items if not v.startswith("#")]

# colours, one pass: attribute i gets (16 + i // 220, 16 + i % 220, 90)
saved = {}
codes = {}
for i, (k, rna, attr, _v) in enumerate(colour_items):
    cur = tuple(getattr(rna, attr))
    saved[k] = cur
    rgb = (16 + i // 220, 16 + i % 220, 90)
    codes[rgb] = k
    setattr(rna, attr, tuple(c / 255 for c in rgb) + cur[3:])
probe = dna()
cmap, unmapped = {}, []
for p, v in probe.items():
    if isinstance(v, bytes) and len(v) in (3, 4) and tuple(v[:3]) in codes:
        k = codes[tuple(v[:3])]
        if k in cmap:
            unmapped.append([k, "two DNA fields took its colour: " + str(cmap[k]) + " and " + str(p)])
        cmap[k] = list(p)
for k, rna, attr, _v in colour_items:
    setattr(rna, attr, saved[k])
    if k not in cmap:
        unmapped.append([k, "no DNA field took its colour"])
hidden = {k for k, _r, _a, v in colour_items if v == "#hidden"}
mapping = {k: dict({"path": p, "kind": "colour"}, **({"hidden": True} if k in hidden else {})) for k, p in cmap.items()}

# everything else, one attribute at a time
base = dna()
for k, rna, attr, xml_val in other_items:
    prop = rna.bl_rna.properties[attr]
    cur = getattr(rna, attr)
    if prop.type == "BOOLEAN":
        tries = [not cur]
    elif prop.type == "ENUM":
        tries = [e.identifier for e in prop.enum_items if e.identifier != cur][:1]
    elif prop.type == "INT":
        tries = [cur + 1 if cur + 1 <= prop.hard_max else cur - 1]
    else:
        tries = [cur + d if cur + d <= prop.hard_max else cur - d for d in (0.125, 0.5, 2.0)]
    changed, now, t = [], {}, None
    for t in tries:
        setattr(rna, attr, t)
        now = dna()
        changed = [p for p in now if now[p] != base.get(p)]
        setattr(rna, attr, cur)
        if changed:
            break
    if len(changed) != 1:
        unmapped.append([k, f"nudge changed {len(changed)} DNA fields: {changed[:4]}"])
        continue
    p = changed[0]
    entry = {"path": list(p)}
    if prop.type == "BOOLEAN":
        vals = {}
        for flag in (True, False):
            setattr(rna, attr, flag)
            vals[flag] = dna()[p]
        setattr(rna, attr, cur)
        mask = vals[True] ^ vals[False]
        entry.update(kind="flag", mask=mask, bit=vals[True] & mask)
    elif prop.type == "ENUM":
        values = {}
        for e in prop.enum_items:
            setattr(rna, attr, e.identifier)
            values[e.identifier] = dna()[p]
        setattr(rna, attr, cur)
        entry.update(kind="enum", values=values)
    elif isinstance(base[p], bytes):  # a factor stored as one channel of a colour (background_alpha -> back[3])
        setattr(rna, attr, tries[0])
        moved = [i for i, (a, b) in enumerate(zip(dna()[p], base[p])) if a != b]
        setattr(rna, attr, cur)
        assert len(moved) == 1, (k, moved)
        entry.update(kind="channel", channel=moved[0])
    else:
        # RNA may scale what DNA stores (a widget's roundness reads back as twice its DNA value): measure the line
        # through the two points the nudge produced, so the emitter writes DNA, not the XML number.
        scale = round((now[p] - base[p]) / (t - cur), 4)
        entry.update(kind="float" if isinstance(base[p], float) else "int", scale=scale,
                     offset=round(base[p] - scale * cur, 4))
    mapping[k] = entry

final = dna()
assert final == base, "the probe did not restore the theme"
baseline = [[list(p), hexval(v) if isinstance(v, bytes) and len(v) in (3, 4) else
             (v.rstrip(b"\x00").decode("ascii") if isinstance(v, bytes) else v)] for p, v in base.items()]

def line(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


with open(out_path, "w") as fh:  # one field and one attribute per line, so a re-dump diffs by name
    fh.write('{"blender": %s,\n "theme_xml_attributes": %d,\n "unmapped": %s,\n "baseline": [\n'
             % (line(bpy.app.version_string), sum(v != "#hidden" for _k, _r, _a, v in items), line(unmapped)))
    fh.write(",\n".join("  " + line(b) for b in baseline) + '\n ],\n "map": {\n')
    fh.write(",\n".join(f"  {line(k)}: {line(mapping[k])}" for k in sorted(mapping)) + "\n }\n}\n")
print("DNA", len(baseline), "fields;", len(mapping), "attributes mapped;", len(unmapped), "unmapped")
