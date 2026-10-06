"""Curation (specs/asset_library/asset_curate.md): ratings, verdicts, relations, boards and smart collections, saved searches, term confirmation, decisions.

Append-only wherever a decision is made (a correction is a new row). Authority: only the user rates as ``captain`` or confirms terms; an agent rates as ``agent:<id>`` and its
stars never move the user's. The effective rating on the asset is the user's latest stars, else the floored mean of the other raters', else NULL."""
from __future__ import annotations

import json
from typing import Optional

from . import ingest as I
from . import query as Q
from . import schema as S
from .store import AssetLibrary, LibraryError

VERDICTS = ("usable", "fix", "reject")
SHELF_VERDICTS = {"chosen": ("usable", "pick"), "runner-up": ("usable", None), "fix": ("fix", None)}


def _decider(rater: str) -> str:
    return "captain" if rater == "captain" else ("rule" if rater.startswith("rule:") else "model")


def map_verdict(word: str):
    """(vocabulary verdict, rating flag) for a verdict word: the contract's usable|fix|reject, or the shelf's chosen|runner-up|fix."""
    if word in SHELF_VERDICTS:
        return SHELF_VERDICTS[word]
    if word in VERDICTS:
        return word, ("reject" if word == "reject" else None)
    raise LibraryError(f"unknown verdict {word!r}; verdicts: {list(VERDICTS)} (the shelf's chosen / runner-up / fix are mapped)")


def rate(lib: AssetLibrary, asset_id: str, rater: str, stars: Optional[int] = None, flag: Optional[str] = None, verdict: Optional[str] = None, note: Optional[str] = None, origin: str = "user") -> dict:
    if not (rater == "captain" or rater.startswith(("agent:", "rule:"))):
        raise LibraryError("rater must be captain, agent:<id> or rule:<id>")
    if rater == "captain" and origin == "agent":
        raise LibraryError("ratings as the user are made in the Vault UI; agents rate as agent:<id>")
    if stars is not None and not (isinstance(stars, int) and 1 <= stars <= 5):
        raise LibraryError("stars are 1 to 5")
    if flag not in (None, "pick", "reject"):
        raise LibraryError("flag: pick|reject")
    if note and len(note) > 300:
        raise LibraryError("note is at most 300 characters")
    mapped = None
    if verdict:
        mapped, vflag = map_verdict(verdict)
        flag = flag or vflag
    res = lib.rate(asset_id, rater, stars=stars, flag=flag, note=note)
    out = {"ok": True, "asset_id": asset_id, "rating": lib.rating_summary(asset_id), "effective": res["rating"], "verdict": mapped}
    if mapped:
        d = lib.decide("verdict", mapped, _decider(rater), asset_id=asset_id, how=f"verdict:{verdict}", words=note)
        out["decision_id"] = d["id"]
    return out


def shelf_word(lib: AssetLibrary, asset_id: str) -> Optional[str]:
    """The word the verdict was first written in (chosen / runner-up / fix / usable ...), recovered from ``how``; nothing is lost in the mapping."""
    row = lib._reader().execute("SELECT answer,how FROM decision WHERE asset_id=? AND question='verdict' ORDER BY id DESC LIMIT 1", (asset_id,)).fetchone()
    if not row:
        return None
    return row[1].split(":", 1)[1] if row[1] and ":" in row[1] and row[1].split(":", 1)[0] in ("verdict", "shelf_seeds") else row[0]


def relate(lib: AssetLibrary, src: str, rtype: str, dst: str, by: str, role: str = "", attrs: Optional[dict] = None, remove: bool = False) -> dict:
    if remove:
        return {"ok": True, "removed": lib.remove_relation(src, rtype, dst, role)}
    r = lib.relate(src, rtype, dst, by=by, role=role, attrs=attrs)
    return {"ok": True, **r, "edges_for_src": lib._reader().execute("SELECT count(*) FROM relation WHERE src=?", (src,)).fetchone()[0]}


def decide(lib: AssetLibrary, question: str, answer: str, asset_ids=(), options=None, words=None, decider: str = "captain", how: Optional[str] = None, session: Optional[str] = None, origin: str = "user") -> dict:
    if decider == "captain" and origin == "agent":
        raise LibraryError("decisions as the user are made in the Vault UI; an agent's decision is recorded as decider 'model'")
    ids = list(asset_ids) or [None]
    last = None
    for a in ids:
        last = lib.decide(question, answer, decider, asset_id=a, options=options, how=how, session=session, words=words)
    return {"ok": True, "decision_id": last["id"]}


def confirm_terms(lib: AssetLibrary, asset_id: str, terms: list, by: str) -> dict:
    """Accepting a proposed term makes it the user's (a decision is recorded); rejecting removes the proposal and remembers the rejection so it is not suggested again."""
    I.Ingest._need_user(by, "confirming terms")
    acc = rej = 0
    for t in terms:
        key = f"term:{t['facet']}:{t['label']}"
        if t.get("accept"):
            lib.add_terms(asset_id, [{"facet": t["facet"], "label": t["label"]}], by="captain")
            lib.decide(key, "accepted", "captain", asset_id=asset_id, how="confirm_terms")
            acc += 1
        else:
            with lib.tx() as db:
                db.execute("DELETE FROM asset_term WHERE asset_id=? AND term_id IN (SELECT id FROM term WHERE facet=? AND label=?) AND by='model'", (asset_id, t["facet"], t["label"]))
                lib._fts_sync(asset_id)
            lib.decide(key, "rejected", "captain", asset_id=asset_id, how="confirm_terms")
            rej += 1
    return {"ok": True, "accepted": acc, "rejected": rej}


def _check_query(lib, query):
    if query:
        Q.query(lib, {**query, "limit": 1})          # an invalid smart query is refused now, with the query engine's own text


def collect(lib: AssetLibrary, action: str, collection: Optional[str] = None, name: Optional[str] = None, kind: str = "board", asset_ids=(), query: Optional[dict] = None, x_y=None) -> dict:
    actions = ("create", "add", "remove", "list", "get", "delete", "save_search", "run_search", "list_searches")
    if action not in actions:
        raise LibraryError(f"unknown action {action!r}; actions: {list(actions)}")
    if action == "create":
        if kind not in ("board", "smart"):
            raise LibraryError("kind: board|smart")
        if kind == "smart":
            _check_query(lib, query)
        with lib.tx() as db:
            cid = lib._id()
            db.execute("INSERT INTO collection(id,name,kind,query_json,created_at) VALUES(?,?,?,?,?)", (cid, name or cid, kind, json.dumps(query) if query else None, lib._now()))
            lib._event("collection", None, {"id": cid, "action": "create"})
        return {"ok": True, "collection": {"id": cid, "name": name or cid, "kind": kind, "items": 0}}
    if action == "list":
        rows = lib._reader().execute("SELECT c.id,c.name,c.kind,(SELECT count(*) FROM collection_item i WHERE i.collection_id=c.id) AS n FROM collection c ORDER BY c.created_at").fetchall()
        return {"ok": True, "collections": [{"id": r[0], "name": r[1], "kind": r[2], "items": r[3]} for r in rows], "total": len(rows)}
    if action == "save_search":
        _check_query(lib, query)
        with lib.tx() as db:
            sid = lib._id()
            db.execute("INSERT INTO saved_search(id,name,query_json,owner,created_at) VALUES(?,?,?,?,?)", (sid, name or sid, json.dumps(query or {}), None, lib._now()))
        return {"ok": True, "search": {"id": sid, "name": name or sid}}
    if action == "list_searches":
        rows = lib._reader().execute("SELECT id,name,query_json FROM saved_search ORDER BY created_at").fetchall()
        return {"ok": True, "searches": [{"id": r[0], "name": r[1], "query": json.loads(r[2])} for r in rows]}
    if action == "run_search":
        row = lib._reader().execute("SELECT query_json FROM saved_search WHERE id=? OR name=?", (collection, collection)).fetchone()
        if not row:
            raise LibraryError(f"no saved search {collection!r}")
        res = Q.query(lib, json.loads(row[0]))
        return {"ok": True, "items": res["items"], "total": res["total"]}
    row = lib._reader().execute("SELECT id,name,kind,query_json FROM collection WHERE id=? OR name=?", (collection, collection)).fetchone()
    if not row:
        raise LibraryError(f"no collection {collection!r}")
    cid, cname, ckind, cq = row
    if action == "get":
        if ckind == "smart":
            res = Q.query(lib, json.loads(cq))
            return {"ok": True, "collection": {"id": cid, "name": cname, "kind": ckind}, "items": res["items"], "total": res["total"]}
        rows = lib._reader().execute("SELECT i.asset_id,i.ord,i.note,i.x,i.y,a.name FROM collection_item i JOIN asset a ON a.id=i.asset_id WHERE i.collection_id=? ORDER BY i.ord", (cid,)).fetchall()
        return {"ok": True, "collection": {"id": cid, "name": cname, "kind": ckind}, "items": [{"id": r[0], "ord": r[1], "note": r[2], "x": r[3], "y": r[4], "name": r[5]} for r in rows], "total": len(rows)}
    if action == "delete":
        with lib.tx() as db:
            db.execute("DELETE FROM collection_item WHERE collection_id=?", (cid,))
            db.execute("DELETE FROM collection WHERE id=?", (cid,))
        return {"ok": True, "deleted": cid}
    if ckind == "smart":
        raise LibraryError("a smart collection is a live query: change its query, not its items")
    with lib.tx() as db:
        if action == "add":
            n = db.execute("SELECT coalesce(max(ord),-1)+1 FROM collection_item WHERE collection_id=?", (cid,)).fetchone()[0]
            for k, a in enumerate(asset_ids):
                if not db.execute("SELECT 1 FROM asset WHERE id=?", (a,)).fetchone():
                    raise LibraryError(f"no asset {a}")
                x, y = (x_y or (None, None))
                db.execute("INSERT OR REPLACE INTO collection_item(collection_id,asset_id,ord,x,y) VALUES(?,?,?,?,?)", (cid, a, n + k, x, y))
        else:
            for a in asset_ids:
                db.execute("DELETE FROM collection_item WHERE collection_id=? AND asset_id=?", (cid, a))
    return {"ok": True, "collection": {"id": cid, "name": cname, "kind": ckind, "items": lib._reader().execute("SELECT count(*) FROM collection_item WHERE collection_id=?", (cid,)).fetchone()[0]}}
