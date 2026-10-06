# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Load a theme XML through the real preset path and read every attribute back (headless; a separate process).

    <lampway binary> --background --factory-startup --python verify_in_blender.py -- <theme.xml> <report.json>
    ... -- <theme.xml> <report.json> --as-default   # load nothing: is the compiled default theme this file?

Fails (exit 1) when: the preset operator does not finish; the loader skips a struct (secure types) or names an
attribute it cannot find; or any value read back from RNA differs from the XML (colours within 1/255). This is the
schema check that cannot be faked by a text comparison: Blender itself parses the file.

--as-default skips the load and compares the factory theme (userdef_default_theme.c) with the file's <Theme>; the
<ThemeStyle> half is not part of the compiled theme, so it is not compared.
"""
import io
import json
import sys
import xml.dom.minidom
from contextlib import redirect_stdout

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
path, report = args[0], args[1]
as_default = "--as-default" in args[2:]

buf = io.StringIO()
res = {'FINISHED'}
if not as_default:
    with redirect_stdout(buf):
        res = bpy.ops.script.execute_preset(filepath=path, menu_idname="USERPREF_MT_interface_theme_presets")
log = buf.getvalue()
problems = []
if res != {'FINISHED'}:
    problems.append(f"execute_preset returned {res}")
for line in log.splitlines():
    if "not found" in line or "skipping" in line:
        problems.append("loader: " + line.strip())

theme = bpy.context.preferences.themes[0]
style = bpy.context.preferences.ui_styles[0]
checked = 0


def compare(xml_node, rna):
    global checked
    for attr in xml_node.attributes.keys():
        want = xml_node.attributes[attr].value
        got = getattr(rna, attr, Ellipsis)
        if got is Ellipsis:
            problems.append(f"{type(rna).__name__}.{attr}: no such property")
            continue
        checked += 1
        if want.startswith("#"):
            hx = want[1:]
            exp = [int(hx[i:i + 2], 16) / 255 for i in range(0, len(hx), 2)]
            vals = list(got)
            if len(vals) != len(exp) or any(abs(a - b) > 1.01 / 255 for a, b in zip(vals, exp)):
                problems.append(f"{type(rna).__name__}.{attr}: wrote {want}, read {[round(v, 4) for v in vals]}")
        elif want in ("TRUE", "FALSE"):
            if bool(got) != (want == "TRUE"):
                problems.append(f"{type(rna).__name__}.{attr}: wrote {want}, read {got}")
        else:
            try:
                ok = abs(float(got) - float(want)) < 1e-4
            except (TypeError, ValueError):
                ok = str(got) == want
            if not ok:
                problems.append(f"{type(rna).__name__}.{attr}: wrote {want}, read {got}")
    elems = {}
    for ch in xml_node.childNodes:
        if ch.nodeType != ch.ELEMENT_NODE:
            continue
        sub = getattr(rna, ch.nodeName, None)
        structs = [c for c in ch.childNodes if c.nodeType == c.ELEMENT_NODE]
        if sub is None:
            problems.append(f"{type(rna).__name__}.{ch.nodeName}: no such pointer")
            continue
        if hasattr(sub, "__len__") and not hasattr(sub, "bl_rna"):
            for i, s in enumerate(structs):
                compare(s, sub[i])
        else:
            for s in structs:
                compare(s, sub)


doc = xml.dom.minidom.parse(path)
root = doc.documentElement
for node in root.childNodes:
    if node.nodeType != node.ELEMENT_NODE or (as_default and node.nodeName != "Theme"):
        continue
    compare(node, theme if node.nodeName == "Theme" else style)

with open(report, "w") as fh:
    json.dump({"theme": path, "attributes_checked": checked, "problems": problems, "blender": bpy.app.version_string}, fh, indent=1)
print("VERIFY", "PASS" if not problems else "FAIL", checked, "attributes,", len(problems), "problems")
sys.exit(1 if problems else 0)
