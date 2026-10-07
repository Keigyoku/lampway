# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The captain's rulings of 2026-10-07.

Ruling 3: the egress private rule refuses by default; it lets private content through only when the user has granted the CH1
acknowledgement (dated, revocable, per option) to the option the call declares - and only to that option's own route. CH1's first-release
observe-only mode stays where a call asks for it.

Ruling 4: OpenRouter ``:free`` models take NON-private inputs only. Private content is never sent to a ``:free`` model: not with an
acknowledgement, not in observe-only mode, not when the model arrives in the request body rather than a declared option. The resolver
skips a ``:free`` option for a private job on the same terms, so a resolution never picks what the gate will refuse."""

import json

import httpx
import pytest

from lampway_server import choices as CH
from lampway_server import egress as E
from lampway_server.choices import resolver as CR
from lampway_server.choices.snapshot import World

TRIPO = "studio:tripo.image"
FREE = "openrouter:nvidia/nemotron-3-embed-1b:free"
DECIDE_FREE = "openrouter:inception/mercury-decide:free"
CLEF = "openrouter:cloudflare/clef"
ZDR = {"zdr": True, "data_collection": "deny"}


@pytest.fixture
def strict(tmp_path):
    eg = E.Egress(tmp_path / "eg")
    for r in ("openrouter", "studio:tripo", "studio:meshy"):
        eg.set_route(r, True)
    E.set_active(eg)
    return eg


def _send(eg, route, **ctx):
    with E.context(**ctx):
        r = eg.begin(route, "POST", 10, explicit_route=route)
    eg.end(r)
    return [x for x in eg.log() if x.get("event") == "send"][-1]


# ------------------------------------------------------------------------------------------------ ruling 3
def test_private_content_to_an_unread_route_is_refused_by_default(strict):
    with pytest.raises(E.EgressRefused):
        _send(strict, "studio:tripo", content_class="private", option=TRIPO)
    assert strict.log()[-1]["event"] == "refused" and strict.log()[-1]["reason"] == "private content"


def test_the_users_acknowledgement_of_that_option_lets_it_through_and_is_logged(strict):
    at = CH.active_store().acknowledge(TRIPO, True, by="user")
    row = _send(strict, "studio:tripo", content_class="private", option=TRIPO)
    assert at and row["acknowledged"] == {"option": TRIPO, "at": at} and "would_refuse_private" not in row


def test_revoking_the_acknowledgement_refuses_again(strict):
    CH.active_store().acknowledge(TRIPO, True, by="user")
    _send(strict, "studio:tripo", content_class="private", option=TRIPO)
    CH.active_store().acknowledge(TRIPO, False, by="user")
    with pytest.raises(E.EgressRefused):
        _send(strict, "studio:tripo", content_class="private", option=TRIPO)


def test_an_acknowledgement_unlocks_only_its_own_option_on_its_own_route(strict):
    CH.active_store().acknowledge(TRIPO, True, by="user")
    with pytest.raises(E.EgressRefused):                                   # no option declared: nothing to match the grant to
        _send(strict, "studio:tripo", content_class="private")
    with pytest.raises(E.EgressRefused):                                   # the option is Tripo's; the bytes are going to Meshy
        _send(strict, "studio:meshy", content_class="private", option=TRIPO)


def test_observe_only_still_records_and_sends_where_a_call_asks_for_it(strict):
    row = _send(strict, "studio:tripo", content_class="private", option=TRIPO, observe_private=True)
    assert row["would_refuse_private"] is True and "acknowledged" not in row


def test_a_resolution_declares_its_option_to_the_gate():
    r = CR.Resolution(purpose="image.plates", option=TRIPO, params={}, scope="global", reason="preferred", why="", skipped=[],
                      content_class="private", needs_click=False, would_refuse_private=False, doc_version="v1", world={})
    assert r.egress_context()["option"] == TRIPO


# ------------------------------------------------------------------------------------------------ ruling 4
def test_private_content_never_goes_to_a_free_model(strict):
    CH.active_store().acknowledge(FREE, True, by="user")
    for observe in (False, True):
        with pytest.raises(E.EgressRefused, match=":free"):
            _send(strict, "openrouter", content_class="private", option=FREE, constraints=ZDR, observe_private=observe)
    assert strict.log()[-1]["reason"] == "private content to a :free model"


def test_non_private_content_may_go_to_a_free_model(strict):
    for cls in ("public", "synthetic"):
        assert _send(strict, "openrouter", content_class=cls, option=FREE)["route"] == "openrouter"


def test_the_model_in_the_request_body_is_checked_too(strict):
    E.install()
    seen = []
    transport = httpx.MockTransport(lambda req: seen.append(req) or httpx.Response(200, json={}))
    body = {"model": "nvidia/nemotron-3-embed-1b:free", "input": "x"}
    with httpx.Client(transport=transport) as c:
        with E.context(content_class="private", constraints=ZDR):
            with pytest.raises(E.EgressRefused, match=":free"):
                c.post("https://openrouter.ai/api/v1/embeddings", content=json.dumps(body), headers={"content-type": "application/json"})
        assert seen == []
        with E.context(content_class="public"):
            c.post("https://openrouter.ai/api/v1/embeddings", content=json.dumps(body), headers={"content-type": "application/json"})
        assert len(seen) == 1


def _world(enforce):
    return World(connections={"openrouter": "connected"}, routes={"openrouter": True},
                 zdr=frozenset({"inception/mercury-decide:free", "cloudflare/clef"}), enforce_private=enforce)


def _doc():
    return {"shipped": {}, "global": {"agent.decide": {"preferred": DECIDE_FREE, "fallbacks": [CLEF]}}, "project": {}, "env": {},
            "acknowledgements": {DECIDE_FREE: {"private": True, "at": "2026-10-07T00:00:00Z"}}, "version": "v1"}


@pytest.mark.parametrize("enforce", [True, False])
def test_the_resolver_skips_a_free_option_for_a_private_job_even_when_acknowledged(enforce):
    r = CR.resolve("agent.decide", CR.Job(content_class="private"), _world(enforce), _doc())
    assert r.option == CLEF and any(s.get("option") == DECIDE_FREE and s.get("constraint") == "privacy" for s in r.skipped), r.skipped


def test_the_resolver_picks_a_free_option_for_a_public_job():
    assert CR.resolve("agent.decide", CR.Job(content_class="public"), _world(True), _doc()).option == DECIDE_FREE
