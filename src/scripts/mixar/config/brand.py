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

#: The OS keyring service the login pair is stored under (macOS Keychain service, Secret Service attribute, Windows credential target suffix). Lampway's
#: own, so a stock Mixar install on the same machine is neither read nor overwritten. The C++ side names the same value (LAMPWAY_KEYRING_SERVICE); there is
#: deliberately NO migration of an old token: it is a credential for another backend.
KEYRING_SERVICE = "LampwaySafeStorage"

#: The approved attribution wording (specs/brand/REBRAND.md section 8), the ONE place the text lives. Splash and About show the short line; the README
#: footer and NOTICE carry the long one. tests/lampway/test_shipped_metadata.py matches both verbatim in the files that ship them.
ATTRIBUTION_SHORT = (
    "Lampway is an independent open-source project, started from the GPL-licensed Mixar client and built on Blender. "
    "Not affiliated with or endorsed by Mixar, Adeveda Enterprises Private Limited or the Blender Foundation."
)
ATTRIBUTION_LONG = (
    "Lampway is free software under GPL-3.0-or-later. It began as a fork of the Mixar desktop client (github.com/Mixar-AI/mixar-app, copyright Adeveda "
    "Enterprises Private Limited, GPL-3.0-or-later), which is itself a custom build of Blender 5.2 (blender.org, GPL-2.0-or-later). Upstream copyright and "
    "licence notices are kept as the GPL requires. The texture-paint module builds on ucupaint by ucupumar (GPL-3.0-or-later). Lampway is not affiliated "
    "with, endorsed by or supported by Mixar, Mixar Inc, Adeveda Enterprises Private Limited or the Blender Foundation. Blender is a registered trademark "
    "of the Blender Foundation in the EU and USA; Mixar and Mixie are trademarks or pending trademarks of Adeveda Enterprises Private Limited. They are "
    "named here only to say where this software came from."
)

#: Where Lampway's code lives: the public GitHub repository (provenance, source, issues).
REPO_URL = "https://github.com/Keigyoku/lampway"

#: Where Lampway's pages live. Every link shown to users (docs, bug report, downloads, privacy policy ...) is built from it; none points at
#: upstream's website. tests/lampway/test_site_links.py requires every page below to exist in the repository's site/ folder.
WEBSITE_URL = "https://lampway.dev"

#: Our documentation.
DOCS_URL = WEBSITE_URL + "/docs/"

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
    """The documentation page ``page``: a section of the docs page (``connect-ai-apps``), the privacy policy, or the docs index when empty."""
    page = (page or "").strip().strip("/")
    if page == "privacy":
        return WEBSITE_URL + "/legal/privacy-policy/"
    return DOCS_URL + ("#" + page if page else "")


#: Paths the client asks for (upstream's names, kept as the call sites' vocabulary) -> the page of our site that serves them.
_PAGES = {
    "/tutorials": "/tutorials/", "/docs": "/docs/", "/bug-report": "/bug-report/", "/downloads": "/downloads/", "/about": "/about/",
    "/legal/privacy-policy": "/legal/privacy-policy/",
}


def website_url(path: str = "") -> str:
    """The Lampway page for a path (``/docs#connect-ai-apps`` is the docs page at that anchor); anything unknown is the site root, never a 404."""
    path = (path or "").strip()
    if not path:
        return WEBSITE_URL
    base, _, fragment = path.partition("#")
    page = _PAGES.get("/" + base.strip("/"))
    if page is None:
        return WEBSITE_URL
    return WEBSITE_URL + page + ("#" + fragment if fragment else "")
