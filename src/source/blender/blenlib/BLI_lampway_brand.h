/* SPDX-FileCopyrightText: 2026 Lampway contributors
 *
 * SPDX-License-Identifier: GPL-3.0-or-later */

/** \file
 * \ingroup bli
 *
 * LAMPWAY: the fork's user-facing identity, mirrored from
 * `src/scripts/mixar/config/brand.py` (the Python side is the source of
 * truth; `tests/lampway/test_lampway_brand.py` pins the two together).
 * Only what a user sees changes: internal identifiers, keyring service
 * names, bundle ids and file extensions stay as upstream wrote them.
 */

#pragma once

/** Product name: window title, platform dialogs, file filters. */
#define LAMPWAY_PRODUCT_NAME "Lampway"

/** Display name of the in-app agent (upstream: "Mixie"). */
#define LAMPWAY_AGENT_NAME "Lampway Agent"

/** OS keyring service for the login pair (Lampway's own; see brand.py KEYRING_SERVICE). */
#define LAMPWAY_KEYRING_SERVICE "LampwaySafeStorage"

/** PLACEHOLDER website every user-facing link is built from. */
#define LAMPWAY_WEBSITE_URL "https://lampway.dev"
