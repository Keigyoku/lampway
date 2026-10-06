# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""N4 (specs/canon/normalization contracts/canon_migration.md section 6): the Vault keeps raw and canonical apart.

Migration 0004 adds the `canonical` table, the version's canon_state and the `normalized_from` relation; every stored version of a
geometry / rig / animation / map / texture kind is canonical (a validated lampway.canonical-asset/1 document) or raw - never an
unlabelled third thing - and a canonical version's dimensions come from its document, never from the raw file's header."""
import copy
import itertools
import json
import sqlite3
from pathlib import Path

import pytest

from lampway_server.library import schema as SCH
from lampway_server.library.store import AssetLibrary, LibraryError

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = json.loads((ROOT / "tests/lampway_tools/canon_goldens/normalization/canonical-asset.examples.json").read_text())


def make(tmp_path):
    ids = itertools.count(1)
    clock = itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))


def ext(tmp_path, name, data=b"x"):
    d = tmp_path / "ext"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_bytes(data)
    return p


def spec(path, key="k1", kind="mesh", **kw):
    return {"kind": kind, "name": "Chest", "source": {"kind": "folder", "key": key}, "files": [{"role": "main", "path": str(path), "storage": "external"}], **kw}


def canon_doc():
    return copy.deepcopy(EXAMPLES["valid"][0]["doc"])


def test_migration_0004_is_the_latest_and_adds_the_relation_type():
    assert SCH.latest_version() >= 4 and "normalized_from" in SCH.RELATION_TYPES
    assert set(SCH.CANONICAL_KINDS) == {"mesh", "rig", "animation", "map", "texture_set", "material"}


def test_a_version_without_a_document_is_stored_raw_and_said_so(tmp_path):
    lib = make(tmp_path)
    r = lib.put(spec(ext(tmp_path, "a.glb", b"raw-bytes")))
    with sqlite3.connect(lib.db_path) as db:
        state = db.execute("SELECT canon_state FROM version WHERE asset_id=?", (r["id"],)).fetchone()[0]
        assert state == "raw" and db.execute("SELECT count(*) FROM canonical").fetchone()[0] == 0


def test_a_claimed_canonical_version_needs_a_valid_document(tmp_path):
    lib = make(tmp_path)
    bad = canon_doc()
    bad["conventions"]["front"] = "+X"
    with pytest.raises(LibraryError, match="not a valid canonical document"):
        lib.put(spec(ext(tmp_path, "c.glb", b"canon-bytes"), canonical=bad))
    with pytest.raises(LibraryError, match="document"):
        lib.put(spec(ext(tmp_path, "d.glb", b"other"), key="k2", canon_state="canonical"))


def test_a_canonical_version_is_recorded_with_its_document_and_its_dimensions_come_from_it(tmp_path):
    lib = make(tmp_path)
    raw = lib.put(spec(ext(tmp_path, "a.glb", b"raw-bytes"), stats={"dim_x": 0.98, "dim_y": 0.5, "dim_z": 0.3}))
    doc = canon_doc()
    can = lib.put(spec(ext(tmp_path, "a.canon.blend", b"canon-bytes"), canonical=doc, normalized_from={"version": raw["version"]},
                       stats={"dim_x": 9.0}))
    assert can["id"] == raw["id"] and can["version"] == 2
    with sqlite3.connect(lib.db_path) as db:
        vid = db.execute("SELECT id FROM version WHERE asset_id=? AND n=2", (raw["id"],)).fetchone()[0]
        row = db.execute("SELECT kind, frame, scale_state, canonical_sha256, raw_sha256 FROM canonical WHERE version_id=?", (vid,)).fetchone()
        assert row == ("mesh", "lampway.body/1", doc["scale"]["state"], doc["canonical_sha256"], doc["raw"]["sha256"])
        assert db.execute("SELECT canon_state FROM version WHERE id=?", (vid,)).fetchone()[0] == "canonical"
        dims = db.execute("SELECT dim_x, dim_y, dim_z FROM mesh_stats WHERE version_id=?", (vid,)).fetchone()
        b = doc["body"]
        assert dims == pytest.approx([b["bbox_max_m"][i] - b["bbox_min_m"][i] for i in range(3)])
        rel = db.execute("SELECT src, dst, type, src_version, dst_version FROM relation WHERE type='normalized_from'").fetchone()
        assert rel == (raw["id"], raw["id"], "normalized_from", 2, 1)


def test_the_migration_marks_existing_versions_raw_and_backs_up(tmp_path):
    lib = make(tmp_path)
    lib.put(spec(ext(tmp_path, "a.glb", b"raw-bytes")))
    lib.close()
    db = sqlite3.connect(tmp_path / "lib" / "library.sqlite")                           # roll the schema back to 3 as an old Vault was
    db.executescript("""PRAGMA foreign_keys=OFF; DROP TABLE canonical; DROP VIEW v_relations;
        CREATE TABLE relation_old AS SELECT * FROM relation; DROP TABLE relation; ALTER TABLE relation_old RENAME TO relation;
        ALTER TABLE version DROP COLUMN canon_state; PRAGMA user_version=3;""")
    db.close()
    (tmp_path / "lib" / "library.sqlite.pre-0004.bak").unlink(missing_ok=True)      # a fresh Vault migrated through 0004 already left one
    lib = make(tmp_path)
    with sqlite3.connect(lib.db_path) as db2:
        assert db2.execute("PRAGMA user_version").fetchone()[0] == SCH.latest_version()
        assert {r[0] for r in db2.execute("SELECT canon_state FROM version")} == {"raw"}
    assert (tmp_path / "lib" / "library.sqlite.pre-0004.bak").exists()


def _glb(path, lo=(-0.49, -0.2, -0.1), hi=(0.49, 0.2, 0.1)):
    import struct
    doc = {"asset": {"version": "2.0"}, "accessors": [{"count": 3, "min": list(lo), "max": list(hi), "type": "VEC3", "componentType": 5126}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}]}
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 20 + len(js)) + struct.pack("<II", len(js), 0x4E4F534A) + js)
    return path


def test_ingest_stores_a_glb_raw_and_its_canonical_twin_canonical_with_the_documents_dimensions(tmp_path):
    from lampway_server.library.ingest import Ingest
    lib = make(tmp_path)
    root = tmp_path / "drop"
    root.mkdir()
    raw = Ingest(lib).ingest_file(root, _glb(root / "seed.glb"), "b1")
    can_path = _glb(root / "seed_canon.glb", lo=(-0.1, -0.3, 0.0), hi=(0.1, 0.3, 0.98))
    doc = canon_doc()
    (root / "seed_canon.glb.canon.json").write_text(json.dumps(doc))
    can = Ingest(lib).ingest_file(root, can_path, "b1")
    with sqlite3.connect(lib.db_path) as db:
        states = dict(db.execute("SELECT asset_id, canon_state FROM version").fetchall())
        assert states[raw["id"]] == "raw" and states[can["id"]] == "canonical"
        dims = db.execute("SELECT m.dim_z FROM mesh_stats m JOIN version v ON v.id = m.version_id WHERE v.asset_id=?", (can["id"],)).fetchone()[0]
        b = doc["body"]
        assert dims == pytest.approx(b["bbox_max_m"][2] - b["bbox_min_m"][2])                  # from the document, not the GLB header's 0.98


def test_get_returns_the_versions_canon_state_and_its_document(tmp_path):
    """asset_place reads what it places from get: the version's canon_state and, for a canonical version, its document."""
    lib = make(tmp_path)
    raw = lib.put(spec(ext(tmp_path, "a.glb", b"raw-bytes")))
    doc = canon_doc()
    lib.put(spec(ext(tmp_path, "a.canon.blend", b"canon-bytes"), canonical=doc, normalized_from={"version": raw["version"]}))
    cur = lib.get(raw["id"])
    assert cur["version"] == 2 and cur["canon_state"] == "canonical" and cur["canonical"] == doc
    old = lib.get(raw["id"], 1)
    assert old["canon_state"] == "raw" and "canonical" not in old
