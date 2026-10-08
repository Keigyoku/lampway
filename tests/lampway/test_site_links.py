# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""G7: every link a user can follow leads somewhere that exists, and only to hosts we chose.

* every path ``brand.website_url()`` can produce is in ``src/scripts/mixar/config/site_routes.txt`` (the route list of the lampway-site repository), so the 404s of the
  rebrand audit (finding 2) cannot come back;
* every ``http(s)`` host in the client, the server, the scripts and the shipped metadata is on a short allow-list (our site and repository, the
  providers the code legitimately calls, W3C/SPDX schema namespaces, the build's dependencies). ``lampway.app`` and ``lampway.org`` are other
  people's sites and are never allowed.
"""

import pathlib
import re
import sys
from urllib.parse import urlparse

import pytest

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
    "queue.fal.run": "provider: the fal queue (specs/mrmak/12, behind the job receipts and egress)", "fal.ai": "provider: fal's site, named in the price-source note",
    "api.fal.ai": "provider: fal's model/price API", "rest.alpha.fal.ai": "provider: fal's storage upload API",
    "api.meshy.ai": "studio REST API (Meshy)", "api.hyper3d.com": "studio REST API (Hyper3D / Rodin)", "api.hitem3d.ai": "studio REST API (Hi3D)",
    "openapi.tripo3d.ai": "studio REST API (Tripo)", "api.worldlabs.ai": "provider: World Labs (wave 6 world_gen; egress route world_labs)",
    "ambientcg.com": "CC0 materials (asset_seed_cc0, the cc0:ambientcg egress route)", "docs.ambientcg.com": "the ambientCG licence page, recorded per asset",
    "api.polyhaven.com": "CC0 assets (asset_seed_cc0, the cc0:polyhaven egress route)", "polyhaven.com": "Poly Haven asset pages and its licence page",
    "creativecommons.org": "the CC0 1.0 deed, recorded on the licence row",
    "example.com": "documentation placeholder", "example.invalid": "placeholder", "api.example.test": "test placeholder",
}
SCAN = ("src/scripts/mixar", "src/scripts/startup", "server/lampway_server", "scripts", "README.md", "SECURITY.md", "SUPPORT.md", "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md", "MAINTAINERS.md", ".env.example", "src/release/freedesktop", "src/build_files/cmake/packaging.cmake")
SUFFIXES = {".py", ".sh", ".bat", ".md", ".xml", ".desktop", ".cmake", ".example", ".toml", ".json"}
SKIP_PARTS = {"tests", "testing", "locale", "__pycache__"}
SKIP_FILES = {"pii_allow.txt", "prepublish_gate.py"}       # the PII gate's own self-test plants fake hosts
URL = re.compile(r"https?://([A-Za-z0-9.\-]+)")
FULL_URL = re.compile(r"https?://[A-Za-z0-9.\-]+[^\s<>\"')\]]*")
# Attribution in these two static corpus files is not runtime egress permission.
# Keep the exact packaged source pins and versioned documentation references.
CORPUS = "server/lampway_server/blender_docs/data/"
STATIC_REFERENCES = {
    CORPUS + "manifest.json": {
        "https://projects.blender.org/blender/blender-manual.git",
        "https://projects.blender.org/lab/blender_mcp.git",
        "https://projects.blender.org/blender/blender.git",
        "https://projects.blender.org/blender/blender/commit/fbe6228777e7d9afefcd61a413844e790ae75db7",
        "https://projects.blender.org/blender/blender-manual/commit/4a3be8f9ed3b66b24913e0a0d491d3429a70ea08",
        "https://docs.blender.org/api/5.2/",
        "https://docs.blender.org/manual/en/5.2/",
    },
    CORPUS + "NOTICE.md": {
        "https://projects.blender.org/blender/blender-manual",
        "https://projects.blender.org/lab/blender_mcp",
    },
}


def _site_pages():
    """The checked-in route list (kept in sync with the lampway-site repository)."""
    lines = (ROOT / "src/scripts/mixar/config/site_routes.txt").read_text(encoding="utf-8").splitlines()
    return {l.strip() for l in lines if l.strip() and not l.startswith("#")}


def _links_in(files):
    out = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for m in FULL_URL.finditer(line):
                out.append((str(f.relative_to(ROOT)), n, m.group(0)))
    return out


def _hosts_in(files):
    return [(p, n, URL.match(url).group(1)) for p, n, url in _links_in(files)]


def _host_offenders(files):
    return [f"{p}:{n}: {URL.match(url).group(1)}" for p, n, url in _links_in(files)
            if URL.match(url).group(1) not in HOSTS and url not in STATIC_REFERENCES.get(p, ())]


def _files(roots):
    for r in roots:
        p = ROOT / r
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and f.suffix in SUFFIXES and f.name not in SKIP_FILES and not SKIP_PARTS & set(f.relative_to(ROOT).parts):
                    yield f


def test_every_website_url_is_a_page_of_our_site():
    pages = _site_pages()
    for path in CALL_SITE_PATHS:
        url = urlparse(brand.website_url(path))
        assert url.netloc == "lampway.dev", (path, url)
        assert (url.path or "/") in pages, f"{path!r} -> {url.path} is not in site_routes.txt"
    assert urlparse(brand.docs_url()).path == "/docs/"
    assert brand.docs_url("connect-ai-apps") == brand.website_url("/docs#connect-ai-apps")


def test_unknown_paths_land_on_the_site_root_never_a_404():
    assert brand.website_url("/no-such-page") == brand.WEBSITE_URL


def test_every_host_in_shipped_source_is_allowed():
    offenders = _host_offenders(_files(SCAN))
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


def test_packaged_attribution_is_exact_and_keeps_the_global_host_gate():
    files = [ROOT / p for p in STATIC_REFERENCES]
    references = [(p, url) for p, _n, url in _links_in(files)
                  if URL.match(url).group(1) not in HOSTS]
    assert len(references) == 10
    assert set(references) == {(p, url) for p, urls in STATIC_REFERENCES.items() for url in urls}
    assert _host_offenders(files) == []
    assert "projects.blender.org" not in HOSTS and "docs.blender.org" not in HOSTS


@pytest.mark.parametrize("path", tuple(STATIC_REFERENCES))
def test_every_static_reference_is_refused_in_runtime_source(tmp_path, monkeypatch, path):
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    runtime = tmp_path / "server/lampway_server/runtime.py"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("\n".join(sorted(STATIC_REFERENCES[path])))
    assert len(_host_offenders([runtime])) == len(STATIC_REFERENCES[path])


@pytest.mark.parametrize("url", (
    "https://docs.blender.org/api/5.3/",
    "https://projects.blender.org/blender/blender/commit/0000000000000000000000000000000000000000",
    "https://docs.blender.org/api/5.2/?redirect=https://example.invalid",
    "https://docs.blender.org.example.invalid/api/5.2/",
    "https://projects.blender.org/api/upload",
    "https://docs.blender.org/api/5.2/#unrecorded-fragment",
))
def test_static_reference_exception_rejects_changed_urls(tmp_path, monkeypatch, url):
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    manifest = tmp_path / (CORPUS + "manifest.json")
    manifest.parent.mkdir(parents=True)
    manifest.write_text(url)
    assert len(_host_offenders([manifest])) == 1


def test_an_allowed_reference_does_not_hide_an_extra_url_on_its_line(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    notice = tmp_path / (CORPUS + "NOTICE.md")
    notice.parent.mkdir(parents=True)
    notice.write_text("https://projects.blender.org/lab/blender_mcp https://projects.blender.org/api/upload")
    assert _host_offenders([notice]) == [f"{CORPUS}NOTICE.md:1: projects.blender.org"]


def test_official_documentation_inventory_does_not_allow_lookalike_hosts(tmp_path):
    f = tmp_path / (CORPUS + "manifest.json")
    f.parent.mkdir(parents=True)
    f.write_text('{"source": "https://projects.blender.org/blender/blender.git",\n'
                 ' "api": "https://docs.blender.org/api/5.2/",\n'
                 ' "lookalike": "https://docs.blender.org.example.invalid/api/5.2/"}\n')
    sys.modules[__name__].ROOT, saved = tmp_path, ROOT
    try:
        bad = _host_offenders([f])
    finally:
        sys.modules[__name__].ROOT = saved
    assert bad == [f"{CORPUS}manifest.json:3: docs.blender.org.example.invalid"]
