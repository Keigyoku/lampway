# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compressed Blender classification sniffs bounded content, not filenames."""
import io
import hashlib

import pytest
import zstandard as zstd

from lampway_server.library import ingest as I
from lampway_server.library.store import AssetLibrary

HEADER = b"BLENDER-v502"
MODERN_HEADER = b"BLENDER17-01v0502"


def make_lib(tmp_path):
    return AssetLibrary(tmp_path / "library")


def snapshot(root):
    return {p.name: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in root.iterdir() if p.is_file()}


@pytest.mark.parametrize("name", ["rigged-warrior.blend", "renamed.dat"])
@pytest.mark.parametrize("header", [HEADER, MODERN_HEADER])
def test_scan_recognizes_zstd_blender_and_preserves_source(tmp_path, name, header):
    root = tmp_path / "inputs"
    root.mkdir()
    (root / name).write_bytes(zstd.ZstdCompressor().compress(header + b"packed image" * 20000))
    before = snapshot(root)
    ing = I.Ingest(make_lib(tmp_path))
    result = ing.scan([root])
    assert result["report"]["by_kind"] == {"mesh": 1}
    assert not result["report"]["unknown"]
    assert snapshot(root) == before and ing.lib.status()["assets"]["total"] == 0


@pytest.mark.parametrize("payload", [
    b"not a blend", b"BLENDER?v502", b"BLENDER-vabc", b"BLENDER-v50", b"PK\x03\x04random zip",
    b"BLENDER99-01v0502", b"BLENDER17-02v0502", b"BLENDER17-01V0502", b"BLENDER17-01v05xx",
    b"BLENDER17-01v050",
])
def test_zstd_wrong_inner_header_is_not_a_blend(tmp_path, payload):
    path = tmp_path / "claimed.blend"
    path.write_bytes(zstd.ZstdCompressor().compress(payload))
    ing = I.Ingest(make_lib(tmp_path))
    assert I.classify(ing._head(path), path.name) is None


@pytest.mark.parametrize("header", [HEADER, MODERN_HEADER])
def test_uncompressed_blender_headers_are_validated(header):
    assert I.classify(header, "renamed.dat")["container"] == "blend"


@pytest.mark.parametrize("payload", [b"\x28\xb5\x2f\xfd", b"\x28\xb5\x2f\xfd\xff\xff\xff\xff", b"arbitrary bytes"])
def test_corrupt_or_filename_only_blend_is_unknown(tmp_path, payload):
    path = tmp_path / "fake.blend"
    path.write_bytes(payload)
    ing = I.Ingest(make_lib(tmp_path))
    assert I.classify(ing._head(path), path.name) is None


def test_zip_is_still_an_archive_not_a_blend():
    assert I.classify(b"PK\x03\x04random", "fake.blend")["kind"] == "archive"


def test_sniff_refuses_oversized_window(tmp_path):
    # Valid zstd frame with a128MiB advertised window and a12-byte raw block.
    payload = b"\x28\xb5\x2f\xfd\x00\x88" + ((len(HEADER) << 3) | 1).to_bytes(3, "little") + HEADER
    assert zstd.get_frame_parameters(payload).window_size == 128 * 1024**2
    path = tmp_path / "large-window.blend"
    path.write_bytes(payload)
    ing = I.Ingest(make_lib(tmp_path))
    assert I.classify(ing._head(path), path.name) is None


def test_sniff_reads_only_a_bounded_prefix_even_for_large_content(tmp_path, monkeypatch):
    payload = zstd.ZstdCompressor().compress(HEADER + b"x" * (16 * 1024**2))
    stream = io.BytesIO(payload + b"unread trailing bytes" * 100000)
    reads = []
    class Source:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size):
            assert 0 <= size <= 256 * 1024
            reads.append(size)
            return stream.read(size)
    monkeypatch.setattr(I, "open", lambda *a, **kw: Source(), raising=False)
    header = I.Ingest(make_lib(tmp_path))._head(tmp_path / "large.blend")
    assert I.classify(header, "large.blend")["container"] == "blend"
    assert sum(reads) <= 256 * 1024 and len(header) == 12


def test_missing_header_within_input_budget_is_unknown(tmp_path):
    # Empty valid raw blocks delay the first output past the compressed-byte budget.
    prefix = b"\x28\xb5\x2f\xfd\x00\x00" + b"\x00\x00\x00" * 100000
    path = tmp_path / "late-header.blend"
    path.write_bytes(prefix + ((len(HEADER) << 3) | 1).to_bytes(3, "little") + HEADER)
    ing = I.Ingest(make_lib(tmp_path))
    assert I.classify(ing._head(path), path.name) is None
