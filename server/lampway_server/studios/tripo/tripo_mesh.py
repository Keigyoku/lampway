#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/studios/tripo/tripo_mesh.py, sha256 c8f38de9d488) on 2026-10-05, SERVER side: it drives the owner's Tripo Studio
# login in the persistent tool browser (CDP), which the app never does. The header below, with its invariants (credits,
# settings read back before every generation, actions on saved copies only), is the original's. Nothing here runs unless the
# studio guard is armed (studios/guard.py); tests run against recorded fixtures only.
# SPIKE (2026-10-04): Tripo Studio Smart Mesh from four cardinal views, on the user's subscription, in the persistent
# tool browser (relief-browser, CDP 9333). His hard rules (memory tripo-studio-invariants): a reload resets settings, so the
# page is reloaded and EVERY setting set and READ BACK right before Generate, refusing on any mismatch; maximum value per
# generation - Smart Mesh, the topology's MAXIMUM polycount read from the slider (Quad 25000; the page defaults to 5000 at the
# same price), refused if a lower count is asked, 4 generations (never fewer);
# the price shown must equal --expect-price (default 100) or the run refuses. Privacy is the user's setting: recorded,
# never changed. Multi-View takes exactly the four cardinal views (the user).
# Usage: <relief venv python> tripo_mesh.py <out_dir> --front F --left L --right R --back B [--polycount max]
#        [--topology Quad|Triangle] [--expect-price 100] [--dry-run]
# Writes run.json (settings read back, inputs sha256, credits before/after, mesh URLs seen) and any meshes the viewer loads.
import argparse, hashlib, json, os, re, sys, time, datetime, urllib.request
from lampway_server.studios import axi as ax
from lampway_server.studios.tripo import studio
from lampway_server.studios import guard
from lampway_server.studios.tripo import verify
ME = '-m lampway_server.studios.tripo.tripo_mesh'

CDP = studio.CDP
sha = lambda b: hashlib.sha256(b).hexdigest()
LEFTTXT = """()=>[...document.querySelectorAll('*')].filter(e=>{const r=e.getBoundingClientRect(); return r.x>70&&r.x<460&&r.y>60&&r.width>0&&e.children.length===0&&(e.innerText||'').trim()}).map(e=>(e.innerText||'').trim()).join(' | ')"""


def credits(pg):
    t = pg.evaluate("()=>document.body.innerText.slice(0,400)"); m = re.findall(r'\b(\d{3,6})\b', t)
    return int(m[0]) if m else None


def slots(pg):
    """{label: file input index} by nearest label above/at each image input in the Multi-View box"""
    return pg.evaluate("""()=>{const ins=[...document.querySelectorAll('input[type=file]')].filter(i=>i.accept.includes('image')&&i.getBoundingClientRect().x<400);
      const labs=[...document.querySelectorAll('*')].filter(e=>e.children.length===0&&['Front','Left','Right','Back'].includes((e.innerText||'').trim())&&e.getBoundingClientRect().x<400);
      const out={}; for(const l of labs){const lr=l.getBoundingClientRect(); let best=null,bd=1e9;
        ins.forEach((i,k)=>{const r=i.closest('div').getBoundingClientRect(); const cx=r.x+r.width/2, cy=r.y+r.height/2; const d=Math.hypot(cx-(lr.x+lr.width/2), cy-(lr.y+lr.height/2)); if(d<bd){bd=d;best=k}});
        out[l.innerText.trim()]=best} return out}""")


def main():
    if len(sys.argv) == 1:
        ax.home(__file__, 'Tripo Studio Smart Mesh from four cardinal views at maximum value (4 variants, topology max polycount); every setting read back before Generate'); ax.kv(studio.live())
        ax.helps(['python -m lampway_server.studios.tripo.tripo_mesh.py <out_dir> --front F --left L --right R --back B [--topology Quad|Triangle] --dry-run']); return
    ap = argparse.ArgumentParser(); ap.add_argument('out')
    for v in ('front', 'left', 'right', 'back'): ap.add_argument('--' + v, required=True)
    ap.add_argument('--polycount', default='max'); ap.add_argument('--topology', default='Quad'); ap.add_argument('--expect-price', default='100')
    ap.add_argument('--dry-run', action='store_true'); a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if os.path.exists(os.path.join(a.out, 'run.json')): ax.refuse(f'{a.out}/run.json exists; never overwritten', [f'{studio.PY} {ME} <new_out_dir> --front F --left L --right R --back B --dry-run'])
    files = {'Front': a.front, 'Left': a.left, 'Right': a.right, 'Back': a.back}
    rec = {'tool': 'tripo_mesh.py', 'date': datetime.datetime.now().isoformat(timespec='seconds'),
           'inputs': {k: {'file': os.path.abspath(f), 'sha256': sha(open(f, 'rb').read())} for k, f in files.items()}}
    from patchright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(CDP); ctx = b.contexts[0]
        pg = next(x for x in ctx.pages if 'studio.tripo3d.ai' in x.url); pg.set_viewport_size({'width': 1600, 'height': 1100})
        pg.reload(wait_until='load', timeout=90000); pg.wait_for_timeout(4000)
        pg.evaluate("()=>{const e=[...document.querySelectorAll('*')].find(e=>e.children.length<=2&&(e.innerText||'').trim()==='Model'&&e.getBoundingClientRect().x<90); if(e) e.click()}")
        pg.wait_for_timeout(3000); rec['credits_before'] = credits(pg)
        pg.locator('button').filter(has_text=re.compile(r'^\s*Smart Mesh\s*$')).first.click(); pg.wait_for_timeout(1500)
        # the Multi-View input (the four labelled slots)
        for _ in range(4):
            if all(k in pg.evaluate(LEFTTXT) for k in ('Front', 'Left', 'Right', 'Back')): break
            btns = pg.evaluate("""()=>[...document.querySelectorAll('button')].map(b=>b.getBoundingClientRect())
              .filter(r=>r.x<320&&r.width>=36&&r.width<=64&&r.height>=20&&r.height<=36&&r.y>130&&r.y<260)   // the input-type icons (49x28 px), one row
              .sort((a,b)=>a.x-b.x).map(r=>[r.x+r.width/2, r.y+r.height/2])""")
            if len(btns) >= 2: pg.mouse.click(*btns[1]); pg.wait_for_timeout(1500)
        sl = slots(pg); rec['slot_map'] = sl
        if sorted(sl) != ['Back', 'Front', 'Left', 'Right']: ax.refuse(f'Multi-View slots not found: {sl}', [f'{studio.PY} {ME}'])
        ins = pg.locator('input[type=file][accept*=image]')
        for lab, f in files.items():                                    # re-read the map each time: a filled slot replaces its input
            cur = slots(pg)
            if lab not in cur: ax.refuse(f'slot {lab} not found before its upload: {cur}', [f'{studio.PY} {ME}'])
            ins.nth(cur[lab]).set_input_files(f); pg.wait_for_timeout(3000)
        for _ in range(60):                                             # all four thumbnails really there
            n = pg.evaluate("()=>[...document.querySelectorAll('img')].filter(i=>i.getBoundingClientRect().x<400&&i.getBoundingClientRect().y>120&&i.getBoundingClientRect().y<520&&i.complete&&i.naturalWidth>0).length")
            if n >= 4: break
            pg.wait_for_timeout(1000)
        rec['thumbnails_seen'] = n
        # topology + polycount (set, read back)
        pg.get_by_text('Topology', exact=True).first.click(); pg.wait_for_timeout(1200)
        pg.locator('button').filter(has_text=re.compile(r'^\s*' + a.topology)).first.click(); pg.wait_for_timeout(500)
        num = pg.locator('input[type=text]').filter(has_not=pg.locator('xpath=ancestor::textarea')).last   # the polycount box (a text input) beside its slider
        slider = lambda: pg.evaluate("()=>{const s=[...document.querySelectorAll('[role=slider]')].find(s=>+s.getAttribute('aria-valuemax')>=25000); return s? s.getAttribute('aria-valuenow')+'/'+s.getAttribute('aria-valuemax'):null}")
        smax = lambda: (slider() or '/0').split('/')[1]
        if a.polycount == 'max': a.polycount = smax()                   # the topology's own ceiling (Quad 25000, Triangle 50000 measured by dry run)
        rec['polycount_max_shown'] = smax()
        for _ in range(3):
            num.fill(a.polycount); num.press('Enter'); pg.wait_for_timeout(800)
            if num.input_value().replace(',', '') == a.polycount and (slider() or '/').split('/')[0] == a.polycount: break
        topo = pg.evaluate("""()=>[...document.querySelectorAll('button')].filter(b=>/Quad|Triangle/.test(b.innerText)).map(b=>({t:b.innerText.trim(), cls:b.className, st:b.getAttribute('data-state')||b.getAttribute('aria-pressed')}))""")
        rec['topology_buttons'] = topo; rec['polycount_read_back'] = num.input_value(); rec['polycount_slider'] = slider()
        pg.keyboard.press('Escape'); pg.wait_for_timeout(600)
        for _ in range(3):                                              # number of generations
            st = pg.evaluate("()=>Object.fromEntries([...document.querySelectorAll('button')].filter(b=>['1','2','4'].includes(b.innerText.trim())&&b.getBoundingClientRect().x<460&&b.offsetParent).map(b=>[b.innerText.trim(), b.getAttribute('data-state')]))")
            if st.get('4') == 'on': break
            pg.evaluate("()=>{const b=[...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='4'&&b.getBoundingClientRect().x<460&&b.offsetParent); if(b) b.click()}"); pg.wait_for_timeout(600)
        rec['generations_state'] = st
        panel = pg.evaluate(LEFTTXT); rec['panel_text'] = panel
        gen = pg.locator('button').filter(has_text=re.compile(r'^\s*Generate')).last; gtxt = gen.inner_text().replace('\n', ' ')
        rec['generate_button'] = gtxt; rec['privacy'] = next((w for w in ('Sharing Only', 'Private', 'Public') if w in pg.evaluate("()=>document.body.innerText")), None)
        smart_on = 'Smart Mesh' in pg.evaluate("()=>[...document.querySelectorAll('button')].filter(b=>b.getAttribute('data-state')==='on'||/bg-white/.test(b.className)).map(b=>b.innerText).join('|')")
        rec['thumbnails_seen'] = n
        bad = verify.mesh_problems(rec, polycount=a.polycount, topology=a.topology, expect_price=a.expect_price, smart_mesh_on=smart_on)
        if bad:
            rec['refused'] = bad; json.dump(rec, open(os.path.join(a.out, 'run.json'), 'w'), indent=1); ax.refuse('; '.join(bad), [f'{studio.PY} {ME} <out_dir> ... --dry-run'])
        if a.dry_run:
            rec['dry_run'] = True; json.dump(rec, open(os.path.join(a.out, 'run.json'), 'w'), indent=1); ax.kv({'dry_run': 'verified', **{k: rec[k] for k in ('polycount_read_back', 'generate_button', 'privacy', 'thumbnails_seen')}}); ax.helps([f'{studio.PY} {ME} <out_dir> <same args without --dry-run>']); return
        guard.require_armed('generating a Smart Mesh (Tripo Studio, spends credits)')   # after the dry run
        seen = []
        pg.on('response', lambda r: seen.append(r.url.split('?')[0]) if re.search(r'\.(glb|fbx|obj)(\?|$)', r.url) and r.url.split('?')[0] not in seen else None)
        gen.click(); t0 = time.time(); rec['clicked'] = datetime.datetime.now().isoformat(timespec='seconds')
        while time.time() - t0 < 1800:
            pg.wait_for_timeout(15000)
            if len(seen) >= 4: break
        rec['seconds'] = round(time.time() - t0); rec['mesh_urls_seen'] = seen; rec['credits_after'] = credits(pg)
        json.dump(rec, open(os.path.join(a.out, 'run.json'), 'w'), indent=1)
        ax.kv({'generated': True, 'meshes_seen': len(seen), 'credits': f"{rec['credits_before']} -> {rec['credits_after']}", 'seconds': rec['seconds'], 'record': os.path.join(a.out, 'run.json')})
        ax.helps([f'{studio.PY} -m lampway_server.studios.tripo.tripo_fetch.py <out_dir> "<MM-DD HH:MM of the new cards>"'])


if __name__ == '__main__':
    main()
