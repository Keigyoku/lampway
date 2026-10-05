# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""G4: no string literal in the native code shows the upstream brand.

Comments are stripped first (cppstrings.py). A literal is user-visible, and fails here, when it names ``Mixar``/``Mixie`` and is prose (has a space), a
path, or is exactly the name (a keymap, folder or window class). Pure identifiers (``SpaceMixie``, ``rna_uiLayoutMixarStyle``, ``MixarLoginDialog``) are
internal names and pass. ``#include`` lines are not literals. Exemptions live in ``brand_allowlist.toml`` with the line that looks the string up.
"""

import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import brandgate  # noqa: E402
import cppstrings  # noqa: E402

ROOT = HERE.parents[1]
CAP = re.compile(r"(?<![A-Za-z])(Mixar|Mixie)")
PROSE_LOWER = re.compile(r"(?<![\w.\-/$:@~_])mixar(?![\w.\-/:$@_])")
SUFFIXES = (".cc", ".hh", ".h", ".c", ".cpp", ".mm", ".hpp")


def flagged(lit):
    if CAP.search(lit) and (re.search(r"\s", lit) or "/" in lit or "\\" in lit or lit in ("Mixar", "Mixie")):
        return True
    return bool(re.search(r"\s", lit) and PROSE_LOWER.search(lit))


def hits_in_text(text):
    lines = text.split("\n")
    return [(n, lit) for n, lit in cppstrings.literals(text) if flagged(lit) and not re.match(r"\s*#\s*include", lines[n - 1])]


def native_files(base=ROOT):
    for r in ("src/source", "src/intern"):
        for dp, _dn, fn in os.walk(base / r):
            for f in fn:
                if f.endswith(SUFFIXES):
                    yield pathlib.Path(dp) / f


def test_no_native_string_literal_shows_the_upstream_brand():
    allow = brandgate.load()
    offenders = []
    for p in native_files():
        rel = p.relative_to(ROOT).as_posix()
        for n, lit in hits_in_text(p.read_text(encoding="utf-8", errors="replace")):
            if not brandgate.is_allowed(allow, rel, lit):
                offenders.append(f"{rel}:{n}: {lit[:70]!r}")
    assert offenders == [], f"{len(offenders)}:\n" + "\n".join(offenders[:80])


def test_the_scanner_ignores_comments_includes_and_identifiers_and_sees_the_rest():
    text = ('// "Mixar" in a comment\n/* and "Mixie" too */\n#include "GHOST_MixarX11.hh"\nconst char *a = "SpaceMixie";\nconst char *b = "rna_uiLayoutMixarStyle";\n'
            'const char *c = "Open a Mixar file";\nconst char *d = "Mixie";\nconst char *e = "%s/Mixar/%s";\nconst char *f = "Cannot read mixar file";\nconst char *g = "//Mixar is not a comment";\n')
    assert [n for n, _ in hits_in_text(text)] == [6, 7, 8, 9, 10]
