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
