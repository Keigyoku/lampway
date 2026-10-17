# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_store.md tests 4, 7, 9 and 11, the write rules of section 4.2 and the routes of 4.1: the store holds ids, model names, numbers and
short texts - never a credential; only the user's click writes; a crash keeps the old file and an unreadable one is set aside; a choice
whose connection is missing is accepted with a note; the Providers dialog's saved values and the environment show as scopes."""

import json

import pytest

from lampway_server.choices import store as CS

FLARE = "openrouter:openai/gpt-image-2.5-flare"
RIVER = "openrouter:sourceful/riverflow-v2.5-pro"
KEY = "sk-" "or-v1-FAKE-CHOICE-SENTINEL-0000000000000"


@pytest.fixture(params=["memory", "file"])
def store(request, tmp_path):
    return CS.MemoryStore() if request.param == "memory" else CS.FileStore(tmp_path / "state")


def test_set_and_read_back_a_global_and_a_project_choice(store, tmp_path):
    store.set("image.plates", "global", None, {"preferred": FLARE, "fallbacks": [RIVER], "params": {"size": "2880x2880"}}, by="user")
    store.set("image.plates", "project", str(tmp_path / "proj"), {"preferred": RIVER}, by="user")
    assert store.global_doc()["purposes"]["image.plates"]["preferred"] == FLARE
    assert store.project_doc(str(tmp_path / "proj"))["purposes"]["image.plates"]["preferred"] == RIVER
    store.clear("image.plates", str(tmp_path / "proj"), by="user")
    assert "image.plates" not in store.project_doc(str(tmp_path / "proj"))["purposes"]


@pytest.mark.parametrize("entry,text", [
    ({"preferred": "studio:nope.action"}, "studio:nope.action is not an option for image.plates: its options are "),
    ({"preferred": FLARE, "fallbacks": [FLARE]}, "a fallback cannot repeat the preferred option or another fallback"),
    ({"preferred": FLARE, "fallbacks": [RIVER] * 2}, "a fallback cannot repeat the preferred option or another fallback"),
    ({"preferred": FLARE, "params": {"size": KEY}}, "a choice never holds a credential: Connections does"),
])
def test_bad_writes_are_refused_and_change_nothing(store, entry, text):
    before = json.dumps(store.global_doc(), sort_keys=True)
    with pytest.raises(CS.Refused) as exc:
        store.set("image.plates", "global", None, entry, by="user")
    assert str(exc.value).startswith(text)
    assert json.dumps(store.global_doc(), sort_keys=True) == before


def test_a_chain_longer_than_eight_is_refused(store):
    with pytest.raises(CS.Refused, match="at most 8"):
        store.set("3d.image_to_3d", "global", None, {"preferred": "local:visual_hull", "fallbacks": [
            "local:extrude", "local:relief", "studio:tripo.mesh", "studio:meshy.image_to_3d", "studio:hi3d.image_to_3d", "studio:hyper3d.generate",
            "studio:hyper3d.mcp.generate", "studio:tripo.rest.image_to_model"]}, by="user")


def test_agent_main_keeps_its_override_policy_none(store):
    with pytest.raises(CS.Refused, match="an agent must not change its own provider"):
        store.set("agent.main", "global", None, {"preferred": "anthropic:claude-sonnet-5-5", "override_policy": "chain"}, by="user")


def test_only_the_user_writes(store):
    for call in (lambda: store.set("image.plates", "global", None, {"preferred": FLARE}, by="agent"),
                 lambda: store.acknowledge("studio:tripo.image", True, by="agent"),
                 lambda: store.clear("image.plates", None, by="agent")):
        with pytest.raises(CS.Refused) as exc:
            call()
        assert str(exc.value) == "only your click in Choices can change a choice: an agent may propose one"


def test_no_secret_in_store(tmp_path):
    store = CS.FileStore(tmp_path / "state")
    for bad in ({"preferred": FLARE, "params": {"note": KEY}}, {"preferred": FLARE, "params": {"template": f"x {KEY}"}}):
        with pytest.raises(CS.Refused):
            store.set("image.plates", "global", None, bad, by="user")
    with pytest.raises(CS.Refused):
        store.propose("agent:s1", "image.plates", {"preferred": RIVER}, f"because {KEY}", [])
    for f in (tmp_path / "state").rglob("*"):
        if f.is_file():
            assert KEY not in f.read_text()


def test_crash_mid_write_keeps_the_old_file(tmp_path, monkeypatch):
    from lampway_server.connections import files as CF
    store = CS.FileStore(tmp_path / "state")
    store.set("image.plates", "global", None, {"preferred": FLARE}, by="user")
    before = (tmp_path / "state" / "choices.json").read_text()

    def boom(src, dst):
        raise KeyboardInterrupt("killed")
    monkeypatch.setattr(CF.os, "replace", boom)
    with pytest.raises(KeyboardInterrupt):
        store.set("image.plates", "global", None, {"preferred": RIVER}, by="user")
    monkeypatch.undo()
    assert (tmp_path / "state" / "choices.json").read_text() == before


def test_unparseable_store_is_set_aside(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "choices.json").write_text('{"purposes": {"image.pl')
    store = CS.FileStore(tmp_path / "state")
    doc = store.global_doc()
    assert doc["purposes"] == {} and doc.get("error", "").startswith("choices.json was unreadable and was set aside")
    assert list((tmp_path / "state").glob("choices.json.corrupt-*"))


def test_acknowledgements_are_dated_and_revocable(store):
    store.acknowledge("studio:tripo.image", True, by="user", at="2026-10-06T10:00:00Z")
    assert store.global_doc()["acknowledgements"]["studio:tripo.image"] == {"private": True, "at": "2026-10-06T10:00:00Z"}
    store.acknowledge("studio:tripo.image", False, by="user")
    assert "studio:tripo.image" not in store.global_doc()["acknowledgements"]


def test_proposals_change_nothing_until_the_user_accepts(store):
    store.set("image.plates", "global", None, {"preferred": FLARE}, by="user")
    version = store.global_doc()["version"]
    pid = store.propose("agent:s1", "image.plates", {"preferred": RIVER}, "rated higher over 6 runs", ["ledger:run-81"])
    assert store.global_doc()["version"] == version and store.proposals()[0]["state"] == "open"
    store.decide(pid, True, by="user")
    assert store.global_doc()["purposes"]["image.plates"]["preferred"] == RIVER
    assert store.proposals()[0]["state"] == "accepted"
    with pytest.raises(CS.Refused):
        store.decide(pid, True, by="agent")


def test_an_origin_may_keep_five_proposals_open(store):
    for i in range(5):
        store.propose("agent:s1", "image.plates", {"preferred": RIVER}, f"reason {i}", [])
    with pytest.raises(CS.Refused, match="5 proposals are waiting for the user already"):
        store.propose("agent:s1", "image.plates", {"preferred": RIVER}, "one more", [])
