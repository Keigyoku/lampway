"""Asset Vault importers for the user's existing shelf (specs/asset_library/asset_seed_captain.md section 10): a synthetic seeds.sqlite of the real 20-column shape,
plus, when LAMPWAY_SHELF_SEEDS names the real file, the real 61 rows."""
import hashlib
import itertools
import json
import os
import sqlite3

import pytest

from lampway_server.library import curate as C
from lampway_server.library import importers as M
from lampway_server.library.store import AssetLibrary

COLS = ("id TEXT PRIMARY KEY, piece TEXT, kind TEXT, parent_id TEXT, project_id TEXT, created_at INTEGER, topology TEXT, faces INTEGER, url TEXT, file TEXT, sha256 TEXT, "
        "bytes INTEGER, plates_json TEXT, score_rms REAL, score_json TEXT, verdict TEXT, verdict_note TEXT, audit_path TEXT, added_at INTEGER, source TEXT")


def make_lib(tmp_path):
    ids, clock = itertools.count(1), itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))


def fbx(path, tag):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"Kaydara FBX Binary  \x00" + tag.encode() * 8)
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size


@pytest.fixture
def shelf(tmp_path):
    root = tmp_path / "shelf"
    plate = root / "img" / "front.jpg"
    plate.parent.mkdir(parents=True)
    plate.write_bytes(b"\xff\xd8\xff\xe0plate")
    plate_sha = hashlib.sha256(plate.read_bytes()).hexdigest()
    plates = json.dumps({"Front": {"file": str(plate), "sha256": plate_sha}})
    run = root / "Boots1_g1"
    (run).mkdir()
    (run / "run.json").write_text(json.dumps({"tool": "tripo_mesh.py", "credits_before": 9390, "credits_after": 9290, "seconds": 105}))
    audit = root / "audit.json"
    audit.write_text('{"ok": true}')
    rows = []
    for i, (kind, parent, verdict) in enumerate([("generation", None, "chosen"), ("local_edit", "s1", "runner-up"), ("local_edit", "s2", "fix"), ("multiview_to_model", None, None), ("local_edit", "ghost", None)], 1):
        sha, n = fbx(run / f"v{i}.fbx", str(i))
        rows.append((f"s{i}", "boots1", kind, parent, f"proj{i}", 1791000000 + i, "Triangle" if i == 2 else "Quad", 100 * i,
                     f"https://cdn.example.test/o_{i}.fbx?Signature=SECRETSIG&Expires=9", str(run / f"v{i}.fbx"), sha if i != 5 else "0" * 64, n,
                     plates if i in (1, 2) else None, 0.4 if i == 1 else None, '{"rms": 0.4}' if i == 1 else None, verdict, "the words" if verdict else None,
                     str(audit) if i == 1 else None, 1791100000 + i, str(root / "variants.json")))
    db = sqlite3.connect(root / "seeds.sqlite")
    db.execute(f"create table seeds ({COLS})")
    db.executemany("insert into seeds values (" + ",".join("?" * 20) + ")", rows)
    db.commit()
    db.close()
    return root


def sha_tree(root):
    return {str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in root.rglob("*") if p.is_file()}


def run_import(tmp_path, shelf):
    lib = make_lib(tmp_path)
    return lib, M.import_shelf_seeds(lib, shelf / "seeds.sqlite", by="captain")


def test_every_seed_with_a_file_becomes_a_mesh_asset_with_the_matching_sha_and_bytes(tmp_path, shelf):
    lib, rep = run_import(tmp_path, shelf)
    assert rep["meshes"] == 5 and lib.status()["assets"]["by_kind"]["mesh"] == 5 and rep["assets"] == 7      # + the plate and the audit receipt
    a = lib.get(lib.find_by_name("v1")[0])
    assert a["files"][0]["sha256"] == hashlib.sha256((shelf / "Boots1_g1" / "v1.fbx").read_bytes()).hexdigest()
    assert a["stats"]["faces"] == 100 and a["stats"]["topology"] == "Quad" and lib.get(lib.find_by_name("v2")[0])["stats"]["topology"] == "Tri"
    assert {(t["facet"], t["label"]) for t in a["terms"]} >= {("piece_type", "boots"), ("studio", "tripo")}


def test_parent_ids_become_derived_from_relations_orphans_are_listed_not_dropped(tmp_path, shelf):
    lib, rep = run_import(tmp_path, shelf)
    assert rep["relations"]["derived_from"] == 2                                  # s2->s1, s3->s2
    assert [u["ref"] for u in rep["unresolved"] if u["why"].startswith("parent")] == ["s5"]
    s2 = lib.get(lib.find_by_name("v2")[0])
    assert [(r["type"], r["dst"]) for r in s2["relations"] if r["src"] == s2["id"] and r["type"] == "derived_from"] == [("derived_from", lib.find_by_name("v1")[0])]


def test_verdicts_are_decisions_with_the_words_and_a_pick_flag_only_for_chosen(tmp_path, shelf):
    lib, rep = run_import(tmp_path, shelf)
    assert rep["verdicts"] == 3
    rows = lib._db.execute("select question,answer,decider,words,asset_id,how from decision order by id").fetchall()
    assert [(r[1], r[3], r[5]) for r in rows] == [("usable", "the words", "shelf_seeds:chosen"), ("usable", "the words", "shelf_seeds:runner-up"), ("fix", "the words", "shelf_seeds:fix")] and {r[2] for r in rows} == {"captain"}
    assert C.shelf_word(lib, lib.find_by_name("v1")[0]) == "chosen"          # the shelf's own word survives the mapping
    flags = lib._db.execute("select asset_id,flag from rating").fetchall()
    assert flags == [(lib.find_by_name("v1")[0], "pick")]


def test_run_json_credits_become_the_cost(tmp_path, shelf):
    lib, rep = run_import(tmp_path, shelf)
    gen = lib.get(lib.find_by_name("v1")[0])["generation"][0]
    assert gen["cost_credits"] == 100 and gen["cost_basis"] == "measured" and gen["studio"] == "tripo" and gen["action"] == "image_to_model"
    assert lib.get(lib.find_by_name("v2")[0])["generation"][0]["action"] == "local_edit"


def test_credits_that_went_up_are_refused_by_naming_the_row(tmp_path, shelf):
    (shelf / "Boots1_g1" / "run.json").write_text(json.dumps({"credits_before": 100, "credits_after": 150}))
    lib, rep = run_import(tmp_path, shelf)
    assert any(f["what"] == "credits_increased" and f["ref"] == "s1" for f in rep["findings"])
    assert lib.get(lib.find_by_name("v1")[0])["generation"][0]["cost_credits"] is None


def test_signed_urls_never_reach_the_library(tmp_path, shelf):
    lib, _ = run_import(tmp_path, shelf)
    blob = json.dumps([lib.get(i) for i in lib.find_by_name("v")], default=str)
    assert "SECRETSIG" not in blob and "?" not in lib.get(lib.find_by_name("v1")[0])["attrs"]["source_url"]


def test_a_shelf_sha_that_disagrees_with_the_file_is_a_finding_and_the_row_is_kept(tmp_path, shelf):
    lib, rep = run_import(tmp_path, shelf)
    assert [f["ref"] for f in rep["findings"] if f["what"] == "sha256_mismatch"] == ["s5"]
    assert lib.find_by_name("v5")


def test_plates_are_image_assets_shared_across_seeds_and_linked_generated_from(tmp_path, shelf):
    lib, rep = run_import(tmp_path, shelf)
    plates = [r[0] for r in lib._db.execute("select id from asset where kind='image'")]
    assert len(plates) == 1                                                      # one plate used by two seeds
    rels = lib._db.execute("select src,type,role from relation where type='generated_from'").fetchall()
    assert len(rels) == 2 and {r[2] for r in rels} == {"Front"}
    assert {(t["facet"], t["label"]) for t in lib.get(plates[0])["terms"]} >= {("view", "front")}


def test_the_score_is_a_measurement_not_a_pass(tmp_path, shelf):
    lib, _ = run_import(tmp_path, shelf)
    g = lib.get(lib.find_by_name("v1")[0])["gates"][0]
    assert g["gate"] == "proportion_rms" and g["value"] == 0.4 and g["threshold"] is None and json.loads(g["detail_json"])["measurement_only"] is True


def test_the_audit_file_is_a_receipt_derived_from_the_seed(tmp_path, shelf):
    lib, rep = run_import(tmp_path, shelf)
    r = lib._db.execute("select id from asset where kind='receipt'").fetchall()
    assert len(r) == 1 and rep["relations"]["receipt_derived_from"] == 1
    rels = lib._db.execute("select src,dst from relation where src=?", (r[0][0],)).fetchall()
    assert rels == [(r[0][0], lib.find_by_name("v1")[0])]


def test_sources_are_untouched_and_reimport_is_idempotent_and_batch_rollback_is_soft(tmp_path, shelf):
    before = sha_tree(shelf)
    lib, first = run_import(tmp_path, shelf)
    again = M.import_shelf_seeds(lib, shelf / "seeds.sqlite", by="captain")
    assert sha_tree(shelf) == before
    assert again["assets"] == 0 and again["verdicts"] == 0 and lib.status()["assets"]["total"] == 5 + 1 + 1       # 5 meshes, 1 plate, 1 audit receipt
    assert lib._db.execute("select count(*) from decision").fetchone()[0] == 3
    out = lib.rollback(first["batch"])
    assert out["soft_deleted"] == 7 and lib.status()["assets"]["active"] == 0 and (shelf / "Boots1_g1" / "v1.fbx").exists()


def test_the_import_needs_the_users_click(tmp_path, shelf):
    with pytest.raises(Exception, match="user's click"):
        M.import_shelf_seeds(make_lib(tmp_path), shelf / "seeds.sqlite", by="agent")


# ---- meshqa decisions ---------------------------------------------------------------------------------------------------------
def _row(i, session="chest_9c052d49_r2_2026-10-04"):
    desc = {"id": f"L{i}", "kind": "open_loop"}
    return {"answer": "keep" if i % 2 else "hole", "captain_words": f"words {i}", "decider": "captain", "descriptor": desc, "descriptor_sha256": hashlib.sha256(json.dumps(desc, sort_keys=True).encode()).hexdigest(),
            "how": "everything_else", "options": ["hole", "keep"], "question": "open_loop_defect", "region_rule": None, "session": session, "source": "x/candidates.json"}


def test_meshqa_rows_round_trip_with_words_options_and_sha_and_reimport_is_idempotent(tmp_path):
    lib = make_lib(tmp_path)
    p = tmp_path / "decisions.jsonl"
    p.write_text("\n".join(json.dumps(_row(i)) for i in range(5)) + "\n")
    rep = M.import_meshqa(lib, p, by="captain")
    assert rep["rows"] == 5 and rep["imported"] == 5
    got = lib._db.execute("select question,options_json,answer,decider,how,words,descriptor_sha256,session from decision order by id").fetchall()
    want = [_row(i) for i in range(5)]
    assert [(g[0], json.loads(g[1]), g[2], g[3], g[4], g[5], g[6], g[7]) for g in got] == [(w["question"], w["options"], w["answer"], w["decider"], w["how"], w["captain_words"], w["descriptor_sha256"], w["session"]) for w in want]
    assert M.import_meshqa(lib, p, by="captain")["imported"] == 0 and lib._db.execute("select count(*) from decision").fetchone()[0] == 5


def test_meshqa_rows_with_no_matching_asset_are_listed_never_dropped(tmp_path):
    lib = make_lib(tmp_path)
    f = tmp_path / "chest_9c052d49.fbx"
    f.write_bytes(b"Kaydara FBX Binary  \x00" + b"c" * 16)
    a = lib.put({"kind": "mesh", "name": "chest_9c052d49", "source": {"kind": "t", "key": "c"}, "files": [{"role": "main", "path": str(f), "storage": "external"}]})["id"]
    p = tmp_path / "d.jsonl"
    p.write_text(json.dumps(_row(1)) + "\n" + json.dumps(_row(2, session="boots_ffffffff_r1")) + "\n")
    rep = M.import_meshqa(lib, p, by="captain")
    assert rep["matched"] == 1 and [u["ref"] for u in rep["unresolved"]] == ["boots_ffffffff_r1"] and rep["imported"] == 2
    assert lib._db.execute("select asset_id from decision order by id").fetchall() == [(a,), (None,)]


# ---- the real shelf (opt in: LAMPWAY_SHELF_SEEDS names the file; the test reads a read-only backup) ------------------------------------------
@pytest.mark.skipif(not os.environ.get("LAMPWAY_SHELF_SEEDS"), reason="LAMPWAY_SHELF_SEEDS not set: the real 61-row import is an opt-in check")
def test_the_real_shelf_61_seeds_37_derived_from_8_verdicts(tmp_path):
    src = sqlite3.connect(f"file:{os.environ['LAMPWAY_SHELF_SEEDS']}?mode=ro", uri=True)
    cp = tmp_path / "seeds.sqlite"
    dst = sqlite3.connect(cp)
    src.backup(dst)
    dst.close()
    lib = make_lib(tmp_path)
    rep = M.import_shelf_seeds(lib, cp, by="captain")
    assert rep["meshes"] == 61 and rep["relations"]["derived_from"] == 37 and rep["verdicts"] == 8
    assert not [f for f in rep["findings"] if f["what"] == "sha256_mismatch"]


def test_a_seed_whose_file_is_gone_is_listed_unresolved_and_the_rest_still_import(tmp_path, shelf):
    (shelf / "Boots1_g1" / "v4.fbx").unlink()
    lib, rep = run_import(tmp_path, shelf)
    assert rep["meshes"] == 4 and [u["ref"] for u in rep["unresolved"] if u["why"].startswith("file not found")] == ["s4"]
