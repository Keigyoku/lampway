"""Asset Vault query (specs/asset_library/asset_query.md section 10) on a deterministic 300-asset corpus."""
import itertools
import random
import time

import pytest

from lampway_server.library import query as Q
from lampway_server.library.store import AssetLibrary, LibraryError

PIECES = ["helmet", "chest", "gauntlets", "greaves", "waist", "boots"]
MATERIALS = ["plate_metal", "leather", "cloth", "trim"]


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("corpus")
    ids, clock = itertools.count(1), itertools.count(1000)
    lib = AssetLibrary(tmp / "lib", idgen=lambda: f"a{next(ids):04d}", clock=lambda: float(next(clock)))
    rnd = random.Random(7)
    recs = []
    with lib.bulk():
        for i in range(300):
            kind = ["mesh", "image", "material"][i % 3]
            piece, mat = rnd.choice(PIECES), rnd.choice(MATERIALS)
            faces = rnd.randrange(500, 90000)
            name = f"{piece} {rnd.choice(['gold', 'bronze', 'iron'])} {i}"
            desc = "embroidered leather trim" if i % 7 == 0 else ""
            spec = {"kind": kind, "name": name, "description": desc, "source": {"kind": "t", "key": str(i)},
                    "files": [{"role": "main", "bytes": f"b{i}".encode(), "storage": "cas"}],
                    "terms": [{"facet": "piece_type", "label": piece}, {"facet": "material_role", "label": mat}], "tags": ["v3"] if i % 5 == 0 else []}
            if kind == "mesh":
                spec["stats"] = {"faces": faces, "verts": faces // 2, "topology": "Quad"}
            elif kind == "image":
                spec["stats"] = {"width": 1024, "height": 1024}
            r = lib.put(spec)
            stars = rnd.choice([None, 1, 2, 3, 4, 5])
            if stars:
                lib.rate(r["id"], "captain", stars=stars)
            recs.append({"id": r["id"], "kind": kind, "piece": piece, "mat": mat, "faces": faces if kind == "mesh" else None, "rating": stars, "name": name, "i": i, "desc": desc, "tags": ["v3"] if i % 5 == 0 else []})
    return lib, recs


def ids(res):
    return [it["id"] for it in res["items"]]


def test_filter_only_returns_the_exact_set_a_brute_force_filter_returns(corpus):
    lib, recs = corpus
    q = {"kinds": ["mesh"], "where": {"all": [{"field": "mesh_stats.faces", "op": "between", "value": [5000, 40000]}, {"field": "rating", "op": ">=", "value": 4}]}, "terms": {"piece_type": ["gauntlets", "chest"]}, "limit": 200}
    want = {r["id"] for r in recs if r["kind"] == "mesh" and 5000 <= r["faces"] <= 40000 and (r["rating"] or 0) >= 4 and r["piece"] in ("gauntlets", "chest")}
    got = Q.query(lib, q)
    assert want and set(ids(got)) == want and got["total"] == len(want)


def test_all_any_none_and_tags_and_relations_compose(corpus):
    lib, recs = corpus
    got = Q.query(lib, {"where": {"any": [{"field": "kind", "op": "=", "value": "mesh"}, {"field": "kind", "op": "=", "value": "image"}], "none": [{"field": "rating", "op": "exists", "value": False}]},
                        "tags": {"all": ["v3"]}, "limit": 200})
    want = {r["id"] for r in recs if r["kind"] in ("mesh", "image") and r["rating"] and "v3" in r["tags"]}
    assert want and set(ids(got)) == want
    a, b = recs[0]["id"], recs[1]["id"]
    lib.relate(a, "derived_from", b, by="rule")
    out = Q.query(lib, {"relations": [{"type": "derived_from", "direction": "out", "exists": True}], "limit": 5})
    assert ids(out) == [a]
    assert ids(Q.query(lib, {"relations": [{"type": "derived_from", "direction": "in", "of": a, "exists": True}], "limit": 5})) == [b]


def test_text_ranks_a_name_match_above_a_description_match(corpus):
    lib, recs = corpus
    only_desc = next(r for r in recs if r["desc"] and "gold" not in r["name"])
    only_name = next(r for r in recs if not r["desc"] and "gold" in r["name"])
    lib.put({"kind": "prompt", "name": "plain note", "description": "embroidered embroidered embroidered gold", "source": {"kind": "t", "key": "x1"}, "files": [{"role": "main", "bytes": b"x1", "storage": "cas"}]})
    lib.put({"kind": "prompt", "name": "embroidered", "description": "", "source": {"kind": "t", "key": "x2"}, "files": [{"role": "main", "bytes": b"x2", "storage": "cas"}]})
    got = Q.query(lib, {"text": "embroidered", "limit": 5})
    top = [it["name"] for it in got["items"]]
    assert top[0] == "embroidered" and "plain note" in top
    assert got["items"][0]["score"] > got["items"][1]["score"] and only_desc and only_name


def test_unknown_field_is_refused_with_the_nearest_names(corpus):
    lib, _ = corpus
    with pytest.raises(LibraryError, match=r"unknown field 'mesh_stats.facse'; nearest: \['mesh_stats.faces'"):
        Q.query(lib, {"where": {"all": [{"field": "mesh_stats.facse", "op": ">", "value": 1}]}})
    with pytest.raises(LibraryError, match="limit max 200"):
        Q.query(lib, {"limit": 201})
    with pytest.raises(LibraryError, match="unknown op"):
        Q.query(lib, {"where": {"all": [{"field": "rating", "op": "~", "value": 1}]}})


def test_a_sql_fragment_in_a_value_is_bound_not_executed(corpus):
    lib, recs = corpus
    got = Q.query(lib, {"where": {"all": [{"field": "name", "op": "=", "value": "1; DROP TABLE asset"}]}})
    assert got["items"] == [] and lib.status()["assets"]["total"] >= 300
    got = Q.query(lib, {"text": 'x" OR 1=1 --'})                          # an FTS operator in the text is a literal, not syntax
    assert isinstance(got["items"], list)


def test_like_is_prefix_only(corpus):
    lib, _ = corpus
    assert Q.query(lib, {"where": {"all": [{"field": "name", "op": "like", "value": "helmet"}]}, "limit": 3})["items"]
    with pytest.raises(LibraryError, match="prefix"):
        Q.query(lib, {"where": {"all": [{"field": "name", "op": "like", "value": "%helmet"}]}})


def test_facet_counts_equal_group_by_of_the_filtered_set_and_ignore_limit(corpus):
    lib, recs = corpus
    got = Q.query(lib, {"kinds": ["mesh", "image"], "facets": ["kind", "piece_type"], "limit": 3})
    want = {}
    for r in recs:
        if r["kind"] in ("mesh", "image"):
            want[r["piece"]] = want.get(r["piece"], 0) + 1
    assert {f["value"]: f["count"] for f in got["facets"]["piece_type"]} == want
    assert {f["value"]: f["count"] for f in got["facets"]["kind"]} == {"mesh": 100, "image": 100} and len(got["items"]) == 3


def test_rrf_beats_either_list_on_a_planted_query():
    text = [f"t{i}" for i in range(60)]
    image = [f"i{i}" for i in range(60)]
    text[39] = "plant"
    image[34] = "plant"
    fused = Q.fuse([text, image], [1.0, 1.0])
    assert fused[0][0] == "plant" and [x for x, _ in fused].index("plant") < 5
    assert "plant" not in text[:30] and "plant" not in image[:30]


def test_paging_cursor_is_stable_and_goes_stale_after_a_write(corpus):
    lib, _ = corpus
    p1 = Q.query(lib, {"kinds": ["mesh"], "sort": [{"by": "name"}], "limit": 10})
    p2 = Q.query(lib, {"kinds": ["mesh"], "sort": [{"by": "name"}], "limit": 10, "cursor": p1["cursor"]})
    names = [it["name"] for it in p1["items"] + p2["items"]]
    assert names == sorted(names) and len(set(names)) == 20
    lib.put({"kind": "prompt", "name": "late", "source": {"kind": "t", "key": "late"}, "files": [{"role": "main", "bytes": b"late", "storage": "cas"}]})
    with pytest.raises(LibraryError, match="cursor_stale"):
        Q.query(lib, {"kinds": ["mesh"], "sort": [{"by": "name"}], "limit": 10, "cursor": p1["cursor"]})


def test_the_decision_place_ask_none_follows_threshold_and_margin(corpus):
    lib, _ = corpus
    lib.put({"kind": "prompt", "name": "zzzunique zzzunique", "source": {"kind": "t", "key": "u1"}, "files": [{"role": "main", "bytes": b"u1", "storage": "cas"}]})
    r = Q.query(lib, {"text": "zzzunique", "threshold": 0.1})
    assert r["decision"] == "place"
    assert Q.query(lib, {"text": "zzzunique", "threshold": 0.99})["decision"] == "none"
    assert Q.query(lib, {"text": "zzznothing", "threshold": 0.1})["decision"] == "none"


def test_includes_stats_tags_and_explanations(corpus):
    lib, recs = corpus
    m = next(r for r in recs if r["kind"] == "mesh" and r["tags"])
    got = Q.query(lib, {"where": {"all": [{"field": "id", "op": "=", "value": m["id"]}]}, "include": ["stats", "tags"], "explain": True})
    it = got["items"][0]
    assert it["stats"]["faces"] == m["faces"] and it["tags"] == ["v3"] and "filters" in it["why"]


def test_empty_library_says_so(tmp_path):
    lib = AssetLibrary(tmp_path / "lib")
    r = Q.query(lib, {"text": "x"})
    assert r["items"] == [] and "library is empty" in r["note"]


# ---- the read-only SQL view -----------------------------------------------------------------------------------------------------
def test_sql_view_reads_the_views_and_nothing_else(corpus):
    lib, recs = corpus
    rows = Q.readonly_sql(lib, "SELECT kind, count(*) AS n FROM v_assets GROUP BY kind ORDER BY kind")
    assert {r["kind"]: r["n"] for r in rows["rows"]}["mesh"] == 100
    assert rows["rows"][0].keys() == {"kind", "n"}
    for bad, why in [("INSERT INTO asset(id,kind,name,created_at,updated_at) VALUES('x','mesh','x',0,0)", "denied"), ("DELETE FROM asset", "denied"), ("ATTACH DATABASE ':memory:' AS m", "denied"),
                     ("PRAGMA writable_schema=1", "denied"), ("SELECT load_extension('x')", "denied"), ("SELECT * FROM asset", "denied"), ("SELECT id, name FROM asset", "denied"), ("SELECT vec FROM embedding", "denied"), ("SELECT * FROM event", "denied"), ("SELECT * FROM sqlite_master", "denied"),
                     ("DROP TABLE asset", "denied")]:
        with pytest.raises(LibraryError, match=why):
            Q.readonly_sql(lib, bad)
    assert lib.status()["assets"]["total"] >= 300


def test_sql_view_aborts_a_long_query_and_caps_rows(corpus):
    lib, _ = corpus
    t = time.time()
    with pytest.raises(LibraryError, match="time limit"):
        Q.readonly_sql(lib, "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM c", timeout_s=0.5)
    assert time.time() - t < 3
    assert len(Q.readonly_sql(lib, "SELECT id FROM v_assets", limit=7)["rows"]) == 7
    with pytest.raises(LibraryError, match="limit max 10000"):
        Q.readonly_sql(lib, "SELECT 1", limit=10001)


def test_the_view_set_is_pinned(corpus):
    lib, _ = corpus
    names = {r[0] for r in lib._db.execute("select name from sqlite_master where type='view'")}
    assert names == {"v_assets", "v_versions", "v_files", "v_relations", "v_provenance", "v_gates", "v_video_clips", "v_ratings_latest", "v_terms"}
    cols = [r[1] for r in lib._db.execute("PRAGMA table_info(v_assets)")]
    assert cols[:6] == ["id", "kind", "subtype", "name", "status", "rating"] and "faces" in cols and "duration_s" in cols


def test_soft_deleted_assets_are_hidden_unless_asked_for(corpus):
    lib, recs = corpus
    victim = recs[2]["id"]
    lib.set_status(victim, "deleted")
    assert victim not in ids(Q.query(lib, {"limit": 200, "kinds": [recs[2]["kind"]]}))
    got = Q.query(lib, {"where": {"all": [{"field": "status", "op": "=", "value": "deleted"}]}})
    assert ids(got) == [victim]
    lib.set_status(victim, "active")


def test_an_unknown_relation_type_in_a_query_is_refused(corpus):
    lib, _ = corpus
    with pytest.raises(LibraryError, match="unknown relation 'adores'"):
        Q.query(lib, {"relations": [{"type": "adores", "exists": True}]})
