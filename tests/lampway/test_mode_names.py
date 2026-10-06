# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The captain's rename (2026-10-06, "Go with Lamplight and Workshop"): Mixar's "Zen Mode" is Lamplight (the agent-first
workspace) and its "Engine Mode" is Workshop (full Blender), in every string a person can read.

Read the way the brand gate reads (test_no_mixar_in_ui_strings): every Python string literal that is not a plain
docstring (an operator's, panel's or menu's docstring is its tooltip and counts), every string literal in the fork's C++
(src/source), and the user documentation. Internal identifiers stay (the 'ZEN' / 'ENGINE' tokens, `zen_` names, file
names): they are one token, so the phrases below never match them; the few that do are allow-listed with a reason."""

import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_no_mixar_in_ui_strings as g1  # noqa: E402

#: Phrases that name the old modes anywhere they appear.
PHRASES = re.compile(r"\b(Zen Mode|Engine Mode|Zen mode|Engine mode|Start with Zen|Start with Engine|Open in Zen|Open in Engine"
                     r"|Zen workspace|Engine workspace|Zen and Engine|Zen & Engine|Zen/Engine|Zen, Engine|Zen & Panel)\b")
#: A string that is the old mode's bare name (a toggle segment, a workspace name, a menu label).
BARE = re.compile(r"^\s*(Zen|Engine)\s*$")
PY_ROOTS = ("src/scripts/mixar", "src/scripts/startup", "scripts/lampway")
CPP_ROOT = "src/source"
DOC_ROOTS = ("docs/lampway",)
CPP_STRING = re.compile(r'"((?:[^"\\\n]|\\.)*)"')

#: (path suffix, literal, reason): kept on purpose.
ALLOW = {
    ("workflow/constants.py", "Zen Mode", "the old workspace name, kept only to find and rename it in a file saved before the rename"),
    ("common/ui/properties/ui_gallery_props.py", "Zen", "the 'Zen' component style of the account card's theme profile, not the workspace"),
    ("makesrna/intern/rna_ui_api.cc", "Zen", "the same theme profile's enum label in C++"),
}


def _py_files():
    for r in PY_ROOTS:
        for dp, _dn, fn in os.walk(ROOT / r):
            if "__pycache__" in dp or os.sep + "tests" in dp or os.sep + "testing" in dp:
                continue
            yield from (pathlib.Path(dp) / f for f in fn if f.endswith(".py"))


def _cpp_files():
    for dp, _dn, fn in os.walk(ROOT / CPP_ROOT):
        yield from (pathlib.Path(dp) / f for f in fn if f.endswith((".cc", ".hh", ".h", ".c")))


def _cpp_strings(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    for n, line in enumerate(text.splitlines(), 1):
        line = re.sub(r"//.*$", "", line) if '"' not in line.split("//", 1)[0][-1:] else line
        for m in CPP_STRING.finditer(line):
            yield n, m.group(1)


def offending(value):
    return bool(PHRASES.search(value) or BARE.match(value))


def _allowed(rel, value):
    return any(rel.endswith(k) and value == v for k, v, _why in ALLOW)


def test_no_user_visible_string_names_zen_or_engine_mode():
    out = []
    for path in _py_files():
        rel = path.relative_to(ROOT).as_posix()
        out += [f"{rel}:{n}: {v[:90]!r}" for n, v in g1._visible_strings(path) if offending(v) and not _allowed(rel, v)]
    for path in _cpp_files():
        rel = path.relative_to(ROOT).as_posix()
        out += [f"{rel}:{n}: {v[:90]!r}" for n, v in _cpp_strings(path) if offending(v) and not _allowed(rel, v)]
    for r in DOC_ROOTS:
        for path in (ROOT / r).rglob("*.md"):
            rel = path.relative_to(ROOT).as_posix()
            out += [f"{rel}:{n}: {line[:90]!r}" for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                    if PHRASES.search(line)]
    assert out == [], f"{len(out)} strings still name Zen / Engine mode (say Lamplight / Workshop):\n" + "\n".join(out[:80])


def test_the_scan_sees_planted_offenders_and_ignores_identifiers(tmp_path):
    p = tmp_path / "x.py"
    p.write_text('A = "Start with Zen Mode"\nB = "Zen"\nC = "ZEN"\nD = "zen_chrome"\nE = "Render Engine"\nF = "Engine"\n'
                 'class Op(Operator):\n    """Switch to Engine Mode"""\n    bl_idname = "mixar.zen"\n')
    hits = sorted(v for _n, v in g1._visible_strings(p) if offending(v))
    assert hits == ["Engine", "Start with Zen Mode", "Switch to Engine Mode", "Zen"], hits
    c = tmp_path / "x.cc"
    c.write_text('/* "Zen Mode" in a comment */\nconst char *a = IFACE_("Zen Mode"); // "Engine Mode"\nconst char *b = "ZEN";\n')
    assert [v for _n, v in _cpp_strings(c) if offending(v)] == ["Zen Mode"]
