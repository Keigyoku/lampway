"""The user's own folders into the Vault: the clickable initial import (specs/asset_library/asset_seed_captain.md, the folder sets: downloads, pictures, videos,
the Lampway projects root, and any root the user adds).

Nothing is read until the user clicks. ``card`` only stats each root (exists or not); ``scan`` (the user's click) previews through ``asset_ingest``; ``import_`` (the
user's click again) puts exactly what the preview listed, REFERENCED (opened ``rb`` and hashed, never copied, moved or written), as one batch that rolls back by
soft delete. After the import: ledger rows in the projects root become generation rows on the assets whose sha256 they name, clips get ``asset_video``'s
analysis, and every scanned file is re-hashed to prove the sources are untouched. The defaults are generic home folders; a studio or project folder is a root
the user adds."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Optional

from . import ingest as I
from .store import AssetLibrary, LibraryError

GENERIC = (("downloads", "Downloads", "Downloads"), ("pictures", "Pictures", "Pictures"), ("videos", "Videos", "Videos"))


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


class SeedSets:
    def __init__(self, home=None, project_root=None):
        self.home = Path(home) if home else Path.home()
        self.project_root = Path(project_root) if project_root else Path(os.environ.get("LAMPWAY_PROJECT_ROOT") or self.home / ".local/share/lampway/projects")

    # -- the sets -------------------------------------------------------------------------------------------------------------------
    def _added_file(self, lib: AssetLibrary) -> Path:
        return lib.root / "seed_sets.json"

    def sets(self, lib: AssetLibrary) -> list:
        out = [{"id": sid, "label": label, "root": str(self.home / sub)} for sid, label, sub in GENERIC]
        out.append({"id": "lampway_projects", "label": "Lampway projects", "root": str(self.project_root)})
        f = self._added_file(lib)
        return out + (json.loads(f.read_text()) if f.exists() else [])

    def add_root(self, lib: AssetLibrary, root, label: str, by: str) -> dict:
        I.Ingest._need_user(by, "adding a folder to the initial import")
        sid = "folder:" + (re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "root")
        added = [s for s in self.sets(lib)[len(GENERIC) + 1:] if s["id"] != sid] + [{"id": sid, "label": label, "root": str(root)}]
        self._added_file(lib).write_text(json.dumps(added, indent=1))
        return {"ok": True, "id": sid}

    def card(self, lib: AssetLibrary) -> dict:
        """The initial import card: each root and whether it exists. Nothing inside a folder is read."""
        return {"ok": True, "action": "scan", "note": "Nothing is read until you click Scan; then you see what would be imported before anything is.",
                "sets": [{**s, "exists": Path(s["root"]).is_dir()} for s in self.sets(lib)]}

    # -- scan / import ----------------------------------------------------------------------------------------------------------------
    def scan(self, lib: AssetLibrary, set_ids, by: str) -> dict:
        I.Ingest._need_user(by, "scanning your folders")
        known = {s["id"]: s for s in self.sets(lib)}
        roots, skipped = {}, []
        for sid in set_ids:
            if sid not in known:
                raise LibraryError(f"unknown set {sid!r}; sets: {sorted(known)}")
            root = Path(known[sid]["root"])
            if root.is_dir():
                roots[str(root)] = sid
            else:
                skipped.append(f"set '{sid}' not found at {root}: skipped")
        if roots:
            res = I.Ingest(lib).scan(list(roots), source_label="initial import")
        else:
            res = {"scan_id": None, "report": {"seen": 0, "by_kind": {}}}
        if res["scan_id"]:
            (lib.root / "scans" / f"{res['scan_id']}.sets.json").write_text(json.dumps(roots))
        res["report"]["skipped_sets"] = skipped
        return res

    def import_(self, lib: AssetLibrary, scan_id: str, by: str, analyse_videos: bool = True) -> dict:
        I.Ingest._need_user(by, "importing your folders")
        ing = I.Ingest(lib)
        f = lib.root / "scans" / f"{scan_id}.json"
        if not scan_id or not f.exists():
            raise LibraryError(f"no scan {scan_id}: scan first, then import what the preview listed")
        scan = json.loads(f.read_text())
        set_of = json.loads((lib.root / "scans" / f"{scan_id}.sets.json").read_text())
        rep = {"ok": True, "scan_id": scan_id, "batch": scan_id, "sets": {}, "findings": [], "generation_rows": 0, "videos_analysed": 0, "video_failures": [], "archives": 0}
        for root in sorted(set(set_of)):
            lib.upsert_source("folder", root, "initial import")
        videos = []
        for rec in scan["files"]:
            s = rep["sets"].setdefault(set_of[rec["root"]], {"files": 0, "bytes": 0, "assets_created": 0, "deduped": 0, "new_versions": 0, "failed": []})
            s["files"] += 1
            s["bytes"] += rec["size"]
            try:
                # LEGACY(normalize): the user's meshes, clips and textures enter through asset_ingest's spec, not canon_io (not yet on lp/wave5); raw sha256 recorded, no frame or scale claimed
                res = lib.put(ing._spec(rec, scan_id, "initial import"))
            except LibraryError as e:
                s["failed"].append({"path": rec["path"], "why": str(e)})
                continue
            if res["deduped"]:
                s["deduped"] += 1
            elif res["created"] and res["version"] == 1:
                s["assets_created"] += 1
            elif res["created"]:
                s["new_versions"] += 1                             # (an unchanged re-import counts nowhere: nothing happened)
            if rec["kind"] == "video":
                videos.append(res["id"])
        for a in scan["report"].get("archives", []):
            lib.record_blob(a, note="archive: recorded, never unpacked")
            rep["archives"] += 1
        rep["findings"] += ing._verify_manifests(scan["files"])
        if "lampway_projects" in set_of.values():
            rep["generation_rows"] = self._ledger(lib)
        if analyse_videos:
            self._videos(lib, sorted(set(videos)), rep)
        rep["untouched_sources"] = self._untouched(scan["files"])
        return rep

    # -- after the import --------------------------------------------------------------------------------------------------------------
    def _ledger(self, lib: AssetLibrary) -> int:
        """Each ledger row's output hashes name assets: the row becomes that asset's generation row once (``ledger_ref = ledger:<row id>``)."""
        path = self.project_root / "ledger" / "runs.jsonl"
        if not path.is_file():
            return 0
        n = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue                                           # a torn line in the user's ledger is skipped, never repaired here
            ref = f"ledger:{row.get('id') or row.get('job_key')}"
            cost = row.get("cost") or {}
            price = row.get("price") or {}
            for sha in row.get("output_hashes") or []:
                aid = lib.resolve_asset(sha)
                if not aid:
                    continue
                vid = lib.version_of(aid)
                if lib._reader().execute("SELECT 1 FROM generation WHERE version_id=? AND ledger_ref=?", (vid, ref)).fetchone():
                    continue
                usd = cost.get("developer_api_usd", price.get("usd") if isinstance(price, dict) else None)
                credits = cost.get("generation_credits", price.get("credits") if isinstance(price, dict) else None)
                lib.add_generation(vid, {"studio": row.get("studio") or row.get("provider"), "provider": row.get("provider") or row.get("studio"),
                                         "model": row.get("model_version") or row.get("model"), "action": row.get("stage") or row.get("kind"), "cost_usd": usd,
                                         "cost_credits": credits, "cost_basis": "measured" if usd is not None or credits is not None else "none",
                                         "job_id": row.get("job_key") or row.get("id"), "finished_at": row.get("t"), "ledger_ref": ref, "tool": "ledger",
                                         "params_json": json.dumps({"piece": row.get("piece"), "reason": row.get("reason"), "price_source": cost.get("price_source")}, sort_keys=True)})
                n += 1
        return n

    @staticmethod
    def _videos(lib: AssetLibrary, ids: list, rep: dict):
        import shutil
        if not ids or not shutil.which("ffmpeg"):
            return
        from . import video as V
        for aid in ids:
            if str((lib.get(aid)["stats"] or {}).get("analyzed_with") or "").startswith("lampway.video@"):
                continue                                           # (ingest's probe writes analyzed_with "ffprobe": that is not the motion analysis)
            try:
                V.analyze(lib, aid)
                rep["videos_analysed"] += 1
            except LibraryError as e:
                rep["video_failures"].append({"id": aid, "why": str(e)})

    @staticmethod
    def _untouched(files: list) -> dict:
        changed = []
        for r in files:
            p = Path(r["path"])
            st = p.stat() if p.exists() else None
            if st is None or st.st_size != r["size"] or st.st_mtime_ns != r["mtime_ns"] or _sha(p) != r["sha256"]:
                changed.append(r["path"])
        return {"checked": len(files), "changed": len(changed), **({"changed_paths": changed} if changed else {})}

    # -- the tool surface ---------------------------------------------------------------------------------------------------------------
    def handle(self, lib: AssetLibrary, req: dict, by: str = "agent") -> dict:
        """``asset_seed_captain``: card (anyone) | scan | import | add_root (the user's clicks) -> ``{ok, ...}`` or ``{ok: false, error, help}``."""
        a = req.get("action") or "card"
        try:
            if a == "card":
                return self.card(lib)
            if a == "scan":
                return {"ok": True, **self.scan(lib, req.get("sets") or [], by)}
            if a == "import":
                return self.import_(lib, req.get("scan_id"), by)
            if a == "add_root":
                return self.add_root(lib, req.get("root"), req.get("label") or "", by)
            raise LibraryError(f"unknown action {a!r}: card|scan|import|add_root")
        except LibraryError as e:
            return {"ok": False, "error": str(e), "help": ["the card shows each folder and whether it exists; the user clicks Scan to preview and Import to bring it in",
                                                           "nothing is copied: files are referenced, and the import rolls back as one batch"]}
