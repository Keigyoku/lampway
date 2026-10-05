#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/studios/tripo/tripo_texture.py, sha256 522d313b796d) on 2026-10-05, SERVER side: it
# drives the owner's Tripo Studio login in the persistent tool browser (CDP), which the app never does. The header below, with
# its invariants, is the original's. Without --go nothing is clicked but the panel's own controls (set + read back); --go
# additionally needs the studio guard armed (studios/guard.py), and the check functions live in verify.py, tested against the
# owner's recorded dry run. The Blender that extracts the maps comes from LAMPWAY_BLENDER (the app's own binary when the app
# runs the tool).
# SPIKE (2026-10-05): Tripo Studio Texture + PBR on the SELECTED model (captain's login, tool browser CDP 9333). Promoted from the
# chest1 test scripts (scratch/scratch-tmp/tripo_texture/). Rules (memory tripo-studio-invariants):
#   - TEXTURING COMES LAST: refuses unless the selected model's History holds a Smart UV step (texture fills the Smart UV islands;
#     anything done after a texture discards it). Act on a saved COPY (the clone), never the original.
#   - every setting is set and READ BACK before Generate; refuses on any mismatch (measured: a first script read aria-checked
#     'true' as off and switched Remove Lighting OFF before a 30-credit run - the captain cancelled it, credits refunded).
#   - price read from the button and refused unless it equals --expect-price.
# Verbs:
#   state                                         settings, price, history stamps (no clicks beyond opening panels)
#   refs  --front F --left L --right R --back B   replace the 4 reference images (default: the generation plates)
#   texture --res 8K [--remove-lighting] --expect-price 30 [--go] [--out DIR]   (without --go: set + verify only)
#   pbr --expect-price 5 [--go] [--out DIR]
#   restore --stamp "MM-DD HH:MM"                 make that History version current (free; the current one stays in History)
# Each --go run logs the network responses and downloads the produced FBX to --out, then extracts its maps (via Blender).
# Measured on chest1 (2026-10-05): Texture 8K = 30 credits, ~4 min; PBR = 5 credits, ~1 min (8K base + 4K normal/rough/metal);
# both keep the Smart UV layout and the face count, so the maps drop onto our patched mesh (texlib/pbr_merge.py).
import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request

from lampway_server.studios import axi as _ax
from lampway_server.studios import guard
from lampway_server.studios.tripo import studio, verify

ME = '-m lampway_server.studios.tripo.tripo_texture'
BLENDER = os.environ.get('LAMPWAY_BLENDER', 'blender')

PANEL_JS = """() => {
  const sw = document.querySelector('.ml-auto.group.rounded-full');
  const res = [...document.querySelectorAll('*')].filter(e => ['2K','4K','8K'].includes(e.textContent.trim()) && e.children.length <= 1)
     .map(e => { const b = e.closest('[data-state]'); return {t: e.textContent.trim(), on: b ? b.getAttribute('data-state') === 'on' : null}; });
  const g = [...document.querySelectorAll('button')].find(b => /Generate (Texture|PBR)/.test(b.innerText));
  return {remove_lighting: sw ? sw.getAttribute('aria-checked') : null, res, button: g ? g.innerText.replace(/\\s+/g, ' ').trim() : null, disabled: g ? g.disabled : null};
}"""
HISTORY_JS = """() => { const out = []; const title = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && e.textContent.trim() === 'History');
  let panel = title; for (let i = 0; i < 8 && panel; i++) { if (panel.getBoundingClientRect().height > 250) break; panel = panel.parentElement; }
  if (!panel) return out;
  const cards = [...panel.querySelectorAll('*')].filter(e => e.children.length === 0 && /^\\d\\d-\\d\\d \\d\\d:\\d\\d$|^Current Version$/.test(e.textContent.trim()));
  for (const c of cards) { let k = c; for (let i = 0; i < 6 && k; i++) { if (k.getBoundingClientRect().height > 100) break; k = k.parentElement; }
    const icon = k ? [...k.querySelectorAll('div')].map(d => d.className.toString()).find(x => /i-tripo:/.test(x) && !/time-past|back|copy/.test(x)) : null;
    out.push({stamp: c.textContent.trim(), icon: icon ? icon.match(/i-tripo:[a-z-]+/)[0] : null}); } return out; }"""


def parse_args(argv):
    ap = argparse.ArgumentParser(prog='tripo_texture')
    sub = ap.add_subparsers(dest='verb', required=True)
    sub.add_parser('state')
    r = sub.add_parser('refs')
    for v in ('front', 'left', 'right', 'back'):
        r.add_argument('--' + v)
    r.add_argument('--views', default='front,left,right,back')      # 'front,back' for a paired piece: only those slots are filled
    r.add_argument('--set', default='custom', choices=('generation', 'painted', 'custom'))
    r.add_argument('--out')
    t = sub.add_parser('texture')
    t.add_argument('--res', choices=('2K', '4K', '8K'), required=True)
    t.add_argument('--remove-lighting', action='store_true')
    t.add_argument('--expect-price', type=int, required=True)
    t.add_argument('--go', action='store_true')
    t.add_argument('--out')
    p = sub.add_parser('pbr')
    p.add_argument('--expect-price', type=int, required=True)
    p.add_argument('--go', action='store_true')
    p.add_argument('--out')
    s = sub.add_parser('restore')
    s.add_argument('--stamp', required=True)
    return ap.parse_args(argv)


async def page(pw):
    b = await pw.chromium.connect_over_cdp(studio.CDP)
    ctx = b.contexts[0]
    pg = next((x for x in ctx.pages if 'studio.tripo3d' in x.url), None)
    if not pg:
        _ax.refuse('no Tripo Studio tab in the tool browser', ['open studio.tripo3d.ai in the tool browser window'])
    await pg.bring_to_front()
    return pg


async def open_tool(pg, name):
    await pg.get_by_text(name, exact=True).first.click()
    await pg.wait_for_timeout(2000)


async def history(pg):
    pos = await pg.evaluate("""() => { const e = [...document.querySelectorAll('div')].find(d => /i-tripo:(history|time-past)/.test(d.className.toString())); if (!e) return null; const r = (e.closest('button') || e).getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2]; }""", isolated_context=False)
    is_open = await pg.evaluate("() => [...document.querySelectorAll('*')].some(e => e.children.length === 0 && e.textContent.trim() === 'History')", isolated_context=False)
    if pos and not is_open:
        await pg.mouse.click(*pos)
        await pg.wait_for_timeout(1500)
    return await pg.evaluate(HISTORY_JS, isolated_context=False)


async def guard_uv(pg):
    h = await history(pg)
    problem = verify.texturing_last_refusal(h)
    if problem:
        _ax.refuse(problem, ['Smart UV the clone first, then texture'])
    return h


async def run_and_fetch(pg, out, timeout_s=1100):
    guard.require_armed('generating a texture or PBR set (Tripo Studio, credits)')
    os.makedirs(out, exist_ok=True)
    urls = []
    pg.on('response', lambda r: urls.append({'url': r.url, 'status': r.status}) if ('.fbx' in r.url or 'operation' in r.url) else None)
    btn = pg.locator('button', has_text='Generate').first
    await btn.click()
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        await pg.wait_for_timeout(10000)
        if time.time() - t0 > 40 and not await btn.is_disabled():
            break
    await pg.wait_for_timeout(4000)
    await pg.screenshot(path=os.path.join(out, 'done.png'))
    json.dump(urls, open(os.path.join(out, 'responses.json'), 'w'), indent=1)
    fbx = [u['url'] for u in urls if '.fbx' in u['url'] and u['status'] == 200]
    if not fbx:
        _ax.refuse('no FBX in the responses (cancelled or failed?)', [f'see {out}/done.png'])
    dst = os.path.join(out, 'model.fbx')
    urllib.request.urlretrieve(fbx[-1], dst)
    code = f"""import bpy
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.fbx(filepath={dst!r})
o = [o for o in bpy.data.objects if o.type == 'MESH'][0]; print('MESH', len(o.data.polygons), [u.name for u in o.data.uv_layers])
for n in o.data.materials[0].node_tree.nodes:
    if n.type == 'TEX_IMAGE' and n.image:
        to = [l.to_socket.name for x in n.outputs for l in x.links]; tag = {{'Base Color': 'BaseColor', 'Roughness': 'Roughness', 'Metallic': 'Metallic', 'Color': 'Normal'}}.get(to[0] if to else '', 'Map')
        n.image.filepath_raw = {out!r} + '/' + tag + '.png'; n.image.file_format = 'PNG'; n.image.save(); print('MAP', tag, n.image.size[:])"""
    res = subprocess.run(['nice', '-n', '15', BLENDER, '-b', '--python-expr', code], capture_output=True, text=True, timeout=900)
    lines = [ln for ln in res.stdout.splitlines() if ln.startswith(('MESH', 'MAP'))]
    return {'seconds': round(time.time() - t0), 'fbx': dst, 'extracted': lines}


async def main(a):
    from patchright.async_api import async_playwright
    async with async_playwright() as pw:
        pg = await page(pw)
        if a.verb == 'state':
            await open_tool(pg, 'Texture')
            st = await pg.evaluate(PANEL_JS, isolated_context=False)
            h = await history(pg)
            _ax.kv({'texture_panel': json.dumps(st)})
            _ax.table('history', h, ['stamp', 'icon'])
            return
        if a.verb == 'restore':
            await history(pg)
            pos = await pg.evaluate("""(stamp) => { const t = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && e.textContent.trim() === stamp); if (!t) return null;
                let card = t; for (let i = 0; i < 6 && card; i++) { if (card.getBoundingClientRect().height > 100) break; card = card.parentElement; }
                const b = [...card.querySelectorAll('div')].find(d => /i-tripo:back/.test(d.className.toString())); if (!b) return null; const r = b.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2]; }""", a.stamp, isolated_context=False)
            if not pos:
                _ax.refuse(f'no restorable History card stamped {a.stamp!r}', [f'{studio.PY} {ME} state'])
            await pg.mouse.click(*pos)
            await pg.wait_for_timeout(2500)
            _ax.kv({'restored': a.stamp})
            return
        if a.verb == 'refs':
            await open_tool(pg, 'Texture')
            for _ in range(8):
                pos = await pg.evaluate("""() => { const d = [...document.querySelectorAll('div.i-tripo\\\\:delete')].map(e => e.closest('button')).filter(b => b && b.getBoundingClientRect().x < 400); if (!d.length) return null; const r = d[d.length-1].getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2]; }""", isolated_context=False)
                if not pos:
                    break
                await pg.mouse.move(*pos)
                await pg.wait_for_timeout(300)
                await pg.mouse.click(*pos)
                await pg.wait_for_timeout(800)
            slots = [v for v in a.views.split(',') if v]
            files = {v: getattr(a, v) for v in slots}
            if any(not f for f in files.values()):
                _ax.refuse(f'refs needs a file for each of: {slots}', [])
            for f in files.values():
                await pg.locator('input[type=file][accept*="image"]').first.set_input_files(f)
                await pg.wait_for_timeout(4000)
            n = await pg.evaluate("() => [...document.querySelectorAll('input[type=file][accept*=\"image\"]')].length", isolated_context=False)
            if n:
                _ax.refuse(f'{n} reference slot(s) still empty after upload', [])
            if a.out:
                os.makedirs(a.out, exist_ok=True)
                with open(os.path.join(a.out, 'refs.json'), 'w') as fh:
                    json.dump(verify.refs_receipt(files, a.set), fh, indent=1)
            _ax.kv({'refs': f"{', '.join(slots)} uploaded", 'set': a.set})
            return
        if a.verb == 'texture':
            await open_tool(pg, 'Texture')
            await guard_uv(pg)
            await pg.get_by_text(a.res, exact=True).first.click()
            await pg.wait_for_timeout(600)
            st = await pg.evaluate(PANEL_JS, isolated_context=False)
            if (st['remove_lighting'] == 'true') != a.remove_lighting:
                await pg.locator('.ml-auto.group.rounded-full').first.click()
                await pg.wait_for_timeout(800)
            st = await pg.evaluate(PANEL_JS, isolated_context=False)
            bad = verify.texture_problems(st, res=a.res, remove_lighting=a.remove_lighting, expect_price=a.expect_price)
            _ax.kv({'settings': json.dumps(st), 'verified': not bad})
            if bad:
                _ax.refuse('; '.join(bad), [])
        if a.verb == 'pbr':
            await open_tool(pg, 'PBR')
            await guard_uv(pg)
            await open_tool(pg, 'PBR')
            st = await pg.evaluate(PANEL_JS, isolated_context=False)
            bad = verify.pbr_problems(st, expect_price=a.expect_price)
            _ax.kv({'button': st['button'], 'verified': not bad})
            if bad:
                _ax.refuse('; '.join(bad), [])
        if not a.go:
            _ax.helps([f'{studio.PY} {ME} {a.verb} ... --go --out <dir>   (needs LAMPWAY_STUDIO_ARMED=1: it spends credits)'])
            return
        if not a.out:
            _ax.refuse('--go needs --out', [])
        res = await run_and_fetch(pg, a.out)
        _ax.kv(res)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        _ax.home(__file__, 'Tripo Studio Texture + PBR on the selected (Smart UV) model; every setting read back; texturing-last guard')
        _ax.kv(studio.live())
        _ax.helps([f'{studio.PY} {ME} state', f'{studio.PY} {ME} texture --res 8K --remove-lighting --expect-price 30 [--go --out DIR]',
                   f'{studio.PY} {ME} pbr --expect-price 5 [--go --out DIR]'])
        raise SystemExit(0)
    asyncio.run(main(parse_args(sys.argv[1:])))
