# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""G7: every link a user can follow leads somewhere that exists, and only to hosts we chose.

* every path ``brand.website_url()`` can produce is a page of ``site/`` (listed in ``site/sitemap.xml`` and present on disk), so the 404s of the
  rebrand audit (finding 2) cannot come back;
* every ``http(s)`` host in the client, the server, the scripts and the shipped metadata is on a short allow-list (our site and repository, the
  providers the code legitimately calls, W3C/SPDX schema namespaces, the build's dependencies). ``lampway.app`` and ``lampway.org`` are other
  people's sites and are never allowed.
"""

import pathlib
import re
import sys
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/scripts"))
from mixar.config import brand  # noqa: E402

# Everything the in-app call sites ask for (grep website_url / docs_url): the strings are the call sites' own.
CALL_SITE_PATHS = ("", "/tutorials", "/docs", "/docs#connect-ai-apps", "/bug-report", "/downloads", "/about", "/legal/privacy-policy")

HOSTS = {
    "lampway.dev": "our site", "github.com": "the repository and upstream provenance", "127.0.0.1": "loopback", "localhost": "loopback",
    "api.github.com": "release checks", "openrouter.ai": "provider", "api.anthropic.com": "provider", "auth.openai.com": "provider login",
    "api.openai.com": "provider", "chatgpt.com": "provider login", "clerk.higgsfield.ai": "provider login", "mcp.higgsfield.ai": "provider",
    "higgsfield.ai": "provider", "www.tripo3d.ai": "studio", "wavespeed.ai": "provider named in a prompt template", "www.eachlabs.ai": "provider named in a prompt template",
    "huggingface.co": "model downloads", "opencode.ai": "documentation of a connected app", "www.blender.org": "provenance", "developer.blender.org": "provenance",
    "spdx.dev": "licence tooling", "www.contributor-covenant.org": "code of conduct source", "json-schema.org": "schema namespace", "www.w3.org": "xml namespace",
    "schemas.microsoft.com": "xml namespace", "developer.nvidia.com": "build dependency", "www.apple.com": "signing certificate authority",
    "example.com": "documentation placeholder", "example.invalid": "placeholder", "api.example.test": "test placeholder",
}
SCAN = ("src/scripts/mixar", "src/scripts/startup", "server/lampway_server", "scripts", "README.md", "SECURITY.md", "SUPPORT.md", "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md", "MAINTAINERS.md", ".env.example", "src/release/freedesktop", "src/build_files/cmake/packaging.cmake")
SUFFIXES = {".py", ".sh", ".bat", ".md", ".xml", ".desktop", ".cmake", ".example", ".toml", ".json"}
SKIP_PARTS = {"tests", "testing", "locale", "__pycache__"}
URL = re.compile(r"https?://([A-Za-z0-9.\-]+)")


def _site_pages():
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [e.text for e in ET.parse(ROOT / "site/sitemap.xml").getroot().findall("s:url/s:loc", ns)]
    return {urlparse(loc).path for loc in locs}


def _hosts_in(files):
    out = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for m in URL.finditer(line):
                out.append((str(f.relative_to(ROOT)), n, m.group(1)))
    return out


def _files(roots):
    for r in roots:
        p = ROOT / r
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and f.suffix in SUFFIXES and not SKIP_PARTS & set(f.relative_to(ROOT).parts):
                    yield f


def test_every_website_url_is_a_page_of_our_site():
    pages = _site_pages()
    for path in CALL_SITE_PATHS:
        url = urlparse(brand.website_url(path))
        assert url.netloc == "lampway.dev", (path, url)
        assert (url.path or "/") in pages, f"{path!r} -> {url.path} is not in site/sitemap.xml"
        page = ROOT / "site" / url.path.strip("/") / "index.html" if url.path.strip("/") else ROOT / "site/index.html"
        assert page.is_file(), page
        if url.fragment:
            assert f'id="{url.fragment}"' in page.read_text(encoding="utf-8"), (path, url.fragment)
    assert urlparse(brand.docs_url()).path == "/docs/"
    assert brand.docs_url("connect-ai-apps") == brand.website_url("/docs#connect-ai-apps")


def test_unknown_paths_land_on_the_site_root_never_a_404():
    assert brand.website_url("/no-such-page") == brand.WEBSITE_URL


def test_every_host_in_shipped_source_is_allowed():
    offenders = [f"{p}:{n}: {h}" for p, n, h in _hosts_in(_files(SCAN)) if h not in HOSTS]
    assert offenders == [], offenders[:40]


def test_the_host_gate_sees_a_planted_offender(tmp_path):
    f = tmp_path / "x.py"
    f.write_text('A = "https://lampway.app/docs"\nB = "https://lampway.dev/docs/"\nC = "https://www.mixar.app"\n')
    sys.modules[__name__].ROOT, saved = tmp_path, ROOT
    try:
        bad = [h for _p, _n, h in _hosts_in([f]) if h not in HOSTS]
    finally:
        sys.modules[__name__].ROOT = saved
    assert bad == ["lampway.app", "www.mixar.app"]
