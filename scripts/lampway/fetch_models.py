#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bundle the Asset Vault's open-weights embedding models into a build (called by build_linux.sh).

    fetch_models.py --dest <build>/bin/5.2/datafiles/lampway/models      fetch what is missing, verify every sha256
    fetch_models.py --plan [--dest D]                                      list the pinned files and the total, touch nothing

The pins (repository commit URLs and sha256) are server/lampway_server/library/models.json, the same file the server reads. A file already present with the right
sha256 is not fetched again; a mismatch deletes the partial file and exits 5. Only https URLs (and loopback, for tests) are fetched. Standard library only: the build
box's python3 has nothing else. Weights never go into git: the destination is inside the build tree.
Exit codes: 0 ok, 2 bad arguments, 5 a download or a checksum failed."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "server/lampway_server/library/models.json"
CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def allowed(url: str) -> bool:
    u = urllib.parse.urlparse(url)
    return u.scheme == "https" or (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1"))


def fetch_file(url: str, want: str, dest: Path) -> int:
    part = dest.with_name(dest.name + ".part")
    h, n = hashlib.sha256(), 0
    try:
        with urllib.request.urlopen(url, timeout=600) as r, open(part, "wb") as out:
            while chunk := r.read(CHUNK):
                h.update(chunk)
                n += len(chunk)
                out.write(chunk)
        if h.hexdigest() != want:
            raise SystemExit(f"sha256 mismatch for {dest.parent.name}/{dest.name}: expected {want}, got {h.hexdigest()}; the file was discarded")
        os.replace(part, dest)
    finally:
        part.unlink(missing_ok=True)
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dest", type=Path, help="the models directory inside the build")
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--plan", action="store_true")
    a = ap.parse_args(argv)
    models = json.loads(a.manifest.read_text(encoding="utf-8"))["models"]
    if a.plan:
        total = 0
        print(f"manifest: {a.manifest}\ndest: {a.dest or '(none given)'}")
        for m in models:
            for f in m["files"]:
                total += int(f.get("bytes") or 0)
                print(f"  {m['id']}/{f['name']}  {f['sha256']}  {f.get('bytes', '?')} bytes  {f['url']}")
        print(f"total_bytes: {total}")
        return 0
    if not a.dest:
        ap.error("--dest is required (or --plan)")
    for m in models:
        d = a.dest / m["id"]
        done = []
        for f in m["files"]:
            target = d / f["name"]
            if not allowed(f["url"]):
                print(f"refused: {f['url']}: only https URLs are fetched", file=sys.stderr)
                return 5
            if target.is_file() and sha256_of(target) == f["sha256"]:
                print(f"present: {m['id']}/{f['name']}")
                done.append({"name": f["name"], "url": f["url"], "sha256": f["sha256"], "bytes": target.stat().st_size, "verified_against": "manifest"})
                continue
            d.mkdir(parents=True, exist_ok=True)
            print(f"fetching: {m['id']}/{f['name']} ({f.get('bytes', '?')} bytes)", flush=True)
            try:
                n = fetch_file(f["url"], f["sha256"], target)
            except SystemExit as e:
                print(str(e), file=sys.stderr)
                return 5
            except OSError as e:
                print(f"download failed: {f['url']}: {e}", file=sys.stderr)
                return 5
            done.append({"name": f["name"], "url": f["url"], "sha256": f["sha256"], "bytes": n, "verified_against": "manifest"})
        (d / "PROVENANCE.json").write_text(json.dumps({"id": m["id"], "license": m.get("license"), "source": m.get("source"), "fetched_at": time.time(),
                                                        "bundled_by": "scripts/lampway/fetch_models.py", "files": done}, indent=1))
    print(f"models ready in {a.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
