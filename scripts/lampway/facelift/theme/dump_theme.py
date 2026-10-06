# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Dump the running build's default theme and its RNA schema (headless, read-only).

    <lampway binary> --background --factory-startup --python dump_theme.py -- <out dir>

Writes <out>/default_theme_dump.xml with the same rna map the theme preset menu uses
(USERPREF_MT_interface_theme_presets.preset_xml_map) and <out>/theme_schema.json: every theme struct and
property (type, array size, enum items, range). base/default_theme_0.1.0.xml and base/theme_schema_0.1.0.json
were produced this way from the 0.1.0 Linux build (upstream fbe6228777e7, Blender 5.2.0). Run it with HOME and
the XDG dirs pointed at an empty scratch folder so nothing is written to a real profile.
"""
import json
import os
import sys

import _rna_xml as rna_xml
import bpy
from bl_ui.space_userpref import USERPREF_MT_interface_theme_presets as Presets

out = sys.argv[sys.argv.index("--") + 1]
ctx = bpy.context
rna_xml.xml_file_write(ctx, os.path.join(out, "default_theme_dump.xml"), Presets.preset_xml_map)


def walk(st, seen, acc):
    name = st.bl_rna.identifier
    if name in seen:
        return
    seen.add(name)
    props = {}
    for p in st.bl_rna.properties:
        if p.identifier == "rna_type":
            continue
        d = {"type": p.type, "readonly": p.is_readonly}
        if p.type in ("FLOAT", "INT"):
            d.update(subtype=p.subtype, size=getattr(p, "array_length", 0), min=p.hard_min, max=p.hard_max)
        if p.type == "ENUM":
            d["items"] = [e.identifier for e in p.enum_items]
        if p.type in ("POINTER", "COLLECTION"):
            d["struct"] = p.fixed_type.identifier
        props[p.identifier] = d
        if p.type == "POINTER":
            v = getattr(st, p.identifier, None)
            if v is not None:
                walk(v, seen, acc)
        if p.type == "COLLECTION":
            for v in getattr(st, p.identifier, []):
                walk(v, seen, acc)
    acc[name] = props


acc, seen = {}, set()
walk(ctx.preferences.themes[0], seen, acc)
walk(ctx.preferences.ui_styles[0], seen, acc)
with open(os.path.join(out, "theme_schema.json"), "w") as fh:
    json.dump({"version": bpy.app.version_string, "structs": acc}, fh, indent=1, sort_keys=True)
print("DUMPED", len(acc), "structs")
