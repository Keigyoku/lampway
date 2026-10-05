# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""No production source may name the upstream hosted service.

Every ``mixar.app`` literal (api, www, cdn) goes through configuration:
the backend through ``mixar.config.config.get_server_url`` and the web
links through ``mixar.config.brand.website_url``. This scanner is the
gate: a new literal fails here before it ships.

Scope: the shipped source trees (``src``, ``scripts``, ``cmake``) and the
root build inputs. Test trees, the QA harness, the legacy embedded test
suite and the translation catalogs are not production code and are
excluded; this file lives under ``tests`` and is therefore excluded too.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Word boundary: ``mixar.apply_forest_theme`` is an operator id, not a host.
HOST = re.compile(r"mixar\.app\b")
BRAND_LICENCE = re.compile(r"LicenseRef-Mixar-Brand")

SUFFIXES = {
    ".py", ".cc", ".hh", ".h", ".c", ".cmake", ".sh", ".bat", ".xml", ".desktop",
    ".plist", ".rc", ".toml", ".svg", ".json", ".in", ".txt", ".example",
}
ROOTS = ("src", "scripts", "cmake", ".env.example", "REUSE.toml", "Makefile")
EXCLUDED_NAMES = {"pii_allow.txt", "prepublish_gate.py"}      # the PII gate lists the upstream domain to ALLOW it and plants fake hosts for its self-test
EXCLUDED_PARTS = {"tests", "qa", "testing", "__pycache__", "locale", "upstream", "LICENSES"}


def _production_files():
    for root in ROOTS:
        path = ROOT / root
        if path.is_file():
            yield path
            continue
        for file in path.rglob("*"):
            if not file.is_file():
                continue
            if EXCLUDED_PARTS & set(file.relative_to(ROOT).parts) or file.name in EXCLUDED_NAMES:
                continue
            if file.suffix in SUFFIXES or file.name in ("CMakeLists.txt", "Makefile"):
                yield file


def _hits(pattern):
    hits = []
    for file in _production_files():
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{file.relative_to(ROOT)}:{number}: {line.strip()[:120]}")
    return hits


def test_scanner_sees_the_production_trees():
    files = list(_production_files())
    rels = {str(f.relative_to(ROOT)) for f in files}
    assert "src/scripts/mixar/config/config.py" in rels
    assert "src/source/creator/creator_startup.cc" in rels
    assert "src/scripts/startup/bl_ui/space_topbar.py" in rels
    assert not any("tests/" in r for r in rels)


def test_no_production_source_names_the_mixar_hosts():
    assert _hits(HOST) == []


def test_no_file_claims_the_mixar_brand_licence():
    assert _hits(BRAND_LICENCE) == []
    assert not (ROOT / "LICENSES" / "LicenseRef-Mixar-Brand.txt").exists()
