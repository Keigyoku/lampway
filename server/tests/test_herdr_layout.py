# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The herdr view (docs/reports/agent-modes-spec.md A4): one unit, one tab, minimal switching.

* A unit is one Lampway scene tab's conversation, keyed by its scene session id. Its main agent's pane opens in a tab of its own,
  labelled with the scene tab's name (else a short id).
* A swarm worker's pane splits into its unit's tab: the first worker right of the main agent (herdr's ratio is the share the split
  pane KEEPS, measured on herdr 0.9.3: 0.6 leaves the main agent 60 %), each further worker
  down from the last worker pane. A unit with no main pane yet gets one tab for its workers.
* A pane with no unit (an ad-hoc pane the user starts from the cockpit) keeps its own tab.
* Every pane Lampway starts reports what it is (``pane.report_metadata``); a failure to report never fails a start.
* The record of each pane names its ``unit`` and ``role``, so a reconcile after a restart re-adopts the layout; it never closes a
  pane (law 5).

herdr is played (``herdr_support.PaneHerdr``), as strict about its options as herdr 0.9.3; ``test_herdr_layout_live.py`` drives the
real binary."""
import logging
import threading

import pytest

from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L

from .herdr_support import PaneHerdr

PANE_URL = "http://127.0.0.1:8787/api/v1/mcp/pane"
SCENE = "6f1c2a52-3c1e-4c55-9d7e-2b0f6c1d9a10"
OTHER = "0b7d9e14-55aa-4c2e-8d3f-9a1b2c3d4e5f"


@pytest.fixture
def herdr(monkeypatch):
    fake = PaneHerdr()
    monkeypatch.setattr(L, "run", fake)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    monkeypatch.setenv("LAMPWAY_MCP_LAUNCHER", "/opt/lw/connector/lampway-mcp")
    return fake


@pytest.fixture
def cockpit(tmp_path, herdr):
    (tmp_path / "proj").mkdir()
    c = H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path / "proj"))
    c.pane_mcp_url = PANE_URL
    return c


def adhoc(cockpit, name="Scratch audit pane"):
    return cockpit.create_session("claude", name, cockpit.project_root, by="user")


def main(cockpit, scene=SCENE, label="Chest fit"):
    return cockpit.create_session("claude", "Claude Code for a scene tab", cockpit.project_root, task="fit the chest plate", by="user",
                                  scene_session_id=scene, unit_label=label)


def worker(cockpit, n, unit=SCENE, swarm="sw1", task="boots", planned=None):
    return cockpit.create_session("claude", f"{task} ({swarm} worker-{n})", cockpit.project_root,
                                  task=f"{task}: model the {task} piece and name it {task}_part", by="swarm",
                                  prompt=f"You are worker-{n}. Model the {task}.", swarm_worker=(f"swarm:{swarm}:worker-{n}", f"tok-{n}"),
                                  unit=unit, display_agent=f"Worker {n} · {task}", planned=planned)


def test_an_adhoc_pane_keeps_a_tab_of_its_own_and_reports_what_it_is(cockpit, herdr):
    one, two = adhoc(cockpit), adhoc(cockpit, "Second scratch pane")
    assert [m["args"][:2] for m in herdr.made()] == [["workspace", "create"], ["tab", "create"]]
    assert herdr.splits == {}
    assert two["pane_id"] in herdr.metadata, "every pane Lampway starts reports what it is"
    meta = herdr.metadata[two["pane_id"]]
    assert meta["source"] == "lampway" and meta["agent"] == "claude" and meta["display_agent"] and meta["title"] == "Second scratch pane"
    assert one["tab_id"] != two["tab_id"] and one["unit"] is None and one["role"] is None


def test_one_unit_one_tab_labelled_with_its_scene_tab(cockpit, herdr):
    adhoc(cockpit)
    a, b = main(cockpit), main(cockpit, OTHER, label=None)
    assert {a["tab_id"], b["tab_id"]} == {"tab2", "tab3"} and herdr.splits == {}
    assert herdr.tabs[a["tab_id"]]["label"] == "Chest fit"
    assert herdr.tabs[b["tab_id"]]["label"] == OTHER[:8], "no scene name known: a short id"
    assert (a["unit"], a["role"], a["unit_label"]) == (SCENE, "main", "Chest fit")
    assert (b["unit"], b["role"]) == (OTHER, "main")
    meta = herdr.metadata[a["pane_id"]]
    assert meta["display_agent"] == "Lampway · Chest fit" and meta["title"] == "fit the chest plate"
    assert isinstance(meta["state_labels"], dict) and meta["state_labels"]


def test_workers_split_into_their_units_tab_in_order(cockpit, herdr):
    adhoc(cockpit)
    root = main(cockpit)
    elsewhere = main(cockpit, OTHER, label="Boots")
    tabs_before = len(herdr.tabs)
    w1, w2, w3 = worker(cockpit, 1), worker(cockpit, 2, task="belt"), worker(cockpit, 3, task="gloves")
    assert len(herdr.tabs) == tabs_before, "a worker never opens a tab of its own while its unit has one"
    assert herdr.splits[w1["pane_id"]] == {"of": root["pane_id"], "direction": "right", "ratio": 0.6}, "the main agent keeps 60 %"
    assert herdr.splits[w2["pane_id"]]["of"] == w1["pane_id"] and herdr.splits[w2["pane_id"]]["direction"] == "down"
    assert herdr.splits[w3["pane_id"]]["of"] == w2["pane_id"] and herdr.splits[w3["pane_id"]]["direction"] == "down"
    assert herdr.tabs[root["tab_id"]]["panes"] == [root["pane_id"], w1["pane_id"], w2["pane_id"], w3["pane_id"]]
    assert herdr.tabs[elsewhere["tab_id"]]["panes"] == [elsewhere["pane_id"]], "another unit's tab is left alone"
    for n, w in enumerate((w1, w2, w3), 1):
        assert (w["unit"], w["role"], w["tab_id"]) == (SCENE, "worker", root["tab_id"])
        assert w["scene_session_id"] is None, "a worker is in its unit's tab, never bound to the scene tab"
        assert "HOME" in herdr.env_of(w["pane_id"]), "a split pane gets the same environment a tab's pane does"
    assert herdr.metadata[w2["pane_id"]]["display_agent"] == "Worker 2 · belt"
    assert herdr.metadata[w2["pane_id"]]["title"].startswith("belt: model the belt piece")
    w4 = worker(cockpit, 1, swarm="sw2", task="cape")                    # the unit's next swarm: down the same column
    assert herdr.splits[w4["pane_id"]] == {"of": w3["pane_id"], "direction": "down", "ratio": 0.5}
    assert herdr.closed() == [], "a finished run's worker panes stay as they are (Q13 is not decided)"


def test_a_swarm_that_says_how_many_workers_it_has_gets_an_even_column(cockpit, herdr):
    """Each split keeps 1/(the workers still to come) for the pane it splits, so every worker ends with the same share: 1/3 each."""
    root = main(cockpit)
    w1, w2, w3 = (worker(cockpit, n, task=t, planned=3) for n, t in ((1, "boots"), (2, "belt"), (3, "gloves")))
    assert herdr.splits[w1["pane_id"]] == {"of": root["pane_id"], "direction": "right", "ratio": 0.6}
    assert herdr.splits[w2["pane_id"]]["of"] == w1["pane_id"] and herdr.splits[w2["pane_id"]]["ratio"] == pytest.approx(1 / 3, abs=1e-4)
    assert herdr.splits[w3["pane_id"]]["of"] == w2["pane_id"] and herdr.splits[w3["pane_id"]]["ratio"] == pytest.approx(1 / 2, abs=1e-4)
    w4 = worker(cockpit, 1, swarm="sw2", task="cape", planned=2)        # the unit's next swarm: its first worker halves the column's last
    assert herdr.splits[w4["pane_id"]] == {"of": w3["pane_id"], "direction": "down", "ratio": 0.5}
    w5 = worker(cockpit, 2, swarm="sw2", task="hood", planned=2)
    assert herdr.splits[w5["pane_id"]]["ratio"] == pytest.approx(1 / 2, abs=1e-4)


def test_workers_opened_at_once_still_stand_in_one_column(cockpit, herdr):
    """A swarm opens its workers' panes at the same time (one thread each): each must find the one placed before it."""
    adhoc(cockpit)
    root = main(cockpit)
    made = []
    threads = [threading.Thread(target=lambda n=n: made.append(worker(cockpit, n))) for n in range(1, 5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert len(made) == 4 and {w["tab_id"] for w in made} == {root["tab_id"]}
    split = [herdr.splits[w["pane_id"]] for w in made]
    assert [s["direction"] for s in split].count("right") == 1 and next(s for s in split if s["direction"] == "right")["of"] == root["pane_id"]
    assert len({s["of"] for s in split}) == 4, "a chain down one column, never two panes split from the same one"


def test_a_unit_with_no_main_pane_gets_one_tab_for_its_workers(cockpit, herdr):
    adhoc(cockpit)
    w1, w2 = worker(cockpit, 1), worker(cockpit, 2, task="belt")
    assert w1["tab_id"] == w2["tab_id"] and herdr.tabs[w1["tab_id"]]["label"] == SCENE[:8]
    assert w1["pane_id"] not in herdr.splits and herdr.splits[w2["pane_id"]] == {"of": w1["pane_id"], "direction": "down", "ratio": 0.5}


def test_a_failure_to_report_metadata_never_fails_a_start(cockpit, herdr, caplog):
    herdr.fail.add("report-metadata")
    adhoc(cockpit)
    with caplog.at_level(logging.WARNING, logger="lampway.herdr"):
        root = main(cockpit)
        w1 = worker(cockpit, 1)
    assert root["state"] == "live" and w1["state"] == "live" and herdr.metadata == {}
    assert herdr.splits[w1["pane_id"]]["of"] == root["pane_id"]
    assert [r for r in caplog.records if "metadata" in r.getMessage()], "the failure is logged"


def test_a_herdr_that_cannot_split_still_starts_the_worker_in_a_tab(cockpit, herdr, caplog):
    herdr.fail.add("split")
    adhoc(cockpit)
    root = main(cockpit)
    with caplog.at_level(logging.WARNING, logger="lampway.herdr"):
        w1 = worker(cockpit, 1)
    assert w1["state"] == "live" and w1["tab_id"] != root["tab_id"] and (w1["unit"], w1["role"]) == (SCENE, "worker")
    assert [r for r in caplog.records if "split" in r.getMessage()]


def test_reconcile_re_adopts_unit_and_role_and_the_next_worker_finds_its_column(cockpit, herdr, tmp_path):
    adhoc(cockpit)
    root = main(cockpit)
    w1, w2 = worker(cockpit, 1), worker(cockpit, 2, task="belt")
    moved = herdr.renumber()                                             # herdr kept the panes; their ids changed
    herdr.tabs[root["tab_id"]]["panes"].append("q99")                    # a pane the user split by hand: not Lampway's
    herdr.panes["q99"] = {"terminal_id": "t99", "cmd": "-bash", "tab_id": root["tab_id"]}
    restarted = H.Cockpit(cockpit.root, project_root=cockpit.project_root)   # the Lampway server restarted
    restarted.pane_mcp_url = PANE_URL
    out = restarted.reconcile()
    recs = {r["id"]: r for r in restarted.list_sessions()}
    assert (recs[root["id"]]["pane_id"], recs[root["id"]]["role"], recs[root["id"]]["unit"]) == (moved[root["pane_id"]], "main", SCENE)
    assert [(recs[w["id"]]["pane_id"], recs[w["id"]]["role"]) for w in (w1, w2)] == [(moved[w1["pane_id"]], "worker"), (moved[w2["pane_id"]], "worker")]
    assert out["units"][SCENE] == {"tab_id": root["tab_id"], "main": [root["id"]], "workers": [w1["id"], w2["id"]]}
    assert "q99" in out["unadopted"] and herdr.closed() == [] and "q99" in herdr.panes, "an unknown pane is never closed (law 5)"
    w3 = worker(restarted, 3, task="gloves")
    assert herdr.splits[w3["pane_id"]] == {"of": moved[w2["pane_id"]], "direction": "down", "ratio": 0.5}


def test_binding_a_pane_makes_it_its_units_main_and_unbinding_lets_it_go_without_touching_it(cockpit, herdr):
    pane = adhoc(cockpit)
    bound = cockpit.bind(pane["id"], SCENE)
    assert (bound["unit"], bound["role"]) == (SCENE, "main")
    w1 = worker(cockpit, 1)
    assert herdr.splits[w1["pane_id"]] == {"of": pane["pane_id"], "direction": "right", "ratio": 0.6}
    before = len(herdr.calls)
    out = cockpit.unbind(pane["id"])
    assert (out["unit"], out["role"]) == (None, None) and len(herdr.calls) == before, "unbinding never touches a pane"
