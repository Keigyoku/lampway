"""Importers for the user's existing shelf (specs/asset_library/asset_seed_captain.md): the Tripo ``seeds.sqlite`` and the meshqa ``decisions.jsonl``.

Read-only on every source (the seeds DB is opened ``mode=ro`` and, if a writer holds it, copied through the sqlite backup API). Nothing is dropped: a row that cannot be
resolved goes to ``unresolved`` with its reason. A shelf value that disagrees with the file (sha256) is a ``finding``, not silence, and the row is kept."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

from . import ingest as I
from .store import AssetLibrary, LibraryError

ACTIONS = {"generation": "image_to_model", "local_edit": "local_edit", "multiview_to_model": "multiview_to_model"}
TOPOLOGY = {"triangle": "Tri", "tri": "Tri", "quad": "Quad"}


def _open_ro(path):
    uri = f"file:{path}?mode=ro"
    try:
        db = sqlite3.connect(uri, uri=True)
        db.execute("select count(*) from sqlite_master")
        return db
    except sqlite3.OperationalError:                    # locked by a writer: copy-read through the backup API
        mem = sqlite3.connect(":memory:")
        sqlite3.connect(uri, uri=True).backup(mem)
        return mem


def _run_json(seed_file: Path, stop: Path):
    d = seed_file.parent
    for _ in range(4):
        f = d / "run.json"
        if f.is_file():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                return None
        if d == stop or d.parent == d:
            break
        d = d.parent
    return None


def import_shelf_seeds(lib: AssetLibrary, seeds_db, by: str, batch: str = None) -> dict:
    I.Ingest._need_user(by, "importing the shelf seeds")
    seeds_db = Path(seeds_db)
    db = _open_ro(seeds_db)
    db.row_factory = sqlite3.Row
    rows = [dict(r) for r in db.execute("SELECT * FROM seeds ORDER BY added_at, id")]
    db.close()
    batch = batch or "shelf-seeds-" + str(int(lib._now()))
    rep = {"batch": batch, "assets": 0, "meshes": 0, "relations": {"derived_from": 0, "generated_from": 0, "receipt_derived_from": 0}, "verdicts": 0, "generation_rows": 0, "findings": [], "unresolved": []}
    ids: dict = {}
    lib.upsert_source("tripo_seeds", str(seeds_db), "Tripo seeds")
    with lib.bulk():
        for r in rows:
            f = Path(r["file"] or "")
            if not f.is_file():
                rep["unresolved"].append({"ref": r["id"], "why": f"file not found: {r['file']}"})
                continue
            run = _run_json(f, seeds_db.parent)
            cost = None
            if run and "credits_before" in run and "credits_after" in run:
                if run["credits_after"] > run["credits_before"]:
                    rep["findings"].append({"what": "credits_increased", "ref": r["id"], "detail": f"credits_after {run['credits_after']} > credits_before {run['credits_before']}: no cost recorded"})
                else:
                    cost = run["credits_before"] - run["credits_after"]
            piece = re.sub(r"\d+$", "", (r["piece"] or "").lower())
            topo = TOPOLOGY.get((r["topology"] or "").lower(), "Mixed" if r["topology"] else None)
            terms = ([{"facet": "piece_type", "label": piece}] if piece else []) + [{"facet": "studio", "label": "tripo"}] + ([{"facet": "pipeline_stage", "label": "seed"}] if r["kind"] != "local_edit" else [])
            gates = []
            if r["score_rms"] is not None:
                gates.append({"gate": "proportion_rms", "value": r["score_rms"], "threshold": None, "passed": True,
                              "detail": {"measurement_only": True, "note": "no threshold exists for this score (the user owns it): recorded, not judged", "score_json": r["score_json"]}})
            spec = {"kind": "mesh", "subtype": "model", "name": f.stem, "source": {"kind": "tripo_seeds", "root": str(seeds_db), "key": r["id"], "label": "Tripo seeds"},
                    "files": [{"role": "main", "path": str(f), "storage": "external"}], "stats": {"topology": topo, "faces": r["faces"]} if topo or r["faces"] else {},
                    "attrs": {"kind": r["kind"], "piece_name": r["piece"], "studio_project": r["project_id"], "source_url": r["url"], "harvest_source": r["source"],
                              "shelf_sha256": r["sha256"], "extract": "pending: tier-2 (fbx needs the headless Blender worker)"},
                    "terms": terms, "gates": gates, "batch": batch,
                    "generation": {"studio": "tripo", "provider": "tripo", "action": ACTIONS.get(r["kind"], r["kind"]), "finished_at": r["created_at"], "job_id": r["project_id"], "cost_credits": cost,
                                   "cost_basis": "measured" if cost is not None else None, "tool": (run or {}).get("tool"), "ledger_ref": r["source"]}}
            res = lib.put(spec)
            ids[r["id"]] = res["id"]
            if res["created"]:
                rep["assets"] += 1
                rep["meshes"] += 1
                rep["generation_rows"] += 1
            have = lib.get(res["id"])["files"][0]["sha256"]
            if r["sha256"] and r["sha256"] != have:
                rep["findings"].append({"what": "sha256_mismatch", "ref": r["id"], "expected": r["sha256"], "actual": have})
            plates = json.loads(r["plates_json"]) if r["plates_json"] else {}
            for view, pl in plates.items():
                pf = Path(pl.get("file", ""))
                if not pf.is_file():
                    rep["unresolved"].append({"ref": r["id"], "why": f"plate not found: {pl.get('file')}"})
                    continue
                pres = lib.put({"kind": "image", "subtype": "plate", "name": f"{r['piece']} {view} plate", "source": {"kind": "tripo_seeds", "root": str(seeds_db), "key": f"plate:{pl.get('sha256') or pf.name}"},
                                "files": [{"role": "main", "path": str(pf), "storage": "external"}], "terms": [{"facet": "view", "label": view.lower()}] + ([{"facet": "piece_type", "label": piece}] if piece else []), "batch": batch})
                if pres["created"]:
                    rep["assets"] += 1
                if lib.relate(res["id"], "generated_from", pres["id"], by="rule", role=view)["created"]:
                    rep["relations"]["generated_from"] += 1
            if r["audit_path"] and Path(r["audit_path"]).is_file():
                ares = lib.put({"kind": "receipt", "subtype": "audit", "name": Path(r["audit_path"]).stem, "source": {"kind": "tripo_seeds", "root": str(seeds_db), "key": f"audit:{r['id']}"},
                                "files": [{"role": "main", "path": r["audit_path"], "storage": "external"}], "batch": batch})
                if ares["created"]:
                    rep["assets"] += 1
                if lib.relate(ares["id"], "derived_from", res["id"], by="rule")["created"]:
                    rep["relations"]["receipt_derived_from"] += 1
        for r in rows:                                  # second pass: parents resolve only once every asset exists
            if r["id"] not in ids:
                continue
            if r["parent_id"]:
                parent = ids.get(r["parent_id"])
                if not parent or parent == ids[r["id"]]:
                    rep["unresolved"].append({"ref": r["id"], "why": f"parent {r['parent_id']} is not an imported seed"})
                else:
                    try:
                        if lib.relate(ids[r["id"]], "derived_from", parent, by="rule")["created"]:
                            rep["relations"]["derived_from"] += 1
                    except LibraryError as e:
                        rep["unresolved"].append({"ref": r["id"], "why": str(e)})
            if r["verdict"]:
                d = lib.decide("verdict", r["verdict"], "captain", asset_id=ids[r["id"]], how="shelf_seeds", words=r["verdict_note"], idempotent=True,
                               session=f"shelf_seeds:{r['id']}", descriptor={"seed": r["id"], "piece": r["piece"]})
                if not d["existing"]:
                    rep["verdicts"] += 1
                    if r["verdict"] == "chosen":
                        lib.rate(ids[r["id"]], "captain", flag="pick", note=r["verdict_note"])
    return rep


def import_meshqa(lib: AssetLibrary, jsonl, by: str) -> dict:
    I.Ingest._need_user(by, "importing the meshqa decisions")
    rep = {"rows": 0, "imported": 0, "existing": 0, "matched": 0, "unresolved": []}
    with lib.bulk():
        for line in Path(jsonl).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            rep["rows"] += 1
            m = re.match(r"^([a-z0-9]+_[0-9a-f]{8})", r.get("session") or "")
            hit = lib.find_by_name(m.group(1)) if m else []
            asset = hit[-1] if hit else None
            if asset:
                rep["matched"] += 1
            else:
                rep["unresolved"].append({"ref": r.get("session"), "why": "no asset matches the session's piece name"})
            d = lib.decide(r["question"], r["answer"], r.get("decider", "captain"), asset_id=asset, options=r.get("options"), how=r.get("how"), session=r.get("session"),
                           descriptor=r.get("descriptor"), words=r.get("captain_words"), idempotent=True)
            rep["existing" if d["existing"] else "imported"] += 1
    return rep
