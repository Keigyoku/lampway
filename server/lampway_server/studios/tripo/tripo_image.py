#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/studios/tripo/tripo_image.py, sha256 95ef20e7547a) on 2026-10-05, SERVER side: it drives the owner's Tripo Studio
# login in the persistent tool browser (CDP), which the app never does. The header below, with its invariants (credits,
# settings read back before every generation, actions on saved copies only), is the original's. Nothing here runs unless the
# studio guard is armed (studios/guard.py); tests run against recorded fixtures only.
# SPIKE (2026-10-04): Tripo Studio image generation on the captain's subscription (free image quota, 1000/month), driven in
# the persistent tool browser (relief-browser, CDP 9333; the captain logged in there). His hard rules (memory
# tripo-studio-invariants): a reload resets settings, so EVERY setting is set and then READ BACK from the page right
# before Generate, and the run refuses on any mismatch; every generation takes maximum value - 4 images, 4K on - and
# refuses if the displayed price is not 0 (free quota).
# Usage: <relief venv python> tripo_image.py <out_dir> <prompt_file> [--ref <image>]... [--model "GPT Image 2.5"]
#        [--aspect 1:1] [--count 4] [--no-4k] [--dry-run]
# Writes <out_dir>/<n>.png (full resolution as served) and run.json (settings read back, prompt, reference sha256, image
# URLs and sha256, the quota before and after). --dry-run sets and verifies everything but does not click Generate.
import argparse, hashlib, json, os, sys, time, datetime, urllib.request
from lampway_server.studios import axi as ax
from lampway_server.studios.tripo import studio
from lampway_server.studios import guard
from lampway_server.studios.tripo import verify
ME = '-m lampway_server.studios.tripo.tripo_image'

CDP = studio.CDP
sha = lambda b: hashlib.sha256(b).hexdigest()


def panel_text(pg):
    return pg.evaluate("""()=>{const t=document.querySelector('textarea'); let p=t; for(let i=0;i<8&&p;i++) p=p.parentElement; return p?p.innerText:''}""")


def state(pg):
    return pg.evaluate("""()=>{
      const B=[...document.querySelectorAll('button')].filter(b=>b.getBoundingClientRect().x<400);
      const on=t=>{const b=B.find(b=>b.innerText.trim()===t); return b? b.getAttribute('data-state'):null};
      const sw=document.querySelector('[role=switch]'); const cb=document.querySelector('[role=combobox]');
      const price=[...document.querySelectorAll('*')].filter(e=>e.children.length===0&&e.getBoundingClientRect().x<400&&/^[0-9]+$/.test((e.innerText||'').trim())&&e.className&&String(e.className).includes('text-3')&&!e.closest('button'))
                  .map(e=>({v:+e.innerText.trim(), struck:getComputedStyle(e).textDecorationLine.includes('line-through')}));
      return {model: cb? cb.innerText.trim():null, aspects: Object.fromEntries(['1:1','16:9','9:16','4:3','3:4'].map(a=>[a,on(a)])),
              counts: Object.fromEntries(['1','2','3','4'].map(c=>[c,on(c)])), fourk: sw? sw.getAttribute('aria-checked'):null,
              prompt: (document.querySelector('textarea')||{}).value||'', price};
    }""")


def main():
    if len(sys.argv) == 1:
        ax.home(__file__, 'Tripo Studio image generation (GPT Image 2.5, 4 images, 4K, free quota); every setting read back before Generate'); ax.kv(studio.live())
        ax.helps(['python -m lampway_server.studios.tripo.tripo_image.py <out_dir> <prompt_file> [--ref <image>]... --dry-run']); return
    ap = argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('prompt_file'); ap.add_argument('--ref', action='append', default=[])
    ap.add_argument('--model', default='GPT Image 2.5'); ap.add_argument('--aspect', default='1:1'); ap.add_argument('--count', default='4')
    ap.add_argument('--no-4k', action='store_true'); ap.add_argument('--dry-run', action='store_true'); a = ap.parse_args()
    if verify.image_count_refusal(a.count): ax.refuse(verify.image_count_refusal(a.count), [f'{studio.PY} {ME} <out_dir> <prompt_file> --count 4'])
    prompt = open(a.prompt_file).read().strip(); os.makedirs(a.out, exist_ok=True)
    if os.path.exists(os.path.join(a.out, 'run.json')): ax.refuse(f'{a.out}/run.json exists; never overwritten', [f'{studio.PY} {ME} <new_out_dir> <prompt_file> --dry-run'])
    from patchright.sync_api import sync_playwright
    rec = {'tool': 'tripo_image.py', 'date': datetime.datetime.now().isoformat(timespec='seconds'), 'prompt': prompt,
           'refs': [{'file': os.path.abspath(r), 'sha256': sha(open(r, 'rb').read())} for r in a.ref]}
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(CDP); ctx = b.contexts[0]
        pg = next(x for x in ctx.pages if 'studio.tripo3d.ai' in x.url); pg.set_viewport_size({'width': 1600, 'height': 1100})
        pg.reload(wait_until='load', timeout=90000); pg.wait_for_timeout(4000)   # a clean page: nothing left attached by an earlier run; all settings set below
        if '/generate-image/' not in pg.url: pg.get_by_text('Image', exact=True).first.click(); pg.wait_for_timeout(3000)
        pg.wait_for_selector('textarea', timeout=60000)
        rec['quota_before'] = next((l for l in panel_text(pg).split('\n') if 'Free' in l and '/' in l), None)
        # set everything (a reload resets it)
        before_imgs = pg.evaluate("()=>[...document.querySelectorAll('img')].map(i=>i.src)")
        for k, r in enumerate(a.ref, 1):                                 # references FIRST: a finished upload resets the aspect (measured 2026-10-04)
            pg.locator('input[type=file]').first.set_input_files(r)
            for _ in range(60):                                          # wait until the thumbnail is really there (an upload after a reload is slower)
                pg.wait_for_timeout(1000)
                if len([x for x in pg.evaluate("()=>[...document.querySelectorAll('img')].filter(i=>i.getBoundingClientRect().x<400&&i.complete&&i.naturalWidth>0).map(i=>i.src)") if x not in before_imgs]) >= k: break
            pg.wait_for_timeout(2000)
        after_imgs = pg.evaluate("()=>[...document.querySelectorAll('img')].filter(i=>i.getBoundingClientRect().x<400).map(i=>i.src)")
        cb = pg.locator('[role=combobox]').first
        if a.model not in (cb.inner_text() or ''):
            cb.click(); pg.wait_for_timeout(800); pg.get_by_role('option').filter(has_text=a.model).first.click(); pg.wait_for_timeout(800)
        for label, group in ((a.aspect, 'aspects'), (a.count, 'counts')):   # set, read back, retry
            for _ in range(3):
                if state(pg)[group].get(label) == 'on': break
                pg.evaluate("t=>{const b=[...document.querySelectorAll('button')].find(b=>b.innerText.trim()===t&&b.getBoundingClientRect().x<400&&b.offsetParent);if(b)b.click()}", label)
                pg.wait_for_timeout(600)                                 # the visible panel button by exact text (a hidden duplicate '1:1' exists)
        sw = pg.locator('[role=switch]').first
        if (sw.get_attribute('aria-checked') == 'true') == a.no_4k: sw.click(); pg.wait_for_timeout(500)
        ta = pg.locator('textarea').first; ta.fill(prompt); pg.wait_for_timeout(500)
        ref_thumbs = [s for s in after_imgs if s not in before_imgs]
        st = state(pg); rec['settings_read_back'] = st; rec['ref_thumbnails_seen'] = len(ref_thumbs)
        # verify everything, right before Generate
        bad = verify.image_problems(st, model=a.model, aspect=a.aspect, count=a.count, no_4k=a.no_4k, prompt=prompt, n_refs=len(a.ref), n_ref_thumbs=len(ref_thumbs))
        if bad:
            rec['refused'] = bad; json.dump(rec, open(os.path.join(a.out, 'run.json'), 'w'), indent=1); ax.refuse('; '.join(bad), [f'{studio.PY} {ME} <out_dir> <prompt_file> --dry-run'])
        if a.dry_run:
            rec['dry_run'] = True; json.dump(rec, open(os.path.join(a.out, 'run.json'), 'w'), indent=1); ax.kv({'dry_run': 'verified', 'model': st['model'], '4k': st['fourk'], 'price': st['price']}); ax.helps([f'{studio.PY} {ME} <out_dir> <prompt_file> <same refs, no --dry-run>']); return
        guard.require_armed('generating images (Tripo Studio)')      # after the dry run: only an armed run clicks Generate
        got = []
        def onres(r):
            ct = r.headers.get('content-type') or ''
            if r.request.resource_type == 'image' and ('tripo' in r.url) and ct.startswith('image/') and r.url.split('?')[0] not in [g['url'] for g in got]:
                got.append({'url': r.url.split('?')[0], 'full': r.url, 'ct': ct})
        pg.on('response', onres)
        imgs0 = set(pg.evaluate("()=>[...document.querySelectorAll('img')].map(i=>i.src.split('?')[0])"))
        pg.get_by_role('button', name='Generate Image').last.click(); t0 = time.time()
        new = []
        while time.time() - t0 < 600:
            pg.wait_for_timeout(5000)
            cur = pg.evaluate("()=>[...document.querySelectorAll('img')].filter(i=>i.naturalWidth>=1024).map(i=>({src:i.src, w:i.naturalWidth, h:i.naturalHeight}))")
            new = [c for c in cur if c['src'].split('?')[0] not in imgs0]
            if len(new) >= int(a.count): break
        rec['seconds'] = round(time.time() - t0); rec['images'] = []
        for k, c in enumerate(new[:int(a.count)]):
            data = urllib.request.urlopen(urllib.request.Request(c['src'], headers={'User-Agent': 'Mozilla/5.0'}), timeout=120).read()
            ext = '.png' if data[:4] == b'\x89PNG' else ('.webp' if data[8:12] == b'WEBP' else '.jpg')
            fn = f'{k + 1}{ext}'; open(os.path.join(a.out, fn), 'wb').write(data)
            rec['images'].append({'file': fn, 'url': c['src'].split('?')[0], 'w': c['w'], 'h': c['h'], 'bytes': len(data), 'sha256': sha(data)})
        rec['quota_after'] = next((l for l in panel_text(pg).split('\n') if 'Free' in l and '/' in l), None)
        json.dump(rec, open(os.path.join(a.out, 'run.json'), 'w'), indent=1)
        ax.kv({'images': len(rec['images']), 'seconds': rec['seconds'], 'quota': f"{rec['quota_before']} -> {rec['quota_after']}", 'record': os.path.join(a.out, 'run.json')})
        ax.table('images', [{'file': i['file'], 'w': i['w'], 'h': i['h']} for i in rec['images']], ['file', 'w', 'h'])
        ax.helps(['python3 tools/texlib/fidelity.py <v3_plate.png> <out_dir>/*.jpg'])


if __name__ == '__main__':
    main()
