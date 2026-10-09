"""Asset Vault ingest (specs/asset_library/asset_ingest.md): classify by magic bytes, hash, extract tier-1 stats in pure Python, propose terms from a
committed rules table, and import what a PREVIEW listed once the user has clicked.

Nothing is enrolled automatically. ``scan`` reads and reports and writes only ``<library>/scans/<id>.json``; ``import_`` imports exactly the files
that scan listed and refuses anyone but the user; the user's own files are only ever opened ``rb``. A source folder is registered when the user imports from it
or adds it as a watch root, never before."""
from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import os
import re
import struct
import subprocess
from pathlib import Path
from typing import Optional

from .schema import CANONICAL_KINDS
from .store import AssetLibrary, LibraryError

DEFAULT_IGNORE = ["**/__pycache__/**", "*.pyc", "*.py", "*.pyd", "*.so", "*.dll", "*.blend1", "*.tmp"]
RULES_FILE = Path(__file__).with_name("rules") / "terms.json"
USER = ("captain", "user")
RECEIPT_NAMES = {"checks.json": "gate", "uv_score.json": "qa", "attempts.json": "audit", "recipe.json": "audit", "verification.json": "audit"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
BLEND_SNIFF_INPUT_LIMIT = 256 * 1024
BLEND_SNIFF_WINDOW_LIMIT = 64 * 1024**2


def _blend_header(head: bytes) -> bool:
    # Pinned BLO_core_blend_header.hh: legacy12-byte and modern17-byte formats.
    legacy = (len(head) >= 12 and head[:7] == b"BLENDER" and head[7:8] in (b"_", b"-")
              and head[8:9] in (b"v", b"V") and all(48 <= byte <= 57 for byte in head[9:12]))
    modern = (len(head) >= 17 and head[:13] == b"BLENDER17-01v"
              and all(48 <= byte <= 57 for byte in head[13:17]))
    return legacy or modern


def _compressed_blend_header(head: bytes) -> bytes:
    """Sniff at most17 output bytes; never unpack a source or trust its extension.

    The caller caps compressed input. Reject excessive advertised windows before
    constructing the bounded streaming decoder. This recognizes a header, not
    full-file integrity; native loading remains responsible for the asset body.
    """
    import zstandard

    try:
        if zstandard.get_frame_parameters(head).window_size > BLEND_SNIFF_WINDOW_LIMIT:
            return b""
        decoder = zstandard.ZstdDecompressor(max_window_size=BLEND_SNIFF_WINDOW_LIMIT)
        with decoder.stream_reader(io.BytesIO(head), read_size=1024, read_across_frames=False) as reader:
            header = reader.read(17)
        return header[:12 if header[7:8] in (b"_", b"-") else 17] if _blend_header(header) else b""
    except zstandard.ZstdError:
        return b""


# ---- classify (magic bytes first; an unknown file is reported, never guessed) -----------------------------------------------------
def classify(head: bytes, name: str) -> Optional[dict]:
    ext = os.path.splitext(name)[1].lower()
    if name.lower().endswith(".canon.json"):                                   # a canonical document travels with its asset, never on its own
        return {"kind": "skip", "container": "json"}
    if head.startswith(b"glTF"):
        return {"kind": "mesh", "subtype": "model", "container": "glb"}
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return {"kind": "image", "container": "png"}
    if head.startswith(b"\xff\xd8\xff"):
        return {"kind": "image", "container": "jpeg"}
    if head[:4] == b"GIF8" or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
        return {"kind": "image", "container": "gif" if head[:3] == b"GIF" else "webp"}
    if head[4:8] == b"ftyp":
        return {"kind": "video", "container": "mp4"}
    if head.startswith(b"\x1aE\xdf\xa3"):
        return {"kind": "video", "container": "webm"}
    if head.startswith(b"Kaydara FBX Binary"):
        return {"kind": "mesh", "subtype": "model", "container": "fbx", "tier2": True}
    if _blend_header(head):
        return {"kind": "mesh", "subtype": "model", "container": "blend", "tier2": True}
    if head.startswith(b"PK\x03\x04"):
        return {"kind": "archive", "container": "zip"}
    if head.startswith(b"#?RADIANCE") or head.startswith(b"v/1\x01"):
        return {"kind": "hdri", "container": "hdr" if head[:2] == b"#?" else "exr"}
    if ext == ".obj" and head.lstrip()[:2] in (b"# ", b"v ", b"o ", b"g ", b"mt"):
        return {"kind": "mesh", "subtype": "model", "container": "obj", "tier2": True}
    if ext == ".json" and head.lstrip()[:1] in (b"{", b"["):
        if name.lower() in RECEIPT_NAMES:
            return {"kind": "receipt", "subtype": RECEIPT_NAMES[name.lower()], "container": "json"}
        return {"kind": "skip", "reason": "json is not a known receipt (checks, uv_score, attempts, recipe, verification)"}
    return None


# ---- tier-1 extractors ---------------------------------------------------------------------------------------------------------
def _glb_json(fh) -> dict:
    head = fh.read(20)
    if len(head) < 20 or head[:4] != b"glTF":
        raise ValueError("not a GLB")
    clen, ctype = struct.unpack("<II", head[12:20])
    if ctype != 0x4E4F534A or clen > 256 * 1024 ** 2:
        raise ValueError("GLB JSON chunk missing or implausible")
    return json.loads(fh.read(clen))


def extract_glb(src) -> dict:
    """verts / tris / bbox / materials / UV sets / skin from the JSON chunk alone (no BIN read, so a 1.9 GB GLB costs a few KB).
    Local-space: node transforms are not applied. A primitive with no position data is counted as degenerate, not trusted."""
    doc = _glb_json(io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src)
    acc = doc.get("accessors", [])
    seen_pos, tris, degenerate, uv_sets = set(), 0, 0, 0
    mins, maxs = None, None
    for mesh in doc.get("meshes", []):
        for prim in mesh.get("primitives", []):
            pos = prim.get("attributes", {}).get("POSITION")
            if pos is None or pos >= len(acc) or not acc[pos].get("count"):
                degenerate += 1
                continue
            seen_pos.add(pos)
            uv_sets = max(uv_sets, sum(1 for k in prim["attributes"] if k.startswith("TEXCOORD_")))
            if prim.get("mode", 4) == 4:
                n = acc[prim["indices"]]["count"] if "indices" in prim and prim["indices"] < len(acc) else acc[pos]["count"]
                tris += n // 3
            a = acc[pos]
            if "min" in a and "max" in a:
                mins = a["min"] if mins is None else [min(x, y) for x, y in zip(mins, a["min"])]
                maxs = a["max"] if maxs is None else [max(x, y) for x, y in zip(maxs, a["max"])]
    stats = {"verts": sum(acc[i]["count"] for i in seen_pos), "faces": tris, "tris": tris, "quads": 0, "topology": "Tri",
             "materials": len(doc.get("materials", [])), "uv_sets": uv_sets, "skinned": 1 if doc.get("skins") else 0,
             "bones": len(doc["skins"][0].get("joints", [])) if doc.get("skins") else 0}
    if mins is not None:
        stats.update(bbox_min_json=[float(x) for x in mins], bbox_max_json=[float(x) for x in maxs], dim_x=float(maxs[0] - mins[0]), dim_y=float(maxs[1] - mins[1]), dim_z=float(maxs[2] - mins[2]))
    attrs = {"degenerate_primitives": degenerate, "images": len(doc.get("images", [])), "animations": len(doc.get("animations", [])), "extract": "tier1:glb-json"}
    return {"stats": stats, "attrs": attrs}


def _dhash(img) -> str:
    g = img.convert("L").resize((9, 8))
    px = list(g.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if px[row * 9 + col] > px[row * 9 + col + 1] else 0)
    return f"{bits:016x}"


def extract_image(path) -> dict:
    from PIL import Image, ImageStat
    with Image.open(path) as im:
        im.load()
        channels = {"L": 1, "LA": 2, "RGB": 3, "RGBA": 4, "P": 1, "1": 1, "CMYK": 4}.get(im.mode, len(im.getbands()))
        mean = [round(v, 2) for v in ImageStat.Stat(im.convert("RGB")).mean]
        return {"stats": {"width": im.width, "height": im.height, "channels": channels, "bit_depth": 16 if im.mode.startswith("I;16") else 8,
                          "has_alpha": 1 if "A" in im.getbands() or "transparency" in im.info else 0, "dhash": _dhash(im), "mean_rgb_json": mean},
                "attrs": {"extract": "tier1:pillow", "format": im.format}}


def extract_video(path) -> dict:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
        doc = json.loads(out.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {"stats": {}, "attrs": {"extract": "pending: ffprobe not available or failed"}}
    v = next((s for s in doc.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in doc.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not v:
        return {"stats": {}, "attrs": {"extract": "pending: ffprobe found no video stream"}}

    def fps(s):
        try:
            n, d = s.split("/")
            return float(n) / float(d) if float(d) else None
        except (ValueError, AttributeError):
            return None
    fmt = doc.get("format", {})
    stats = {"container": fmt.get("format_name"), "codec": v.get("codec_name"), "profile": v.get("profile"), "pix_fmt": v.get("pix_fmt"), "width": v.get("width"), "height": v.get("height"),
             "container_fps": fps(v.get("r_frame_rate")), "avg_fps": fps(v.get("avg_frame_rate")), "frame_count": int(v["nb_frames"]) if str(v.get("nb_frames", "")).isdigit() else None,
             "duration_s": float(fmt["duration"]) if fmt.get("duration") else None, "bitrate": int(fmt["bit_rate"]) if str(fmt.get("bit_rate", "")).isdigit() else None,
             "has_audio": 1 if a else 0, "audio_codec": a.get("codec_name") if a else None, "analyzed_with": "ffprobe"}
    return {"stats": stats, "attrs": {"extract": "tier1:ffprobe"}}


# ---- rules -----------------------------------------------------------------------------------------------------------------------
def load_rules() -> list:
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))


def rule_terms(path: str, kind: str, rules=None) -> list:
    path = str(path).replace("\\", "/")
    name = path.rsplit("/", 1)[-1]
    out, seen = [], set()
    for r in rules if rules is not None else load_rules():
        if r.get("kinds") and kind not in r["kinds"]:
            continue
        m = re.search(r["re"], name if r["on"] == "name" else path)
        if not m:
            continue
        facet, label = m.expand(r["term"]).lower().split(":", 1) if "\\" in r["term"] else r["term"].split(":", 1)
        if (facet, label) not in seen:
            seen.add((facet, label))
            out.append({"facet": facet, "label": label, "by": "rule", "confidence": 1.0, "rule": r["re"]})
    return out


def stats_terms(kind: str, stats: dict) -> list:
    out = []
    if kind == "mesh":
        if stats.get("faces") is not None and stats["faces"] <= 5000:
            out.append(("lod", "low"))
        if stats.get("skinned"):
            out.append(("state", "rigged"))
        if stats.get("uv_sets") == 0:
            out.append(("state", "needs_uv"))
    return [{"facet": f, "label": l, "by": "rule", "confidence": 1.0, "rule": "stats"} for f, l in out]


# ---- ingest ----------------------------------------------------------------------------------------------------------------------
def _dir_ignored(rel: str, patterns) -> bool:
    """A pattern ending in ``/**`` names a directory to leave unread (``**/__pycache__/**``): its contents are never listed."""
    name = rel.rsplit("/", 1)[-1]
    return any(p.endswith("/**") and (fnmatch.fnmatch(rel, p[:-3]) or fnmatch.fnmatch(name, p[:-3].rsplit("/", 1)[-1])) for p in patterns)


def _ignored(rel: str, patterns) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return any(not p.endswith("/**") and (fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel, p)) for p in patterns)


def _walk(root: Path, ignore, recursive=True):
    seen_dirs, stack = set(), [root]
    while stack:
        d = stack.pop()
        real = os.path.realpath(d)
        if real in seen_dirs:
            continue                      # symlink loop guard: each real directory is walked once
        seen_dirs.add(real)
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            continue
        for e in entries:
            rel = os.path.relpath(e.path, root).replace(os.sep, "/")
            if e.is_dir(follow_symlinks=True):
                if recursive and not _dir_ignored(rel, ignore):
                    stack.append(Path(e.path))
            elif e.is_file(follow_symlinks=True):
                yield Path(e.path), rel


class Ingest:
    def __init__(self, lib: AssetLibrary, rules=None):
        self.lib = lib
        self.scans = lib.root / "scans"
        self._rules = rules

    @staticmethod
    def _need_user(by, what):
        if by not in USER:
            raise LibraryError(f"{what} needs the user's click in the Vault panel: an agent can preview (scan), not enrol or import")

    def _head(self, p: Path) -> bytes:
        with open(p, "rb") as fh:
            head = fh.read(32)
            if head.startswith(ZSTD_MAGIC):
                prefix = head + fh.read(BLEND_SNIFF_INPUT_LIMIT - len(head))
                return _compressed_blend_header(prefix) or head
            return head

    def scan(self, paths, source_label=None, ignore=None, recursive=True, max_files: int = 200000) -> dict:
        ignore = DEFAULT_IGNORE if ignore is None else ignore
        files, report = [], {"seen": 0, "new_assets": 0, "deduped": 0, "skipped": [], "unknown": [], "failed": [], "archives": [], "by_kind": {}, "bytes": 0}
        shas = set()
        for raw in paths:
            root = Path(raw)
            if not root.is_dir():
                raise LibraryError(f"scan root is not a directory: {root}")
            for p, rel in _walk(root, ignore, recursive):
                if _ignored(rel, ignore):
                    report["skipped"].append({"path": str(p), "reason": "ignore list"})
                    continue
                if report["seen"] >= max_files:
                    report["skipped"].append({"path": str(p), "reason": f"max_files {max_files} reached"})
                    continue
                report["seen"] += 1
                size = p.stat().st_size
                if size == 0:
                    report["failed"].append({"path": str(p), "why": "zero-byte file"})
                    continue
                head = self._head(p)
                c = classify(head, p.name)
                if c is None:
                    report["unknown"].append({"path": str(p), "magic": head[:8].hex()})
                    continue
                if c["kind"] == "skip":
                    report["skipped"].append({"path": str(p), "reason": c["reason"]})
                    continue
                if c["kind"] == "archive":
                    report["archives"].append(str(p))
                    continue
                sha, st = self.lib._hash_file(p)
                dup = sha in shas or self.lib.known_sha(sha)
                shas.add(sha)
                report["deduped" if dup else "new_assets"] += 1
                report["by_kind"][c["kind"]] = report["by_kind"].get(c["kind"], 0) + 1
                report["bytes"] += size
                files.append({"path": str(p), "root": str(root), "rel": rel, "kind": c["kind"], "subtype": c.get("subtype"), "container": c["container"], "tier2": bool(c.get("tier2")),
                              "size": size, "mtime_ns": st.st_mtime_ns, "sha256": sha})
        scan_id = "scan-" + hashlib.sha1(json.dumps([self.lib._now(), [str(x) for x in paths]]).encode()).hexdigest()[:10]
        self.scans.mkdir(parents=True, exist_ok=True)
        (self.scans / f"{scan_id}.json").write_text(json.dumps({"scan_id": scan_id, "paths": [str(x) for x in paths], "label": source_label, "report": report, "files": files}, indent=1))
        return {"scan_id": scan_id, "report": report}

    def _spec(self, rec: dict, batch: str, label=None) -> dict:
        p = Path(rec["path"])
        kind = rec["kind"]
        ex = {"stats": {}, "attrs": {}}
        try:
            if rec["container"] == "glb":
                ex = extract_glb(open(p, "rb"))
            elif kind in ("image", "hdri") and rec["container"] in ("png", "jpeg", "webp", "gif"):
                ex = extract_image(p)
            elif kind == "video":
                ex = extract_video(p)
            elif kind == "receipt":
                doc = json.loads(p.read_text(encoding="utf-8")) if rec["size"] <= 5 * 1024 ** 2 else None
                ex = {"stats": {}, "attrs": {"extract": "tier1:json", "keys": sorted(doc)[:40] if isinstance(doc, dict) else None}}
            elif rec.get("tier2"):
                ex = {"stats": {}, "attrs": {"extract": f"pending: tier-2 ({rec['container']} needs the headless Blender worker)"}}
        except Exception as e:  # noqa: BLE001 - a failed extractor never loses the asset row
            ex = {"stats": {}, "attrs": {"extract": f"failed: {type(e).__name__}: {str(e)[:120]}"}}
        terms = rule_terms(f"{Path(rec['root']).name}/{rec['rel']}", kind, self._rules) + stats_terms(kind, ex["stats"])
        extra = {}
        side = Path(rec["path"] + ".canon.json")                                 # the normalizer's document: the version is canonical, its
        if kind in CANONICAL_KINDS and side.exists():                          # stats come from the document (never the raw file's header)
            extra["canonical"] = json.loads(side.read_text(encoding="utf-8"))
        return {**extra, "kind": kind, "subtype": rec.get("subtype"), "name": p.stem, "source": {"kind": "folder", "root": rec["root"], "key": rec["rel"], "label": label},
                "files": [{"role": "main", "path": rec["path"], "storage": "external"}], "stats": ex["stats"], "attrs": {**ex["attrs"], "container": rec["container"]},
                "terms": terms, "batch": batch}

    def import_(self, scan_id: str, by: str) -> dict:
        self._need_user(by, "importing")
        f = self.scans / f"{scan_id}.json"
        if not f.exists():
            raise LibraryError(f"no scan {scan_id}: preview first (scan), then import what the preview listed")
        scan = json.loads(f.read_text())
        rep = {"new_assets": 0, "new_versions": 0, "deduped": 0, "failed": [], "findings": [], "archives": 0, "by_kind": {}}
        roots = sorted({r["root"] for r in scan["files"]})
        for r in roots:
            self.lib.upsert_source("folder", r, scan.get("label"))
        for rec in scan["files"]:
            try:
                res = self.lib.put(self._spec(rec, scan_id, scan.get("label")))
            except LibraryError as e:
                rep["failed"].append({"path": rec["path"], "why": str(e)})
                continue
            if res["deduped"]:
                rep["deduped"] += 1
            elif res["created"] and res["version"] == 1:
                rep["new_assets"] += 1
                rep["by_kind"][rec["kind"]] = rep["by_kind"].get(rec["kind"], 0) + 1
            elif res["created"]:
                rep["new_versions"] += 1
        for a in scan["report"]["archives"]:
            self.lib.record_blob(a, note="archive: recorded, never unpacked")
            rep["archives"] += 1
        rep["findings"] += self._verify_manifests(scan["files"])
        return {"scan_id": scan_id, "batch": scan_id, "report": rep}

    @staticmethod
    def _verify_manifests(files: list) -> list:
        """A verification.json beside the files lists their sha256: a mismatch is a finding (the library hashes the real bytes, so it can say so)."""
        found, by_dir = [], {}
        for r in files:
            by_dir.setdefault(str(Path(r["path"]).parent), {})[Path(r["path"]).name] = r["sha256"]
        for d in by_dir:
            m = Path(d) / "verification.json"
            if not m.is_file():
                continue
            try:
                doc = json.loads(m.read_text(encoding="utf-8"))
            except ValueError:
                continue
            rows = doc.get("files", doc) if isinstance(doc, dict) else doc
            if isinstance(rows, dict):
                rows = [{"file": k, **(v if isinstance(v, dict) else {"sha256": v})} for k, v in rows.items()]
            for row in rows if isinstance(rows, list) else []:
                name, want = row.get("file") or row.get("name"), row.get("sha256")
                have = by_dir[d].get(os.path.basename(name or ""))
                if want and have and want != have:
                    found.append({"what": "verification_hash_mismatch", "file": os.path.basename(name), "expected": want, "actual": have})
        return found

    # -- watch roots (the user's click enrols a root) ------------------------------------------------------------------
    def watch_add(self, root, by: str) -> dict:
        self._need_user(by, "watching a folder")
        return {"source_id": self.lib.upsert_source("folder", str(root), None, watch=True)}

    def watch_remove(self, root, by: str) -> dict:
        self._need_user(by, "un-watching a folder")
        self.lib.upsert_source("folder", str(root), None, watch=False)
        return {"ok": True}

    def watch_list(self) -> list:
        return [s for s in self.lib.sources() if s["config"].get("watch")]

    def ingest_file(self, root: Path, path: Path, batch: str) -> dict:
        head = self._head(path)
        c = classify(head, path.name)
        if c is None or c["kind"] in ("skip", "archive") or path.stat().st_size == 0:
            return {"skipped": True}
        sha, st = self.lib._hash_file(path)
        rec = {"path": str(path), "root": str(root), "rel": os.path.relpath(path, root).replace(os.sep, "/"), "kind": c["kind"], "subtype": c.get("subtype"),
               "container": c["container"], "tier2": bool(c.get("tier2")), "size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": sha}
        return self.lib.put(self._spec(rec, batch))


class Watcher:
    """A polling scanner (no inotify dependency). A file is ingested once its size has been unchanged for two consecutive polls, so a half-written download is not read."""

    def __init__(self, ing: Ingest, root, ignore=None):
        self.ing, self.root = ing, Path(root)
        self.ignore = DEFAULT_IGNORE if ignore is None else ignore
        if str(self.root) not in {w["root"] for w in ing.watch_list()}:
            raise LibraryError(f"{root} is not a watch root: the user adds it first")
        self._state: dict = {}
        self._known: set = set()

    def poll(self) -> list:
        done, present = [], set()
        for p, rel in _walk(self.root, self.ignore):
            if _ignored(rel, self.ignore):
                continue
            present.add(str(p))
            size = p.stat().st_size
            last, stable = self._state.get(str(p), (None, 0))
            stable = stable + 1 if last == size else 0
            self._state[str(p)] = (size, stable)
            if stable >= 2 and str(p) not in self._known:
                res = self.ing.ingest_file(self.root, p, "watch")
                self._known.add(str(p))
                if not res.get("skipped"):
                    done.append(res)
        for gone in sorted(self._known - present):
            self.ing.lib.mark_missing(gone)
            self._known.discard(gone)
            self._state.pop(gone, None)
        return done
