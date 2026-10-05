# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The brand gate: no user-visible string says "Mixar".

User-visible = every string literal in the Python client that is not a docstring, plus the docstring of an operator / panel / menu class (Blender shows it as its tooltip),
plus every msgid / msgstr of the translation catalogs. A URL on upstream's domains fails wherever it appears in a string. KEPT on purpose (and allow-listed below): GPL
copyright and SPDX attribution (they are comments, which this gate does not read), NOTICE / provenance files, the internal package and module names (`mixar.*`), operator
ids (`mixar.xyz`), the protocol field names the client speaks (X-Mixar-* headers, MIXAR_* environment variables, `mixar_*` MCP tool names: none match the word rule because
they are one token), and the folder names that mirror what the native code computes (appdir.cc names the config and cache folders "Mixar")."""

import ast
import os
import pathlib
import re
import warnings

ROOT = pathlib.Path(__file__).resolve().parents[2]
CLIENT = ROOT / "src/scripts/mixar"
WORD = re.compile(r"(?<![\w-])(Mixar|MIXAR)(?![\w-])")
DOMAIN = re.compile(r"mixar\.(app|ai|com|io)\b", re.I)

#: (path suffix, literal) pairs that must stay: they mirror the native side's folder names.
from mixar.config import brand  # noqa: E402

APPROVED = (brand.ATTRIBUTION_SHORT, brand.ATTRIBUTION_LONG)

ALLOW = {
    ("common/updates/constants.py", "Mixar"),
    ("common/updates/core/app_paths.py", "Mixar"),
}


def _is_ui_class(node) -> bool:
    return isinstance(node, ast.ClassDef) and any(
        (isinstance(b, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("bl_idname", "bl_label") for t in b.targets))
        or (isinstance(b, ast.AnnAssign) and getattr(b.target, "id", "") in ("bl_idname", "bl_label")) for b in node.body)


def _visible_strings(path):
    warnings.filterwarnings("ignore")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return
    docs = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body and isinstance(n.body[0], ast.Expr) \
                and isinstance(getattr(n.body[0], "value", None), ast.Constant) and isinstance(n.body[0].value.value, str):
            docs[id(n.body[0].value)] = _is_ui_class(n)
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and not (id(n) in docs and not docs[id(n)]):
            yield n.lineno, n.value


def _client_files():
    for dp, _dn, fn in os.walk(CLIENT):
        if "__pycache__" in dp or os.sep + "tests" in dp or os.sep + "testing" in dp:
            continue
        for f in fn:
            if f.endswith(".py"):
                yield pathlib.Path(dp) / f


def test_no_user_visible_python_string_says_mixar():
    offenders = []
    for path in _client_files():
        rel = path.relative_to(CLIENT).as_posix()
        for line, value in _visible_strings(path):
            if value in APPROVED:
                continue  # the approved attribution wording, defined once in brand.py
            if (WORD.search(value) or DOMAIN.search(value)) and not any(rel.endswith(k) and value == v for k, v in ALLOW):
                offenders.append(f"{rel}:{line}: {value[:90]!r}")
    assert offenders == [], f"{len(offenders)} user-visible strings still say Mixar (use brand.PRODUCT_NAME or 'Lampway'):\n" + "\n".join(offenders[:40])


def test_the_translation_catalogs_say_lampway_not_mixar():
    offenders = []
    for po in (CLIENT / "modules/common/i18n/locale").glob("*.po"):
        for n, line in enumerate(po.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith(("msgid", "msgstr", '"')) and not line.startswith('"X-Mixar') and WORD.search(line):
                offenders.append(f"{po.name}:{n}: {line[:80]}")
    assert offenders == [], offenders[:20]


def test_no_link_points_at_upstreams_website():
    from mixar.config import brand
    for url in (brand.website_url(), brand.website_url("/docs"), brand.website_url("/docs#connect-ai-apps"), brand.website_url("/bug-report"), brand.website_url("/downloads"),
                brand.docs_url("connect-ai-apps")):
        assert "mixar" not in url.lower(), url


def test_the_gate_sees_a_planted_offender(tmp_path):
    """The falsifier: a file with a user-visible Mixar string is reported, an attribution comment and a protocol token are not."""
    p = tmp_path / "x.py"
    p.write_text('# SPDX-FileCopyrightText: Mixar contributors\nclass Op(Operator):\n    """Open Mixar"""\n    bl_idname = "mixar.open"\n    bl_label = "Open Mixar"\n'
                 'HEADER = "X-Mixar-Locale"\nENV = "MIXAR_SANDBOX"\nTOOL = "mixar_guide"\nNOTE = "Sign in to Mixar"\n')
    hits = [v for _l, v in _visible_strings(p) if WORD.search(v)]
    assert sorted(hits) == ["Open Mixar", "Open Mixar", "Sign in to Mixar"], hits
