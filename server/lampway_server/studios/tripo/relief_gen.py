#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/studios/tripo/relief_gen.py, sha256 769d3c4cfbc6) on 2026-10-05, SERVER side: it drives the owner's Tripo Studio
# login in the persistent tool browser (CDP), which the app never does. The header below, with its invariants (credits,
# settings read back before every generation, actions on saved copies only), is the original's. Nothing here runs unless the
# studio guard is armed (studios/guard.py); tests run against recorded fixtures only.
# SPIKE (2026-10-04): run Tripo's free 3D Relief Generator (https://www.tripo3d.ai/3d-relief-generator) without a person
# (the captain: "Can you make tooling to run the relief generator headlessly?").
# What the site does, measured 2026-10-04: the image is POSTed to /api/relief/upload; Tripo's server estimates depth and
# returns ONE 8-bit 1024x1024 grey PNG (served from S3); every later control - contrast, brightness, sharpen/smooth,
# model resolution, relief depth, board thickness, smoothness, background cutout, depth compression - is applied in the
# browser to that PNG. So this tool keeps the raw PNG (all the information the server produces) and leaves every
# adjustment to deterministic local code (relief_post.py). The PNG is the input image resized to 1024 x 1024, so it
# shares the input's frame.
# The site's upload API refuses headless browsers (Cloudflare 403) and a launched browser re-solves the challenge each
# time, so the tool drives ONE long-lived Chromium (systemd user unit `relief-browser`, CDP on 127.0.0.1:9333, persistent
# profile, window offscreen on the captain's display) and only reloads the page between images (the captain: "stop
# closing the browser each time"). Patchright (the Playwright fork Crawl4AI's undetected mode uses) attaches to it.
# The site's own "Export height map" equals the raw PNG pixel for pixel at default settings (measured 2026-10-04: max
# difference 0, the export is the PNG's grey). --adjust C,B,S sets the page's Contrast, Brightness and Sharpen/Smooth
# sliders (each -1..1) and also saves the site's export with them applied, for comparison with local processing.
# A server error (5xx) is retried with back-off; a refusal (403) is not.
# Usage: <venv>/bin/python relief_gen.py [--adjust C,B,S] <out_dir> <image> [<image> ...]   (venv: the browser python, LAMPWAY_PYTHON_BROWSER)
# Writes <out_dir>/<image stem>.relief.png and <image stem>.relief.json (input sha256, output sha256, source URL), and
# with --adjust <stem>.relief.site_C_B_S.png; never overwrites.
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
from lampway_server.studios import axi as _ax
from lampway_server.studios import guard
_A = _sys.argv[1:]
_bad = [] if __name__ != '__main__' else [x for x in _A if x.startswith('--') and x.split('=')[0] not in ['--adjust']]
if _bad: print(f'error: unknown flag(s) {_bad}'); _ax.helps(['<browser python> -m lampway_server.studios.tripo.relief_gen [--adjust C,B,S] <out_dir> <image> [...]']); _sys.stdout.flush(); raise SystemExit(2)
if __name__ == '__main__' and len(_A) < 2:
    if not _A: _ax.home(__file__, "Tripo's free 3D Relief Generator, unattended in the persistent tool browser: one 8-bit depth PNG per image")
    else: print(f'error: {len(_A)} argument(s); at least 2 needed')
    _ax.helps(['<browser python> -m lampway_server.studios.tripo.relief_gen [--adjust C,B,S] <out_dir> <image> [...]']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import hashlib, json, os, subprocess, sys, time, datetime, urllib.request

PORT = int(os.environ.get('LAMPWAY_STUDIO_CDP_PORT', '9333'))
URL = 'https://www.tripo3d.ai/3d-relief-generator'
BOX = os.environ.get('LAMPWAY_STUDIO_BROWSER_DIR') or os.path.expanduser('~/.local/share/lampway/tool-browser')   # holds the logged-in profile/
CHROME = os.environ.get('LAMPWAY_STUDIO_CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome')
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36'
sha = lambda b: hashlib.sha256(b).hexdigest()


def ensure_browser():
    try:
        urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version', timeout=3).read(); return 'attached'
    except Exception:
        pass
    subprocess.run(['systemd-run', '--user', '--unit', 'relief-browser', '--collect', '--setenv=DISPLAY=:0', '--setenv=XDG_RUNTIME_DIR=/run/user/1000',
                    CHROME, f'--remote-debugging-port={PORT}', '--remote-debugging-address=127.0.0.1', f'--user-data-dir={BOX}/profile',
                    '--window-position=-2400,0', '--window-size=1600,1100', '--no-first-run', '--no-default-browser-check',
                    '--disable-blink-features=AutomationControlled', f'--user-agent={UA}', 'about:blank'], check=True)
    for _ in range(60):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/version', timeout=3).read(); return 'started'
        except Exception:
            time.sleep(0.5)
    raise RuntimeError('relief browser did not come up')


def relief(pg, img, timeout_s=180):
    got = {}
    def onres(r):
        if 'GENERATION_SCENE_RELIEF' in r.url and r.status == 200 and 'png' not in got:
            got['png'] = r.body(); got['url'] = r.url.split('?')[0]
        elif '/api/relief/upload' in r.url:
            got['upload_status'] = r.status
            try: got['upload'] = r.json()
            except Exception: pass
    pg.on('response', onres)
    try:
        pg.goto(URL, wait_until='load', timeout=90000)                      # a reload resets the page's steps; the browser stays
        pg.wait_for_selector('input[type=file]', state='attached', timeout=90000)
        pg.locator('input[type=file]').first.set_input_files(img)
        pg.get_by_role('button', name='Start').click()
        pg.get_by_role('button', name='Generate height map').click()
        t0 = time.time()
        while 'png' not in got and time.time() - t0 < timeout_s:
            st = got.get('upload_status')
            if st is not None and st >= 500: raise Retry(f'upload: HTTP {st}')
            if st not in (None, 200): raise RuntimeError(f"upload refused: HTTP {st}")
            pg.wait_for_timeout(500)
        if 'png' not in got: raise Retry('no height map within %d s' % timeout_s)
        return got
    finally:
        pg.remove_listener('response', onres)


class Retry(Exception): pass


def site_export(pg, adj, path):
    """set the step-3 sliders, go to step 4 and save the site's 'Export height map'"""
    rng = pg.locator('input[type=range]')
    for label, v in zip(('Contrast', 'Brightness', 'Sharpen / Smooth'), adj):
        el = pg.locator(f"xpath=//*[normalize-space(text())='{label}']/ancestor::*[.//input[@type='range']][1]//input[@type='range']").first
        el.evaluate("(e, v) => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(e, String(v)); e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); }", v)
        got = float(el.input_value())
        if abs(got - v) > 1e-6: raise RuntimeError(f'{label} slider reads {got}, wanted {v}')
    pg.get_by_role('button', name='Generate 3D model').click()
    pg.get_by_role('button', name='Export height map').last.wait_for(timeout=120000)
    with pg.expect_download(timeout=60000) as dl: pg.get_by_role('button', name='Export height map').last.click()
    dl.value.save_as(path)


MAX_UPLOAD = 10 * 1024 * 1024                                            # the site: "JPG, PNG, WEBP · Size <= 10MB" (a 15 MB 4K PNG left Generate disabled, 2026-10-04)


def main(out, *imgs):
    adj = None
    if out == '--adjust':
        adj = tuple(float(x) for x in imgs[0].split(',')); out, imgs = imgs[1], imgs[2:]
        if len(adj) != 3 or any(not -1 <= x <= 1 for x in adj): _ax.refuse('--adjust takes C,B,S each in -1..1', ['relief_gen.py --adjust 0.2,0.1,0 <out_dir> <image>'])
    guard.require_armed("Tripo's relief generator (uploads the images to tripo3d.ai)")
    from patchright.sync_api import sync_playwright
    os.makedirs(out, exist_ok=True); how = ensure_browser(); done = []
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(f'http://127.0.0.1:{PORT}')
        ctx = b.contexts[0]
        pg = next((x for x in ctx.pages if 'relief-generator' in x.url), None) or (ctx.pages[0] if ctx.pages else ctx.new_page())
        pg.set_viewport_size({'width': 1600, 'height': 1100})
        for img in imgs:
            stem = os.path.splitext(os.path.basename(img))[0]; base = os.path.join(out, stem)
            if os.path.exists(base + '.relief.png'): print('exists, skipped:', base + '.relief.png'); continue
            src = open(img, 'rb').read(); tries = []
            for attempt in range(4):
                try: g = relief(pg, img); break
                except Retry as e:
                    tries.append(str(e)); print('retry', attempt + 1, img, e); pg.wait_for_timeout(15000 * (attempt + 1))
            else: raise RuntimeError(f'{img}: gave up after {tries}')
            site = None
            if adj:
                site = base + '.relief.site_%s.png' % '_'.join(f'{x:+.2f}' for x in adj)
                if not os.path.exists(site): site_export(pg, adj, site)
            open(base + '.relief.png', 'wb').write(g['png'])
            rec = {'input': os.path.abspath(img), 'input_sha256': sha(src), 'output': os.path.basename(base + '.relief.png'), 'output_sha256': sha(g['png']),
                   'output_bytes': len(g['png']), 'source_url': g['url'], 'upload_media_id': (g.get('upload') or {}).get('mediaId'),
                   'service': URL, 'tool': 'relief_gen.py', 'browser': how, 'retries': tries,
                   'site_export': {'file': os.path.basename(site), 'contrast_brightness_sharpen': adj, 'sha256': sha(open(site, 'rb').read())} if site else None, 'date': datetime.datetime.now().isoformat(timespec='seconds'),
                   'note': '8-bit 1024x1024 depth estimate, the input resized to 1024x1024 (same frame); every site slider is local post-processing and is not applied here'}
            json.dump(rec, open(base + '.relief.json', 'w'), indent=1); done.append(rec['output']); print('ok', img, '->', rec['output'], rec['output_sha256'][:12])
    return done                                                             # leaving the with-block disconnects; the browser keeps running


def too_big(files):
    return [f for f in files if os.path.isfile(f) and os.path.getsize(f) > MAX_UPLOAD]


if __name__ == '__main__':
    big = too_big(sys.argv[1:])
    if big: _ax.refuse(f'over the site limit of 10 MB: {big}', ['save the plate as JPEG (a 4096 px plate is about 3 MB), then rerun'])
    if len(sys.argv) < 3: sys.exit(__doc__ or 'usage: relief_gen.py <out_dir> <image> [<image> ...]')
    main(*sys.argv[1:])
