"""decisions_model: a small judge that picks ONE of a closed set of options (flagged-frame review, caption triage).
The eligible-model list is computed live; private content only goes to ZDR endpoints with data_collection=deny, never to ':free'.
Fake transport, no network. Provider response shapes are [UNVERIFIED] until a live key run."""
import json

import httpx
import pytest

from lampway_server import decisions_model as D

KEY = "sk-or-v1-" + "cd34" * 16
MODELS = {"data": [{"id": i} for i in ("inception/mercury-decide:free", "cloudflare/clef", "liquid/d1", "upstage/solar-decide", "other/x")]}
ZDR = {"data": [{"model_id": "cloudflare/clef"}, {"model_id": "inception/mercury-decide:free"}, {"model_id": "other/x"}]}


def fake(answer=None, seen=None):
    def handler(req: httpx.Request):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELS)
        if req.url.path.endswith("/endpoints/zdr"):
            return httpx.Response(200, json=ZDR)
        body = json.loads(req.content)
        if seen is not None:
            seen.append(body)
        choice = answer(body) if callable(answer) else (answer or "keep")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"choice": choice, "reason": "r"})}}],
                                         "usage": {"cost": 0.001}})
    return httpx.MockTransport(handler)


def test_private_content_is_limited_to_live_zdr_and_never_free():
    d = D.Decider(KEY, transport=fake())
    assert d.eligible("private") == ["cloudflare/clef"]          # in ZDR, a candidate, not :free


def test_public_content_may_use_free_and_needs_no_zdr():
    d = D.Decider(KEY, transport=fake())
    got = d.eligible("public")
    assert "inception/mercury-decide:free" in got and "liquid/d1" in got and "other/x" not in got


def test_the_list_is_live_not_hardcoded():
    global ZDR
    old = ZDR
    ZDR = {"data": [{"model_id": "liquid/d1"}]}
    try:
        assert D.Decider(KEY, transport=fake()).eligible("private") == ["liquid/d1"]
    finally:
        ZDR = old


def test_a_private_request_carries_zdr_and_data_collection_deny():
    seen = []
    r = D.Decider(KEY, transport=fake(seen=seen)).decide("keep or drop?", ["keep", "drop"], "private")
    assert r["choice"] == "keep" and r["model"] == "cloudflare/clef"
    assert seen[0]["provider"] == {"zdr": True, "data_collection": "deny"}
    assert seen[0]["model"] == "cloudflare/clef"


def test_private_with_no_zdr_endpoint_is_refused_and_nothing_is_sent():
    global ZDR
    old = ZDR
    ZDR = {"data": []}
    seen = []
    try:
        r = D.Decider(KEY, transport=fake(seen=seen)).decide("q", ["a", "b"], "private")
    finally:
        ZDR = old
    assert r["choice"] is None and "ZDR" in r["refused"] and seen == []


def test_an_answer_outside_the_options_is_not_a_decision():
    r = D.Decider(KEY, transport=fake("maybe")).decide("q", ["keep", "drop"], "public")
    assert r["choice"] is None and "outside" in r["refused"]


def test_the_key_never_appears_in_a_result():
    assert KEY not in json.dumps(D.Decider(KEY, transport=fake()).decide("q", ["keep", "drop"], "public"))


def test_eval_scores_each_candidate_against_goldens(tmp_path):
    goldens = [{"question": "q1", "options": ["keep", "drop"], "expected": "drop"},
               {"question": "q2", "options": ["keep", "drop"], "expected": "keep"}]
    d = D.Decider(KEY, transport=fake(lambda b: "drop" if "q1" in b["messages"][-1]["content"] else "keep"))
    rep = D.evaluate(d, goldens, "public")
    assert rep["models"]["liquid/d1"] == {"correct": 2, "total": 2, "accuracy": 1.0}
    bad = D.evaluate(D.Decider(KEY, transport=fake("keep")), goldens, "public")
    assert bad["models"]["liquid/d1"]["accuracy"] == 0.5


def test_shipped_goldens_load_and_are_well_formed():
    g = D.load_goldens()
    assert len(g) >= 6
    for row in g:
        assert row["expected"] in row["options"] and row["question"]
