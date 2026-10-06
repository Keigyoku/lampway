"""Asset Vault curation (asset_curate.md section 10): ratings, verdicts, relations, boards, saved searches, term confirmation."""
import itertools
import json

import pytest

from lampway_server.library import curate as C
from lampway_server.library import query as Q
from lampway_server.library.store import AssetLibrary, LibraryError

SHELF_KEYS = {"answer", "captain_words", "decider", "descriptor", "descriptor_sha256", "how", "options", "question", "region_rule", "session", "source"}


def make_lib(tmp_path):
    ids, clock = itertools.count(1), itertools.count(1000)
    return AssetLibrary(tmp_path / "lib", idgen=lambda: f"id{next(ids):05d}", clock=lambda: float(next(clock)))


def add(lib, name, key=None, kind="mesh"):
    return lib.put({"kind": kind, "name": name, "source": {"kind": "t", "key": key or name}, "files": [{"role": "main", "bytes": name.encode(), "storage": "cas"}]})["id"]


def test_the_captains_rating_outranks_an_agents_in_the_effective_rating(tmp_path):
    lib = make_lib(tmp_path)
    a = add(lib, "boots")
    C.rate(lib, a, rater="agent:w3", stars=5)
    assert lib.get(a)["rating"] == 5                                   # no captain rating yet: the agents' mean
    C.rate(lib, a, rater="agent:w4", stars=2)
    assert lib.get(a)["rating"] == 3                                   # floor((5+2)/2)
    out = C.rate(lib, a, rater="captain", stars=1)
    assert lib.get(a)["rating"] == 1 and out["rating"] == {"captain": 1, "agents": [{"id": "w3", "stars": 5}, {"id": "w4", "stars": 2}]}
    C.rate(lib, a, rater="agent:w3", stars=5)
    assert lib.get(a)["rating"] == 1                                   # an agent never moves the captain's rating


def test_an_agent_cannot_rate_as_the_captain_and_stars_are_one_to_five(tmp_path):
    lib = make_lib(tmp_path)
    a = add(lib, "boots")
    with pytest.raises(LibraryError, match="ratings as the user are made in the Vault UI; agents rate as agent:<id>"):
        C.rate(lib, a, rater="captain", stars=5, origin="agent")
    with pytest.raises(LibraryError, match="stars are 1 to 5"):
        C.rate(lib, a, rater="agent:x", stars=6)
    with pytest.raises(LibraryError, match="rater must be"):
        C.rate(lib, a, rater="someone", stars=3)


def test_rating_history_is_append_only_and_latest_wins(tmp_path):
    lib = make_lib(tmp_path)
    a = add(lib, "boots")
    for s in (2, 4, 3):
        C.rate(lib, a, rater="captain", stars=s)
    assert lib._db.execute("select count(*) from rating where asset_id=?", (a,)).fetchone()[0] == 3
    assert lib._db.execute("select stars from v_ratings_latest where asset_id=?", (a,)).fetchall() == [(3,)] and lib.get(a)["rating"] == 3


def test_every_decision_writes_a_journal_line_with_the_shelf_row_shape(tmp_path):
    lib = make_lib(tmp_path)
    a = add(lib, "boots")
    C.rate(lib, a, rater="captain", stars=4, verdict="usable", note="my words")
    C.decide(lib, "seed_pick", "boots_v2", asset_ids=[a], options=["boots_v1", "boots_v2"], words="this one, obviously", decider="captain")
    lines = [json.loads(x) for x in (tmp_path / "lib" / "decisions.jsonl").read_text().splitlines()]
    assert len(lines) == 3
    for row in lines:
        assert SHELF_KEYS <= set(row), SHELF_KEYS - set(row)
        assert row["descriptor"]["asset_id"] == a and len(row["descriptor_sha256"]) == 64
    assert lines[-1]["captain_words"] == "this one, obviously" and lines[-1]["options"] == ["boots_v1", "boots_v2"]


def test_a_verdict_is_a_decision_and_the_shelf_vocabulary_round_trips(tmp_path):
    lib = make_lib(tmp_path)
    a = add(lib, "boots")
    out = C.rate(lib, a, rater="captain", verdict="chosen")
    assert out["verdict"] == "usable" and C.shelf_word(lib, a) == "chosen"
    assert lib._db.execute("select flag from rating where asset_id=?", (a,)).fetchall() == [("pick",)]
    b = add(lib, "greaves")
    C.rate(lib, b, rater="captain", verdict="runner-up")
    assert C.shelf_word(lib, b) == "runner-up" and lib._db.execute("select answer from decision where asset_id=?", (b,)).fetchone()[0] == "usable"
    with pytest.raises(LibraryError, match="verdict"):
        C.rate(lib, a, rater="captain", verdict="great")


def test_relations_are_unique_and_a_cycle_is_refused(tmp_path):
    lib = make_lib(tmp_path)
    a, b = add(lib, "a"), add(lib, "b")
    assert C.relate(lib, a, "variant_of", b, by="captain")["created"] is True
    assert C.relate(lib, a, "variant_of", b, by="captain")["created"] is False
    C.relate(lib, a, "derived_from", b, by="captain")
    with pytest.raises(LibraryError, match="derived_from cycle"):
        C.relate(lib, b, "derived_from", a, by="captain")


def test_removing_a_provenance_relation_requires_supersede_but_a_hand_made_one_can_go(tmp_path):
    lib = make_lib(tmp_path)
    a, b, c = add(lib, "a"), add(lib, "b"), add(lib, "c")
    lib.relate(a, "derived_from", b, by="rule")
    C.relate(lib, a, "uses", c, by="captain")
    with pytest.raises(LibraryError, match="came from provenance capture"):
        C.relate(lib, a, "derived_from", b, by="captain", remove=True)
    assert C.relate(lib, a, "uses", c, by="captain", remove=True)["removed"] is True
    assert C.relate(lib, c, "supersedes", a, by="captain")["created"] is True


def test_a_smart_collection_follows_the_library_and_a_board_does_not(tmp_path):
    lib = make_lib(tmp_path)
    a, b = add(lib, "greave one"), add(lib, "helmet one")
    smart = C.collect(lib, "create", name="greaves", kind="smart", query={"text": "greave"})["collection"]["id"]
    board = C.collect(lib, "create", name="pick", kind="board")["collection"]["id"]
    C.collect(lib, "add", collection=board, asset_ids=[a], x_y=[10, 20])
    assert [i["id"] for i in C.collect(lib, "get", collection=smart)["items"]] == [a]
    c = add(lib, "greave two")
    assert {i["id"] for i in C.collect(lib, "get", collection=smart)["items"]} == {a, c}
    got = C.collect(lib, "get", collection=board)
    assert [(i["id"], i["x"], i["y"]) for i in got["items"]] == [(a, 10.0, 20.0)] and b
    C.collect(lib, "remove", collection=board, asset_ids=[a])
    assert C.collect(lib, "get", collection=board)["items"] == []
    C.collect(lib, "delete", collection=board)
    assert lib.status()["assets"]["total"] == 3                                          # deleting a collection never deletes assets


def test_a_smart_collection_with_an_invalid_query_gets_the_query_refusal(tmp_path):
    with pytest.raises(LibraryError, match="unknown field 'nope'"):
        C.collect(make_lib(tmp_path), "create", name="x", kind="smart", query={"where": {"all": [{"field": "nope", "op": "=", "value": 1}]}})


def test_saved_searches_run(tmp_path):
    lib = make_lib(tmp_path)
    a = add(lib, "greave one")
    sid = C.collect(lib, "save_search", name="gr", query={"text": "greave"})["search"]["id"]
    assert [s["name"] for s in C.collect(lib, "list_searches")["searches"]] == ["gr"]
    assert [i["id"] for i in C.collect(lib, "run_search", collection=sid)["items"]] == [a]


def test_rejecting_a_model_term_suppresses_the_same_suggestion_and_accepting_creates_a_captain_term(tmp_path):
    lib = make_lib(tmp_path)
    a = add(lib, "thing")
    lib.add_terms(a, [{"facet": "piece_type", "label": "helmet"}, {"facet": "piece_type", "label": "chest"}], by="model")
    out = C.confirm_terms(lib, a, [{"facet": "piece_type", "label": "helmet", "accept": True}, {"facet": "piece_type", "label": "chest", "accept": False}], by="captain")
    assert out["accepted"] == 1 and out["rejected"] == 1
    assert {(t["label"], t["by"]) for t in lib.get(a)["terms"]} == {("helmet", "captain")}      # the rejected proposal is gone
    lib.add_terms(a, [{"facet": "piece_type", "label": "chest"}], by="model")                    # the model suggests it again later
    assert {(t["label"], t["by"]) for t in lib.get(a)["terms"]} == {("helmet", "captain")}      # suppressed: a rejection is remembered


def test_agents_may_not_confirm_terms(tmp_path):
    lib = make_lib(tmp_path)
    a = add(lib, "thing")
    with pytest.raises(LibraryError, match="user's"):
        C.confirm_terms(lib, a, [{"facet": "piece_type", "label": "helmet", "accept": True}], by="agent:w1")


def test_an_agent_decision_cannot_claim_to_be_the_users(tmp_path):
    lib = make_lib(tmp_path)
    a = add(lib, "thing")
    with pytest.raises(LibraryError, match="decisions as the user"):
        C.decide(lib, "seed_pick", "x", asset_ids=[a], decider="captain", origin="agent")
    assert C.decide(lib, "seed_pick", "x", asset_ids=[a], decider="model", origin="agent")["ok"]


def test_a_smart_collection_has_no_items_to_edit(tmp_path):
    lib = make_lib(tmp_path)
    a = add(lib, "greave one")
    smart = C.collect(lib, "create", name="g", kind="smart", query={"text": "greave"})["collection"]["id"]
    with pytest.raises(LibraryError, match="live query"):
        C.collect(lib, "add", collection=smart, asset_ids=[a])
