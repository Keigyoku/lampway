#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/studios/tripo/tripo_regen.py, sha256 b775fb92e404) on 2026-10-05, SERVER side: it drives the owner's Tripo Studio
# login in the persistent tool browser (CDP), which the app never does. The header below, with its invariants (credits,
# settings read back before every generation, actions on saved copies only), is the original's. Nothing here runs unless the
# studio guard is armed (studios/guard.py); tests run against recorded fixtures only.
# SPIKE (2026-10-04): free seed sifting on Tripo Studio. Edit Mesh (on ORIGINALS only; the user: it survives an Edit Mesh save
# but is lost once any other tool is committed, hence other tools run on clones) regenerates the region inside its box; with the
# default full box that is a whole-piece regen = a new seed, free on the user's plan. The result shows as Previous Version /
# Current Version with Continue Editing / Apply; closing asks Discard / Save.
#   retry   <out_dir> "<MM-DD HH:MM>" <faces>  select the original by its card stamp and face count, open Edit Mesh, Retry
#           Selection with the default box, wait for Apply, download the Current Version mesh the viewer loaded, record faces
#           shown, screenshot; LEAVES THE MODAL OPEN so the seed can be scored before it is kept or thrown away.
#   sift    <out_dir> <faces> [--n 5]  n free retries on that original, each discarded (= banked in History); stops if the
#           original's face count or the credits change.
#   region  <out_dir> <faces> --bbox-blender x0,y0,z0,x1,y1,z1 [--pad m] --approved-exact-region   an EXACT-box Edit Mesh retry: the UI
#           Retry is pressed and its local_edit request carries the given box (converted to the mesh's glTF frame); modal left open.
#   harvest <out_dir> "<MM-DD HH:MM>" <faces>  download every History version (banked retries) of that original.
#   collect <out_dir>  a retry already running in the open modal: wait for it, download the Current Version mesh.
#   apply   pick Current Version, Apply (commits the new seed onto the original; the previous one stays in History).
#   discard pick Previous Version, close, Discard; verifies the original's face count is back.
#   (no args) AXI home: live Studio state (credits, selected piece, open modal/preview) and next-command templates.
# The resource-timing buffer fills at 250 entries (measured), so mesh URLs are taken from live responses, not performance entries.
import argparse, hashlib, json, os, re, sys, time

from lampway_server.studios.tripo import studio
from lampway_server.studios import guard
from lampway_server.studios.tripo import verify
CDP = studio.CDP
from lampway_server.studios import axi as ax
ME = '-m lampway_server.studios.tripo.tripo_regen'
PY = studio.PY
MESH = re.compile(r'(output_mesh_[0-9a-f-]+\.(fbx|glb|obj)|tripo_model_[0-9a-f-]+_meshopt\.glb)(\?|$)')


def page(p):
    b = p.chromium.connect_over_cdp(CDP); ctx = b.contexts[0]
    return ctx, next(x for x in ctx.pages if 'studio.tripo3d.ai' in x.url)


def faces_in(t, label):
    i = t.find(label); m = re.search(r'Faces\s*\n*\s*([\d,]+)', t[i:]) if i >= 0 else None
    return int(m.group(1).replace(',', '')) if m else None


def select(pg, stamp, faces):
    """click the asset card that shows <faces> and offers Edit Mesh; stamp '*' searches every loaded card (each Discard re-stamps
    a card, measured), else only cards with that stamp. Returns True when selected."""
    if 'Previous Version' in pg.evaluate('()=>document.body.innerText'): ax.refuse('an Edit Mesh result is still open; apply or discard it first', [f'{PY} {ME} discard', f'{PY} {ME} apply'])
    if pg.get_by_text('Restore & Edit').count(): pg.mouse.click(1242, 174); pg.wait_for_timeout(1000)   # a History preview is open: close it
    it = pg.locator('img[src*="studio_wireframe"]') if stamp == '*' else pg.locator(f'text={stamp}')
    for k in range(min(it.count(), 40)):                                # bounded
        it.nth(k).click(); pg.wait_for_timeout(4000)
        m = re.search(r'Faces\s*\n*\s*([\d,]+)', pg.evaluate('()=>document.body.innerText'))
        if m and int(m.group(1).replace(',', '')) == faces and pg.get_by_role('button', name='Edit Mesh').count(): return True
    return False


def done(pg):
    """the retry has landed when Apply is ENABLED and the Current Version shows a face count (Apply is present but disabled while
    it runs - measured: a first version broke on presence after 19 s and fetched the original)"""
    for _ in range(160):                                                # bounded: up to 40 min
        pg.wait_for_timeout(15000)
        ap = pg.get_by_role('button', name='Apply')
        if ap.count() and ap.first.is_enabled() and faces_in(pg.evaluate('()=>document.body.innerText'), 'Current Version'): break
    pg.wait_for_timeout(4000)


def state(pg):
    t = pg.evaluate('()=>document.body.innerText'); m = re.search(r'Topology\s*\n*\s*(Quad|Triangle)\s*\n*\s*Faces\s*\n*\s*([\d,/ ]+)', t)
    cr = re.findall(r'\b(\d{3,6})\b', t[:400])
    return {'credits': cr[0] if cr else None, 'selected': f'{m.group(1)} {m.group(2).strip()} faces' if m else None,
            'edit_mesh_available': bool(pg.get_by_role('button', name='Edit Mesh').count()), 'edit_result_open': 'Previous Version' in t,
            'history_preview_open': bool(pg.get_by_text('Restore & Edit').count())}


def main():
    if len(sys.argv) == 1:                                                 # AXI content first: live Studio state
        ax.home(__file__, 'Free seed sifting on Tripo Studio: full-box Edit Mesh retries on originals, banked in History, harvested for scoring')
        from patchright.sync_api import sync_playwright
        with sync_playwright() as p:
            try: ctx, pg = page(p)
            except Exception as e: ax.refuse(f'tool browser not reachable on {CDP} ({type(e).__name__})', ['systemctl --user start relief-browser'])
            ax.kv(state(pg))
        ax.helps([f'{PY} {ME} sift <out_dir> <original_faces> --n 5', f"{PY} {ME} harvest <out_dir> '*' <original_faces>",
                  f'{PY} {ME} discard --expect-faces <original_faces>', f'{PY} {ME} --help']); return
    ap = argparse.ArgumentParser(description='Tripo Studio free seed sifting (AXI: no args shows live Studio state).'); sp = ap.add_subparsers(dest='cmd', required=True)
    r = sp.add_parser('retry'); r.add_argument('out'); r.add_argument('stamp'); r.add_argument('faces', type=int)
    sf = sp.add_parser('sift'); sf.add_argument('out'); sf.add_argument('faces', type=int); sf.add_argument('--n', type=int, default=5)
    rg = sp.add_parser('region'); rg.add_argument('out'); rg.add_argument('faces', type=int)
    rg.add_argument('--bbox-blender', required=True, help='x0,y0,z0,x1,y1,z1 in the Blender-import frame (X front, Y wearer-left, Z up), as audits report')
    rg.add_argument('--pad', type=float, default=0.0, help='metres added on every side')
    rg.add_argument('--approved-exact-region', action='store_true', help='required: the user approved substituting the exact bbox into the UI Retry request')
    h = sp.add_parser('harvest'); h.add_argument('out'); h.add_argument('stamp'); h.add_argument('faces', type=int)
    c = sp.add_parser('collect'); c.add_argument('out')            # a retry already running in the open modal: wait, then download
    sp.add_parser('apply'); d = sp.add_parser('discard'); d.add_argument('--expect-faces', type=int)
    a = ap.parse_args()
    if a.cmd == 'region' and verify.region_refusal(a.approved_exact_region):                 # refused before anything else, no browser
        ax.refuse(verify.region_refusal(False), [f'{PY} {ME} region <out> <faces> --bbox-blender ... --approved-exact-region'])
    if a.cmd in ('retry', 'sift', 'region', 'apply', 'discard'):                              # these change the studio: armed runs only
        guard.require_armed(f'tripo_regen {a.cmd}')
    from patchright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx, pg = page(p)
        if a.cmd == 'retry':
            os.makedirs(a.out, exist_ok=True)
            if os.path.exists(os.path.join(a.out, 'retry.json')): ax.refuse(f'{a.out}/retry.json exists; never overwritten', [f'{PY} {ME} retry <new_out_dir> <stamp> <faces>'])
            seen = []; pg.on('response', lambda resp: seen.append(resp.url) if MESH.search(resp.url) else None)
            if not select(pg, a.stamp, a.faces): ax.refuse(f'no card ({a.stamp!r}) shows {a.faces} faces with Edit Mesh (clones have none)', [f'{PY} {ME}'])
            eb = pg.get_by_role('button', name='Edit Mesh')
            eb.first.click(); pg.wait_for_timeout(5000)
            g = pg.get_by_role('button', name='Got It')
            if g.count(): g.first.click(); pg.wait_for_timeout(800)
            credits0 = re.findall(r'\b(\d{3,6})\b', pg.evaluate('()=>document.body.innerText.slice(0,400)'))[:1]
            n0 = len(seen); pg.get_by_role('button', name='Retry Selection').first.click(); t0 = time.time()
            done(pg); txt = pg.evaluate('()=>document.body.innerText')
            new = [u for u in seen[n0:]]
            rec = {'stamp': a.stamp, 'original_faces': a.faces, 'seconds': round(time.time() - t0), 'credits_before': credits0,
                   'faces_previous': faces_in(txt, 'Previous Version'), 'faces_current': faces_in(txt, 'Current Version'), 'mesh_urls_seen': [u.split('?')[0] for u in new]}
            if new:
                resp = ctx.request.get(new[-1], timeout=180000); data = resp.body(); ext = MESH.search(new[-1]).group(0).split('.')[-1].split('?')[0]
                fn = os.path.join(a.out, f'seed.{ext}'); open(fn, 'wb').write(data)
                rec.update(file=fn, status=resp.status, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            pg.screenshot(path=os.path.join(a.out, 'compare.png'))
            json.dump(rec, open(os.path.join(a.out, 'retry.json'), 'w'), indent=1)
            ax.kv({k: rec.get(k) for k in ('seconds', 'faces_previous', 'faces_current', 'file', 'bytes')}); print(f"record: {os.path.join(a.out, 'retry.json')}")
            ax.helps([f'{PY} {ME} discard --expect-faces {a.faces}', f'{PY} {ME} apply', f"{PY} {ME} harvest <out_dir> '*' {a.faces}"])
        elif a.cmd == 'region':
            # EXACT region retry: the UI's own Retry Selection is pressed; its local_edit request (measured format: {"bbox":[[min],[max]],
            # "face_limit","project_id","source_operator_id"}) carries the box in the mesh's glTF frame (Y up), default = mesh bounds + 0.01.
            # Blender-import (X front, Y wearer-left, Z up) -> box: [[x0, z0, -y1], [x1, z1, -y0]] (all six faces matched to 0.1 mm).
            if not a.approved_exact_region: ax.refuse('exact-region substitution needs the user\'s approval flag', [f'{PY} {ME} region <out> <faces> --bbox-blender ... --approved-exact-region'])
            x0, y0, z0, x1, y1, z1 = [float(v) for v in a.bbox_blender.split(',')]; q = a.pad
            box = [[x0 - q, z0 - q, -y1 - q], [x1 + q, z1 + q, -y0 + q]]
            os.makedirs(a.out, exist_ok=True)
            if os.path.exists(os.path.join(a.out, 'region.json')): ax.refuse(f'{a.out}/region.json exists; never overwritten', [f'{PY} {ME} region <new_out> ...'])
            sent = {}
            def rewrite(route):
                body = route.request.post_data_json or {}; sent['ui_bbox'] = body.get('bbox'); body['bbox'] = box; sent['sent'] = body
                route.continue_(post_data=json.dumps(body), headers={**route.request.headers, 'content-type': 'application/json'})
            if not select(pg, '*', a.faces): ax.refuse(f'no card shows {a.faces} faces with Edit Mesh', [f'{PY} {ME}'])
            pg.route('**/v2/studio/operation/local_edit', rewrite)
            pg.get_by_role('button', name='Edit Mesh').first.click(); pg.wait_for_timeout(5000)
            g = pg.get_by_role('button', name='Got It')
            if g.count(): g.first.click(); pg.wait_for_timeout(800)
            cr = re.findall(r'\b(\d{3,6})\b', pg.evaluate('()=>document.body.innerText.slice(0,400)'))[:1]
            t0 = time.time(); pg.get_by_role('button', name='Retry Selection').first.click(); pg.wait_for_timeout(5000); pg.unroute('**/v2/studio/operation/local_edit')
            if 'sent' not in sent: ax.refuse('the local_edit request was not seen; nothing substituted (a retry may be running with the UI box)', [f'{PY} {ME} discard'])
            done(pg); txt = pg.evaluate('()=>document.body.innerText'); pg.screenshot(path=os.path.join(a.out, 'compare.png'))
            rec = {'faces': a.faces, 'bbox_blender': [x0, y0, z0, x1, y1, z1], 'pad': q, 'box_sent': box, 'ui_box_replaced': sent['ui_bbox'], 'seconds': round(time.time() - t0),
                   'credits_before': cr, 'faces_previous': faces_in(txt, 'Previous Version'), 'faces_current': faces_in(txt, 'Current Version')}
            json.dump(rec, open(os.path.join(a.out, 'region.json'), 'w'), indent=1)
            ax.kv({k: rec[k] for k in ('seconds', 'faces_previous', 'faces_current')}); print(f"record: {os.path.join(a.out, 'region.json')}")
            ax.helps([f'{PY} {ME} discard --expect-faces {a.faces}', f'{PY} {ME} apply', f"{PY} {ME} harvest <out_dir> '*' {a.faces}"])
        elif a.cmd == 'sift':
            # n free full-box retries on the original showing <faces>; each result is discarded, which banks it in History
            os.makedirs(a.out, exist_ok=True); log = os.path.join(a.out, 'sift.json'); runs = json.load(open(log)) if os.path.exists(log) else []
            for i in range(a.n):
                if not select(pg, '*', a.faces): ax.refuse(f'no original shows {a.faces} faces with Edit Mesh (rerolls done: {i}/{a.n})', [f'{PY} {ME}'])
                pg.get_by_role('button', name='Edit Mesh').first.click(); pg.wait_for_timeout(5000)
                g = pg.get_by_role('button', name='Got It')
                if g.count(): g.first.click(); pg.wait_for_timeout(800)
                cr = re.findall(r'\b(\d{3,6})\b', pg.evaluate('()=>document.body.innerText.slice(0,400)'))[:1]
                t0 = time.time(); pg.get_by_role('button', name='Retry Selection').first.click(); done(pg)
                txt = pg.evaluate('()=>document.body.innerText'); fcur = faces_in(txt, 'Current Version')
                pg.get_by_text('Previous Version', exact=True).first.click(); pg.wait_for_timeout(1000)
                pg.mouse.click(1545, 54); pg.wait_for_timeout(2500); pg.get_by_role('button', name='Discard').first.click(); pg.wait_for_timeout(4000)
                m = re.search(r'Faces\s*\n*\s*([\d,]+)', pg.evaluate('()=>document.body.innerText')); fnow = m and int(m.group(1).replace(',', ''))
                cr2 = re.findall(r'\b(\d{3,6})\b', pg.evaluate('()=>document.body.innerText.slice(0,400)'))[:1]
                runs.append({'original_faces': a.faces, 'k': i, 'seconds': round(time.time() - t0), 'faces_seed': fcur, 'faces_after_discard': fnow, 'credits': [cr, cr2],
                             'at': time.strftime('%H:%M:%S')}); json.dump(runs, open(log, 'w'), indent=1)
                print(f'reroll {i + 1}/{a.n}: seed {fcur} faces, {runs[-1]["seconds"]} s, original back to {fnow}, credits {cr[0] if cr else "-"}', flush=True)
                if fnow != a.faces: ax.refuse(f'the original reads {fnow} faces after discard, expected {a.faces}; stopped after {i + 1}/{a.n}', [f'{PY} {ME}'])
                if cr and cr2 and cr != cr2: ax.refuse(f'credits changed {cr[0]} -> {cr2[0]}; retries are meant to be free; stopped after {i + 1}/{a.n}', [f'{PY} {ME}'])
            ax.kv({'rerolls_done': f'{a.n}/{a.n}', 'banked_in_history': a.n, 'log': log}); ax.helps([f"{PY} {ME} harvest {a.out} '*' {a.faces}"])
        elif a.cmd == 'harvest':
            # every banked seed of one original: Discard keeps a retry in History as a 'local_edit' version (measured 2026-10-04);
            # a History entry clicked (not its restore/copy icons) only PREVIEWS it and the viewer loads its signed mesh URL
            # (signatures are per file, so the viewer is the only door). Downloads each version not yet in <out>.
            os.makedirs(a.out, exist_ok=True); hist = {}; seen = []
            pg.on('response', lambda resp: seen.append(resp.url) if MESH.search(resp.url) else None)
            def onh(resp):
                if '/studio/project/history/' in resp.url and '/check/' not in resp.url:
                    try: hist['j'] = resp.json()
                    except Exception: pass
            pg.on('response', onh)
            if not select(pg, a.stamp, a.faces): ax.refuse(f'no card ({a.stamp!r}) shows {a.faces} faces with Edit Mesh', [f'{PY} {ME}'])
            pg.mouse.click(1291, 390); pg.wait_for_timeout(4000)              # History (clock), measured at 1600x1100
            vers = hist.get('j', {}).get('data', {}).get('history', [])
            if not vers: ax.refuse('History API response not seen after opening History', [f'{PY} {ME}'])
            # entries are matched by POSITION: the panel lists versions in the API's order (newest first), entry 0 = 'Current
            # Version' (no stamp). Stamps are not unique: each Discard adds a copy of the original stamped like its retry (measured).
            stamps = pg.evaluate("""()=>[...document.querySelectorAll('*')].filter(e=>{const r=e.getBoundingClientRect();
                return e.children.length===0 && r.x>1100 && r.x<1320 && /^\\d\\d-\\d\\d \\d\\d:\\d\\d$/.test((e.innerText||'').trim())})
                .map((e,i)=>{e.setAttribute('data-hv', String(i)); return (e.innerText||'').trim()})""")
            got = []
            if len(stamps) != len(vers) - 1: got.append({'error': f'{len(stamps)} stamped entries in the panel for {len(vers)} versions; matching by position refused'}); vers = []
            for i, v in enumerate(vers):
                stamp = time.strftime('%m-%d %H:%M', time.localtime(v['created_at'])); fn = os.path.join(a.out, f"{v['type']}_{v['id'][:8]}")
                if i == 0 or v['type'] != 'local_edit': continue           # Current Version / originals: the copies all hold the original mesh
                if any(os.path.exists(fn + e) for e in ('.fbx', '.glb')): continue
                el = pg.locator(f'[data-hv="{i - 1}"]')
                if stamps[i - 1] != stamp: got.append({'id': v['id'], 'error': f'panel entry {i} reads {stamps[i - 1]}, API says {stamp}'}); continue
                el.scroll_into_view_if_needed(); pg.wait_for_timeout(500); bb = el.bounding_box(); n0 = len(seen)
                pg.mouse.click(bb['x'] - 20, bb['y'] + 55); pg.wait_for_timeout(6000)   # the entry's thumbnail, below its stamp
                new = [u for u in seen[n0:] if v['id'] in u]
                if not new: got.append({'id': v['id'], 'type': v['type'], 'stamp': stamp, 'error': 'no mesh URL with this id loaded'}); continue
                resp = ctx.request.get(new[-1], timeout=180000); data = resp.body(); ext = '.fbx' if '.fbx' in new[-1].split('?')[0] else '.glb'
                open(fn + ext, 'wb').write(data); fc = re.search(r'Faces\s*\n*\s*([\d,]+)', pg.evaluate('()=>document.body.innerText'))
                got.append({'id': v['id'], 'type': v['type'], 'is_retry': v['flags'].get('is_retry'), 'stamp': stamp, 'file': fn + ext, 'bytes': len(data),
                            'sha256': hashlib.sha256(data).hexdigest(), 'faces_shown': fc and int(fc.group(1).replace(',', ''))})
            pg.mouse.click(1242, 174); pg.wait_for_timeout(1000)               # close History (the preview ends with it)
            log = os.path.join(a.out, 'harvest.json'); old = json.load(open(log)) if os.path.exists(log) else []
            json.dump(old + [{'stamp': a.stamp, 'faces': a.faces, 'history': vers, 'downloaded': got}], open(log, 'w'), indent=1)
            ok = [g for g in got if g.get('file')]; bad = [g for g in got if not g.get('file')]
            ax.kv({'history_versions': len(vers), 'downloaded': len(ok), 'failed': len(bad), 'log': log})
            ax.table('seeds', [{'id': g['id'][:8], 'faces': g.get('faces_shown'), 'file': os.path.basename(g['file'])} for g in ok], ['id', 'faces', 'file'])
            if bad: ax.table('failed', [{'id': g.get('id', '-')[:8], 'error': ax.trunc(g['error'], 90)} for g in bad], ['id', 'error'])
            ax.helps([f'<blender> -b -P <lampway_tools>/scripts/proportion/mesh_to_npz.py -- <seed>.npz piece <seed file>',
                      'python3 tools/proportion/proportion_ratios.py <scores.json> <body.npz> <name>=<seed>.npz:-90 ...', f'python3 -m lampway_server.studios.tripo.seed_db.py ingest-harvest {log} <piece>'])
        elif a.cmd == 'collect':
            os.makedirs(a.out, exist_ok=True); seen = []; pg.on('response', lambda resp: seen.append(resp.url) if MESH.search(resp.url) else None)
            done(pg); txt = pg.evaluate('()=>document.body.innerText')
            rec = {'faces_previous': faces_in(txt, 'Previous Version'), 'faces_current': faces_in(txt, 'Current Version'), 'mesh_urls_seen': [u.split('?')[0] for u in seen]}
            if seen:
                resp = ctx.request.get(seen[-1], timeout=180000); data = resp.body(); fn = os.path.join(a.out, 'seed.glb'); open(fn, 'wb').write(data)
                rec.update(file=fn, status=resp.status, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            pg.screenshot(path=os.path.join(a.out, 'compare.png')); json.dump(rec, open(os.path.join(a.out, 'collect.json'), 'w'), indent=1)
            ax.kv({k: rec.get(k) for k in ('faces_previous', 'faces_current', 'file')}); ax.helps([f'{PY} {ME} discard', f'{PY} {ME} apply'])
        elif a.cmd == 'apply':
            pg.get_by_text('Current Version', exact=True).first.click(); pg.wait_for_timeout(1000)
            pg.get_by_role('button', name='Apply').first.click(); pg.wait_for_timeout(6000)
            ax.kv({'applied': True, **state(pg)}); ax.helps([f'{PY} {ME}'])
        else:
            pg.get_by_text('Previous Version', exact=True).first.click(); pg.wait_for_timeout(1000)
            pg.mouse.click(1545, 54); pg.wait_for_timeout(2500)                # the modal's close (x), measured at 1600x1100 viewport
            pg.get_by_role('button', name='Discard').first.click(); pg.wait_for_timeout(4000)
            t = pg.evaluate('()=>document.body.innerText'); m = re.search(r'Faces\s*\n*\s*([\d,]+)', t); f = m and int(m.group(1).replace(',', ''))
            ax.kv({'discarded': True, 'edit_result_open': 'Previous Version' in t, 'faces_now': f, 'banked_in_history': True})
            if a.expect_faces and f != a.expect_faces: ax.refuse(f'faces read {f}, expected {a.expect_faces}', [f'{PY} {ME}'])
            ax.helps([f"{PY} {ME} harvest <out_dir> '*' {f}"])


if __name__ == '__main__':
    main()
