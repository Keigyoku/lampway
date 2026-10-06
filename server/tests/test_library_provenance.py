"""Asset Vault provenance capture (asset_provenance.md section 10): one hook every generating tool calls; a failure never fails the generation."""
import hashlib
import itertools
import json

import pytest

from lampway_server.library import provenance as P
from lampway_server.library.store import AssetLibrary, LibraryError


def make_lib(tmp_path):
    ids, clock = itertools.count(1), itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))


def out_file(tmp_path, name, data=b"mp4-bytes"):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def video_payload(path, **gen):
    g = {"studio": "higgsfield", "provider": "higgsfield", "model": "seedance_2_0", "action": "video_gen", "prompt_text": "a knight walks", "template_id": "side_track", "template_version": "3",
         "vars": {"piece": "boots"}, "params": {"resolution": "720p", "duration": 10}, "seed": "not_exposed", "cost_credits": 45, "cost_basis": "measured", "job_id": "job-1", "approved_by": "captain",
         "started_at": 100.0, "finished_at": 160.0, "parents": {}}
    g.update(gen)
    return {"outputs": [{"path": str(path), "role": "main", "kind": "video", "name": "walk clip"}], "generation": g, "tool": "video_gen", "tool_version": "abc123"}


def test_a_video_completion_creates_an_asset_and_a_complete_generation_row(tmp_path):
    lib = make_lib(tmp_path)
    p = out_file(tmp_path, "walk.mp4")
    res = P.record(lib, video_payload(p))
    assert res["ok"] and res["assets"][0]["created"] and res["completeness"]["missing"] == []
    assert lib._db.execute("select version_id from generation where id=?", (res["generation_ids"][0],)).fetchone()[0] == lib.version_of(res["assets"][0]["id"])
    a = lib.get(res["assets"][0]["id"])
    g = a["generation"][0]
    assert (g["model"], g["provider"], g["job_id"], g["cost_basis"], g["cost_credits"], g["seed_not_exposed"], g["approved_by"]) == ("seedance_2_0", "higgsfield", "job-1", "measured", 45, 1, "captain")
    assert g["prompt_sha256"] == hashlib.sha256(b"a knight walks").hexdigest() and g["seed"] is None and g["template_id"] == "side_track" and g["finished_at"] - g["started_at"] == 60.0
    assert a["kind"] == "video" and a["files"][0]["locations"][0]["storage"] == "cas"           # a generation output is the only copy: managed storage


def test_the_prompt_is_also_an_asset_keyed_by_template_version_and_vars(tmp_path):
    lib = make_lib(tmp_path)
    r1 = P.record(lib, video_payload(out_file(tmp_path, "a.mp4", b"a")))
    r2 = P.record(lib, video_payload(out_file(tmp_path, "b.mp4", b"b"), job_id="job-2"))
    g1, g2 = (lib.get(r["assets"][0]["id"])["generation"][0] for r in (r1, r2))
    assert g1["prompt_asset"] and g1["prompt_asset"] == g2["prompt_asset"]                      # the same template@version+vars is one prompt asset
    assert lib.get(g1["prompt_asset"])["kind"] == "prompt"


def test_a_start_frame_creates_a_generated_from_relation_to_the_image_asset(tmp_path):
    lib = make_lib(tmp_path)
    img = lib.put({"kind": "image", "name": "start", "source": {"kind": "t", "key": "s"}, "files": [{"role": "main", "bytes": b"png", "storage": "cas"}]})["id"]
    res = P.record(lib, video_payload(out_file(tmp_path, "w.mp4"), parents={"start_frame": img}))
    rels = lib.get(res["assets"][0]["id"])["relations"]
    assert [(r["type"], r["dst"], r["role"]) for r in rels if r["src"] == res["assets"][0]["id"]] == [("generated_from", img, "start_frame")]


def test_parents_resolve_by_sha_and_by_job_id_and_an_unresolved_one_is_kept_as_text(tmp_path):
    lib = make_lib(tmp_path)
    parent = P.record(lib, video_payload(out_file(tmp_path, "p.mp4", b"parent"), job_id="job-parent"))["assets"][0]["id"]
    sha = hashlib.sha256(b"parent").hexdigest()
    by_sha = P.record(lib, video_payload(out_file(tmp_path, "c1.mp4", b"c1"), job_id="c1", parents={"parent_seed": sha}))["assets"][0]["id"]
    by_job = P.record(lib, video_payload(out_file(tmp_path, "c2.mp4", b"c2"), job_id="c2", parents={"parent_seed": "job-parent"}))["assets"][0]["id"]
    lost = P.record(lib, video_payload(out_file(tmp_path, "c3.mp4", b"c3"), job_id="c3", parents={"parent_seed": "nowhere"}))
    for child in (by_sha, by_job):
        assert [(r["type"], r["dst"]) for r in lib.get(child)["relations"] if r["src"] == child] == [("derived_from", parent)]
    assert lost["unresolved_parents"] == [{"role": "parent_seed", "ref": "nowhere"}]
    assert lib.get(lost["assets"][0]["id"])["attrs"]["parent_ref"] == {"parent_seed": "nowhere"}


def test_a_signed_url_query_is_stripped_and_the_strip_is_recorded(tmp_path):
    lib = make_lib(tmp_path)
    pl = video_payload(out_file(tmp_path, "w.mp4"))
    pl["outputs"][0]["attrs"] = {"url": "https://cdn.example.test/o.mp4?Signature=SECRET&Expires=2"}
    a = lib.get(P.record(lib, pl)["assets"][0]["id"])
    assert "SECRET" not in json.dumps(a, default=str) and a["attrs"]["url"] == "https://cdn.example.test/o.mp4" and a["attrs"]["url_stripped"] is True


def test_an_estimated_cost_needs_a_number(tmp_path):
    with pytest.raises(LibraryError, match="estimated cost needs a number or basis 'none'"):
        P.record(make_lib(tmp_path), video_payload(out_file(tmp_path, "w.mp4"), cost_basis="estimated", cost_credits=None, cost_usd=None))


def test_a_missing_output_is_refused_and_a_failed_job_records_the_cost_without_an_asset(tmp_path):
    lib = make_lib(tmp_path)
    with pytest.raises(LibraryError, match="output not found"):
        P.record(lib, video_payload(tmp_path / "ghost.mp4"))
    pl = video_payload(tmp_path / "ghost.mp4", ok=False, error="provider 500", cost_credits=45)
    pl["outputs"] = []
    res = P.record(lib, pl)
    assert res["assets"] == [] and res["generation_ids"] and "video" not in lib.status()["assets"]["by_kind"]       # no output asset (the prompt text is its own asset)
    assert lib._db.execute("select count(*) from generation where id=?", (res["generation_ids"][0],)).fetchone()[0] == 1
    row = lib._db.execute("select model,cost_credits,params_json from generation").fetchone()
    assert row[0] == "seedance_2_0" and row[1] == 45 and json.loads(row[2])["error"] == "provider 500" and json.loads(row[2])["ok"] is False


def test_the_seed_is_never_invented(tmp_path):
    lib = make_lib(tmp_path)
    r = P.record(lib, video_payload(out_file(tmp_path, "w.mp4"), seed=None))
    g = lib.get(r["assets"][0]["id"])["generation"][0]
    assert g["seed"] is None and g["seed_not_exposed"] == 0                       # unknown stays unknown
    mesh = video_payload(out_file(tmp_path, "m.glb", b"glb"), job_id="m1", seed=None, action="image_to_model", studio="tripo", provider="tripo", model="v3")
    mesh["outputs"][0]["kind"] = "mesh"
    bad = P.record(lib, mesh)["assets"][0]["id"]
    assert {"id": bad, "missing": ["seed|seed_not_exposed"]} in P.audit(lib)["incomplete"]          # an image_to_model must say its seed or that it is not exposed
    r2 = P.record(lib, video_payload(out_file(tmp_path, "x.mp4", b"x"), seed="123", job_id="j9"))
    assert lib.get(r2["assets"][0]["id"])["generation"][0]["seed"] == "123"


def test_audit_lists_what_each_action_still_lacks(tmp_path):
    lib = make_lib(tmp_path)
    ok = P.record(lib, video_payload(out_file(tmp_path, "a.mp4", b"a")))["assets"][0]["id"]
    bad = P.record(lib, video_payload(out_file(tmp_path, "b.mp4", b"b"), job_id="j2", cost_basis=None))["assets"][0]["id"]
    rep = P.audit(lib)
    assert rep["generated_assets"] == 2 and rep["complete"] == 1 and rep["by_studio"] == {"higgsfield": 2}
    assert rep["incomplete"] == [{"id": bad, "missing": ["cost_basis"]}] and ok


def test_a_provenance_failure_never_fails_the_job_and_is_spooled_then_replayed(tmp_path):
    lib = make_lib(tmp_path)
    spool = tmp_path / "spool.jsonl"
    bad = video_payload(tmp_path / "later.mp4")
    r = P.capture(lib, spool, bad)                                       # the file does not exist yet: record() refuses, capture() does not raise
    assert r["ok"] is False and r["spooled"] is True and len(spool.read_text().splitlines()) == 1
    assert P.audit(lib, spool=spool)["spooled"] == 1
    out_file(tmp_path, "later.mp4")
    rep = P.replay_spool(lib, spool)
    assert rep == {"replayed": 1, "still_failing": 0} and spool.read_text() == "" and lib.status()["assets"]["by_kind"]["video"] == 1


def test_a_spooled_row_never_holds_a_signed_url_or_secret(tmp_path):
    lib = make_lib(tmp_path)
    spool = tmp_path / "spool.jsonl"
    pl = video_payload(tmp_path / "later.mp4")
    pl["generation"]["params"] = {"callback": "https://x.example.test/cb?token=SECRETTOKEN"}
    P.capture(lib, spool, pl)
    assert "SECRETTOKEN" not in spool.read_text()


def test_backfill_of_runs_jsonl_is_idempotent_and_failed_runs_are_kept(tmp_path):
    lib = make_lib(tmp_path)
    rows = [{"kind": "run", "t": 1791222943.1, "job_id": "e8154407", "service": "image_gen", "template": None, "variables": {}, "prompt": "a brass lamp", "model": "default", "cost": None,
             "output": "http://127.0.0.1:8787/api/v1/jobs/files/TOK/1.png", "variant_of": None, "ok": True, "error": None, "provider": None},
            {"kind": "run", "t": 1791222944.0, "job_id": "bd7b24c7", "service": "image_gen", "template": None, "variables": {}, "prompt": "x", "model": "default", "cost": None, "output": None,
             "variant_of": None, "ok": False, "error": "RuntimeError: the image model is down", "provider": None}]
    f = tmp_path / "runs.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    first = P.backfill(lib, f)
    second = P.backfill(lib, f)
    assert first == {"rows": 2, "imported": 2, "skipped": 0} and second == {"rows": 2, "imported": 0, "skipped": 2}
    assert lib._db.execute("select count(*) from generation").fetchone()[0] == 2
    params = lib._db.execute("select params_json from generation where job_id='e8154407'").fetchone()[0]
    assert "TOK" not in params and "127.0.0.1" in params                      # the transient job-file URL is kept as a reference with its token removed


def test_the_same_bytes_from_a_second_job_keep_both_origins(tmp_path):
    lib = make_lib(tmp_path)
    a = P.record(lib, video_payload(out_file(tmp_path, "a.mp4", b"same"), job_id="job-A"))
    b = P.record(lib, video_payload(out_file(tmp_path, "b.mp4", b"same"), job_id="job-B"))
    assert b["assets"][0]["deduped"] is True and b["assets"][0]["id"] == a["assets"][0]["id"]
    assert sorted(g["job_id"] for g in lib.get(a["assets"][0]["id"])["generation"]) == ["job-A", "job-B"]
    assert lib._db.execute("select count(*) from generation").fetchone()[0] == 2


def test_a_signed_url_inside_the_generation_params_is_not_stored(tmp_path):
    lib = make_lib(tmp_path)
    pl = video_payload(out_file(tmp_path, "a.mp4"), params={"callback": "https://x.example.test/cb?token=SECRETTOKEN&x=1"})
    P.record(lib, pl)
    assert "SECRETTOKEN" not in lib._db.execute("select params_json from generation").fetchone()[0]
