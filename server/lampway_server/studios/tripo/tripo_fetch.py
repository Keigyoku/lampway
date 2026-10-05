#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/studios/tripo/tripo_fetch.py, sha256 b09e9899d16a) on 2026-10-05, SERVER side: it drives the owner's Tripo Studio
# login in the persistent tool browser (CDP), which the app never does. The header below, with its invariants (credits,
# settings read back before every generation, actions on saved copies only), is the original's. Nothing here runs unless the
# studio guard is armed (studios/guard.py); tests run against recorded fixtures only.
# SPIKE (2026-10-04): download the variants of one Tripo Studio generation from the captain's asset list, in the persistent
# tool browser (relief-browser, CDP 9333). The asset cards carry their creation stamp ("10-04 15:34"); every card with the
# given stamp is clicked, the signed output_mesh URL the viewer then loads is captured, and the file is fetched with the
# page's own request context (a stripped, unsigned URL answers 403). Quad Smart Meshes load as output_mesh_<id>.fbx; Triangle
# ones as tripo_model_<id>_meshopt.glb (EXT_meshopt_compression, quantised: a viewer copy, not the Export file). Read-only on Studio: it clicks thumbnails, nothing else.
# Usage: <relief venv python> tripo_fetch.py <out_dir> "<MM-DD HH:MM>" [--expect 4]
# Writes variant<k>.<ext> and variants.json (asset index, faces shown, url, sha256, bytes, credits shown); never overwrites.
import argparse, hashlib, json, os, re, sys
from lampway_server.studios import axi as ax
from lampway_server.studios.tripo import studio
from lampway_server.studios import guard
ME = '-m lampway_server.studios.tripo.tripo_fetch'

CDP = studio.CDP


def main():
    if len(sys.argv) == 1:
        ax.home(__file__, 'Download the 4 variants of one Tripo Studio generation (by card stamp) via the viewer; read-only on Studio'); ax.kv(studio.live())
        ax.helps(['python -m lampway_server.studios.tripo.tripo_fetch.py <out_dir> "<MM-DD HH:MM>" [--expect 4]']); return
    ap = argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('stamp'); ap.add_argument('--expect', type=int, default=4)
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    if os.path.exists(os.path.join(a.out, 'variants.json')): ax.refuse(f'{a.out}/variants.json exists; never overwritten', [f'{studio.PY} {ME} <new_out_dir> "<MM-DD HH:MM>"'])
    from patchright.sync_api import sync_playwright
    out = []
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(CDP); ctx = b.contexts[0]; pg = next(x for x in ctx.pages if 'studio.tripo3d.ai' in x.url)
        seen = []
        pg.on('response', lambda r: seen.append(r.url) if re.search(r'(output_mesh_[0-9a-f-]+\.(fbx|glb|obj)|tripo_model_[0-9a-f-]+_meshopt\.glb)(\?|$)', r.url) else None)
        items = pg.locator(f'text={a.stamp}'); n = items.count()
        if n != a.expect: ax.refuse(f'{n} asset cards stamped {a.stamp!r}, expected {a.expect}', [f'{studio.PY} {ME}'])
        for rnd in range(3):                                            # a card already cached by the viewer may load nothing new: reload and retry
            for k in range(n):
                before = len(seen); items.nth(k).click(); pg.wait_for_timeout(5000)
                t = pg.evaluate("()=>document.body.innerText"); fc = re.search(r'Faces\s*\n*\s*(\d+)', t); tp = re.search(r'Topology\s*\n*\s*(Quad|Triangle)\s*\n*\s*Faces', t)
                if rnd == 0: out.append({'asset': k, 'faces_shown': fc and int(fc.group(1)), 'topology_shown': tp and tp.group(1), 'urls': []})
                out[k]['urls'] += seen[before:]
            if all(o['urls'] for o in out): break
            pg.reload(wait_until='load'); pg.wait_for_timeout(5000); items = pg.locator(f'text={a.stamp}')
        credits = re.findall(r'\b(\d{3,6})\b', pg.evaluate("()=>document.body.innerText.slice(0,400)"))
        for o in out:
            if not o['urls']: o['error'] = 'no mesh URL seen'; o.pop('urls'); continue
            u = o['urls'][-1]; resp = ctx.request.get(u, timeout=180000); data = resp.body()
            ext = os.path.splitext(u.split('?')[0])[1]; fn = f"variant{o['asset'] + 1}{ext}"
            open(os.path.join(a.out, fn), 'wb').write(data)
            o.update(url=u.split('?')[0], file=fn, status=resp.status, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()); o.pop('urls')
    json.dump({'stamp': a.stamp, 'credits_shown': int(credits[0]) if credits else None, 'variants': out}, open(os.path.join(a.out, 'variants.json'), 'w'), indent=1)
    ok = [o for o in out if o.get('file')]; ax.kv({'variants': f'{len(ok)}/{len(out)} downloaded', 'credits': credits[0] if credits else None, 'record': os.path.join(a.out, 'variants.json')})
    ax.table('variants', [{'file': o['file'], 'faces': o['faces_shown'], 'topology': o['topology_shown']} for o in ok], ['file', 'faces', 'topology'])
    ax.helps([f'python3 -m lampway_server.studios.tripo.seed_db.py ingest-variants {os.path.join(a.out, "variants.json")} <piece>', 'blender -b -P tools/proportion/mesh_to_npz.py -- <out.npz> piece <variant>'])


if __name__ == '__main__':
    main()
