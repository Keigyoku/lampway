#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/studios/tripo/seed_db.py, sha256 03f4280c486a) on 2026-10-05, SERVER side: it drives the owner's Tripo Studio
# login in the persistent tool browser (CDP), which the app never does. The header below, with its invariants (credits,
# settings read back before every generation, actions on saved copies only), is the original's. Nothing here runs unless the
# studio guard is armed (studios/guard.py); tests run against recorded fixtures only.
# SPIKE (2026-10-04): one local catalog of every Tripo seed (the captain: "Should the tool be making like a DB of meshes and URLs?").
# SQLite at <shelf>/scratch/scratch-tmp/tripo_mesh/seeds.sqlite. One row per mesh VERSION (a generation variant, or an Edit
# Mesh retry banked in History), keyed by its Tripo id. Stores the stable unsigned URL and the local file + sha256 - NEVER a
# signed URL (per-file CloudFront signatures expire and act as credentials; a fresh one comes from the History preview).
# Proportion scores (proportion_ratios.py output) and audit verdicts attach by id or by local file.
#   seed_db.py ingest-variants <variants.json> <piece> [--plates <run.json>]   tripo_fetch.py output (a 4-variant generation)
#   seed_db.py ingest-harvest  <harvest.json>  <piece>                         tripo_regen.py harvest output (History versions)
#   seed_db.py ingest-scores   <scores.json>                                   proportion_ratios.py output (matched by npz->mesh file stem)
#   seed_db.py verdict <id-prefix> <verdict> [--note TEXT] [--audit PATH]      record an audit verdict
#   seed_db.py list [--piece P] [--by score|created]                          ranked table
#   seed_db.py                                                                 (no args) AXI home: catalog summary + top seeds
import argparse, hashlib, json, os, re, sqlite3, sys, time

def db_path():
    from lampway_server.seeds import default_path     # one catalogue: <project root>/seeds/seeds.sqlite, shared with the typed Catalog (seeds.py)
    return str(default_path())


SCHEMA = """CREATE TABLE IF NOT EXISTS seeds (
  id TEXT PRIMARY KEY, piece TEXT, kind TEXT, parent_id TEXT, project_id TEXT, created_at INTEGER, topology TEXT, faces INTEGER,
  url TEXT, file TEXT, sha256 TEXT, bytes INTEGER, plates_json TEXT, score_rms REAL, score_json TEXT, verdict TEXT, verdict_note TEXT,
  audit_path TEXT, added_at INTEGER, source TEXT)"""


def con():
    p = os.path.abspath(db_path()); os.makedirs(os.path.dirname(p), exist_ok=True); c = sqlite3.connect(p); c.execute(SCHEMA); return c


def unsigned(u): return u.split('?')[0] if u else None


def tid(u):
    m = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', u or ''); return m and m.group(1)


def upsert(c, row):
    row = {k: v for k, v in row.items() if v is not None}; row.setdefault('added_at', int(time.time()))
    cols = ','.join(row); q = ','.join('?' * len(row)); upd = ','.join(f'{k}=excluded.{k}' for k in row if k != 'id')
    c.execute(f'INSERT INTO seeds ({cols}) VALUES ({q}) ON CONFLICT(id) DO UPDATE SET {upd}', list(row.values()))


def sha(f): return hashlib.sha256(open(f, 'rb').read()).hexdigest() if f and os.path.exists(f) else None


from lampway_server.studios import axi as ax
ME = '-m lampway_server.studios.tripo.seed_db'


def ranked(c, piece=None, limit=None, by='score'):
    q = 'SELECT id,piece,kind,topology,faces,score_rms,verdict FROM seeds' + (' WHERE piece=?' if piece else '')
    q += ' ORDER BY score_rms IS NULL, score_rms' if by == 'score' else ' ORDER BY created_at'
    rows = [dict(id=r[0][:8], piece=r[1], kind=r[2], topo=r[3], faces=r[4], score=r[5], verdict=r[6]) for r in c.execute(q, (piece,) if piece else ())]
    return rows if limit is None else rows[:limit], len(rows)


def main():
    c = con()
    if len(sys.argv) == 1:                                                 # AXI content first: the live catalog, not a usage dump
        ax.home(__file__, 'Local catalog of every 3D seed (generation variants and banked Edit Mesh retries) with proportion scores and audit verdicts')
        pieces = [r[0] for r in c.execute('SELECT DISTINCT piece FROM seeds')]
        ax.kv({'db': os.path.relpath(os.path.abspath(db_path())), 'seeds': c.execute('SELECT COUNT(*) FROM seeds').fetchone()[0],
               'scored': c.execute('SELECT COUNT(*) FROM seeds WHERE score_rms IS NOT NULL').fetchone()[0], 'pieces': ' '.join(pieces) or '0 pieces'})
        rows, tot = ranked(c, limit=8); ax.table('top_by_score', rows, ['id', 'piece', 'topo', 'faces', 'score', 'verdict'], total=tot)
        ax.helps([f'python3 {ME} list --piece <piece>', f'python3 {ME} verdict <id> <usable|fix|reject> --note "<why>" --audit <report>',
                  f'python3 {ME} ingest-harvest <harvest.json> <piece>', f'python3 {ME} --help']); return
    ap = argparse.ArgumentParser(description='Local seed catalog (AXI: no args shows the ranked catalog).'); sp = ap.add_subparsers(dest='cmd', required=True)
    v = sp.add_parser('ingest-variants'); v.add_argument('json'); v.add_argument('piece'); v.add_argument('--plates')
    h = sp.add_parser('ingest-harvest'); h.add_argument('json'); h.add_argument('piece')
    s = sp.add_parser('ingest-scores'); s.add_argument('json')
    d = sp.add_parser('verdict'); d.add_argument('id'); d.add_argument('verdict'); d.add_argument('--note'); d.add_argument('--audit')
    l = sp.add_parser('list'); l.add_argument('--piece'); l.add_argument('--by', default='score', choices=['score', 'created'])
    a = ap.parse_args(); base = os.path.dirname(os.path.abspath(getattr(a, 'json', '.') or '.'))
    if getattr(a, 'json', None) and not os.path.exists(a.json): ax.refuse(f'{a.json} not found', [f'python3 {ME}'])
    n0 = c.execute('SELECT COUNT(*) FROM seeds').fetchone()[0]
    if a.cmd == 'ingest-variants':
        j = json.load(open(a.json)); vs = j['variants'] if isinstance(j, dict) else j
        plates = json.dumps(json.load(open(a.plates)).get('inputs')) if a.plates else None; k = 0
        for o in vs:
            if not o.get('url'): continue
            f = os.path.join(base, o['file']) if not os.path.isabs(o['file']) else o['file']; k += 1
            upsert(c, dict(id=tid(o['url']), piece=a.piece, kind='generation', topology=o.get('topology_shown') or ('Quad' if o['url'].endswith('.fbx') else 'Triangle'),
                           faces=o.get('faces_shown'), url=unsigned(o['url']), file=os.path.abspath(f), sha256=o.get('sha256') or sha(f), bytes=o.get('bytes'),
                           plates_json=plates, source=os.path.abspath(a.json)))
        c.commit(); ax.kv({'ingested': k, 'new_rows': c.execute('SELECT COUNT(*) FROM seeds').fetchone()[0] - n0})
        ax.helps([f'python3 {ME} list --piece {a.piece}'])
    elif a.cmd == 'ingest-harvest':
        k = 0
        for run in json.load(open(a.json)):
            ver = {x['id']: x for x in run.get('history', [])}
            orig = min((x for x in run.get('history', []) if x['type'] != 'local_edit'), key=lambda x: x['created_at'], default=None)
            for g in run.get('downloaded', []):
                if not g.get('file'): continue
                hv = ver.get(g['id'], {}); f = g['file']
                if not os.path.isabs(f):                                    # harvest writes paths relative to where it ran (the tripo_mesh dir)
                    cands = [os.path.join(os.path.dirname(os.path.abspath(db_path())), f), os.path.join(base, os.path.basename(f))]
                    f = next((x for x in cands if os.path.exists(x)), cands[0])
                upsert(c, dict(id=g['id'], piece=a.piece, kind=g['type'], parent_id=(orig['id'] if orig and g['type'] == 'local_edit' else None),
                               created_at=hv.get('created_at'), topology='Quad' if str(g['file']).endswith('.fbx') else 'Triangle', faces=g.get('faces_shown'),
                               file=os.path.abspath(f), sha256=g.get('sha256'), bytes=g.get('bytes'), source=os.path.abspath(a.json))); k += 1
        c.commit(); ax.kv({'ingested': k, 'new_rows': c.execute('SELECT COUNT(*) FROM seeds').fetchone()[0] - n0})
        ax.helps(['python3 tools/proportion/proportion_ratios.py <scores.json> <body.npz> <name>=<seed.npz>:-90 ...', f'python3 {ME} ingest-scores <scores.json>'])
    elif a.cmd == 'ingest-scores':
        j = json.load(open(a.json)); n = 0; miss = []
        for name, r in j['pieces'].items():
            stem = os.path.splitext(os.path.basename(r['file']))[0]      # npz stem = mesh stem (mesh_to_npz naming)
            row = c.execute("SELECT id FROM seeds WHERE file LIKE ? OR id LIKE ?", (f'%/{stem}.%', f'{stem.split("_")[-1]}%')).fetchone()
            if not row: miss.append(f'{name} ({stem})'); continue
            c.execute('UPDATE seeds SET score_rms=?, score_json=? WHERE id=?', (r['rms_logdev'], json.dumps({k: r[k] for k in ('ratios', 'dev_pct', 'placed')}), row[0])); n += 1
        c.commit(); ax.kv({'scores_attached': n, 'unmatched': len(miss)})
        if miss: ax.table('unmatched', [{'name': m} for m in miss], ['name'])
        ax.helps([f'python3 {ME} list --piece <piece>'])
    elif a.cmd == 'verdict':
        r = c.execute('SELECT id FROM seeds WHERE id LIKE ?', (a.id + '%',)).fetchall()
        if len(r) != 1: ax.refuse(f'{len(r)} seeds match {a.id!r}; give a longer id prefix', [f'python3 {ME} list'])
        c.execute('UPDATE seeds SET verdict=?, verdict_note=?, audit_path=? WHERE id=?', (a.verdict, a.note, a.audit, r[0][0])); c.commit()
        ax.kv({'id': r[0][0][:8], 'verdict': a.verdict}); ax.helps([f'python3 {ME}'])
    else:
        rows, tot = ranked(c, a.piece, by=a.by); ax.table('seeds', rows, ['id', 'piece', 'kind', 'topo', 'faces', 'score', 'verdict'], total=tot)
        ax.helps([f'python3 {ME} verdict <id> <verdict> --note "<why>"'])


if __name__ == '__main__':
    main()
