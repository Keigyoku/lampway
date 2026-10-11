# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_store.md tests 1, 2, 3, 5, 6, 8, 12 and 13: the pure resolver. One answer for one job, world and document; the seven
constraints in their order with the first failure named; preferred, fallback and override; the private rule (enforced here; the first
release observes it, CH1); a refusal before anything is sent; the agents' override policy (CH3); scopes; the environment as a session
layer (CH4)."""

import json
import multiprocessing

import pytest

from lampway_server.choices import registry as REG
from lampway_server.choices import resolver as CR
from lampway_server.choices.snapshot import World

FLARE = "openrouter:openai/gpt-image-2.5-flare"
RIVER = "openrouter:sourceful/riverflow-v2.5-pro"
TRIPO = "studio:tripo.image"


def world(**kw):
    base = dict(connections={"openrouter": "connected", "studio:tripo": "connected", "chatgpt_plan": "connected", "claude_cli": "not_checked"},
                routes={"openrouter": True, "studio:tripo": True, "chatgpt_plan": True, "claude_plan": True},
                zdr=frozenset({"openai/gpt-image-2.5-flare"}), enforce_private=True)
    base.update(kw)
    return World(**base)


def doc(**layers):
    d = {"shipped": {}, "global": {}, "project": {}, "env": {}, "acknowledgements": {}, "version": "v1"}
    d.update(layers)
    return d


PLATES = {"image.plates": {"preferred": TRIPO, "fallbacks": [FLARE, RIVER], "params": {"size": "2880x2880"}}}


# ------------------------------------------------------------------------------------------------ 1
def test_resolution_is_deterministic():
    w, d = world(), doc(**{"global": PLATES})
    first = json.dumps(CR.resolve("image.plates", CR.Job(content_class="public"), w, d).record(), sort_keys=True)
    for _ in range(100):
        assert json.dumps(CR.resolve("image.plates", CR.Job(content_class="public"), w, d).record(), sort_keys=True) == first


def _child(q):
    q.put(json.dumps(CR.resolve("image.plates", CR.Job(content_class="public"), world(), doc(**{"global": PLATES})).record(), sort_keys=True))


def test_resolution_is_the_same_in_another_process():
    ctx = multiprocessing.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_child, args=(q,))
    p.start()
    other = q.get(timeout=60)
    p.join(30)
    assert other == json.dumps(CR.resolve("image.plates", CR.Job(content_class="public"), world(), doc(**{"global": PLATES})).record(), sort_keys=True)


# ------------------------------------------------------------------------------------------------ 2, 3
def test_constraint_order_names_the_first_failure():
    w = world(connections={"openrouter": "connected", "studio:tripo": "missing"})
    r = CR.resolve("image.plates", CR.Job(content_class="private"), w, doc(**{"global": PLATES}))
    skipped = {s["option"]: s["constraint"] for s in r.skipped}
    assert skipped[TRIPO] == "privacy", "private-incompatible AND unconnected: privacy comes first"


def test_preferred_fallback_override_reasons():
    d = doc(**{"global": PLATES})
    r = CR.resolve("image.plates", CR.Job(content_class="public"), world(), d)
    assert (r.option, r.reason, r.scope) == (TRIPO, "preferred", "global")
    r = CR.resolve("image.plates", CR.Job(content_class="public"), world(routes={"openrouter": True, "studio:tripo": False}), d)
    assert (r.option, r.reason) == (FLARE, "fallback")
    assert r.why == "fallback: studio:tripo.image: studio:tripo is off: switch it on in Privacy"
    r = CR.resolve("image.plates", CR.Job(content_class="public", override=RIVER, origin="agent"), world(), d)
    assert (r.option, r.reason) == (RIVER, "override")
    assert r.params == {"size": "2880x2880"}


# ------------------------------------------------------------------------------------------------ 5: the private rule (enforced)
def test_private_job_never_resolves_to_unknown_retention():
    d = doc(**{"global": {"image.plates": {"preferred": TRIPO, "fallbacks": [FLARE]}}})
    r = CR.resolve("image.plates", CR.Job(content_class="private"), world(), d)
    assert r.option == FLARE and r.skipped[0]["constraint"] == "privacy"
    assert r.skipped[0]["text"] == "private content: studio:tripo.image keeps what it receives (unknown): pick a local or ZDR option"
    d["acknowledgements"] = {TRIPO: {"private": True, "at": "2026-10-06"}}
    assert CR.resolve("image.plates", CR.Job(content_class="private"), world(), d).option == TRIPO
    d2 = doc(**{"global": {"image.plates": {"preferred": RIVER, "fallbacks": ["openrouter:google/gemini-3.1-flash-image"]}}})
    with pytest.raises(CR.NoChoice):
        CR.resolve("image.plates", CR.Job(content_class="private"), world(), d2)        # neither is on the ZDR list
    d3 = doc(**{"global": {"agent.decide": {"preferred": "openrouter:inception/mercury-decide:free"}}})
    w = world(zdr=frozenset({"inception/mercury-decide:free"}))
    with pytest.raises(CR.NoChoice) as exc:
        CR.resolve("agent.decide", CR.Job(content_class="private"), w, d3)              # a :free model is never ZDR
    assert "privacy" in json.dumps(exc.value.skipped)


def test_the_first_release_observes_the_private_rule_and_refuses_nothing():
    d = doc(**{"global": {"image.plates": {"preferred": TRIPO, "fallbacks": [FLARE]}}})
    r = CR.resolve("image.plates", CR.Job(content_class="private"), world(enforce_private=False), d)
    assert r.option == TRIPO and r.would_refuse_private is True and r.record()["would_refuse_private"] is True


# ------------------------------------------------------------------------------------------------ 6
def test_nothing_passes_refuses_with_every_candidate_and_the_first_fix():
    w = world(routes={"openrouter": False, "studio:tripo": False})
    with pytest.raises(CR.NoChoice) as exc:
        CR.resolve("image.plates", CR.Job(content_class="public"), w, doc(**{"global": PLATES}))
    e = exc.value
    assert [s["option"] for s in e.skipped] == [TRIPO, FLARE, RIVER]
    assert e.fix == "studio:tripo is off: switch it on in Privacy" and e.needs_choice == "image.plates"
    assert str(e).startswith("nothing can serve Plates now:")


def test_a_purpose_with_no_choice_says_so():
    with pytest.raises(CR.NoChoice) as exc:
        CR.resolve("track.body_3d", CR.Job(), world(), doc())
    assert str(exc.value) == "no choice is set for Video to body motion yet: choose one in Choices"


# ------------------------------------------------------------------------------------------------ 8: CH3
def test_agent_override_policy():
    d = doc(**{"global": PLATES})
    with pytest.raises(CR.NoChoice) as exc:
        CR.resolve("image.plates", CR.Job(content_class="public", override="openrouter:google/gemini-3.1-flash-image", origin="agent"), world(), d)
    assert str(exc.value) == "openrouter:google/gemini-3.1-flash-image is not one of your choices for image.plates: propose it with lampway_choices"
    assert CR.resolve("image.plates", CR.Job(content_class="public", override="openrouter:google/gemini-3.1-flash-image", origin="user"),
                      world(), d).reason == "override", "the user's own per-job override is always allowed"
    dm = doc(**{"global": {"agent.main": {"preferred": "chatgpt_plan:gpt-6.1-sol", "fallbacks": ["anthropic:claude-sonnet-5-5"]}}})
    with pytest.raises(CR.NoChoice, match="an agent must not change its own provider"):
        CR.resolve("agent.main", CR.Job(override="anthropic:claude-sonnet-5-5", origin="agent"), world(), dm)
    dr = doc(**{"global": {"3d.retopo": {"preferred": "local:quadriflow", "fallbacks": ["studio:meshy.remesh"]}}})
    assert CR.resolve("3d.retopo", CR.Job(override="local:voxel", origin="agent"), world(), dr).option == "local:voxel"
    dr2 = doc(**{"global": {"3d.retopo": {"preferred": "local:quadriflow"}}})
    with pytest.raises(CR.NoChoice):
        CR.resolve("3d.retopo", CR.Job(override="studio:meshy.remesh", origin="agent"), world(), dr2)


# ------------------------------------------------------------------------------------------------ 12, 13
def test_project_scope_is_a_whole_chain():
    d = doc(**{"global": PLATES, "project": {"image.plates": {"preferred": RIVER, "params": {"quality": "high"}}}})
    r = CR.resolve("image.plates", CR.Job(content_class="public"), world(routes={"openrouter": True, "studio:tripo": True}), d)
    assert (r.option, r.scope) == (RIVER, "project")
    assert r.params == {"size": "2880x2880", "quality": "high"}, "params merge per key, most specific first"
    w = world(routes={"openrouter": False, "studio:tripo": True})
    with pytest.raises(CR.NoChoice) as exc:                     # the project chain does not fall through to the global one
        CR.resolve("image.plates", CR.Job(content_class="public"), w, d)
    assert [s["option"] for s in exc.value.skipped] == [RIVER]


def test_environment_is_a_session_layer():
    d = doc(**{"global": {"agent.main": {"preferred": "chatgpt_plan:gpt-6.1-sol"}},
               "env": {"agent.main": {"preferred": "openrouter:anthropic/claude-sonnet-5.5", "source": "LAMPWAY_PROVIDER"}}})
    r = CR.resolve("agent.main", CR.Job(content_class="public"), world(), d)
    assert (r.option, r.scope) == ("openrouter:anthropic/claude-sonnet-5.5", "env")
    del d["env"]["agent.main"]
    assert CR.resolve("agent.main", CR.Job(content_class="public"), world(), d).option == "chatgpt_plan:gpt-6.1-sol"


def test_follow_resolves_through_the_purpose_it_names():
    d = doc(**{"global": {"agent.main": {"preferred": "chatgpt_plan:gpt-6.1-sol"}}, "shipped": {"agent.material_script": {"preferred": "follow:agent.main"}}})
    r = CR.resolve("agent.material_script", CR.Job(content_class="public"), world(), d)
    assert r.option == "chatgpt_plan:gpt-6.1-sol" and r.record()["followed"] == "agent.main"


def test_the_registry_has_every_purpose_and_the_normalization_judge():
    assert len(REG.PURPOSES) == 57 and "normalize.judge" in REG.PURPOSES and "agent.worker_mode" in REG.PURPOSES
    assert {p.group for p in REG.PURPOSES.values()} == {g for g, _ in REG.GROUPS}
    for p in REG.PURPOSES.values():
        assert set(p.default) <= set(p.options), p.id
