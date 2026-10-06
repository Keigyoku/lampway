# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""scripts/lampway/fetch_models.py: the build step that bundles the Asset Vault's embedding weights into the install, each file checked against its pinned sha256.

A loopback HTTP server stands in for Hugging Face; nothing here reaches the network."""

from __future__ import annotations

import hashlib
import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/lampway/fetch_models.py"
REAL_MANIFEST = REPO / "server/lampway_server/library/models.json"


@pytest.fixture
def served(tmp_path):
    files = {"/a/model.onnx": b"onnx-bytes-a" * 100, "/b/vocab.txt": b"[PAD]\n[UNK]\n"}
    hits = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            body = files.get(self.path)
            self.send_response(200 if body is not None else 404)
            self.end_headers()
            if body is not None:
                self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    manifest = {"models": [{"id": "m-a", "files": [{"name": "model.onnx", "url": base + "/a/model.onnx", "sha256": hashlib.sha256(files["/a/model.onnx"]).hexdigest()}]},
                           {"id": "m-b", "files": [{"name": "vocab.txt", "url": base + "/b/vocab.txt", "sha256": hashlib.sha256(files["/b/vocab.txt"]).hexdigest()}]}]}
    mpath = tmp_path / "models.json"
    mpath.write_text(json.dumps(manifest))
    yield {"manifest": mpath, "files": files, "hits": hits, "doc": manifest}
    srv.shutdown()


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, timeout=120)


def test_it_fetches_every_pinned_file_and_records_provenance(served, tmp_path):
    dest = tmp_path / "install/datafiles/lampway/models"
    r = run("--manifest", served["manifest"], "--dest", dest)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (dest / "m-a/model.onnx").read_bytes() == served["files"]["/a/model.onnx"]
    assert (dest / "m-b/vocab.txt").read_bytes() == served["files"]["/b/vocab.txt"]
    prov = json.loads((dest / "m-a/PROVENANCE.json").read_text())
    assert prov["files"][0]["sha256"] == served["doc"]["models"][0]["files"][0]["sha256"] and prov["files"][0]["verified_against"] == "manifest"


def test_a_second_run_downloads_nothing(served, tmp_path):
    dest = tmp_path / "models"
    assert run("--manifest", served["manifest"], "--dest", dest).returncode == 0
    n = len(served["hits"])
    r = run("--manifest", served["manifest"], "--dest", dest)
    assert r.returncode == 0 and len(served["hits"]) == n and "present" in r.stdout


def test_a_checksum_mismatch_fails_the_build_and_leaves_nothing(served, tmp_path):
    served["doc"]["models"][0]["files"][0]["sha256"] = "0" * 64
    served["manifest"].write_text(json.dumps(served["doc"]))
    dest = tmp_path / "models"
    r = run("--manifest", served["manifest"], "--dest", dest)
    assert r.returncode == 5 and "sha256 mismatch" in r.stdout + r.stderr
    assert not (dest / "m-a/model.onnx").exists() and not list(dest.rglob("*.part"))


def test_a_file_whose_bytes_changed_on_disk_is_fetched_again(served, tmp_path):
    dest = tmp_path / "models"
    run("--manifest", served["manifest"], "--dest", dest)
    (dest / "m-a/model.onnx").write_bytes(b"tampered")
    n = len(served["hits"])
    assert run("--manifest", served["manifest"], "--dest", dest).returncode == 0
    assert len(served["hits"]) == n + 1 and (dest / "m-a/model.onnx").read_bytes() == served["files"]["/a/model.onnx"]


def test_plan_reads_the_real_manifest_and_touches_no_network(tmp_path):
    r = run("--plan", "--dest", tmp_path / "models")
    assert r.returncode == 0, r.stderr
    doc = json.loads(REAL_MANIFEST.read_text())
    for m in doc["models"]:
        for f in m["files"]:
            assert f["sha256"] in r.stdout
    assert "total_bytes:" in r.stdout and not (tmp_path / "models").exists()


def test_only_https_or_loopback_urls_are_fetched(tmp_path):
    m = tmp_path / "m.json"
    m.write_text(json.dumps({"models": [{"id": "x", "files": [{"name": "f", "url": "http://example.invalid/f", "sha256": "0" * 64}]}]}))
    r = run("--manifest", m, "--dest", tmp_path / "d")
    assert r.returncode == 5 and "https" in r.stdout + r.stderr
