# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The herdr view (docs/reports/agent-modes-spec.md A4) against the REAL herdr binary: every command ``herdr/layout.py`` spells is
taken by a herdr server of Lampway's own, and the unit's tab comes out as the spec draws it: the main agent keeps the left 60 %, a
swarm that said its size stands in an even column beside it, and each pane carries the metadata herdr's sidebar shows.

Placement is decided by ``layout.place`` from the records it would have, exactly as ``Cockpit`` does; the panes are shells (a
harness pane needs that harness installed and its route on, which the played-herdr tests cover). Needs herdr (``LAMPWAY_HERDR_BIN``,
on PATH or ``~/.local/bin/herdr``): it SKIPS without it, and a skip is not a pass."""
import json
import time

from lampway_server.herdr import launcher as L
from lampway_server.herdr import layout as LY
from lampway_server.herdr.host import Cockpit

from .herdr_support import lroot, needs_herdr  # noqa: F401  (the isolated server root fixture)

SCENE = "6f1c2a52-3c1e-4c55-9d7e-2b0f6c1d9a10"


def _open(root, where, snap, cwd, label):
    ws = next((w for w in snap["workspaces"] if w.get("label") == LY.WORKSPACE_LABEL), None)
    if where.verb == "workspace":
        return LY.created_pane(L.run(root, LY.workspace_create(cwd, [])))
    if where.verb == "split":
        return LY.created_pane(L.run(root, LY.pane_split(where.of, where.direction, where.ratio, cwd, [])))
    return LY.created_pane(L.run(root, LY.tab_create(ws["workspace_id"], cwd, label, [])))


@needs_herdr
def test_a_unit_on_the_real_herdr_is_one_tab_the_main_agent_keeps_60_percent_and_three_workers_share_the_column(lroot, tmp_path):  # noqa: F811
    c = Cockpit(lroot)
    c.ensure_server()
    cwd = str(tmp_path)
    records = []

    def start(role, unit, label, swarm=None, planned=None, meta=None):
        snap = c.snapshot()
        pane = _open(lroot, LY.place(role, unit, label, records, snap, swarm=LY.swarm_of(swarm), planned=planned), snap, cwd, label)
        records.append({"pane_id": pane["pane_id"], "tab_id": pane.get("tab_id"), "unit": unit, "role": role, "state": "live",
                        "swarm_binding": swarm, "created_at": time.time() + len(records)})
        L.run(lroot, LY.pane_report_metadata(pane["pane_id"], meta))           # herdr refuses an option it does not know
        return pane

    LY.created_pane(L.run(lroot, LY.workspace_create(cwd, [])))                  # Lampway's workspace, as the first pane makes it
    main = start(LY.MAIN, SCENE, "Chest fit", meta=LY.metadata("claude", LY.MAIN, unit_name="Chest fit", name="main", task="fit it"))
    workers = [start(LY.WORKER, SCENE, "Chest fit", swarm=f"swarm:sw1:worker-{n}", planned=3,
                     meta=LY.metadata("claude", LY.WORKER, unit_name="Chest fit", name=f"w{n}", task=f"part {n}",
                                      display_agent=f"Worker {n} · part {n}")) for n in (1, 2, 3)]

    snap = c.snapshot()
    tab = next(t for t in snap["tabs"] if t["tab_id"] == main["tab_id"])
    assert tab.get("label") == "Chest fit", tab
    assert {w["tab_id"] for w in workers} == {main["tab_id"]}, "every worker is in its unit's tab"
    layout = json.loads(L.run(lroot, ["pane", "layout", "--pane", main["pane_id"]]))["result"]["layout"]
    rect = {p["pane_id"]: p["rect"] for p in layout["panes"]}
    width = layout["area"]["width"]
    assert abs(rect[main["pane_id"]]["width"] / width - LY.MAIN_SHARE) < 0.03, (rect, width)
    column = [rect[w["pane_id"]] for w in workers]
    assert len({r["x"] for r in column}) == 1, "the workers stand in one column right of the main agent"
    heights = [r["height"] for r in column]
    assert max(heights) - min(heights) <= 2, f"an even column: {heights}"


OTHER = "0b7d9e14-55aa-4c2e-8d3f-9a1b2c3d4e5f"


@needs_herdr
def test_on_the_real_herdr_a_units_next_swarm_closes_its_finished_worker_panes_and_splits_right_of_the_main_pane_again(lroot, tmp_path):  # noqa: F811
    """Spec A4, Q13 (built 2026-10-07) on a real herdr server: the previous run's finished worker panes of the unit are closed by
    ``Cockpit.close_ended_workers`` (and only they: the main pane, another unit's finished worker and a pane no record names stay),
    then the next swarm's first worker splits right of the main pane, which keeps 60 % again."""
    c = Cockpit(lroot)
    c.ensure_server()
    cwd = str(tmp_path)

    def record(pane, role, unit, swarm=None, by="user"):
        rec = {"id": f"r{len(c.list_sessions()) + 1}", "name": f"{role} {swarm or unit[:8]}", "agent": "shell", "pane_id": pane["pane_id"],
               "terminal_id": pane.get("terminal_id"), "tab_id": pane.get("tab_id"), "unit": unit, "role": role, "state": "live",
               "swarm_binding": swarm, "created_by": by, "match": [], "created_at": time.time() + len(c.list_sessions())}
        c._update(lambda d: d["sessions"].append(rec))
        return rec

    def start(role, unit, label, swarm=None, planned=None):
        snap = c.snapshot()
        pane = _open(lroot, LY.place(role, unit, label, c.list_sessions(), snap, swarm=LY.swarm_of(swarm), planned=planned), snap, cwd, label)
        return pane, record(pane, role, unit, swarm, by="swarm" if role == LY.WORKER else "user")

    LY.created_pane(L.run(lroot, LY.workspace_create(cwd, [])))
    main, _ = start(LY.MAIN, SCENE, "Chest fit")
    old = [start(LY.WORKER, SCENE, "Chest fit", swarm=f"swarm:sw1:worker-{n}", planned=2) for n in (1, 2)]
    _theirs_main, _ = start(LY.MAIN, OTHER, "Boots")
    theirs, _ = start(LY.WORKER, OTHER, "Boots", swarm="swarm:sw9:worker-1", planned=1)
    ws = next(w for w in c.snapshot()["workspaces"] if w.get("label") == LY.WORKSPACE_LABEL)
    unknown = LY.created_pane(L.run(lroot, LY.tab_create(ws["workspace_id"], cwd, "the user's own", [])))
    rect = {p["pane_id"]: p["rect"] for p in json.loads(L.run(lroot, ["pane", "layout", "--pane", main["pane_id"]]))["result"]["layout"]["panes"]}
    assert old[0][0]["pane_id"] in rect, "the first run's workers stand beside the main pane"

    closed = c.close_ended_workers(SCENE, lambda binding: False)                 # sw1 and sw9 finished: no live binding
    assert sorted(x["id"] for x in closed) == sorted(r["id"] for _, r in old)
    live = {p["pane_id"] for p in c.snapshot()["panes"]}
    assert not {p["pane_id"] for p, _ in old} & live, "the finished worker panes are gone from herdr"
    assert {main["pane_id"], theirs["pane_id"], unknown["pane_id"]} <= live, "never the main pane, another unit's or an unknown pane"
    assert {r["state"] for r in c.list_sessions() if r["id"] in {x["id"] for x in closed}} == {"ended"}

    where = LY.place(LY.WORKER, SCENE, "Chest fit", c.list_sessions(), c.snapshot(), swarm="sw2", planned=1)
    assert (where.verb, where.of, where.direction, where.ratio) == ("split", main["pane_id"], "right", LY.MAIN_SHARE)
    fresh, _ = start(LY.WORKER, SCENE, "Chest fit", swarm="swarm:sw2:worker-1", planned=1)
    layout = json.loads(L.run(lroot, ["pane", "layout", "--pane", main["pane_id"]]))["result"]["layout"]
    rect = {p["pane_id"]: p["rect"] for p in layout["panes"]}
    assert set(rect) == {main["pane_id"], fresh["pane_id"]}, f"the unit's tab is the main pane and the new run's worker: {rect}"
    assert abs(rect[main["pane_id"]]["width"] / layout["area"]["width"] - LY.MAIN_SHARE) < 0.03, (rect, layout["area"])
    assert rect[fresh["pane_id"]]["x"] > rect[main["pane_id"]]["x"], "the new worker is right of the main pane"
