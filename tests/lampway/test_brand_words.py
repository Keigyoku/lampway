# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""G2 + G3: the user-visible-string gate, widened to everything a person can read.

G1 (test_no_mixar_in_ui_strings) scans the client's own package for the capital word ``Mixar``. This file adds:

* G2 -- the same AST scan over ``src/scripts/startup`` (Blender's own menus), ``server/lampway_server`` and ``scripts/**/*.py``;
* G3 -- the words the first gate never looked for: ``Mixie`` (the upstream agent's name) and lowercase ``mixar`` used as a word in prose (a string
  with spaces: ``"reconnect mixar"``), in all of the above. A lowercase ``mixar`` that is a whole token or sits in a path/identifier position
  (``mixar.camera_project``, ``~/.mixar``, ``mixar_*``, ``X-Mixar-*``) is an internal name and is the business of the identity-leak gate (G8).

Exemptions live in ``brand_allowlist.toml`` with a reason (G9); the approved attribution wording of ``brand.py`` is exempt by construction.
"""

import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import brandgate  # noqa: E402
import test_no_mixar_in_ui_strings as g1  # noqa: E402
from mixar.config import brand  # noqa: E402

CAP = re.compile(r"(?<![\w-])(Mixar|Mixie)(?![\w-])")
PROSE_LOWER = re.compile(r"(?<![\w.\-/$:@~_])mixar(?![\w.\-/:$@_])")
APPROVED = (brand.ATTRIBUTION_SHORT, brand.ATTRIBUTION_LONG)
ROOTS = ("src/scripts/mixar", "src/scripts/startup", "server/lampway_server", "scripts")


def hits_in(path, text_lines=None):
    """(line number, literal) for every user-visible literal of ``path`` that breaks G2/G3."""
    out = []
    for line, value in g1._visible_strings(path):
        if value in APPROVED:
            continue
        if CAP.search(value) or g1.DOMAIN.search(value) or (re.search(r"\s", value) and PROSE_LOWER.search(value)):
            out.append((line, value))
    return out


def _files(roots=ROOTS, base=ROOT):
    for r in roots:
        scan_root = base / r
        for dp, dirs, fn in os.walk(scan_root):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests", "testing")]
            for f in fn:
                if f.endswith(".py"):
                    yield pathlib.Path(dp) / f


def test_no_user_visible_string_names_the_upstream_brand_or_its_agent():
    allow = brandgate.load()
    offenders = []
    for path in _files():
        rel = path.relative_to(ROOT).as_posix()
        for line, value in hits_in(path):
            if any(rel.endswith(k) and value == v for k, v in g1.ALLOW):
                continue
            if brandgate.is_allowed(allow, rel, value):
                continue
            offenders.append(f"{rel}:{line}: {value[:80]!r}")
    assert offenders == [], f"{len(offenders)}:\n" + "\n".join(offenders[:60])


def test_the_translation_catalogs_do_not_carry_the_upstream_agent_name():
    offenders = []
    for po in (ROOT / "src/scripts/mixar/modules/common/i18n/locale").glob("*.po"):
        for n, line in enumerate(po.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith(("msgid", "msgstr", '"')) and not line.startswith('"X-') and CAP.search(line):
                offenders.append(f"{po.name}:{n}: {line[:70]}")
    assert offenders == [], offenders[:20]


def test_the_scan_sees_planted_offenders_in_every_root_and_ignores_identifiers(tmp_path):
    for r in ROOTS:
        d = tmp_path / r
        d.mkdir(parents=True)
        (d / "x.py").write_text('A = "Open Mixie"\nB = "reconnect mixar now"\nC = "mixar.camera_project"\nD = "~/.mixar"\nE = "mixar"\nF = "MIXIE"\nG = "X-Mixar-Id"\n')
    seen = {r: [v for _l, v in hits_in(next(_files((r,), tmp_path)))] for r in ROOTS}
    assert all(v == ["Open Mixie", "reconnect mixar now"] for v in seen.values()), seen


def test_brand_scan_excludes_only_test_descendants_of_each_scan_root(tmp_path):
    base = tmp_path / 'tests' / 'testing' / 'checkout'
    root = base / ROOTS[0]
    root.mkdir(parents=True)
    production = root / 'production.py'
    production.write_text('A = "Open Mixie"\n')
    for name in ('tests', 'testing', '__pycache__'):
        nested = root / name
        nested.mkdir()
        (nested / 'fixture.py').write_text('A = "Open Mixie"\n')
    assert list(_files((ROOTS[0],), base)) == [production]
    assert [v for _line, v in hits_in(production)] == ['Open Mixie']
