# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/studios/tripo/studio.py, sha256 ff1aab55f9d3) on 2026-10-05, SERVER side: it drives the owner's Tripo Studio
# login in the persistent tool browser (CDP), which the app never does. The header below, with its invariants (credits,
# settings read back before every generation, actions on saved copies only), is the original's. Nothing here runs unless the
# studio guard is armed (studios/guard.py); tests run against recorded fixtures only.
"""Shared live state of the captain's Tripo Studio page in the persistent tool browser (relief-browser, CDP 9333), for the AXI
no-args home views of the Tripo drivers. Read-only: it never clicks."""
import re

import os
import sys

CDP = os.environ.get('LAMPWAY_STUDIO_CDP', 'http://127.0.0.1:9333')            # the persistent tool browser's debugging port
PY = os.environ.get('LAMPWAY_PYTHON_BROWSER') or sys.executable                  # a python with patchright (settings: python_browser)


def live():
    try:
        from patchright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.connect_over_cdp(CDP); pages = b.contexts[0].pages
            pg = next((x for x in pages if 'studio.tripo3d.ai' in x.url), None)
            if pg is None: return {'browser': 'up', 'studio_tab': 'not open'}
            t = pg.evaluate('()=>document.body.innerText'); cr = re.findall(r'\b(\d{3,6})\b', t[:400])
            q = next((l for l in t.split('\n') if 'Free' in l and '/' in l), None)
            m = re.search(r'Topology\s*\n*\s*(Quad|Triangle)\s*\n*\s*Faces\s*\n*\s*([\d,/ ]+)', t)
            return {'browser': 'up', 'credits': cr[0] if cr else None, 'image_quota': q, 'page': pg.url.split('/workspace/')[-1][:60],
                    'selected': f'{m.group(1)} {m.group(2).strip()} faces' if m else None}
    except Exception as e:
        return {'browser': f'unreachable ({type(e).__name__})', 'fix': 'start the tool browser (see studios/tripo/relief_gen.py ensure_browser)'}
