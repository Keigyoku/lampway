"""The Vault's gates (specs/asset_library/asset_gates.md section 10): a deterministic corpus, gates that print numbers against thresholds and record a receipt,
a mutant for every gate that turns it red, and a refusal to write to the user's library. The suite builds a 1 500-asset corpus; the 10k baseline is a separate
run (docs/reports/asset-gates-baseline.md)."""
import json
import sqlite3

import pytest

from lampway_server.library import corpus as K
from lampway_server.library import gates as G
from lampway_server.library import query as Q
from lampway_server.library.store import AssetLibrary, LibraryError

N = 1500


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return K.build(tmp_path_factory.mktemp("corpus") / "lib", n=N, exact_dupes=60, near_dupes=60)


def fresh(tmp_path):
    return K.build(tmp_path / "lib", n=400, exact_dupes=20, near_dupes=20)


def test_corpus_is_deterministic_for_a_seed(tmp_path):
    a, ma = K.build(tmp_path / "a", n=120, exact_dupes=5, near_dupes=5)
    b, mb = K.build(tmp_path / "b", n=120, exact_dupes=5, near_dupes=5)
    rows = lambda lib: lib._reader().execute("select a.id,a.kind,a.name,v.content_key from asset a join version v on v.asset_id=a.id order by a.id").fetchall()   # noqa: E731
    assert [tuple(r) for r in rows(a)] == [tuple(r) for r in rows(b)] and ma["cluster_of"] == mb["cluster_of"]
    c, _ = K.build(tmp_path / "c", n=120, seed=7, exact_dupes=5, near_dupes=5)
    assert [tuple(r) for r in rows(c)] != [tuple(r) for r in rows(a)]


def test_the_kind_mix_and_the_planted_truth(built):
    lib, meta = built
    kinds = dict(lib._reader().execute("select kind,count(*) from asset group by kind").fetchall())
    assert abs(kinds["mesh"] / N - 0.40) < 0.05 and abs(kinds["image"] / sum(kinds.values()) - 0.30) < 0.06
    assert all(e["deduped"] for e in meta["exact"]) and not any(lib.get(e["result"])["name"].endswith("copy") for e in meta["exact"])


PERFORMANCE = ("latency", "throughput", "memory")                            # load-dependent: their verdicts belong to the baseline run, not to a shared box's CI


@pytest.mark.timeout(600)
def test_every_correctness_gate_passes_on_the_corpus_and_a_receipt_records_all(built):
    lib, meta = built
    rep = G.run(lib, meta, G.MACHINE_GATES, queries=40)
    by = {g["id"]: g for g in rep["gates"]}
    assert set(by) == set(G.MACHINE_GATES)
    failed = {k: v for k, v in by.items() if not v["passed"] and k not in PERFORMANCE}
    assert not failed, json.dumps(failed, indent=1, default=str)
    for k in PERFORMANCE:
        assert by[k]["value"] is not None and by[k]["verdict"] in ("pass", "fail"), by[k]                 # measured, whatever the box's load
    receipt = lib.get(rep["receipt"])
    assert receipt["kind"] == "receipt" and receipt["subtype"] == "gate"
    assert {g["gate"] for g in receipt["gates"]} == set(G.MACHINE_GATES) and json.loads(open(receipt["files"][0]["locations"][0]["path"]).read())["corpus"]["sha256"] == rep["corpus"]["sha256"]


def test_idle_is_not_run_without_a_render_batch_and_never_reads_as_a_pass(built):
    lib, meta = built
    rep = G.run(lib, meta, ["idle"])
    assert rep["gates"][0]["verdict"] == "not-run" and rep["gates"][0]["passed"] is False


def test_the_gate_runner_fails_when_a_threshold_is_missed(tmp_path, monkeypatch):
    lib, meta = fresh(tmp_path)
    real = Q.query

    def slow(l, q):
        import time
        time.sleep(0.08)
        return real(l, q)

    monkeypatch.setattr(Q, "query", slow)
    g = G.run(lib, meta, ["latency"], queries=10)["gates"][0]
    assert g["passed"] is False and g["verdict"] == "fail" and g["value"]["text_filter_p95_ms"] > 50


MUTANTS = {
    "fts_parity": lambda lib, meta: lib._db.execute("DELETE FROM asset_fts WHERE rowid=(SELECT min(rowid) FROM asset_fts)"),
    "dedupe": lambda lib, meta: lib._db.execute("UPDATE version SET content_key=(SELECT content_key FROM version WHERE asset_id=?) WHERE asset_id=?",
                                                (meta["near"][0]["original"], meta["near"][0]["result"])),
    "coverage": lambda lib, meta: lib._db.execute("DELETE FROM version_file WHERE role='thumb' AND version_id IN (SELECT id FROM version LIMIT 50)"),
    "provenance": lambda lib, meta: lib._db.execute("UPDATE generation SET job_id=NULL WHERE rowid=(SELECT min(rowid) FROM generation)"),
    "privacy": lambda lib, meta: lib._db.execute("UPDATE version SET attrs_json=? WHERE rowid=1", (json.dumps({"url": "https://x.example/f.png?X-Amz-Signature=abc"}),)),
    "schema": lambda lib, meta: (lib._db.execute("PRAGMA foreign_keys=OFF"), lib._db.execute("INSERT INTO version_file(version_id,role,ord,sha256) VALUES('nope','main',0,'f00')")),
    "recall": lambda lib, meta: lib._db.execute("UPDATE embedding SET vec=(SELECT vec FROM embedding WHERE space=? LIMIT 1) WHERE space=?", (K.SPACE, K.SPACE)),
    "integrity": "backup",
    "throughput": "slow_put",
    "memory": "threshold",
    "latency": "slow_query",
}


@pytest.mark.timeout(1800)
def test_every_gate_has_a_mutant_that_turns_it_red(tmp_path, monkeypatch):
    assert set(MUTANTS) == set(G.MACHINE_GATES)
    for gate, mutate in MUTANTS.items():
        lib, meta = K.build(tmp_path / gate, n=300, exact_dupes=10, near_dupes=10)
        if gate in PERFORMANCE:
            m0 = G.THRESHOLDS.copy()
            monkeypatch.setitem(G.THRESHOLDS, "puts_per_s", 1.0)                 # on a busy shared box the real threshold can already fail: green it first,
            monkeypatch.setitem(G.THRESHOLDS, "memory_mb", 100000.0)             # then the mutant must turn it red
            monkeypatch.setitem(G.THRESHOLDS, "latency", {**m0["latency"], "text_filter_p95_ms": 75.0})
        green = G.run(lib, meta, [gate], queries=10)["gates"][0]
        assert green["passed"] is True, gate
        with monkeypatch.context() as m:
            if mutate == "backup":
                m.setattr(AssetLibrary, "backup", lambda self, dest=None: (open(dest, "wb").close(), {"path": str(dest), "bytes": 0})[1])
            elif mutate == "slow_put":                                       # half the measured rate is the bar; a put twice as slow must miss it
                rate = green["value"]["puts_per_s"]
                m.setitem(G.THRESHOLDS, "puts_per_s", rate / 2)
                real_put = AssetLibrary.put
                m.setattr(AssetLibrary, "put", lambda self, spec: (__import__("time").sleep(2.5 / rate), real_put(self, spec))[1])
            elif mutate == "threshold":
                m.setitem(G.THRESHOLDS, "memory_mb", 1)
            elif mutate == "slow_query":
                real_q = Q.query
                m.setattr(Q, "query", lambda l, q: (__import__("time").sleep(0.1), real_q(l, q))[1])
            else:
                mutate(lib, meta)
            assert G.run(lib, meta, [gate], queries=10)["gates"][0]["passed"] is False, gate
        lib.close()


def test_gates_refuse_to_write_to_the_live_db(tmp_path):
    live = AssetLibrary(tmp_path / "live")
    live.put({"kind": "prompt", "name": "p", "source": {"kind": "t", "key": "p"}, "files": [{"role": "main", "bytes": b"p", "storage": "cas"}]})
    with pytest.raises(LibraryError, match="gates run on a copy: pass corpus=shelf only with a read-only library"):
        G.run(live, None, ["coverage"])
    rep = G.run_on_copy(live, tmp_path / "copy", ["coverage", "fts_parity", "schema", "integrity", "privacy"])
    assert {g["id"] for g in rep["gates"]} == {"coverage", "fts_parity", "schema", "integrity", "privacy"}
    assert live._reader().execute("select count(*) from asset where kind='receipt'").fetchone()[0] == 0          # the user's library got no receipt, no row
    assert rep["copy"].startswith(str(tmp_path / "copy"))
