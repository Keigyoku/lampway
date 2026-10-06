"""The Asset Vault's tool family for the main agent, swarm workers and external MCP clients (specs/asset_library/asset_mcp.md; the captain's answer, BUILD_ORDER.md Wave 5b
item 3: the MCP tool names are ``lampway_vault_*``). The SAME definitions serve every caller and run here on the server: no Blender round trip, so they work with no scene
open. ``lampway_vault_place`` and ``lampway_vault_catalog_export`` are Blender-side Defs in lampway_tools.py.

Authority is a table, not a habit: every tool needs one authority (read, write_curation, write_ingest, spend) and every caller's origin holds a set of them. No tool here
spends. An agent's ingest is a preview (``scan``) of folders inside the project root or a source the user registered; importing, watching and an uploading embedding run are
the user's click in the Vault panel. Writes are attributed (``agent:<id>``; the rater is never the caller's choice), and a rate limit per caller keeps a swarm from flooding
the library."""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections import deque
from pathlib import Path

from ..library import curate as CU
from ..library import provenance as P
from ..library import similar as SIM
from ..library.store import LibraryError
from .providers.base import ToolSpec

AUTHORITY = {"lampway_vault": "read", "lampway_vault_search": "read", "lampway_vault_get": "read", "lampway_vault_similar": "read", "lampway_vault_provenance": "read",
             "lampway_vault_relate": "write_curation", "lampway_vault_rate": "write_curation", "lampway_vault_collect": "write_curation",
             "lampway_vault_scan": "write_ingest", "lampway_vault_embed": "write_ingest"}
NAMES = set(AUTHORITY)
GRANTS = {"agent": {"read", "write_curation", "write_ingest"}, "mcp": {"read", "write_curation", "write_ingest"}, "worker": {"read", "write_curation"}}
WRITES = {n for n, a in AUTHORITY.items() if a != "read"}
SCAN_HELP = "the library is empty: preview a folder with lampway_vault_scan {paths: [<a folder in the project>]}; the user imports the preview in the Vault panel"


def _obj(props: dict, required=()) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": props, "required": list(required)}


S, I, N, B, O = {"type": "string"}, {"type": "integer"}, {"type": "number"}, {"type": "boolean"}, {"type": "object"}
SA = {"type": "array", "items": {"type": "string"}}

SPECS = [
    ToolSpec("lampway_vault", "The Asset Vault at a glance: asset counts by kind, missing files, embedding coverage and the next steps (no arguments). action verify re-hashes a sample "
             "of the files and lists the moved and changed ones. Read-only.", _obj({"action": S})),
    ToolSpec("lampway_vault_search", "Search the user's Asset Vault BEFORE generating or modelling anything: `text` (name, tags, terms: ranked, the name weighs most), `kinds`, `terms` "
             "{facet: label}, `tags`, `where` (typed filters: {field, op, value} or {all|any|none: [...]}; fields such as kind, rating, mesh_stats.tris), `image` (a picture inside "
             "the project: matched by look), `threshold` 0..1 for a decision (place: one confident match; ask: show the user the candidates; none), `limit` (default 20, max 200), "
             "`cursor` (next_cursor of the last page). Items are compact; read one with lampway_vault_get, put it in the scene with lampway_vault_place. only_library: what is "
             "missing stays missing.", _obj({"text": S, "kinds": SA, "terms": O, "tags": SA, "where": O, "image": S, "threshold": N, "limit": I, "cursor": S, "facets": SA,
                                              "only_library": B})),
    ToolSpec("lampway_vault_get", "One asset's record: kind, stats, terms, tags, relations, generation, and `files` as {role: {path, bytes, sha256}} so a path can go to another tool. "
             "include [members] lists a texture set's maps.", _obj({"id": S, "version": I, "include": SA}, ["id"])),
    ToolSpec("lampway_vault_similar", "Assets like a selection: `asset_ids` (what is selected), or `image` (a picture inside the project), or `text`; `axes` shape | look | name "
             "(default all that apply); `kinds` to restrict; `k` (default 12). Scores renormalise over the axes both sides have.",
             _obj({"asset_ids": SA, "image": S, "text": S, "axes": SA, "kinds": SA, "k": I})),
    ToolSpec("lampway_vault_scan", "Preview what folders would add to the Vault: `paths` inside the project root or under a source the user registered. It reads and reports (kinds, "
             "counts, duplicates, proposed terms) and enrols and imports NOTHING; importing the preview is the user's click in the Vault panel.", _obj({"paths": SA}, ["paths"])),
    ToolSpec("lampway_vault_relate", "Record how two assets relate: `type` derived_from | variant_of | part_of | textured_by | fits_body | rigged_to | generated_from | drives | uses | "
             "frame_of | supersedes, from `src` to `dst` (remove: true takes it back). Attributed to you.",
             _obj({"src": S, "type": S, "dst": S, "role": S, "remove": B}, ["src", "type", "dst"])),
    ToolSpec("lampway_vault_rate", "Rate an asset as yourself (agent:<id>): `stars` 1..5, `flag` pick | reject, `verdict` usable | fix | reject, a short `note`. The user's stars always "
             "win the effective rating; yours are shown, labelled agent.", _obj({"id": S, "stars": I, "flag": S, "verdict": S, "note": S}, ["id"])),
    ToolSpec("lampway_vault_collect", "Boards, smart collections and saved searches: action list | create (name, kind board | smart, query for smart) | add / remove (collection, "
             "asset_ids) | get | save_search | run_search | list_searches.", _obj({"action": S, "collection": S, "name": S, "kind": S, "asset_ids": SA, "query": O}, ["action"])),
    ToolSpec("lampway_vault_provenance", "Where an asset came from: action show (id: its generation rows, prompt, parents and children) or audit (what the library cannot trace yet).",
             _obj({"action": S, "id": S}, ["action"])),
    ToolSpec("lampway_vault_embed", "Similarity vectors: action plan (space image_hist | image_dhash | shape_d2 | a bundled local space, or text_api with a model) says what would be "
             "embedded and whether anything would leave the machine; action run (plan_id) computes a plan that uploads nothing. A plan that uploads is the user's confirm in "
             "the Vault panel.", _obj({"action": S, "space": S, "model": S, "asset_ids": SA, "plan_id": S}, ["action"])),
]
BY_NAME = {s.name: s for s in SPECS}


class Limiter:
    """Calls and writes per caller per minute (sizes from the contract, [UNVERIFIED] against real swarm load)."""

    def __init__(self, calls: int = 120, writes: int = 20, window: float = 60.0):
        self.calls, self.writes, self.window = calls, writes, window
        self._seen: dict = {}
        self._lock = threading.Lock()

    def check(self, actor: str, write: bool) -> None:
        now = time.monotonic()
        with self._lock:
            calls, writes = self._seen.setdefault(actor, (deque(), deque()))
            for q in (calls, writes):
                while q and now - q[0] > self.window:
                    q.popleft()
            if len(calls) >= self.calls:
                raise LibraryError(f"{self.calls} calls per minute reached for {actor}: wait a moment")
            if write and len(writes) >= self.writes:
                raise LibraryError(f"{self.writes} writes per minute reached for {actor}: wait a moment")
            calls.append(now)
            if write:
                writes.append(now)


LIMITER = Limiter()


def _inside(path: Path, root: Path) -> bool:
    real_root = Path(os.path.realpath(root))
    return path == real_root or real_root in path.parents


def _project_path(vault, path: str) -> str:
    root = vault.project_root
    real = Path(os.path.realpath(Path(path) if Path(path).is_absolute() else root / path))
    if not _inside(real, root):
        raise LibraryError(f"{path} is outside the project root: the user adds other source folders in the Vault panel")
    return str(real)


def _scan_path(vault, path: str) -> str:
    real = Path(os.path.realpath(Path(path) if Path(path).is_absolute() else vault.project_root / path))
    if _inside(real, vault.project_root) or any(s.get("kind") == "folder" and s.get("root") and _inside(real, Path(s["root"])) for s in vault.lib.sources()):
        return str(real)
    raise LibraryError(f"{path} is outside the project root and every source the user registered: the user adds source folders in the Vault panel")


def compact_record(rec: dict) -> dict:
    files = {}
    for f in rec.get("files") or []:
        key = f["role"] if not f.get("ord") else f"{f['role']}:{f['ord']}"
        loc = next((l for l in f.get("locations") or [] if not l.get("missing")), None)
        files[key] = {"path": loc["path"] if loc else None, "bytes": f.get("bytes"), "sha256": f.get("sha256"), "storage": loc["storage"] if loc else None}
    out = {k: rec.get(k) for k in ("id", "kind", "subtype", "name", "version", "status", "rating", "license_id", "attribution", "description")}
    out.update({"files": files, "stats": {k: v for k, v in (rec.get("stats") or {}).items() if v is not None and k != "version_id"}, "terms": rec.get("terms"), "tags": rec.get("tags"),
                "relations": rec.get("relations"), "generation": [{k: g.get(k) for k in ("studio", "model", "action", "prompt_text", "job_id", "cost_usd")} for g in rec.get("generation") or []]})
    if "members" in rec:
        out["members"] = [compact_record(m) for m in rec["members"]]
    return out


def _search(vault, a: dict) -> dict:
    if a.get("image"):
        return SIM.similar(vault.lib, {"image_path": _project_path(vault, a["image"])}, axes=("look",), kinds=a.get("kinds"), k=int(a.get("limit") or 12))
    q = {k: a[k] for k in ("text", "terms", "kinds", "threshold", "cursor", "facets") if a.get(k) not in (None, "", [], {})}
    where = a.get("where")
    if where:
        q["where"] = {"all": [where]} if "field" in where else where           # one bare condition is a one-item tree: every field still goes through the registry
    if a.get("tags"):
        q["tags"] = {"all": list(a["tags"])}
    q["limit"] = int(a.get("limit") or 20)
    q["include"] = ["tags"]
    res = vault.query(q)
    res["next_cursor"] = res.pop("cursor", None)
    if res["total"] == 0 and res.get("note"):
        res["help"] = [SCAN_HELP]
    if a.get("only_library") and not res["items"]:
        res["decision"] = "none"
        res["note"] = "only_library: nothing in the library matches; it is never replaced by a generation or a substitute: tell the user it is missing"
    return res


def _overview(vault, a: dict) -> dict:
    if a.get("action") == "verify":
        return vault.lib.verify()
    if a.get("action"):
        raise LibraryError("lampway_vault takes no action, or action verify")
    st = vault.lib.status()
    out = {"assets": st["assets"], "missing_files": st["missing_files"], "embeddings": st["embeddings"], "schema_version": st["schema_version"]}
    out["help"] = [SCAN_HELP] if not st["assets"]["total"] else ["try lampway_vault_search {text: ...}", "lampway_vault_place {asset_id} puts one in the scene"]
    return out


def _scan(vault, a: dict) -> dict:
    paths = [_scan_path(vault, p) for p in a.get("paths") or []]
    if not paths:
        raise LibraryError("scan needs paths: folders inside the project root or a source the user registered")
    out = vault.ingest.scan(paths)
    out["note"] = "a preview: nothing was enrolled or imported; the user's click in the Vault panel imports it"
    return out


def _embed(vault, a: dict, actor: str) -> dict:
    if a.get("action") == "plan":
        return vault.embed.plan(str(a.get("space") or ""), a.get("asset_ids") or None, model=a.get("model"))
    if a.get("action") == "run":
        return vault.embed.run(str(a.get("plan_id") or ""), by=actor)
    raise LibraryError("action is plan or run")


def _run(vault, name: str, a: dict, actor: str) -> dict:
    if name == "lampway_vault":
        return _overview(vault, a)
    if name == "lampway_vault_search":
        return _search(vault, a)
    if name == "lampway_vault_get":
        return compact_record(vault.get_record(str(a["id"]), a.get("version"), include=a.get("include") or ()))
    if name == "lampway_vault_similar":
        sel = {"asset_ids": list(a.get("asset_ids") or []), "text": a.get("text")}
        if a.get("image"):
            sel["image_path"] = _project_path(vault, a["image"])
        return SIM.similar(vault.lib, sel, **{k: v for k, v in (("axes", a.get("axes")), ("kinds", a.get("kinds")), ("k", a.get("k"))) if v})
    if name == "lampway_vault_scan":
        return _scan(vault, a)
    if name == "lampway_vault_embed":
        return _embed(vault, a, actor)
    if name == "lampway_vault_relate":
        return CU.relate(vault.lib, str(a["src"]), str(a["type"]), str(a["dst"]), by=actor, role=str(a.get("role") or ""), remove=bool(a.get("remove")))
    if name == "lampway_vault_rate":
        return vault.rate(str(a["id"]), actor, origin="agent", stars=a.get("stars"), flag=a.get("flag"), verdict=a.get("verdict"), note=a.get("note"))
    if name == "lampway_vault_collect":
        return CU.collect(vault.lib, str(a["action"]), a.get("collection"), a.get("name"), a.get("kind") or "board", a.get("asset_ids") or (), a.get("query"))
    if name == "lampway_vault_provenance":
        if a.get("action") == "audit":
            return P.audit(vault.lib)
        if a.get("action") == "show" and a.get("id"):
            rec = vault.get(str(a["id"]))
            return {"id": rec["id"], "generation": rec["generation"], "relations": rec["relations"]}
        raise LibraryError("action is show (with id) or audit")
    raise LibraryError(f"unknown tool {name!r}")


async def call(vault, name: str, arguments: dict, ctx: dict = None, limiter: Limiter = None) -> tuple:
    """(JSON text, is_error) for one call. ``ctx`` = {origin: agent | worker | mcp, agent_id}: the authority comes from the origin, the attribution (agent:<id>) from the id."""
    ctx = ctx or {}
    origin, actor = str(ctx.get("origin") or "agent"), f"agent:{ctx.get('agent_id') or 'main'}"
    if vault is None:
        return "the Asset Vault is not available on this server", True
    if name not in NAMES:
        return f"unknown tool {name!r}", True
    need = AUTHORITY[name]
    if need not in GRANTS.get(origin, set()):
        return f"{name} needs {need}, which a {origin} is not allowed: ask the main agent or the user", True
    a = arguments if isinstance(arguments, dict) else {}
    spec = BY_NAME[name].parameters
    unknown = sorted(set(a) - set(spec["properties"]))
    if unknown:
        return f"{name} takes no argument {', '.join(unknown)}; its arguments are {sorted(spec['properties'])} (the rater is always you)", True
    missing = [k for k in spec["required"] if a.get(k) in (None, "", [])]
    if missing:
        return f"{name} needs {', '.join(missing)}", True
    try:
        (limiter or LIMITER).check(actor, name in WRITES)
        out = await asyncio.to_thread(_run, vault, name, a, actor)
    except (LibraryError, ValueError, TypeError) as exc:
        return str(exc).strip("'\""), True
    return json.dumps({"ok": True, **out} if isinstance(out, dict) else {"ok": True, "result": out}, default=str), False


def specs() -> list:
    return list(SPECS)
