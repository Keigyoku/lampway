"""AssetLibrary: the Asset Vault's one deep module (specs/asset_library/asset_store.md). SQLite (WAL) + FTS5 + a content-addressed blob store.

One writer (this process; a second is refused with the holder's pid), any number of read-only readers. The user's own files are REFERENCED: opened
``rb``, hashed, recorded by (sha256, path, mtime, size) and never moved, copied or modified. Only bytes the library is handed (generation outputs) go into
``cas/<aa>/<bb>/<sha256>``. Deletion is soft; nothing the library did not create is ever unlinked."""
from __future__ import annotations

import fcntl
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Callable, Optional

from . import schema as S

MIN_FREE = 5 * 1024 ** 3
CHUNK = 1024 * 1024


class LibraryError(RuntimeError):
    pass


def _free_bytes(path) -> int:
    return shutil.disk_usage(path).free


def _uuid7() -> str:
    return str(uuid.uuid7())


def _clean_urls(o):
    """A signed URL acts as a credential: every URL-looking string loses its query and fragment before it is stored."""
    if isinstance(o, str):
        return re.sub(r"(https?://[^\s?#\"']+)[?#][^\s\"']*", r"\1", o)
    if isinstance(o, dict):
        return {k: _clean_urls(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean_urls(v) for v in o]
    return o


def _tokens(text: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text or ""))
    return re.sub(r"[_\-./\\]+", " ", text).lower()


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class AssetLibrary:
    def __init__(self, root, idgen: Callable[[], str] = _uuid7, clock: Callable[[], float] = time.time, allowed_roots=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "library.sqlite"
        self.cas = self.root / "cas"
        self.journal = self.root / "decisions.jsonl"
        self._id, self._now = idgen, clock
        self._allowed = [Path(os.path.realpath(r)) for r in (allowed_roots or [])] or None
        self._lock = threading.RLock()
        self._after_blobs: Callable[[], None] = lambda: None
        self._memo: dict = {}
        self._lockfile = open(self.root / "writer.lock", "a+")
        try:
            fcntl.flock(self._lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lockfile.seek(0)
            pid = (self._lockfile.read().strip() or "?")
            self._lockfile.close()
            raise LibraryError(f"library DB is locked by another writer (pid {pid}): the server owns writes; use the REST API") from None
        self._lockfile.seek(0)
        self._lockfile.truncate()
        self._lockfile.write(str(os.getpid()))
        self._lockfile.flush()
        try:
            self._db = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
            self._pragmas(self._db)
            self._migrate(None, dry_run=False, opening=True)
        except Exception:
            self.close()
            raise

    # -- plumbing ------------------------------------------------------------------------------------------------
    @staticmethod
    def _pragmas(db):
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")

    def close(self):
        db = getattr(self, "_db", None)
        if db is not None:
            db.close()
            self._db = None
        lf = getattr(self, "_lockfile", None)
        if lf is not None and not lf.closed:
            lf.close()

    def _reader(self) -> sqlite3.Connection:
        db = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=5000")
        return db

    def _migrate(self, to, dry_run=True, opening=False) -> dict:
        have = self._db.execute("PRAGMA user_version").fetchone()[0]
        latest = S.latest_version()
        if have > latest:
            raise LibraryError(f"library schema {have} is newer than this server ({latest}): update the server")
        target = latest if to is None else min(int(to), latest)
        pending = [p for p in S.migration_files() if have < int(p.name[:4]) <= target]
        if not dry_run:
            for p in pending:
                n = int(p.name[:4])
                if have > 0:
                    self._db.execute(f"VACUUM INTO '{self.db_path}.pre-{n:04d}.bak'")
                self._db.executescript(f"BEGIN;\n{p.read_text(encoding='utf-8')}\nPRAGMA user_version={n};\nCOMMIT;")
                have = n
        return {"from": have, "to": target, "pending": [p.name for p in pending], "dry_run": dry_run}

    def migrate(self, to=None, dry_run=True) -> dict:
        with self._lock:
            return self._migrate(to, dry_run)

    def _event(self, verb, asset_id=None, detail=None, actor="server"):
        self._db.execute("INSERT INTO event(ts,actor,verb,asset_id,detail_json) VALUES(?,?,?,?,?)", (self._now(), actor, verb, asset_id, json.dumps(detail or {}, sort_keys=True)))

    def _journal(self, row: dict):
        with open(self.journal, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    # -- files ---------------------------------------------------------------------------------------------------
    def _check_root(self, path: Path):
        if self._allowed is None:
            return
        real = Path(os.path.realpath(path))
        if not any(real == r or r in real.parents for r in self._allowed):
            raise LibraryError(f"path is outside the roots the library may read: {path} (the project root, a configured source root, or a user-confirmed import)")

    def _hash_file(self, path: Path):
        st = path.stat()
        memo = (str(path), st.st_mtime_ns, st.st_size)
        if memo in self._memo:
            return self._memo[memo], st
        with self._lock:
            row = self._db.execute("SELECT sha256 FROM location WHERE path=? AND mtime=? AND size=? AND storage='external' LIMIT 1", (str(path), st.st_mtime, st.st_size)).fetchone()
        if row:
            return row[0], st
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            while chunk := fh.read(CHUNK):
                h.update(chunk)
        self._memo[memo] = h.hexdigest()               # a scan then an import reads the bytes once
        return h.hexdigest(), st

    def _cas_path(self, sha: str) -> Path:
        return self.cas / sha[:2] / sha[2:4] / sha

    def _write_cas(self, sha: str, data: bytes) -> Path:
        dest = self._cas_path(sha)
        if dest.exists():
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + f".tmp{os.getpid()}")
        tmp.write_bytes(data)
        os.replace(tmp, dest)
        return dest

    def _prepare(self, files: list) -> list:
        incoming = sum(len(f["bytes"]) for f in files if f.get("storage") == "cas")
        if incoming and _free_bytes(self.root) < max(MIN_FREE, 2 * incoming):
            raise LibraryError(f"free space low: {_free_bytes(self.root) / 1024 ** 3:.1f} GB (a managed write needs max(5 GB, 2x incoming))")
        out, seen = [], {}
        for f in files:
            role = f.get("role")
            storage = f.get("storage", "external")
            if not role:
                raise LibraryError("every file needs a role")
            ord_ = seen.get(role, 0)
            seen[role] = ord_ + 1
            if storage == "cas":
                data = f["bytes"]
                sha = hashlib.sha256(data).hexdigest()
                path = self._write_cas(sha, data)
                out.append({"role": role, "ord": ord_, "sha256": sha, "bytes": len(data), "path": str(path), "storage": "cas", "mtime": None, "size": len(data), "mime": mimetypes.guess_type(f.get("name", ""))[0]})
            elif storage == "external":
                p = Path(f["path"])
                self._check_root(p)
                if not p.is_file():
                    raise LibraryError(f"file not found: {p}")
                sha, st = self._hash_file(p)
                out.append({"role": role, "ord": ord_, "sha256": sha, "bytes": st.st_size, "path": str(p), "storage": "external", "mtime": st.st_mtime, "size": st.st_size, "mime": mimetypes.guess_type(str(p))[0]})
            else:
                raise LibraryError(f"unknown storage {storage!r}: external|cas")
        return out

    # -- write interface -----------------------------------------------------------------------------------------
    def put(self, spec: dict) -> dict:
        kind = spec.get("kind")
        if kind not in S.KINDS:
            raise LibraryError(f"unknown kind {kind!r}; kinds: {sorted(S.KINDS)}")
        if not spec.get("name"):
            raise LibraryError("an asset needs a name")
        src = spec.get("source") or {}
        if not src.get("key"):
            raise LibraryError("an asset needs source.key (idempotent re-ingest)")
        with self._lock:
            files = self._prepare(spec.get("files") or [])
            self._after_blobs()
            ck = hashlib.sha256("\n".join(sorted(f"{f['role']}:{f['ord']}:{f['sha256']}" for f in files)).encode()).hexdigest()
            self._db.execute("BEGIN IMMEDIATE")
            try:
                res = self._put_tx(spec, kind, src, files, ck)
                self._db.execute("COMMIT")
                return res
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def _put_tx(self, spec, kind, src, files, ck) -> dict:
        db, now = self._db, self._now()
        for f in files:
            db.execute("INSERT OR IGNORE INTO blob(sha256,bytes,mime,cas_path,first_seen) VALUES(?,?,?,?,?)", (f["sha256"], f["bytes"], f["mime"], f["path"] if f["storage"] == "cas" else None, now))
            db.execute("INSERT INTO location(sha256,path,storage,mtime,size,last_verified,missing) VALUES(?,?,?,?,?,?,0) ON CONFLICT(sha256,path) DO UPDATE SET mtime=excluded.mtime,size=excluded.size,last_verified=excluded.last_verified,missing=0",
                       (f["sha256"], f["path"], f["storage"], f["mtime"], f["size"], now))
        db.execute("INSERT OR IGNORE INTO source(kind,root,label) VALUES(?,?,?)", (src.get("kind", "tool"), src.get("root", ""), src.get("label")))
        source_id = db.execute("SELECT id FROM source WHERE kind=? AND root=?", (src.get("kind", "tool"), src.get("root", ""))).fetchone()[0]
        row = db.execute("SELECT id,current_version FROM asset WHERE source_id=? AND source_key=?", (source_id, src["key"])).fetchone()
        if row:
            aid = row[0]
            cur = db.execute("SELECT n,content_key FROM version WHERE asset_id=? AND n=?", (aid, row[1])).fetchone()
            if cur and cur[1] == ck:
                return {"id": aid, "version": cur[0], "created": False, "deduped": False, "near_duplicates": []}
            old = db.execute("SELECT n FROM version WHERE asset_id=? AND content_key=?", (aid, ck)).fetchone()
            if old:
                db.execute("UPDATE asset SET current_version=?,updated_at=? WHERE id=?", (old[0], now, aid))
                self._fts_sync(aid)
                self._event("revert", aid, {"version": old[0]})
                return {"id": aid, "version": old[0], "created": False, "deduped": False, "reverted": True, "near_duplicates": []}
            n = db.execute("SELECT max(n) FROM version WHERE asset_id=?", (aid,)).fetchone()[0] + 1
            created = False
            made = True
        else:
            dup = db.execute("SELECT asset_id FROM version WHERE content_key=? AND ?>0 LIMIT 1", (ck, len(files))).fetchone()
            if dup:
                self._event("dedupe", dup[0], {"source_key": src["key"], "paths": [f["path"] for f in files]})
                return {"id": dup[0], "version": db.execute("SELECT current_version FROM asset WHERE id=?", (dup[0],)).fetchone()[0], "created": False, "deduped": True, "dedupe_of": dup[0], "near_duplicates": []}
            aid, n, created, made = self._id(), 1, True, True
            batch = spec.get("batch")
            if batch:
                db.execute("INSERT OR IGNORE INTO batch(id,label,source_id,started_at) VALUES(?,?,?,?)", (batch, src.get("label"), source_id, now))
            lic = spec.get("license")
            if lic:
                db.execute("INSERT OR IGNORE INTO license(id,name) VALUES(?,?)", (lic, lic))
            db.execute("INSERT INTO asset(id,kind,subtype,name,slug,description,source_id,source_key,license_id,attribution,current_version,created_at,updated_at,batch_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (aid, kind, spec.get("subtype"), spec["name"], _slug(spec["name"]), spec.get("description"), source_id, src["key"], lic, spec.get("attribution"), 1, now, now, batch))
        vid = self._id()
        attrs = _clean_urls(dict(spec.get("attrs") or {}))
        stats = dict(spec.get("stats") or {})
        table = S.KINDS[kind]["stats_table"]
        if table:
            cols = set(S.stats_columns(table, db)) - {"version_id"}
            row_vals = {k: v for k, v in stats.items() if k in cols}
            attrs.update({k: v for k, v in stats.items() if k not in cols})
            db.execute(f"INSERT INTO {table}(version_id{''.join(',' + k for k in row_vals)}) VALUES(?{',?' * len(row_vals)})", (vid, *[json.dumps(v) if isinstance(v, (dict, list)) else v for v in row_vals.values()]))
        elif stats:
            attrs.update(stats)
        db.execute("INSERT INTO version(id,asset_id,n,content_key,created_at,note,attrs_json) VALUES(?,?,?,?,?,?,?)", (vid, aid, n, ck, now, spec.get("note"), json.dumps(attrs, sort_keys=True)))
        for f in files:
            db.execute("INSERT INTO version_file(version_id,role,ord,sha256) VALUES(?,?,?,?)", (vid, f["role"], f["ord"], f["sha256"]))
        db.execute("UPDATE asset SET current_version=?,updated_at=? WHERE id=?", (n, now, aid))
        self._terms_tx(aid, spec.get("terms") or [], "rule")
        for g in spec.get("gates") or []:
            db.execute("INSERT INTO gate_result(version_id,gate,value,threshold,passed,detail_json,run_id,ts) VALUES(?,?,?,?,?,?,?,?)",
                       (vid, g["gate"], g.get("value"), g.get("threshold"), 1 if g.get("passed") else 0, json.dumps(g.get("detail") or {}, sort_keys=True), g.get("run_id"), now))
        for tag in spec.get("tags") or []:
            db.execute("INSERT OR IGNORE INTO tag(asset_id,tag,by) VALUES(?,?,?)", (aid, tag, spec.get("tags_by", "rule")))
        gen = spec.get("generation")
        if gen:
            gcols = {r[1] for r in db.execute("PRAGMA table_info(generation)")} - {"id", "version_id"}
            g = _clean_urls({k: v for k, v in gen.items() if k in gcols})
            if isinstance(g.get("params_json"), (dict, list)):
                g["params_json"] = json.dumps(g["params_json"], sort_keys=True)
            db.execute(f"INSERT INTO generation(id,version_id{''.join(',' + k for k in g)}) VALUES(?,?{',?' * len(g)})", (self._id(), vid, *g.values()))
        for r in spec.get("relations") or []:
            self._relate_tx(aid, r["type"], r["to"], r.get("by", "rule"), r.get("role", ""), r.get("attrs"))
        self._fts_sync(aid)
        self._event("put" if created else "version", aid, {"version": n, "source_key": src["key"]})
        return {"id": aid, "version": n, "created": True, "deduped": False, "near_duplicates": []}

    _RANK = {"model": 1, "rule": 2, "captain": 3}

    def _terms_tx(self, aid, terms, default_by):
        """A term row is replaced only by an equal or higher authority: captain > rule > model. A model's guess never overwrites a captain's term."""
        db, now = self._db, self._now()
        for t in terms:
            if t["facet"] not in S.FACETS:
                raise LibraryError(f"unknown facet {t['facet']!r}; facets: {S.FACETS}")
            by = t.get("by", default_by)
            if by not in self._RANK:
                raise LibraryError("term by: captain|rule|model")
            db.execute("INSERT OR IGNORE INTO term(facet,label) VALUES(?,?)", (t["facet"], t["label"]))
            tid = db.execute("SELECT id FROM term WHERE facet=? AND label=?", (t["facet"], t["label"])).fetchone()[0]
            cur = db.execute("SELECT by FROM asset_term WHERE asset_id=? AND term_id=?", (aid, tid)).fetchone()
            if cur and self._RANK[cur[0]] > self._RANK[by]:
                continue
            db.execute("INSERT OR REPLACE INTO asset_term(asset_id,term_id,by,confidence,rule,ts) VALUES(?,?,?,?,?,?)", (aid, tid, by, t.get("confidence"), t.get("rule"), now))

    def add_terms(self, aid: str, terms: list, by: str = "rule") -> dict:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if not self._db.execute("SELECT 1 FROM asset WHERE id=?", (aid,)).fetchone():
                    raise LibraryError(f"no asset {aid}")
                self._terms_tx(aid, [{**t, "by": t.get("by", by)} for t in terms], by)
                self._fts_sync(aid)
                self._event("terms", aid, {"terms": [f"{t['facet']}:{t['label']}" for t in terms]}, by)
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return {"id": aid, "terms": len(terms)}

    def record_blob(self, path, note=None) -> dict:
        """Hash a referenced file into ``blob`` + ``location`` with no asset (an archive the user keeps, recorded and never unpacked)."""
        with self._lock:
            p = Path(path)
            self._check_root(p)
            sha, st = self._hash_file(p)
            self._db.execute("BEGIN IMMEDIATE")
            try:
                now = self._now()
                self._db.execute("INSERT OR IGNORE INTO blob(sha256,bytes,mime,cas_path,first_seen) VALUES(?,?,?,?,?)", (sha, st.st_size, mimetypes.guess_type(str(p))[0], None, now))
                self._db.execute("INSERT INTO location(sha256,path,storage,mtime,size,last_verified,missing) VALUES(?,?,?,?,?,?,0) ON CONFLICT(sha256,path) DO UPDATE SET mtime=excluded.mtime,size=excluded.size,last_verified=excluded.last_verified,missing=0",
                                 (sha, str(p), "external", st.st_mtime, st.st_size, now))
                self._event("blob", None, {"sha256": sha, "path": str(p), "note": note})
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return {"sha256": sha, "bytes": st.st_size}

    def rollback(self, batch: str) -> dict:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                ids = [r[0] for r in self._db.execute("SELECT id FROM asset WHERE batch_id=? AND status='active'", (batch,))]
                for aid in ids:
                    self._db.execute("UPDATE asset SET status='deleted',updated_at=? WHERE id=?", (self._now(), aid))
                    self._fts_sync(aid)
                self._event("rollback", None, {"batch": batch, "soft_deleted": len(ids)})
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return {"batch": batch, "soft_deleted": len(ids)}

    def _fts_sync(self, aid: str):
        db = self._db
        a = db.execute("SELECT rowid,name,description,status,current_version FROM asset WHERE id=?", (aid,)).fetchone()
        db.execute("DELETE FROM asset_fts WHERE rowid=?", (a[0],))
        if a[3] != "active":
            return
        terms = " ".join(f"{r[0]} {r[1] or ''}" for r in db.execute("SELECT t.label,t.synonyms_json FROM asset_term a JOIN term t ON t.id=a.term_id WHERE a.asset_id=?", (aid,)))
        tags = " ".join(r[0] for r in db.execute("SELECT tag FROM tag WHERE asset_id=?", (aid,)))
        prompt = " ".join(r[0] for r in db.execute("SELECT g.prompt_text FROM generation g JOIN version v ON v.id=g.version_id WHERE v.asset_id=? AND g.prompt_text IS NOT NULL", (aid,)))
        paths = " ".join(_tokens(r[0]) for r in db.execute("SELECT l.path FROM location l JOIN version_file f ON f.sha256=l.sha256 JOIN version v ON v.id=f.version_id WHERE v.asset_id=? AND v.n=?", (aid, a[4])))
        db.execute("INSERT INTO asset_fts(rowid,name,description,terms,tags,prompt,path_tokens) VALUES(?,?,?,?,?,?,?)", (a[0], _tokens(a[1]) + " " + a[1], a[2] or "", terms, tags, prompt, paths))

    def set_status(self, aid: str, status: str, actor="server") -> dict:
        if status not in ("active", "archived", "deleted"):
            raise LibraryError("status: active|archived|deleted")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if not self._db.execute("SELECT 1 FROM asset WHERE id=?", (aid,)).fetchone():
                    raise LibraryError(f"no asset {aid}")
                self._db.execute("UPDATE asset SET status=?,updated_at=? WHERE id=?", (status, self._now(), aid))
                self._fts_sync(aid)
                self._event("status", aid, {"status": status}, actor)
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return {"id": aid, "status": status}

    def _relate_tx(self, src, rtype, dst, by, role="", attrs=None) -> dict:
        db = self._db
        if rtype not in S.RELATION_TYPES:
            raise LibraryError(f"unknown relation {rtype!r}; types: {S.RELATION_TYPES}")
        if src == dst:
            raise LibraryError("an asset cannot relate to itself")
        for x in (src, dst):
            if not db.execute("SELECT 1 FROM asset WHERE id=?", (x,)).fetchone():
                raise LibraryError(f"no asset {x}")
        if rtype == "derived_from":
            seen, queue = {dst: [dst]}, [dst]
            while queue:
                cur = queue.pop(0)
                if cur == src:
                    raise LibraryError("derived_from cycle: " + " -> ".join([src] + seen[cur]))
                for (nxt,) in db.execute("SELECT dst FROM relation WHERE src=? AND type='derived_from'", (cur,)):
                    if nxt not in seen:
                        seen[nxt] = seen[cur] + [nxt]
                        queue.append(nxt)
        cur = db.execute("INSERT OR IGNORE INTO relation(src,dst,type,role,attrs_json,by,created_at) VALUES(?,?,?,?,?,?,?)", (src, dst, rtype, role or "", json.dumps(attrs or {}, sort_keys=True), by, self._now()))
        if cur.rowcount:
            self._event("relate", src, {"type": rtype, "dst": dst, "role": role}, by)
        return {"created": bool(cur.rowcount)}

    def relate(self, src, rtype, dst, by, role="", attrs=None) -> dict:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                r = self._relate_tx(src, rtype, dst, by, role, attrs)
                self._db.execute("COMMIT")
                return r
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def rate(self, aid, rater, stars=None, flag=None, note=None) -> dict:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if not self._db.execute("SELECT 1 FROM asset WHERE id=?", (aid,)).fetchone():
                    raise LibraryError(f"no asset {aid}")
                ts = self._now()
                self._db.execute("INSERT INTO rating(asset_id,rater,stars,flag,note,ts) VALUES(?,?,?,?,?,?)", (aid, rater, stars, flag, note, ts))
                if stars is not None:
                    self._db.execute("UPDATE asset SET rating=?,updated_at=? WHERE id=?", (stars, ts, aid))
                self._event("rate", aid, {"stars": stars, "flag": flag}, rater)
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._journal({"question": "rating", "answer": {"stars": stars, "flag": flag}, "decider": rater, "asset_id": aid, "how": "rate", "words": note, "ts": ts})
        return {"id": aid, "stars": stars, "flag": flag}

    def decide(self, question, answer, decider, asset_id=None, version_id=None, options=None, how=None, session=None, descriptor=None, words=None, idempotent=False) -> dict:
        if decider not in ("captain", "model", "rule"):
            raise LibraryError("decider: captain|model|rule")
        desc = json.dumps(descriptor, sort_keys=True) if descriptor is not None else None
        with self._lock:
            if idempotent:
                sha = hashlib.sha256(desc.encode()).hexdigest() if desc else None
                row = self._db.execute("SELECT id FROM decision WHERE question=? AND answer=? AND decider=? AND session IS ? AND descriptor_sha256 IS ?", (question, answer, decider, session, sha)).fetchone()
                if row:
                    return {"id": row[0], "existing": True}
            ts = self._now()
            self._db.execute("BEGIN IMMEDIATE")
            try:
                cur = self._db.execute("INSERT INTO decision(session,asset_id,version_id,question,options_json,answer,decider,how,descriptor_json,descriptor_sha256,words,ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                                       (session, asset_id, version_id, question, json.dumps(options) if options is not None else None, answer, decider, how, desc,
                                        hashlib.sha256(desc.encode()).hexdigest() if desc else None, words, ts))
                self._event("decide", asset_id, {"question": question, "answer": answer}, decider)
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._journal({"session": session, "descriptor": descriptor, "question": question, "options": options, "answer": answer, "decider": decider, "how": how, "words": words, "asset_id": asset_id, "ts": ts})
        return {"id": cur.lastrowid, "existing": False}

    # -- helpers the ingest layer needs --------------------------------------------------------------------------
    def known_sha(self, sha: str) -> bool:
        with closing(self._reader()) as db:
            return db.execute("SELECT 1 FROM blob WHERE sha256=?", (sha,)).fetchone() is not None

    def mark_missing(self, path) -> int:
        with self._lock:
            n = self._db.execute("UPDATE location SET missing=1 WHERE path=?", (str(path),)).rowcount
            if n:
                self._event("missing", None, {"path": str(path)})
            return n

    def upsert_source(self, kind: str, root: str, label=None, watch: Optional[bool] = None) -> int:
        with self._lock:
            self._db.execute("INSERT OR IGNORE INTO source(kind,root,label,config_json) VALUES(?,?,?,?)", (kind, root, label, json.dumps({"watch": bool(watch)})))
            if watch is not None:
                self._db.execute("UPDATE source SET config_json=?,enabled=1 WHERE kind=? AND root=?", (json.dumps({"watch": bool(watch)}), kind, root))
            return self._db.execute("SELECT id FROM source WHERE kind=? AND root=?", (kind, root)).fetchone()[0]

    def sources(self) -> list:
        with closing(self._reader()) as db:
            return [{**dict(r), "config": json.loads(r["config_json"] or "{}")} for r in db.execute("SELECT id,kind,root,label,config_json,enabled FROM source ORDER BY id")]

    # -- read interface ------------------------------------------------------------------------------------------
    def get(self, aid: str, version: Optional[int] = None) -> dict:
        with closing(self._reader()) as db:
            db.execute("BEGIN")
            a = db.execute("SELECT * FROM asset WHERE id=?", (aid,)).fetchone()
            if not a:
                raise LibraryError(f"no asset {aid}")
            out = dict(a)
            v = db.execute("SELECT * FROM version WHERE asset_id=? AND n=?", (aid, version or a["current_version"])).fetchone()
            out["version"] = v["n"]
            out["attrs"] = json.loads(v["attrs_json"])
            out["files"] = [{"role": f["role"], "ord": f["ord"], "sha256": f["sha256"], "bytes": f["bytes"],
                             "locations": [dict(l) for l in db.execute("SELECT path,storage,missing FROM location WHERE sha256=? ORDER BY path", (f["sha256"],))]}
                            for f in db.execute("SELECT f.role,f.ord,f.sha256,b.bytes FROM version_file f JOIN blob b ON b.sha256=f.sha256 WHERE f.version_id=? ORDER BY f.role,f.ord", (v["id"],))]
            table = S.KINDS[a["kind"]]["stats_table"]
            out["stats"] = dict(db.execute(f"SELECT * FROM {table} WHERE version_id=?", (v["id"],)).fetchone() or {}) if table else {}
            out["terms"] = [dict(r) for r in db.execute("SELECT t.facet,t.label,a.by,a.confidence FROM asset_term a JOIN term t ON t.id=a.term_id WHERE a.asset_id=? ORDER BY t.facet,t.label", (aid,))]
            out["tags"] = [r[0] for r in db.execute("SELECT tag FROM tag WHERE asset_id=? ORDER BY tag", (aid,))]
            out["relations"] = [dict(r) for r in db.execute("SELECT src,dst,type,role,by FROM relation WHERE src=? OR dst=? ORDER BY id", (aid, aid))]
            out["generation"] = [dict(r) for r in db.execute("SELECT * FROM generation WHERE version_id=?", (v["id"],))]
            out["gates"] = [dict(r) for r in db.execute("SELECT gate,value,threshold,passed,detail_json FROM gate_result WHERE version_id=? ORDER BY id", (v["id"],))]
            return out

    def status(self) -> dict:
        with closing(self._reader()) as db:
            db.execute("BEGIN")
            q = lambda sql, *a: db.execute(sql, a).fetchone()[0]
            by_kind = {r[0]: r[1] for r in db.execute("SELECT kind,count(*) FROM asset WHERE status!='deleted' GROUP BY kind ORDER BY kind")}
            ref = q("SELECT coalesce(sum(b.bytes),0) FROM blob b WHERE EXISTS(SELECT 1 FROM location l WHERE l.sha256=b.sha256 AND l.storage='external') AND NOT EXISTS(SELECT 1 FROM location l WHERE l.sha256=b.sha256 AND l.storage='cas')")
            man = q("SELECT coalesce(sum(b.bytes),0) FROM blob b WHERE EXISTS(SELECT 1 FROM location l WHERE l.sha256=b.sha256 AND l.storage='cas')")
            wal = self.db_path.with_name(self.db_path.name + "-wal")
            return {"schema_version": q("PRAGMA user_version"),
                    "assets": {"by_kind": by_kind, "total": q("SELECT count(*) FROM asset"), "active": q("SELECT count(*) FROM asset WHERE status='active'")},
                    "versions": q("SELECT count(*) FROM version"), "blobs": q("SELECT count(*) FROM blob"), "bytes": {"referenced": ref, "managed": man},
                    "missing_files": q("SELECT count(*) FROM location WHERE missing=1"), "fts_rows": q("SELECT count(*) FROM asset_fts"),
                    "embeddings": {r[0]: r[1] for r in db.execute("SELECT space,count(*) FROM embedding GROUP BY space")},
                    "wal_bytes": wal.stat().st_size if wal.exists() else 0, "db_bytes": self.db_path.stat().st_size,
                    "integrity": q("PRAGMA quick_check(1)")}

    def verify(self, deep: bool = False, sample: int = 200) -> dict:
        with self._lock:
            db = self._db
            locs = db.execute("SELECT sha256,path,storage,mtime,size FROM location ORDER BY path LIMIT ?", (int(sample),)).fetchall()
            missing, mismatch, changed = [], [], []
            for sha, path, storage, mtime, size in locs:
                p = Path(path)
                if not p.is_file():
                    missing.append(path)
                    db.execute("UPDATE location SET missing=1 WHERE sha256=? AND path=?", (sha, path))
                    continue
                st = p.stat()
                if storage == "external" and (st.st_size != size or st.st_mtime != mtime):
                    changed.append(path)
                if deep:
                    h = hashlib.sha256()
                    with open(p, "rb") as fh:
                        while chunk := fh.read(CHUNK):
                            h.update(chunk)
                    if h.hexdigest() != sha:
                        mismatch.append(path)
            known = {r[0] for r in db.execute("SELECT sha256 FROM blob")}
            orphans = sorted(f.name for f in self.cas.rglob("*") if f.is_file() and ".tmp" not in f.name and f.name not in known) if self.cas.exists() else []
            fk = db.execute("PRAGMA foreign_key_check").fetchall()
            active = db.execute("SELECT count(*) FROM asset WHERE status='active'").fetchone()[0]
            return {"checked": len(locs), "missing": missing, "hash_mismatch": mismatch, "changed": changed,
                    "fts_drift": active - db.execute("SELECT count(*) FROM asset_fts").fetchone()[0], "orphan_rows": len(fk), "orphan_blobs": orphans}

    def backup(self, dest=None) -> dict:
        with self._lock:
            target = Path(dest) if dest else self.root / "backups" / f"library-{int(self._now())}.sqlite"
            if target.exists():
                raise LibraryError(f"backup target exists: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            self._db.execute(f"VACUUM INTO '{target}'")
            return {"path": str(target), "bytes": target.stat().st_size}

    def vacuum(self) -> dict:
        with self._lock:
            self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._db.execute("VACUUM")
            return {"ok": True}

