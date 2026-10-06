"""The Vault's gates (specs/asset_library/asset_gates.md): the library's claims as numbers against thresholds, recorded as a ``receipt/gate`` asset with its
``gate_result`` rows. A gate that cannot fail is not a gate: the suite holds a mutant for every one (tests/test_library_gates.py).

Gates run on the synthetic corpus (``corpus.build``) or on a COPY of the user's library (``run_on_copy``: a ``VACUUM INTO`` backup in a temp dir): never with
writes on the user's own DB. ``idle`` needs a live render batch's evidence and is reported ``not-run`` (never a pass) without it. The thresholds are the
contract's targets; the measured baseline is docs/reports/asset-gates-baseline.md."""
from __future__ import annotations

import hashlib
import json
import random
import re
import resource
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Optional

import numpy as np

from . import provenance as P
from . import query as Q
from . import vectors as V
from .store import AssetLibrary, LibraryError

MACHINE_GATES = ("latency", "throughput", "coverage", "provenance", "dedupe", "fts_parity", "recall", "schema", "integrity", "privacy", "memory")
LIVE_GATES = ("idle",)
THRESHOLDS = {"latency": {"text_filter_p95_ms": 50.0, "similar_p95_ms": 100.0, "get_p95_ms": 20.0, "cold_ms": 300.0}, "puts_per_s": 200.0, "coverage": 0.99,
              "provenance": 1.0, "near_recall": 0.9, "near_hamming": 4, "recall_at_10": 0.9, "memory_mb": 400.0, "idle_load_fraction": 0.6}
THUMB_KINDS = ("mesh", "image", "video", "hdri", "map", "material", "texture_set")
SECRET = re.compile(r"X-Amz-Signature|[?&]Signature=|[?&]token=|[?&]Expires=|sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{12,}", re.I)
WORDS = ("bronze", "gold", "iron", "steel", "leather", "helmet", "chest", "gauntlets", "greaves", "boots")


def _pct(xs, p):
    return round(float(np.percentile(np.asarray(xs) * 1000.0, p)), 3) if xs else None


def _row(gid, value, threshold, passed, detail=None, verdict=None):
    return {"id": gid, "value": value, "threshold": threshold, "passed": bool(passed), "verdict": verdict or ("pass" if passed else "fail"), "detail": detail or {}}


def _timed(fn):
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


# ---- the gates -------------------------------------------------------------------------------------------------------------------
def g_latency(lib, meta, queries):
    rnd = random.Random(5)
    ids = [r[0] for r in lib._reader().execute("SELECT id FROM asset WHERE status='active' ORDER BY id").fetchall()]
    cold = _timed(lambda: Q.query(lib, {"text": "bronze", "limit": 20}))
    tf = [_timed(lambda: Q.query(lib, {"text": rnd.choice(WORDS), "kinds": ["mesh"], "limit": 20})) for _ in range(queries)]
    fo = [_timed(lambda: Q.query(lib, {"kinds": [rnd.choice(("mesh", "image"))], "limit": 20})) for _ in range(queries)]
    gets = [_timed(lambda: lib.get(rnd.choice(ids))) for _ in range(queries)] if ids else []
    spaces = lib.embedding_spaces()
    sim = []
    if spaces:
        sid, mat = lib.load_space(max(spaces, key=spaces.get))
        idx = V.NumpyBrute(sid, mat)
        sim = [_timed(lambda: idx.topk(mat[rnd.randrange(len(mat))], 12)) for _ in range(queries)] if len(mat) else []
    v = {"cold_ms": round(cold * 1000, 3), "text_filter_p50_ms": _pct(tf, 50), "text_filter_p95_ms": _pct(tf, 95), "filter_p95_ms": _pct(fo, 95),
         "get_p95_ms": _pct(gets, 95), "similar_p95_ms": _pct(sim, 95), "queries_per_type": queries, "assets": len(ids)}
    t = THRESHOLDS["latency"]
    ok = v["text_filter_p95_ms"] < t["text_filter_p95_ms"] and (v["get_p95_ms"] or 0) < t["get_p95_ms"] and (v["similar_p95_ms"] or 0) < t["similar_p95_ms"] and v["cold_ms"] < t["cold_ms"]
    return _row("latency", v, t, ok)


def g_throughput(lib, meta, queries):
    with tempfile.TemporaryDirectory(dir=lib.root.parent) as d:
        tmp = AssetLibrary(Path(d) / "t")
        try:
            n, t0 = 300, time.perf_counter()
            with tmp.bulk():
                for i in range(n):
                    tmp.put({"kind": "prompt", "name": f"p{i}", "source": {"kind": "t", "key": str(i)}, "files": [{"role": "main", "bytes": f"p{i}".encode(), "storage": "cas"}]})
            rate = n / (time.perf_counter() - t0)
        finally:
            tmp.close()
    return _row("throughput", {"puts_per_s": round(rate, 1)}, THRESHOLDS["puts_per_s"], rate >= THRESHOLDS["puts_per_s"])


def g_coverage(lib, meta, queries):
    kinds = ",".join("?" * len(THUMB_KINDS))
    rows = lib._reader().execute(f"SELECT a.id, EXISTS(SELECT 1 FROM version_file f WHERE f.version_id=v.id AND f.role='thumb') FROM asset a JOIN version v ON v.asset_id=a.id "
                                 f"AND v.n=a.current_version WHERE a.status='active' AND a.kind IN ({kinds})", THUMB_KINDS).fetchall()
    have = sum(r[1] for r in rows)
    value = have / len(rows) if rows else 1.0
    return _row("coverage", round(value, 5), THRESHOLDS["coverage"], value >= THRESHOLDS["coverage"], {"should": len(rows), "have": have, "missing": [r[0] for r in rows if not r[1]][:20]})


def g_provenance(lib, meta, queries):
    a = P.audit(lib)
    value = a["complete"] / a["generated_assets"] if a["generated_assets"] else 1.0
    return _row("provenance", round(value, 5), THRESHOLDS["provenance"], value >= THRESHOLDS["provenance"], {"generated": a["generated_assets"], "incomplete": a["incomplete"][:20]})


def _dhash(path) -> int:
    from PIL import Image
    with Image.open(path) as im:
        g = np.asarray(im.convert("L").resize((9, 8)), dtype=np.int64)
    bits = (g[:, :-1] > g[:, 1:]).reshape(-1)
    return int("".join("1" if b else "0" for b in bits), 2)


def g_dedupe(lib, meta, queries):
    db = lib._reader()
    merged = db.execute("SELECT v.content_key, count(DISTINCT a.id) FROM asset a JOIN version v ON v.asset_id=a.id AND v.n=a.current_version WHERE a.status='active' "
                        "GROUP BY v.content_key HAVING count(DISTINCT a.id) > 1").fetchall()
    detail = {"identical_content_in_two_assets": len(merged)}
    ok = not merged
    if meta:
        exact = meta["exact"]
        detail["exact_deduped"] = sum(1 for e in exact if e["deduped"] and e["result"] == e["original"]) / len(exact) if exact else 1.0
        near = meta["near"]
        hits, auto = 0, 0
        for p in near:
            main = lambda aid: next(f for f in lib.get(aid)["files"] if f["role"] == "main")["locations"][0]["path"]   # noqa: E731
            hits += bin(_dhash(main(p["original"])) ^ _dhash(main(p["result"]))).count("1") <= THRESHOLDS["near_hamming"]
            auto += p["result"] == p["original"]
        detail.update(near_recall=hits / len(near) if near else 1.0, near_auto_merged=auto)
        ok = ok and detail["exact_deduped"] == 1.0 and detail["near_recall"] >= THRESHOLDS["near_recall"] and auto == 0
    return _row("dedupe", detail, {"exact": 1.0, "false_merges": 0, "near_recall": THRESHOLDS["near_recall"]}, ok)


def g_fts_parity(lib, meta, queries):
    db = lib._reader()
    active, rows = db.execute("SELECT count(*) FROM asset WHERE status='active'").fetchone()[0], db.execute("SELECT count(*) FROM asset_fts").fetchone()[0]
    texts = {r[0]: " ".join(x or "" for x in r[1:]).lower() for r in db.execute(
        "SELECT a.id, a.name, a.description, (SELECT group_concat(tag,' ') FROM tag WHERE asset_id=a.id) FROM asset a WHERE a.status='active'")}
    tokens = (meta or {}).get("token_queries") or [w for w in WORDS[:5]]
    bad = []
    for tok in tokens[:20]:
        want = {aid for aid, t in texts.items() if any(w.startswith(tok) for w in re.findall(r"[a-z0-9_]+", t))}
        got = Q.query(lib, {"text": tok, "limit": 200})["total"]
        if got < len(want):
            bad.append({"token": tok, "fts": got, "brute": len(want)})
    ok = active == rows and not bad
    return _row("fts_parity", {"active": active, "fts_rows": rows, "mismatched_queries": bad}, "exact", ok)


def g_recall(lib, meta, queries):
    if not meta:
        return _row("recall", None, THRESHOLDS["recall_at_10"], False, {"why": "planted relevance exists only in the synthetic corpus"}, "not-run")
    from .corpus import SPACE
    ids, mat = lib.load_space(SPACE)
    idx, rnd = V.NumpyBrute(ids, mat), random.Random(9)
    scores, size = [], {}
    for a in ids:
        size[meta["cluster_of"].get(a)] = size.get(meta["cluster_of"].get(a), 0) + 1
    for i in rnd.sample(range(len(ids)), min(60, len(ids))):
        k = min(10, size[meta["cluster_of"].get(ids[i])] - 1)                   # a cluster of 6 has 5 true neighbours, not 10
        if k < 1:
            continue
        nn = [a for a, _ in idx.topk(mat[i], k + 1) if a != ids[i]][:k]
        scores.append(sum(meta["cluster_of"].get(a) == meta["cluster_of"].get(ids[i]) for a in nn) / k)
    value = float(np.mean(scores)) if scores else 0.0
    return _row("recall", round(value, 4), THRESHOLDS["recall_at_10"], value >= THRESHOLDS["recall_at_10"])


def g_schema(lib, meta, queries):
    fk = lib._db.execute("PRAGMA foreign_key_check").fetchall()
    pending = lib.migrate(dry_run=True)["pending"]
    refused = False
    with tempfile.TemporaryDirectory(dir=lib.root.parent) as d:
        db = sqlite3.connect(Path(d) / "library.sqlite")
        db.execute(f"PRAGMA user_version={lib._db.execute('PRAGMA user_version').fetchone()[0] + 1}")
        db.close()
        try:
            AssetLibrary(d).close()
        except LibraryError as e:
            refused = "newer" in str(e)
    ok = not fk and not pending and refused
    return _row("schema", {"foreign_key_violations": len(fk), "pending_migrations": pending, "newer_db_refused": refused}, "pass", ok)


def g_integrity(lib, meta, queries):
    check = lib._db.execute("PRAGMA integrity_check").fetchone()[0]
    with tempfile.TemporaryDirectory(dir=lib.root.parent) as d:
        dest = Path(d) / "backup.sqlite"
        lib.backup(dest)
        try:
            restored = sqlite3.connect(f"file:{dest}?mode=ro", uri=True).execute("SELECT count(*) FROM asset").fetchone()[0]
        except sqlite3.DatabaseError:
            restored = -1
    live = lib._reader().execute("SELECT count(*) FROM asset").fetchone()[0]
    return _row("integrity", {"integrity_check": check, "assets": live, "restored_from_backup": restored}, "ok + backup restores", check == "ok" and restored == live)


def g_privacy(lib, meta, queries):
    db, found = lib._reader(), []
    for table, col in (("version", "attrs_json"), ("generation", "params_json"), ("generation", "prompt_text"), ("location", "path"), ("asset", "description"), ("event", "detail_json")):
        for (val,) in db.execute(f"SELECT {col} FROM {table} WHERE {col} IS NOT NULL"):
            if SECRET.search(str(val)):
                found.append({"table": table, "column": col})
    return _row("privacy", len(found), 0, not found, {"findings": found[:20]})


def g_memory(lib, meta, queries):
    for space in lib.embedding_spaces():
        lib.load_space(space)
    mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    return _row("memory", round(mb, 1), THRESHOLDS["memory_mb"], mb < THRESHOLDS["memory_mb"], {"measure": "peak RSS of this process (ru_maxrss) after loading every space"})


def g_idle(lib, meta, queries, evidence: Optional[dict] = None):
    if not evidence:
        return _row("idle", None, THRESHOLDS["idle_load_fraction"], False, {"why": "needs a live render batch's evidence (load samples, cores, bridge contacts)"}, "not-run")
    frac = max(evidence["loads"]) / evidence["cores"]
    ok = frac < THRESHOLDS["idle_load_fraction"] or evidence.get("deferred_while_busy", False)
    return _row("idle", {"max_load_per_core": round(frac, 3), "bridge_contacts": evidence.get("bridge_contacts", 0)}, THRESHOLDS["idle_load_fraction"], ok and not evidence.get("bridge_contacts"))


GATES = {"latency": g_latency, "throughput": g_throughput, "coverage": g_coverage, "provenance": g_provenance, "dedupe": g_dedupe, "fts_parity": g_fts_parity,
         "recall": g_recall, "schema": g_schema, "integrity": g_integrity, "privacy": g_privacy, "memory": g_memory}


# ---- the runner -------------------------------------------------------------------------------------------------------------------
def _corpus_facts(lib, meta) -> dict:
    db = lib._reader()
    keys = [r[0] for r in db.execute("SELECT content_key FROM version ORDER BY content_key")]
    return {"assets": db.execute("SELECT count(*) FROM asset").fetchone()[0], "versions": len(keys), "blobs": db.execute("SELECT count(*) FROM blob").fetchone()[0],
            "bytes": db.execute("SELECT coalesce(sum(bytes),0) FROM blob").fetchone()[0], "seed": (meta or {}).get("seed"),
            "sha256": hashlib.sha256("\n".join(keys).encode()).hexdigest(), "sqlite": sqlite3.sqlite_version}


def run(lib: AssetLibrary, meta: Optional[dict], gates, queries: int = 200, copy: bool = False, idle_evidence: Optional[dict] = None) -> dict:
    if meta is None and not copy:
        raise LibraryError("gates run on a copy: pass corpus=shelf only with a read-only library (use run_on_copy)")
    t0 = time.perf_counter()
    rows = []
    for g in gates:
        if g in LIVE_GATES:
            rows.append(g_idle(lib, meta, queries, idle_evidence))
        elif g in GATES:
            rows.append(GATES[g](lib, meta, queries))
        else:
            raise LibraryError(f"unknown gate {g!r}; gates: {list(MACHINE_GATES) + list(LIVE_GATES)}")
    facts = _corpus_facts(lib, meta)
    report = {"ok": all(r["passed"] for r in rows), "gates": rows, "corpus": facts, "took_s": round(time.perf_counter() - t0, 2)}
    body = json.dumps(report, sort_keys=True, default=str).encode()
    rec = lib.put({"kind": "receipt", "subtype": "gate", "name": f"gates {time.strftime('%Y-%m-%d %H:%M:%S')}", "source": {"kind": "gates", "key": hashlib.sha256(body).hexdigest()[:16]},
                   "files": [{"role": "main", "bytes": body, "storage": "cas", "name": "gates.json"}],
                   "gates": [{"gate": r["id"], "value": _num(r["value"]), "threshold": _num(r["threshold"]), "passed": r["passed"], "detail": {"verdict": r["verdict"]}} for r in rows]})
    return {**report, "receipt": rec["id"]}


def _num(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, dict):
        return next((float(x) for x in v.values() if isinstance(x, (int, float)) and not isinstance(x, bool)), None)
    return None


def run_on_copy(live: AssetLibrary, dest, gates, queries: int = 200) -> dict:
    """The user's library, measured on a ``VACUUM INTO`` copy: nothing is written to the original (no receipt, no row)."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    live.backup(dest / "library.sqlite")
    copy = AssetLibrary(dest)
    try:
        return {**run(copy, None, gates, queries, copy=True), "copy": str(dest)}
    finally:
        copy.close()
