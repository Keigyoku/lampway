"""Asset Vault query (specs/asset_library/asset_query.md): one typed query shape over the library, plus the read-only SQL view.

Every value is bound; every field comes from a registry (a name, never a SQL fragment). Text is FTS5 BM25 (name weighted highest) over the filtered rows; similarity
lists, when an embedding space exists, fuse with it by reciprocal rank (``fuse``). Paging is an offset cursor tied to the DB generation (the highest ``event`` id): a
write makes the cursor stale instead of silently shifting a page."""
from __future__ import annotations

import base64
import difflib
import json
import re
import sqlite3
import time
from contextlib import closing

from . import schema as S
from .store import AssetLibrary, LibraryError

TOP = {"id": "a.id", "rating": "a.rating", "kind": "a.kind", "subtype": "a.subtype", "name": "a.name", "created_at": "a.created_at", "updated_at": "a.updated_at", "license": "a.license_id",
       "source": "s.kind", "status": "a.status"}
OPS = {"=": "=", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">="}
BM25_WEIGHTS = "10.0, 2.0, 4.0, 3.0, 1.0, 1.0"
SCORE_K = 5.0
RRF_K = 60
TERM_FACETS = set(S.FACETS)


def fuse(lists: list, weights: list) -> list:
    """Reciprocal rank fusion: score = sum_i w_i / (60 + rank_i). Scales differ between lists, so ranks are fused, never raw scores."""
    score: dict = {}
    for lst, w in zip(lists, weights):
        for rank, item in enumerate(lst, 1):
            score[item] = score.get(item, 0.0) + w / (RRF_K + rank)
    return sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))


def _stats_cols(db) -> dict:
    return {t: [r[1] for r in db.execute(f"PRAGMA table_info({t})") if r[1] != "version_id"] for t in {k["stats_table"] for k in S.KINDS.values() if k["stats_table"]}}


class _Compiler:
    def __init__(self, db):
        self.stats = _stats_cols(db)
        self.gen_cols = [r[1] for r in db.execute("PRAGMA table_info(generation)")]
        self.joins: set = set()
        self.params: list = []
        self.filters_text: list = []
        self.names = sorted(set(TOP) | {f"{t}.{c}" for t, cs in self.stats.items() for c in cs} | {f"generation.{c}" for c in self.gen_cols})

    def field(self, name: str) -> str:
        if name in TOP:
            return TOP[name]
        if name.startswith("gate."):
            parts = name.split(".")
            if len(parts) == 3 and parts[2] in ("passed", "value"):
                self.params.append(parts[1])
                return f"(SELECT g.{parts[2]} FROM gate_result g WHERE g.version_id=v.id AND g.gate=? ORDER BY g.id DESC LIMIT 1)"
        if "." in name:
            t, c = name.split(".", 1)
            if t in self.stats and c in self.stats[t]:
                self.joins.add(t)
                return f"{t}.{c}"
            if t == "generation" and c in self.gen_cols:
                return f"(SELECT g.{c} FROM generation g WHERE g.version_id=v.id LIMIT 1)"
        near = difflib.get_close_matches(name, self.names, n=3, cutoff=0.6)
        raise LibraryError(f"unknown field {name!r}; nearest: {near}; list: lampway_asset_schema")

    def cond(self, c: dict) -> str:
        op, value = c.get("op"), c.get("value")
        if op not in OPS and op not in ("between", "in", "like", "exists"):
            raise LibraryError(f"unknown op {op!r}; ops: = != < <= > >= between in like exists")
        pre = len(self.params)
        expr = self.field(c["field"])                       # a gate field binds its id first
        self.filters_text.append(f"{c['field']} {op} {value!r}")
        if op in OPS:
            self.params.append(value)
            return f"{expr} {OPS[op]} ?"
        if op == "between":
            if not (isinstance(value, (list, tuple)) and len(value) == 2):
                raise LibraryError("between needs [low, high]")
            self.params.extend(value)
            return f"{expr} BETWEEN ? AND ?"
        if op == "in":
            if not isinstance(value, (list, tuple)) or not value:
                raise LibraryError("in needs a non-empty list")
            self.params.extend(value)
            return f"{expr} IN ({','.join('?' * len(value))})"
        if op == "like":
            if not isinstance(value, str) or any(ch in value for ch in "%_"):
                raise LibraryError("like is prefix only: give plain text, no % or _ wildcards")
            self.params.append(value + "%")
            return f"{expr} LIKE ?"
        return f"{expr} IS NOT NULL" if value else f"{expr} IS NULL"

    def tree(self, node: dict) -> list:
        parts = []
        if node.get("all"):
            parts.append("(" + " AND ".join(self._item(c) for c in node["all"]) + ")")
        if node.get("any"):
            parts.append("(" + " OR ".join(self._item(c) for c in node["any"]) + ")")
        if node.get("none"):
            parts.append("NOT (" + " OR ".join(self._item(c) for c in node["none"]) + ")")
        return parts

    def _item(self, c):
        return "(" + " AND ".join(self.tree(c)) + ")" if ("all" in c or "any" in c or "none" in c) else self.cond(c)


def _compile(db, q: dict):
    c = _Compiler(db)
    where = []
    if q.get("kinds"):
        where.append(f"a.kind IN ({','.join('?' * len(q['kinds']))})")
        c.params.extend(q["kinds"])
    if q.get("where"):
        where.extend(c.tree(q["where"]))
    if not any(f.startswith("status ") for f in c.filters_text):
        where.append("a.status='active'")
    for facet, labels in (q.get("terms") or {}).items():
        if labels is None:
            continue
        if facet not in TERM_FACETS:
            raise LibraryError(f"unknown facet {facet!r}; facets: {S.FACETS}")
        labels = [labels] if isinstance(labels, str) else list(labels)
        where.append(f"EXISTS(SELECT 1 FROM asset_term at JOIN term t ON t.id=at.term_id WHERE at.asset_id=a.id AND t.facet=? AND t.label IN ({','.join('?' * len(labels))}))")
        c.params.extend([facet, *labels])
        c.filters_text.append(f"{facet} in {labels}")
    tags = q.get("tags") or {}
    for tag in tags.get("all") or []:
        where.append("EXISTS(SELECT 1 FROM tag g WHERE g.asset_id=a.id AND g.tag=?)")
        c.params.append(tag)
    if tags.get("any"):
        where.append(f"EXISTS(SELECT 1 FROM tag g WHERE g.asset_id=a.id AND g.tag IN ({','.join('?' * len(tags['any']))}))")
        c.params.extend(tags["any"])
    if tags.get("none"):
        where.append(f"NOT EXISTS(SELECT 1 FROM tag g WHERE g.asset_id=a.id AND g.tag IN ({','.join('?' * len(tags['none']))}))")
        c.params.extend(tags["none"])
    for r in q.get("relations") or []:
        if r["type"] not in S.RELATION_TYPES:
            raise LibraryError(f"unknown relation {r['type']!r}; types: {S.RELATION_TYPES}")
        mine, other = ("r.src", "r.dst") if r.get("direction", "out") == "out" else ("r.dst", "r.src")
        sub = f"SELECT 1 FROM relation r WHERE {mine}=a.id AND r.type=?" + (f" AND {other}=?" if r.get("of") else "")
        c.params.extend([r["type"]] + ([r["of"]] if r.get("of") else []))
        where.append(("EXISTS(" if r.get("exists", True) else "NOT EXISTS(") + sub + ")")
    return c, where


def _fts_match(text: str) -> str:
    toks = re.findall(r"[A-Za-z0-9_]+", text.lower())
    return " ".join(f'"{t}"*' for t in toks)


def _gen(db) -> int:
    return db.execute("SELECT coalesce(max(id),0) FROM event").fetchone()[0]


def _cursor(offset, gen) -> str:
    return base64.urlsafe_b64encode(json.dumps({"o": offset, "g": gen}).encode()).decode()


def query(lib: AssetLibrary, q: dict) -> dict:
    t0 = time.time()
    limit = int(q.get("limit", 50))
    if limit > 200:
        raise LibraryError("limit max 200: page with cursor")
    if limit < 1:
        raise LibraryError("limit min 1")
    if q.get("similar_to"):
        raise LibraryError("similar_to needs an embedding space: none is built yet (asset_embed)")
    with closing(lib._reader()) as db:
        db.execute("BEGIN")
        gen = _gen(db)
        offset = 0
        if q.get("cursor"):
            cur = json.loads(base64.urlsafe_b64decode(q["cursor"]))
            if cur["g"] != gen:
                raise LibraryError("cursor_stale: the library changed since this page; re-run the query")
            offset = cur["o"]
        c, where = _compile(db, q)
        text = _fts_match(q["text"]) if q.get("text") else None
        frm = "FROM asset a LEFT JOIN source s ON s.id=a.source_id JOIN version v ON v.asset_id=a.id AND v.n=a.current_version " + " ".join(f"LEFT JOIN {t} ON {t}.version_id=v.id" for t in sorted(c.joins))
        params = list(c.params)
        rank_sel = "0.0 AS rank"
        if q.get("text"):
            frm += " JOIN asset_fts ON asset_fts.rowid=a.rowid"
            where.append("asset_fts MATCH ?")
            params.append(text or '""')
            rank_sel = f"bm25(asset_fts, {BM25_WEIGHTS}) AS rank"
        wsql = (" WHERE " + " AND ".join(where)) if where else ""
        total = db.execute(f"SELECT count(*) {frm}{wsql}", params).fetchone()[0]
        if total == 0 and db.execute("SELECT count(*) FROM asset").fetchone()[0] == 0:
            return {"ok": True, "total": 0, "items": [], "facets": {}, "cursor": None, "took_ms": 0, "decision": None, "note": "library is empty: import the user's folders or the shelf seeds first"}
        sort = q.get("sort") or [{"by": "score" if q.get("text") else "created"}]
        order = []
        for s in sort:
            by, d = s["by"], s.get("dir")
            col = {"score": "rank", "created": "a.created_at", "name": "lower(a.name)", "rating": "a.rating"}.get(by)
            if by == "faces":
                col = "mesh_stats.faces"
                if "mesh_stats" not in c.joins:
                    frm += " LEFT JOIN mesh_stats ON mesh_stats.version_id=v.id"
            elif by == "duration":
                col = "video_stats.duration_s"
                if "video_stats" not in c.joins:
                    frm += " LEFT JOIN video_stats ON video_stats.version_id=v.id"
            if col is None:
                raise LibraryError(f"unknown sort {by!r}; sorts: score created name rating faces duration")
            default = "ASC" if by in ("name", "score") else "DESC"      # bm25 is negative: ascending is best-first
            if by == "score":
                d = "asc" if (d or "desc") == "desc" else "desc"
            order.append(f"{col} {(d or default).upper()}")
        order.append("a.id ASC")
        rows = db.execute(f"SELECT a.id,a.kind,a.subtype,a.name,v.n AS version,a.rating,v.id AS vid,{rank_sel} {frm}{wsql} ORDER BY {', '.join(order)} LIMIT ? OFFSET ?", [*params, limit, offset]).fetchall()
        include = q.get("include") or ["thumb", "tags"]
        items = []
        for r in rows:
            x = -r["rank"] if q.get("text") else 0.0
            score = round(x / (x + SCORE_K), 6) if q.get("text") else 0.0
            it = {"id": r["id"], "kind": r["kind"], "subtype": r["subtype"], "name": r["name"], "version": r["version"], "score": score, "rating": r["rating"], "thumb": None,
                  "why": {"text": score if q.get("text") else None, "image": None, "shape": None, "filters": c.filters_text, "terms": [f"{k}:{v}" for k, v in (q.get("terms") or {}).items() if v]}}
            if "tags" in include:
                it["tags"] = [t[0] for t in db.execute("SELECT tag FROM tag WHERE asset_id=? ORDER BY tag", (r["id"],))]
            if "stats" in include:
                table = S.KINDS[r["kind"]]["stats_table"]
                it["stats"] = dict(db.execute(f"SELECT * FROM {table} WHERE version_id=?", (r["vid"],)).fetchone() or {}) if table else {}
            if "provenance" in include:
                it["provenance"] = [dict(g) for g in db.execute("SELECT * FROM generation WHERE version_id=?", (r["vid"],))]
            if "relations" in include:
                it["relations"] = [dict(g) for g in db.execute("SELECT src,dst,type,role FROM relation WHERE src=? OR dst=?", (r["id"], r["id"]))]
            items.append(it)
        facets = {}
        sub = f"SELECT a.id {frm}{wsql}"
        for f in q.get("facets") or []:
            if f in ("kind", "license", "source", "rating", "status"):
                col = {"kind": "a.kind", "license": "a.license_id", "source": "(SELECT kind FROM source WHERE id=a.source_id)", "rating": "a.rating", "status": "a.status"}[f]
                rs = db.execute(f"SELECT {col} AS v, count(*) AS n FROM asset a WHERE a.id IN ({sub}) AND {col} IS NOT NULL GROUP BY v ORDER BY n DESC, v", params).fetchall()
            elif f in TERM_FACETS:
                rs = db.execute(f"SELECT t.label AS v, count(*) AS n FROM asset_term at JOIN term t ON t.id=at.term_id WHERE t.facet=? AND at.asset_id IN ({sub}) GROUP BY v ORDER BY n DESC, v", [f, *params]).fetchall()
            elif f == "model":
                rs = db.execute(f"SELECT g.model AS v, count(*) AS n FROM generation g JOIN version vv ON vv.id=g.version_id JOIN asset a ON a.id=vv.asset_id AND vv.n=a.current_version WHERE g.model IS NOT NULL AND a.id IN ({sub}) GROUP BY v ORDER BY n DESC, v", params).fetchall()
            elif f == "verdict":
                rs = db.execute(f"SELECT d.answer AS v, count(*) AS n FROM decision d WHERE d.question='verdict' AND d.asset_id IN ({sub}) GROUP BY v ORDER BY n DESC, v", params).fetchall()
            else:
                raise LibraryError(f"unknown facet {f!r}")
            facets[f] = [{"value": r["v"], "count": r["n"]} for r in rs]
        more = offset + len(rows) < total
        decision = None
        if q.get("threshold") is not None:
            scores = [it["score"] for it in items]
            if not scores or scores[0] < q["threshold"]:
                decision = "none"
            else:
                decision = "place" if len(scores) == 1 or scores[0] - scores[1] >= 0.1 else "ask"
        out = {"ok": True, "total": total, "items": items, "facets": facets, "cursor": _cursor(offset + len(rows), gen) if more else None, "took_ms": round((time.time() - t0) * 1000, 2), "decision": decision}
        if q.get("explain"):
            out["plan"] = {"sql": f"SELECT ... {frm}{wsql}", "order": order, "limit": limit, "offset": offset}
        return out


def readonly_sql(lib: AssetLibrary, sql: str, params=None, limit: int = 1000, timeout_s: float = 5.0) -> dict:
    """SELECT over the ``v_*`` views and the FTS table only. The authoriser denies every other action (writes, ATTACH, PRAGMA, load_extension, reads of base tables)."""
    if limit > 10000:
        raise LibraryError("limit max 10000")
    db = sqlite3.connect(f"file:{lib.db_path}?mode=ro", uri=True, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    banned = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}

    def auth(action, a1, a2, dbname, trigger):
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION:
            return sqlite3.SQLITE_DENY if (a2 or "").lower() in banned else sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            if a2 == "":
                return sqlite3.SQLITE_OK          # a table-level touch with no column data (a view's JOIN ... ON): it reads no values, only lets a count through
            if (a1 or "").startswith("v_") or (a1 or "").startswith("asset_fts") or (trigger or "").startswith("v_"):
                return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    db.set_authorizer(auth)
    deadline = time.time() + timeout_s
    db.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 10000)
    try:
        cur = db.execute(sql, params or [])
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(limit + 1)
        return {"columns": cols, "rows": [dict(r) for r in rows[:limit]], "truncated": len(rows) > limit}
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            raise LibraryError(f"query exceeded the time limit ({timeout_s:g} s) and was aborted") from None
        if "not authorized" in str(e):
            raise LibraryError(f"denied: only SELECT over the v_* views is allowed here ({e})") from None
        raise LibraryError(f"sql error: {e}") from None
    except sqlite3.DatabaseError as e:
        raise LibraryError(f"denied: only SELECT over the v_* views is allowed here ({e})") from None
    finally:
        db.close()
