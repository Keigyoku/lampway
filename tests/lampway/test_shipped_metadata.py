# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""G5: the files a user or a packager reads first say Lampway.

A fixed list of shipped metadata (desktop entry, AppStream, plist, rc, installer templates, packaging, settings, README, the governance documents) must
contain no upstream host or handle, no ``lampway.app`` (somebody else's site), and the words ``Mixar``/``Mixie`` only inside the two approved attribution
sentences of ``brand.py`` (matched verbatim, so a paraphrase does not pass). Lowercase ``mixar`` in an identifier or path position (``mixar.json``,
``com.mixar.mixar``, ``MIXAR_ENV``) is an internal name and is the business of the identity-leak and runtime gates.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import brandgate  # noqa: E402
sys.path.insert(0, str(ROOT / "src/scripts"))
from mixar.config import brand  # noqa: E402

FILES = (
    "src/release/freedesktop/mixar.desktop", "src/release/freedesktop/org.mixar.Mixar.metainfo.xml", "src/release/darwin/Mixar.app/Contents/Info.plist",
    "src/release/windows/icons/winmixar.rc", "src/release/windows/installer_wix/WIX.template", "src/release/windows/msix/AppxManifest.xml.template",
    "src/build_files/cmake/packaging.cmake", "scripts/unix/settings.sh", "scripts/windows/settings.bat", ".env.example", "README.md", "SECURITY.md",
    "SUPPORT.md", "CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "MAINTAINERS.md",
)
BANNED = re.compile(r"mixar\.app|@mixar\.app|discord\.gg|youtube\.com/@mixar|lampway\.app|Mixar-AI(?!/mixar-app\b)", re.I)
WORD = re.compile(r"(?<![\w.\-/@])(Mixar|Mixie)(?![\w])")


def _scrub(text):
    return text.replace(brand.ATTRIBUTION_LONG, "").replace(brand.ATTRIBUTION_SHORT, "")


def violations(path, text, allow=()):
    out = []
    for n, line in enumerate(_scrub(text).splitlines(), 1):
        if (BANNED.search(line) or WORD.search(line)) and not brandgate.is_allowed(allow, path, line):
            out.append(f"{path}:{n}: {line.strip()[:110]}")
    return out


def test_shipped_metadata_names_no_upstream_host_and_no_stray_brand():
    found = []
    for rel in FILES:
        p = ROOT / rel
        if p.exists():
            found += violations(rel, p.read_text(encoding="utf-8", errors="replace"), brandgate.load())
    assert found == [], found


def test_the_readme_carries_the_approved_sentences_verbatim():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert brand.ATTRIBUTION_SHORT in readme and brand.ATTRIBUTION_LONG in readme


def test_the_gate_sees_a_paraphrase_and_a_planted_host():
    paraphrase = brand.ATTRIBUTION_LONG.replace("began as a fork of", "started life as a fork of")
    assert violations("x.md", paraphrase), "a reworded attribution must not pass"
    assert violations("x.md", brand.ATTRIBUTION_SHORT + "\nSee https://www.mixar.app/downloads\nSupport: ajay@mixar.app\n") == [
        "x.md:2: See https://www.mixar.app/downloads", "x.md:3: Support: ajay@mixar.app"]
    assert violations("x.md", "Open in Mixar") != [] and violations("x.md", "id com.mixar.mixar, MIXAR_ENV, ~/.mixar, mixar.json") == []
