# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The native transcript cursor progresses through records larger than one poll."""
import json
import os
import builtins
import threading
from types import SimpleNamespace

import pytest

from lampway_server.agent import byoa as B


def line(value):
    return json.dumps(value, ensure_ascii=False).encode() + b"\n"


def observer(tmp_path, path):
    seen = []
    conv = SimpleNamespace(feed=lambda record, at: seen.append((at, record)) or [])
    watch = B._Watch({"id": "owned", "harness": "codex"}, conv, 0)
    watch.path = str(path)
    view = B.ByoaView(SimpleNamespace(switch_dir=tmp_path))
    return view, watch, seen


@pytest.mark.anyio
async def test_complete_native_record_larger_than_poll_does_not_block_completion(tmp_path):
    path = tmp_path / "native.jsonl"
    records = [
        {"type": "response_item", "payload": {"type": "message", "role": "assistant",
         "content": [{"type": "output_text", "text": "x" * (B.READ_CHUNK + 100)}]}},
        {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "owned-turn"}},
        {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "next-turn"}},
    ]
    encoded = [line(record) for record in records]
    path.write_bytes(b"".join(encoded))
    view, watch, seen = observer(tmp_path, path)
    for _ in range(5):
        await view._poll("scene", watch)
    assert seen == [(0, records[0]), (len(encoded[0]), records[1]),
                    (len(encoded[0]) + len(encoded[1]), records[2])]
    assert watch.offset == path.stat().st_size
    view.mirrors["scene"] = watch
    view.forget("scene")


@pytest.mark.anyio
async def test_large_native_response_reaches_real_codex_turn_completion(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "READ_CHUNK", 64)
    path = tmp_path / "native.jsonl"
    records = [
        {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "native-turn"}},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant",
         "content": [{"type": "output_text", "text": "x" * 400}]}},
        {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "native-turn"}},
    ]
    path.write_bytes(b"".join(line(record) for record in records))
    watch = B._Watch({"id": "owned", "harness": "codex"}, B.MR.for_harness("codex", "owned"), 0)
    watch.path = str(path)
    view = B.ByoaView(SimpleNamespace(switch_dir=tmp_path))
    observed = []

    async def apply(session_id, current_watch, ops, at, nxt):
        observed.extend((kind, tid) for kind, tid, data in ops)

    monkeypatch.setattr(view, "_apply", apply)
    try:
        for _ in range(20):
            await view._poll("scene", watch)
        starts = [tid for kind, tid in observed if kind == "start"]
        ends = [tid for kind, tid in observed if kind == "end"]
        assert len(starts) == 1
        assert ends == starts
        assert watch.offset == path.stat().st_size
    finally:
        watch.reader.close()


def drain(reader, path, offset=0, polls=20):
    seen = []
    for _ in range(polls):
        records, offset = reader.read(str(path), offset)
        seen.extend(records)
    return seen, offset


def test_incomplete_utf8_row_is_spooled_without_partial_emission(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "READ_CHUNK", 7)
    path = tmp_path / "native.jsonl"
    encoded = line({"text": "🙂" * 12})
    path.write_bytes(encoded[:-1])
    reader = B._RecordReader(tmp_path)
    try:
        assert drain(reader, path) == ([], 0)
        assert reader.scanned == len(encoded) - 1
        assert reader.spool is not None
        assert os.fstat(reader.spool.fileno()).st_mode & 0o777 == 0o600
        assert set(tmp_path.iterdir()) == {path}  # no named spool survives
        with path.open("ab") as fh:
            fh.write(b"\n" + line({"next": True}))
        seen, offset = drain(reader, path)
        assert seen == [(0, len(encoded), {"text": "🙂" * 12}),
                        (len(encoded), path.stat().st_size, {"next": True})]
        assert offset == path.stat().st_size
        assert drain(reader, path, offset) == ([], offset)
    finally:
        spool = reader.spool
        reader.close()
    assert spool.closed


@pytest.mark.parametrize("change", ["replace", "truncate", "reset"])
def test_pending_row_is_discarded_on_native_file_change_or_cursor_reset(tmp_path, monkeypatch, change):
    monkeypatch.setattr(B, "READ_CHUNK", 8)
    path = tmp_path / "native.jsonl"
    first = line({"first": True})
    path.write_bytes(first + b'{"unfinished":"' + b"x" * 80)
    reader = B._RecordReader(tmp_path)
    try:
        seen, offset = drain(reader, path)
        assert seen == [(0, len(first), {"first": True})]
        assert offset == len(first)
        old_spool = reader.spool
        fresh = line({"new": True})
        if change == "replace":
            replacement = tmp_path / "replacement"
            replacement.write_bytes(fresh + b" " * 160 + b"\n")
            replacement.replace(path)  # larger replacement also must reset
        elif change == "truncate":
            path.write_bytes(fresh)
        else:
            offset = 0               # explicit resume cursor discards the partial row
        seen, offset = drain(reader, path, offset)
        expected = {"first": True} if change == "reset" else {"new": True}
        assert seen[0] == (0, len(first if change == "reset" else fresh), expected)
        assert len(seen) == 1
        assert old_spool.closed
    finally:
        reader.close()


def test_read_error_retains_pending_bytes_and_complete_cursor(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "READ_CHUNK", 8)
    path = tmp_path / "native.jsonl"
    record = {"text": "x" * 40}
    path.write_bytes(line(record))
    reader = B._RecordReader(tmp_path)
    try:
        assert reader.read(str(path), 0) == ([], 0)
        scanned = reader.scanned
        hidden = tmp_path / "hidden"
        path.rename(hidden)
        assert reader.read(str(path), 0) == ([], 0)
        assert reader.scanned == scanned
        hidden.rename(path)
        assert drain(reader, path) == ([(0, path.stat().st_size, record)], path.stat().st_size)
    finally:
        reader.close()


def test_invalid_rows_and_crlf_keep_exact_byte_offsets(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "READ_CHUNK", 5)
    path = tmp_path / "native.jsonl"
    prefix = b"\xff\nnot-json\n\r\n"
    valid = b'{"ok":true}\r\n'
    path.write_bytes(prefix + valid)
    reader = B._RecordReader(tmp_path)
    try:
        assert drain(reader, path) == ([(len(prefix), len(prefix + valid), {"ok": True})], len(prefix + valid))
    finally:
        reader.close()


def test_native_reads_stay_within_one_poll_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "READ_CHUNK", 13)
    path = tmp_path / "native.jsonl"
    record = {"text": "x" * 200}
    path.write_bytes(line(record))
    sizes = []

    class NativeFile:
        def __init__(self, *args, **kwargs):
            self.fh = builtins.open(*args, **kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.fh.close()

        def __getattr__(self, name):
            return getattr(self.fh, name)

        def read(self, size):
            sizes.append(size)
            return self.fh.read(size)

    monkeypatch.setattr(B, "open", NativeFile, raising=False)
    reader = B._RecordReader(tmp_path)
    try:
        assert drain(reader, path)[0] == [(0, path.stat().st_size, record)]
        assert sizes and all(0 <= size <= 13 for size in sizes)
    finally:
        reader.close()


def test_close_during_completed_decode_does_not_block_or_emit(tmp_path, monkeypatch):
    path = tmp_path / "native.jsonl"
    path.write_bytes(line({"done": True}))
    reader = B._RecordReader(tmp_path)
    entered, release = threading.Event(), threading.Event()
    loads = json.loads

    def blocked_loads(value):
        entered.set()
        assert release.wait(5)
        return loads(value)

    monkeypatch.setattr(B.json, "loads", blocked_loads)
    results = []
    worker = threading.Thread(target=lambda: results.append(reader.read(str(path), 0)))
    worker.start()
    try:
        assert entered.wait(5)
        spool = reader.spool
        reader.close()               # returns while decoding still owns the lock
        assert worker.is_alive()
        assert reader.closed
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert results == [([], 0)]
    assert spool.closed
    assert reader.read(str(path), 0) == ([], 0)


def test_spool_failure_retries_unemitted_batch_without_duplicates(tmp_path, monkeypatch):
    path = tmp_path / "native.jsonl"
    first, second = line({"one": True}), line({"two": True})
    path.write_bytes(first + second)
    temporary_file = B.tempfile.TemporaryFile
    writes = 0

    class FailingSpool:
        def __init__(self, *args, **kwargs):
            self.fh = temporary_file(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self.fh, name)

        def write(self, value):
            nonlocal writes
            writes += 1
            if writes == 2:
                self.fh.write(value[:2])
                raise OSError("synthetic spool failure")
            return self.fh.write(value)

    monkeypatch.setattr(B.tempfile, "TemporaryFile", FailingSpool)
    reader = B._RecordReader(tmp_path)
    try:
        with pytest.raises(OSError, match="synthetic spool failure"):
            reader.read(str(path), 0)
        assert reader.offset == reader.scanned == 0
        seen, offset = drain(reader, path)
        assert seen == [(0, len(first), {"one": True}), (len(first), len(first + second), {"two": True})]
        assert drain(reader, path, offset) == ([], offset)
    finally:
        reader.close()
