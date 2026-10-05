# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Lampway fork identity: the ONE place the user-facing name, the agent's
display name, the website and the default backend live.

Lampway is a fork of the GPL Mixar client. Internal identifiers stay as
upstream wrote them (``mixar.*`` packages, ``mixie_chat`` operator ids,
keyring service names, bundle ids): only what a user sees changes, and it
changes here. The C++ side mirrors these values in
``src/source/blender/blenlib/BLI_lampway_brand.h``;
``tests/lampway/test_lampway_brand.py`` keeps the two in step.

This module must stay free of ``bpy`` and of other ``mixar`` imports:
``scripts/generate_config.py`` loads it by file path at build time, outside
Blender.
"""

#: Product name shown in the window title, menus, dialogs and notices.
PRODUCT_NAME = "Lampway"

#: Display name of the in-app agent (upstream: "Mixie"). The owner may rename it.
AGENT_NAME = "Lampway Agent"

#: The collection the agent's work lands in (the v3 harness commit). The server defines the same value once in lampway_server/brand.py; tests/lampway pins the two together.
AGENT_COLLECTION = AGENT_NAME

#: Where Lampway lives: the public GitHub repository. Every link shown to users
#: (docs, bug report, downloads, privacy policy ...) is built from it; none points
#: at upstream's website. One constant; change it here.
REPO_URL = "https://github.com/Keigyoku/lampway"
WEBSITE_URL = REPO_URL

#: Our documentation: the markdown pages in the repository's docs/lampway folder.
DOCS_URL = REPO_URL + "/blob/main/docs/lampway"

#: Our backend when no build-time or runtime configuration says otherwise.
DEFAULT_BACKEND_URL = "http://127.0.0.1:8787"

#: Runtime override of the backend (and the SSO frontend, which our server
#: also serves). Read on top of the bundled ``mixar.json``.
ENV_BACKEND_URL = "LAMPWAY_BACKEND_URL"

#: Tour language packs are served by the backend at this path.
TOUR_PACKS_PATH = "/tour-packs/manifest.json"

#: Hosts a sandboxed script may download assets from: our own local asset
#: server only. Upstream's CDN hosts (amazonaws.com, cloudflarestorage.com)
#: admitted every bucket in the world as a GET target, which is a one-way
#: channel out of the sandbox; Lampway serves its assets itself. Add hosts
#: with MIXAR_ASSET_HOSTS when a setup needs one.
DEFAULT_ASSET_HOSTS = ("127.0.0.1", "localhost")


def docs_url(page: str = "") -> str:
    """The documentation page ``page`` (docs/lampway/<page>.md); the docs index when empty."""
    page = (page or "").strip().strip("/")
    return DOCS_URL + "/" + (page if page else "README") + ".md"


#: Upstream's website paths -> where the same thing lives for Lampway.
_PAGES = {"/docs": "README", "/tutorials": "README", "/legal/privacy-policy": "privacy"}
_REPO_PATHS = {"/bug-report": "/issues/new", "/downloads": "/releases", "/about": "", "/creator-program": "", "/app/referrals": ""}


def website_url(path: str = "") -> str:
    """The Lampway page for an upstream-style path: docs pages are our markdown docs (``/docs#connect-ai-apps`` is docs/lampway/connect-ai-apps.md), the rest is
    the repository (issues, releases)."""
    path = (path or "").strip()
    if not path:
        return WEBSITE_URL
    base, _, fragment = path.partition("#")
    base = "/" + base.lstrip("/")
    if base == "/docs" and fragment:
        return docs_url(fragment)
    if base in _PAGES:
        return docs_url(_PAGES[base])
    if base in _REPO_PATHS:
        return WEBSITE_URL + _REPO_PATHS[base]
    if base.startswith("/docs/"):
        return docs_url(base[len("/docs/"):])
    return WEBSITE_URL
