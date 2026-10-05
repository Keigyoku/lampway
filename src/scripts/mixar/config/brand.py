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

#: PLACEHOLDER website for every link shown to users (docs, bug report,
#: downloads, privacy policy, referrals ...). One constant; change it here.
WEBSITE_URL = "https://lampway.app"

#: Our backend when no build-time or runtime configuration says otherwise.
DEFAULT_BACKEND_URL = "http://127.0.0.1:8787"

#: Runtime override of the backend (and the SSO frontend, which our server
#: also serves). Read on top of the bundled ``mixar.json``.
ENV_BACKEND_URL = "LAMPWAY_BACKEND_URL"

#: Tour language packs are served by the backend at this path.
TOUR_PACKS_PATH = "/tour-packs/manifest.json"

#: Hosts a sandboxed script may download assets from. The upstream CDNs stay;
#: loopback is added so our local asset server works out of the box.
DEFAULT_ASSET_HOSTS = ("amazonaws.com", "cloudflarestorage.com", "127.0.0.1", "localhost")


def website_url(path: str = "") -> str:
    """``WEBSITE_URL`` joined with ``path`` (leading slash optional)."""
    path = (path or "").strip()
    if not path:
        return WEBSITE_URL
    return WEBSITE_URL + "/" + path.lstrip("/")
