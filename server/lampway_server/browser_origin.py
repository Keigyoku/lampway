# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The served pages are no-referrer (brand_page), so a browser serializes the Origin of their own form posts as "null". Its
Sec-Fetch-Site, which no page can set, says whether the post came from this origin."""


def own_page_post(request) -> bool:
    """A form post from one of this server's own pages: Origin "null" with the browser's Sec-Fetch-Site: same-origin."""
    return request.headers.get("origin") == "null" and request.headers.get("sec-fetch-site") == "same-origin"
