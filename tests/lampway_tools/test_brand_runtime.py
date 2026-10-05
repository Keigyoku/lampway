# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""G6: the runtime sweep, the one that catches what no source scan can.

Inside the real binary (headless) enumerate every text a person can be shown by the registered UI classes and by Blender's own RNA: the label,
description and category of every Operator, Panel, Menu, Header and UIList; the name and description of every operator in ``bpy.ops`` and of every RNA
struct, property and enum item; and ``bpy.app.version_string``. It fails on ``Mixar``/``Mixie`` (and lowercase prose ``mixar``) anywhere in them. The
source scans (G1-G4) read what is written; this reads what the program says.
"""

import json
import re

import pytest

from blender_run import run_script

SWEEP = r'''
import bpy, json, re, sys
CAP = re.compile(r"(?<![A-Za-z])(Mixar|Mixie)")
LOW = re.compile(r"(?<![\w.\-/$:@~_])mixar(?![\w.\-/:$@_])")
found, seen = [], 0

def check(kind, name, text):
    global seen
    if not isinstance(text, str) or not text:
        return
    seen += 1
    if CAP.search(text) or (re.search(r"\s", text) and LOW.search(text)):
        found.append([kind, name, text[:120]])

def walk(base):
    for c in base.__subclasses__():
        yield c
        yield from walk(c)

for base in (bpy.types.Operator, bpy.types.Panel, bpy.types.Menu, bpy.types.Header, bpy.types.UIList):
    for c in walk(base):
        for attr in ("bl_label", "bl_description", "bl_category"):
            check(base.__name__ + "." + attr, c.__name__, getattr(c, attr, None))
        doc = (c.__doc__ or "").strip()
        if base is bpy.types.Operator:
            check(base.__name__ + ".doc", c.__name__, doc)

for mod in dir(bpy.ops):
    ns = getattr(bpy.ops, mod)
    for fn in dir(ns):
        try:
            rna = getattr(ns, fn).get_rna_type()
        except Exception:
            continue
        check("ops.name", mod + "." + fn, rna.name)
        check("ops.description", mod + "." + fn, rna.description)
        for p in rna.properties:
            check("ops.prop.name", mod + "." + fn + "." + p.identifier, p.name)
            check("ops.prop.description", mod + "." + fn + "." + p.identifier, p.description)

for name in dir(bpy.types):
    t = getattr(bpy.types, name, None)
    rna = getattr(t, "bl_rna", None)
    if rna is None:
        continue
    check("rna.name", name, rna.name)
    check("rna.description", name, rna.description)
    for p in rna.properties:
        check("rna.prop.name", name + "." + p.identifier, p.name)
        check("rna.prop.description", name + "." + p.identifier, p.description)
        if p.type == "ENUM":
            for it in p.enum_items:
                check("rna.enum.name", name + "." + p.identifier + "." + it.identifier, it.name)
                check("rna.enum.description", name + "." + p.identifier + "." + it.identifier, it.description)

check("app.version_string", "bpy.app", bpy.app.version_string)
print("RESULT " + json.dumps({"seen": seen, "found": found}))
'''


def _sweep():
    run = run_script(SWEEP, timeout=600)
    assert run.rc == 0, run.out[-2000:]
    return run.results[-1]


def test_no_text_the_program_can_show_names_the_upstream_brand_or_its_agent():
    result = _sweep()
    assert result["seen"] > 20000, f"the sweep looked at {result['seen']} texts; it is not reaching the registered UI"
    assert result["found"] == [], f"{len(result['found'])} found:\n" + "\n".join(map(str, result["found"][:60]))


def test_the_sweep_sees_a_planted_offender():
    planted = SWEEP.replace('check("app.version_string"', 'check("planted", "x", "Open the Mixie panel")\ncheck("planted", "y", "Save Mixar File")\ncheck("app.version_string"')
    run = run_script(planted, timeout=600)
    found = run.results[-1]["found"]
    assert [f[0] for f in found if f[0] == "planted"] == ["planted", "planted"]
