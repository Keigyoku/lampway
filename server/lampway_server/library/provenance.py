"""Provenance capture (specs/asset_library/asset_provenance.md): one hook every generating tool calls, so an asset's origin exists the moment the asset does.

``record`` writes the assets (generation outputs go into managed storage: they are the only copy), one ``generation`` row per output, the prompt as its own asset keyed by
template@version + variables, and ``generated_from`` / ``derived_from`` relations to every parent it can resolve (an unresolved parent is kept as text). ``capture`` is what
tools call: provenance failures are returned/spooled (secrets and signed URLs removed), so they cannot fail a generation; owning-operation cancellation
propagates. ``replay_spool`` retries capture and indexed output relationships."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from pathlib import Path
from typing import Optional

from .store import AssetLibrary, LibraryError, _clean_urls

REQUIRED = {"video_gen": ["model", "provider", "prompt_sha256", "params_json", "cost_basis", "job_id", "started_at"],
            "image_to_model": ["studio", "model", "action", "job_id", "seed|seed_not_exposed"],
            "local_edit": ["tool", "parent_seed"], "image_gen": ["model", "prompt_sha256", "job_id"],
            "motion_graphics": ["action", "job_id", "params_json"]}
DEFAULT_REQUIRED = ["action", "job_id"]
PARENT_RELATIONS = {"parent_seed": ("derived_from", "parent_seed"), "start_frame": ("generated_from", "start_frame"), "end_frame": ("generated_from", "end_frame"),
                    "reference_video": ("generated_from", "reference_video")}
_JOBFILE_TOKEN = re.compile(r"(/jobs/files/)[^/\s\"']+")


def _clean(o):
    if isinstance(o, str):
        return _JOBFILE_TOKEN.sub(r"\1[redacted]", _clean_urls(o))
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


def _missing(action: str, g: dict, has_parent: bool) -> list:
    out = []
    for f in REQUIRED.get(action, DEFAULT_REQUIRED):
        if f == "seed|seed_not_exposed":
            ok = g.get("seed") is not None or g.get("seed_not_exposed")
        elif f == "parent_seed":
            ok = has_parent
        elif f == "params_json":
            ok = bool(g.get("params_json")) and g["params_json"] not in ("{}", "null")
        else:
            ok = g.get(f) not in (None, "")
        if not ok:
            out.append(f)
    return out


def _checked_spool_output(output: dict) -> dict:
    if not output.get("spool_blob"):
        return output
    path = Path(output["path"])
    expected = output.get("spool_sha256") or path.name
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise LibraryError("spooled bytes need their capture SHA-256")
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise LibraryError("spooled bytes must be a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            data = source.read()
    finally:
        os.close(descriptor)
    if hashlib.sha256(data).hexdigest() != expected:
        raise LibraryError("spooled bytes changed after capture; preserve the spool and restore the captured blob")
    return {**output, "bytes": data}


def _put_owned(lib, spec, cancel=None):
    """Cancellation and publication share an admission point; record every admitted commit before returning."""
    def put():
        result = lib.put(spec)
        if cancel is not None:
            cancel.record_assets([{"id": result["id"], "kind": spec["kind"]}])
        return result
    return cancel.commit_owned(put) if cancel is not None else put()


def record(lib: AssetLibrary, payload: dict, *, cancel=None) -> dict:
    g = dict(payload.get("generation") or {})
    outputs = [_checked_spool_output(o) for o in payload.get("outputs") or []]
    ok = g.get("ok", True)
    if g.get("cost_basis") == "estimated" and g.get("cost_usd") is None and g.get("cost_credits") is None:
        raise LibraryError("estimated cost needs a number or basis 'none'")
    for o in outputs:
        if ok and "bytes" not in o and not Path(o["path"]).is_file():
            raise LibraryError(f"output not found: {o['path']}; record only after the file exists")
    seed = g.get("seed")
    prompt = g.get("prompt_text")
    template_id, template_version, vars_ = g.get("template_id"), g.get("template_version"), g.get("vars") or {}
    prompt_asset = None
    if prompt:
        if cancel is not None:
            cancel.check()
        vars_sha = hashlib.sha256(json.dumps(vars_, sort_keys=True).encode()).hexdigest()[:16]
        key = f"{template_id}@{template_version}:{vars_sha}" if template_id else "prompt:" + hashlib.sha256(prompt.encode()).hexdigest()[:16]
        prompt_asset = _put_owned(lib, {"kind": "prompt", "subtype": "filled" if vars_ or not template_id else "template", "name": f"{template_id or 'prompt'} {template_version or ''}".strip(),
                                "source": {"kind": "provenance", "key": key}, "files": [{"role": "main", "bytes": prompt.encode(), "storage": "cas"}],
                                "stats": {"template_id": template_id, "template_version": template_version, "vars_json": json.dumps(vars_, sort_keys=True), "chars": len(prompt)}}, cancel)["id"]
    parents, unresolved, rels = g.get("parents") or {}, [], []
    cols = {"parent_seed": "parent_seed_asset", "start_frame": "start_frame_asset", "end_frame": "end_frame_asset", "reference_video": "reference_video_asset"}
    gen = {"studio": g.get("studio"), "provider": g.get("provider"), "model": g.get("model"), "model_version": g.get("model_version"), "action": g.get("action"), "prompt_asset": prompt_asset,
           "prompt_text": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest() if prompt else None, "template_id": template_id, "template_version": template_version,
           "seed": None if seed in (None, "not_exposed") else str(seed), "seed_not_exposed": 1 if seed == "not_exposed" else 0, "cost_usd": g.get("cost_usd"), "cost_credits": g.get("cost_credits"),
           "cost_basis": g.get("cost_basis"), "job_id": g.get("job_id"), "started_at": g.get("started_at"), "finished_at": g.get("finished_at"), "approved_by": g.get("approved_by"),
           "tool": payload.get("tool"), "tool_version": payload.get("tool_version"),
           "params_json": json.dumps(_clean({"params": g.get("params") or {}, "vars": vars_, "ok": bool(ok), "error": g.get("error")}), sort_keys=True)}
    for role, (rtype, label) in PARENT_RELATIONS.items():
        ref = parents.get(role)
        if ref:
            aid = lib.resolve_asset(ref)
            if aid:
                rels.append({"type": rtype, "to": aid, "role": label})
                if role in cols:
                    gen[cols[role]] = aid
            else:
                unresolved.append({"role": role, "ref": ref})
    refs = []
    for ref in parents.get("reference_images") or []:
        aid = lib.resolve_asset(ref)
        if aid:
            rels.append({"type": "generated_from", "to": aid, "role": "reference_image"})
            refs.append(aid)
        else:
            unresolved.append({"role": "reference_images", "ref": ref})
    gen["reference_image_assets_json"] = json.dumps(refs) if refs else None
    res = {"ok": True, "assets": [], "generation_ids": [], "relations": [], "unresolved_parents": unresolved}
    missing_all: list = []
    if not outputs:
        generation_id = cancel.commit_owned(lib.add_generation, None, gen) if cancel is not None else lib.add_generation(None, gen)
        res["generation_ids"].append(generation_id)
        res["completeness"] = _completeness(g.get("action"), gen, bool(rels))
        return res
    for i, o in enumerate(outputs):
        attrs = dict(o.get("attrs") or {})
        if any(isinstance(v, str) and "?" in v and v.startswith("http") for v in attrs.values()):
            attrs["url_stripped"] = True
        if unresolved:
            attrs["parent_ref"] = {u["role"]: u["ref"] for u in unresolved}
        terms = [{"facet": f, "label": l, "by": "rule"} for f, l in (o.get("terms") or {}).items()]
        ident = o.get("path") or o.get("name") or str(i)
        spec = {"kind": o["kind"], "subtype": o.get("subtype"), "name": o.get("name") or Path(o["path"]).stem, "source": {"kind": "generation", "key": f"{g.get('job_id') or hashlib.sha1(ident.encode()).hexdigest()[:12]}:{o.get('role', 'main')}:{i}"},
                "files": [{"role": o.get("role", "main"), "storage": "cas", **({"bytes": o["bytes"]} if "bytes" in o else {"path": o["path"]})}], "attrs": attrs, "terms": terms, "relations": [{**r, "by": "rule"} for r in rels], "generation": gen}
        try:
            if cancel is not None:
                cancel.check()
            put = _put_owned(lib, spec, cancel)
            res["assets"].append({"id": put["id"], "version": put["version"], "created": put["created"], "deduped": put["deduped"]})
            if put["deduped"]:  # the same bytes were made before: this job's origin is still a fact worth keeping
                def add_generation():
                    return lib.add_generation(lib.version_of(put["dedupe_of"]), gen)
                generation_id = cancel.commit_owned(add_generation) if cancel is not None else add_generation()
                res["generation_ids"].append(generation_id)
            elif put["created"]:
                res["generation_ids"].append(lib._reader().execute("SELECT id FROM generation WHERE version_id=? ORDER BY rowid DESC LIMIT 1", (lib.version_of(put["id"], put["version"]),)).fetchone()[0])
            for r in rels:
                res["relations"].append({"src": put["id"], "dst": r["to"], "type": r["type"]})
            res["completeness"] = _completeness(g.get("action"), gen, bool(rels))
        except Exception as exc:
            if cancel is not None:
                cancel.check()
            if "output_relations" not in payload:
                raise
            return {**res, "ok": False, "partial": bool(res["assets"]), "error": str(exc)}
    try:
        from . import curate
        for relation in payload.get("output_relations") or []:
            if cancel is not None:
                cancel.check()
            src, dst = relation["src"], relation["dst"]
            if type(src) is not int or type(dst) is not int or not (0 <= src < len(res["assets"]) and 0 <= dst < len(res["assets"])):
                raise LibraryError("output relation indices must name captured outputs")
            source, target = res["assets"][src]["id"], res["assets"][dst]["id"]
            if cancel is not None:
                cancel.commit_owned(curate.relate, lib, source, relation["type"], target, by="rule", role=relation.get("role", ""))
            else:
                curate.relate(lib, source, relation["type"], target, by="rule", role=relation.get("role", ""))
            res["relations"].append({"src": source, "dst": target, "type": relation["type"]})
    except Exception as exc:
        if cancel is not None:
            cancel.check()
        return {**res, "ok": False, "partial": bool(res["assets"]), "error": str(exc)}
    return res


def _completeness(action, gen, has_parent):
    miss = _missing(action or "", gen, has_parent)
    need = REQUIRED.get(action or "", DEFAULT_REQUIRED)
    return {"required": len(need), "present": len(need) - len(miss), "missing": miss}


def audit(lib: AssetLibrary, spool=None) -> dict:
    db = lib._reader()
    rows = db.execute("SELECT a.id,g.* FROM generation g JOIN version v ON v.id=g.version_id JOIN asset a ON a.id=v.asset_id AND a.current_version=v.n WHERE a.status='active' ORDER BY a.id, g.rowid").fetchall()
    seen, complete, incomplete, by_studio = set(), 0, [], {}
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        d = dict(r)
        has_parent = db.execute("SELECT 1 FROM relation WHERE src=? AND type='derived_from' LIMIT 1", (r["id"],)).fetchone() is not None
        miss = _missing(d.get("action") or "", d, has_parent)
        by_studio[d["studio"]] = by_studio.get(d["studio"], 0) + 1
        if miss:
            incomplete.append({"id": r["id"], "missing": miss})
        else:
            complete += 1
    out = {"assets_checked": db.execute("SELECT count(*) FROM asset WHERE status='active'").fetchone()[0], "generated_assets": len(seen), "complete": complete, "incomplete": incomplete, "by_studio": by_studio}
    if spool is not None:
        p = Path(spool)
        out["spooled"] = len([x for x in p.read_text().splitlines() if x.strip()]) if p.exists() else 0
    return out


def capture(lib: Optional[AssetLibrary], spool, payload: dict, *, cancel=None) -> dict:
    """Return/spool provenance failures for retry; explicit owning-operation cancellation propagates."""
    partial = {}
    try:
        if cancel is not None:
            cancel.check()
        if lib is None:
            raise LibraryError("the library is not open")
        result = record(lib, payload, cancel=cancel)
        if result.get("ok"):
            return result
        partial = result
        raise LibraryError(result.get("error") or "capture incomplete")
    except Exception as e:  # noqa: BLE001 - a provenance failure must never fail the generation
        if cancel is not None:
            cancel.check()
        try:
            def write_spool():
                p = Path(spool)
                p.parent.mkdir(parents=True, exist_ok=True)
                safe = _spoolable(payload, p.parent / "spool_blobs")
                with open(p, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"t": time.time(), "error": _clean(f"{type(e).__name__}: {e}"), "payload": _clean(safe)}, sort_keys=True) + "\n")
            if cancel is not None:
                cancel.commit_owned(write_spool)
            else:
                write_spool()
        except Exception:  # noqa: BLE001
            if cancel is not None:
                cancel.check()
            return {**partial, "ok": False, "spooled": False, "error": str(e)}
        return {**partial, "ok": False, "spooled": True, "error": str(e)}


def _spoolable(payload: dict, blob_dir: Path) -> dict:
    """In-memory output bytes are the ONLY copy of a generation: they go to ``spool_blobs/<sha256>`` and the row points at that file, so a closed library loses nothing."""
    out = json.loads(json.dumps({k: v for k, v in payload.items() if k != "outputs"}, default=str))
    outs = []
    for o in payload.get("outputs") or []:
        o = dict(o)
        if "bytes" in o:
            data = o.pop("bytes")
            blob_dir.mkdir(parents=True, exist_ok=True)
            sha256 = hashlib.sha256(data).hexdigest()
            f = blob_dir / sha256
            f.write_bytes(data)
            o.update(path=str(f), spool_blob=True, spool_sha256=sha256)
        outs.append(o)
    out["outputs"] = outs
    return out


def replay_spool(lib: AssetLibrary, spool) -> dict:
    p = Path(spool)
    if not p.exists():
        return {"replayed": 0, "still_failing": 0}
    keep, done, cleanup = [], 0, set()
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)                                  # a line torn by a crash mid-write is kept, never fatal
            result = record(lib, row["payload"])
            if not result.get("ok"):
                raise LibraryError(result.get("error") or "capture incomplete")
            for o in row["payload"].get("outputs") or []:
                if o.get("spool_blob"):
                    cleanup.add(Path(o["path"]))
            done += 1
        except Exception:  # noqa: BLE001
            keep.append(line)
    p.write_text("".join(x + "\n" for x in keep), encoding="utf-8")
    retained = set()
    for line in keep:
        try:
            for output in json.loads(line)["payload"].get("outputs") or []:
                if output.get("spool_blob"):
                    retained.add(Path(output["path"]).resolve())
        except (TypeError, ValueError, KeyError, AttributeError):
            # A torn/invalid row may name any shared blob. Keep evidence until its references can be recovered.
            cleanup.clear()
            break
    for path in cleanup:
        if path.resolve() not in retained:
            path.unlink(missing_ok=True)  # all queued consumers succeeded and no retained row needs these bytes
    return {"replayed": done, "still_failing": len(keep)}


def backfill(lib: AssetLibrary, runs_jsonl) -> dict:
    """Import the ledger's run history, idempotently keyed by job_id. A run's output is a transient job-file URL, not a file: it is kept as a reference with its token removed."""
    rep = {"rows": 0, "imported": 0, "skipped": 0}
    for line in Path(runs_jsonl).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        rep["rows"] += 1
        if lib._reader().execute("SELECT 1 FROM generation WHERE job_id=?", (r.get("job_id"),)).fetchone():
            rep["skipped"] += 1
            continue
        cost = r.get("cost")
        prompt = r.get("prompt")
        lib.add_generation(None, {"studio": r.get("provider") or "lampway", "provider": r.get("provider"), "model": r.get("model"), "action": r.get("service"), "prompt_text": prompt,
                                  "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest() if prompt else None, "template_id": r.get("template"), "job_id": r["job_id"], "finished_at": r.get("t"),
                                  "cost_usd": cost if isinstance(cost, (int, float)) else None, "cost_basis": "measured" if isinstance(cost, (int, float)) else "none", "tool": "ledger/runs.jsonl",
                                  "params_json": json.dumps(_clean({"ok": r.get("ok"), "error": r.get("error"), "output_ref": r.get("output"), "variables": r.get("variables") or {}, "variant_of": r.get("variant_of"),
                                                                    "backfill": True}), sort_keys=True)})
        rep["imported"] += 1
    return rep
