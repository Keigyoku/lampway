"""Asset Vault store (specs/asset_library/asset_store.md section 10): real SQLite, tmp dirs, fixed clock and ids."""
import hashlib
import itertools
import os
import random
import sqlite3
import threading

import pytest

from lampway_server.library.store import AssetLibrary, LibraryError


def make(tmp_path, **kw):
    ids = itertools.count(1)
    clock = itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)), **kw)


def ext(tmp_path, name, data=b"x"):
    d = tmp_path / "ext"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_bytes(data)
    return p


def spec(path, key="k1", name="Chest", kind="mesh", **kw):
    return {"kind": kind, "name": name, "source": {"kind": "folder", "key": key}, "files": [{"role": "main", "path": str(path), "storage": "external"}], **kw}


def test_put_same_bytes_twice_is_one_asset_one_blob(tmp_path):
    lib, p = make(tmp_path), ext(tmp_path, "a.glb", b"glb-bytes")
    a = lib.put(spec(p))
    b = lib.put(spec(p))
    assert a["created"] is True and b["created"] is False and b["id"] == a["id"]
    st = lib.status()
    assert st["assets"]["by_kind"] == {"mesh": 1} and st["blobs"] == 1 and st["versions"] == 1


def test_same_bytes_new_path_adds_location_not_asset(tmp_path):
    lib = make(tmp_path)
    a = lib.put(spec(ext(tmp_path, "a.glb", b"same"), key="k1"))
    r = lib.put(spec(ext(tmp_path, "copy.glb", b"same"), key="k2", name="Copy"))
    assert r["deduped"] is True and r["dedupe_of"] == a["id"] and r["created"] is False
    assert lib.status()["assets"]["by_kind"] == {"mesh": 1}
    with sqlite3.connect(lib.db_path) as db:
        assert db.execute("select count(*) from location").fetchone()[0] == 2


def test_changed_content_same_source_key_makes_version_2_and_keeps_v1_files(tmp_path):
    lib, p = make(tmp_path), ext(tmp_path, "a.glb", b"one")
    a = lib.put(spec(p))
    p.write_bytes(b"two-longer")
    b = lib.put(spec(p))
    assert b["id"] == a["id"] and b["version"] == 2 and b["created"] is True
    got = lib.get(a["id"])
    assert got["current_version"] == 2
    v1 = lib.get(a["id"], version=1)
    assert v1["files"][0]["sha256"] == hashlib.sha256(b"one").hexdigest()      # v1 keeps its own file hash


def test_referenced_file_is_never_modified(tmp_path):
    lib, p = make(tmp_path), ext(tmp_path, "a.glb", b"keep me")
    before = (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
    lib.put(spec(p))
    lib.verify(deep=True)
    assert (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) == before
    assert not (tmp_path / "lib" / "cas").exists() or not any((tmp_path / "lib" / "cas").rglob("*.glb"))   # referenced = never copied


def test_cas_bytes_are_stored_once_under_the_library_root(tmp_path):
    lib = make(tmp_path)
    s = {"kind": "image", "name": "n", "source": {"kind": "tool", "key": "j1"}, "files": [{"role": "main", "bytes": b"png-bytes", "storage": "cas"}]}
    r = lib.put(s)
    sha = hashlib.sha256(b"png-bytes").hexdigest()
    cas = tmp_path / "lib" / "cas" / sha[:2] / sha[2:4] / sha
    assert cas.read_bytes() == b"png-bytes" and r["created"]
    lib.put({**s, "source": {"kind": "tool", "key": "j2"}})
    assert len(list((tmp_path / "lib" / "cas").rglob(sha))) == 1


def test_fts_matches_rows_after_100_random_puts_and_deletes(tmp_path):
    lib, rnd = make(tmp_path), random.Random(5)
    ids = []
    for i in range(100):
        r = lib.put({"kind": "prompt", "name": f"item {i} greave", "source": {"kind": "t", "key": str(i)}, "description": "bronze " * (i % 3),
                     "files": [{"role": "main", "bytes": f"b{i}".encode(), "storage": "cas"}]})
        ids.append(r["id"])
    for i in rnd.sample(ids, 30):
        lib.set_status(i, "deleted")
    assert lib.verify()["fts_drift"] == 0
    assert lib.status()["fts_rows"] == lib.status()["assets"]["active"]


def test_migration_applies_and_refuses_newer_db(tmp_path):
    lib = make(tmp_path)
    lib.close()
    with sqlite3.connect(lib.db_path) as db:
        db.execute("PRAGMA user_version = 99")
    with pytest.raises(LibraryError, match=r"library schema 99 is newer than this server \(1\): update the server"):
        AssetLibrary(tmp_path / "lib")


def test_concurrent_readers_see_a_consistent_snapshot_during_a_write(tmp_path):
    lib = make(tmp_path)
    errors, stop = [], threading.Event()

    def reader():
        while not stop.is_set():
            try:
                st = lib.status()
                assert st["versions"] >= st["assets"]["total"] - 0 and st["fts_rows"] == st["assets"]["active"]
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))
                return
    ts = [threading.Thread(target=reader) for _ in range(2)]
    [t.start() for t in ts]
    for i in range(60):
        lib.put({"kind": "prompt", "name": f"n{i}", "source": {"kind": "t", "key": str(i)}, "files": [{"role": "main", "bytes": os.urandom(8), "storage": "cas"}]})
    stop.set()
    [t.join() for t in ts]
    assert errors == []


def test_crash_mid_put_leaves_no_half_asset(tmp_path):
    lib = make(tmp_path)

    def boom():
        raise RuntimeError("killed after the blob write")
    lib._after_blobs = boom
    with pytest.raises(RuntimeError):
        lib.put({"kind": "image", "name": "n", "source": {"kind": "t", "key": "1"}, "files": [{"role": "main", "bytes": b"orphan", "storage": "cas"}]})
    lib._after_blobs = lambda: None
    st = lib.status()
    assert st["assets"]["total"] == 0 and st["blobs"] == 0
    assert lib.verify()["orphan_blobs"] == [hashlib.sha256(b"orphan").hexdigest()]


def test_signed_url_never_stored(tmp_path):
    lib = make(tmp_path)
    r = lib.put({"kind": "mesh", "name": "n", "source": {"kind": "t", "key": "1"}, "files": [{"role": "main", "bytes": b"m", "storage": "cas"}],
                 "attrs": {"url": "https://cdn.example.test/a.glb?Signature=SECRET&Expires=1"}})
    blob = str(lib.get(r["id"]))
    assert "SECRET" not in blob and "?" not in lib.get(r["id"])["attrs"]["url"]


def test_a_path_outside_the_allowed_roots_is_refused(tmp_path):
    lib = make(tmp_path, allowed_roots=[tmp_path / "ext"])
    ok = ext(tmp_path, "a.glb")
    lib.put(spec(ok))
    outside = tmp_path / "other.glb"
    outside.write_bytes(b"z")
    with pytest.raises(LibraryError, match="outside the roots"):
        lib.put(spec(outside, key="k9"))


def test_relations_are_closed_acyclic_and_never_self(tmp_path):
    lib = make(tmp_path)
    a = lib.put(spec(ext(tmp_path, "a", b"1"), key="a"))["id"]
    b = lib.put(spec(ext(tmp_path, "b", b"2"), key="b"))["id"]
    lib.relate(a, "derived_from", b, by="rule")
    with pytest.raises(LibraryError, match="unknown relation 'friends'"):
        lib.relate(a, "friends", b, by="rule")
    with pytest.raises(LibraryError, match="itself"):
        lib.relate(a, "derived_from", a, by="rule")
    with pytest.raises(LibraryError, match="derived_from cycle"):
        lib.relate(b, "derived_from", a, by="rule")


def test_rating_is_append_only_latest_wins_and_decisions_are_journaled(tmp_path):
    lib = make(tmp_path)
    a = lib.put(spec(ext(tmp_path, "a", b"1")))["id"]
    lib.rate(a, rater="captain", stars=2)
    lib.rate(a, rater="captain", stars=5, note="better")
    assert lib.get(a)["rating"] == 5
    lib.decide(question="keep?", answer="yes", decider="captain", asset_id=a, options=["yes", "no"], how="ui")
    lines = (tmp_path / "lib" / "decisions.jsonl").read_text().splitlines()
    assert len(lines) == 3 and '"answer": "yes"' in lines[-1]


def test_a_second_writer_is_refused_with_the_holders_pid(tmp_path):
    held = make(tmp_path)           # the holder must stay referenced: a collected library releases its lock
    with pytest.raises(LibraryError, match=r"locked by another writer \(pid \d+\)"):
        AssetLibrary(tmp_path / "lib")
    assert held.status()["schema_version"] == 1


def test_low_disk_refuses_managed_writes(tmp_path, monkeypatch):
    lib = make(tmp_path)
    monkeypatch.setattr("lampway_server.library.store._free_bytes", lambda p: 1 * 1024 ** 3)
    with pytest.raises(LibraryError, match="free space low"):
        lib.put({"kind": "image", "name": "n", "source": {"kind": "t", "key": "1"}, "files": [{"role": "main", "bytes": b"x", "storage": "cas"}]})
