# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The herdr view (docs/reports/agent-modes-spec.md A4): one unit, one tab, minimal switching.

* **A unit** is one Lampway scene tab's conversation, keyed by its scene session id. Its **main** agent's pane (Mode 2: the harness
  pane bound to the tab; Mode 1: Lampway's Hermes pane, A1) opens in a tab of its own, labelled with the scene tab's name when it
  is known, else a short id.
* **A swarm worker's** pane splits into its unit's tab: the first worker right of the main agent, which keeps 60 %, each further
  worker down from the last worker pane, so the main agent keeps the left and the workers stand in one column beside it. A swarm
  that says how many workers it has (``planned``) gets an even column: each split keeps 1/(its workers still to come) for the pane
  it splits. A unit whose main pane is not there gets one tab for its workers.
* **A pane with no unit** (an ad-hoc pane the user starts from the cockpit) keeps a tab of its own.
* **Every pane Lampway starts reports what it is** (``pane.report_metadata``), best effort.

``place`` decides from the cockpit's records and herdr's snapshot (the live server is the truth: a record whose pane is gone is no
place to split from). This module only decides and spells; ``host.py`` runs every command through ``launcher.run``.

The argv shapes of the herdr CLI are all here, checked against herdr 0.9.3 (its CLI reference and a live server,
``tests/test_herdr_layout_live.py``):
- ``pane split <pane> --direction right|down --ratio R``: ``R`` is the share the split pane KEEPS (herdr's first child); the
  answer is ``result.pane``, with its ``tab_id``.
- ``pane report-metadata <pane> --source … --state-label STATUS=TEXT …``: one ``--state-label`` per status (idle, working, blocked,
  done, unknown); herdr refuses an option it does not know, ``--state-labels`` included.
The test suite's played herdr (``tests/herdr_support.py`` ``PaneHerdr``) is as strict.
"""
import json
from dataclasses import dataclass
from typing import Optional

WORKSPACE_LABEL = "lampway"
SOURCE = "lampway"
#: What the main agent keeps of its unit's tab when the first worker splits right of it (spec A4: the left 60 %). herdr's ratio is
#: the share the split pane keeps (measured on herdr 0.9.3).
MAIN_SHARE = 0.6
#: A further worker of a swarm that did not say its size splits the last worker pane down the middle.
COLUMN_RATIO = 0.5
LABEL_MAX = 40
TITLE_MAX = 80
SHORT_ID = 8

MAIN, WORKER = "main", "worker"
#: What the sidebar says for each state herdr detects (``--state-label STATUS=TEXT``; herdr caps each at 80 characters).
STATE_LABELS = {
    MAIN: {"working": "working", "blocked": "waiting for you", "idle": "ready", "done": "done"},
    WORKER: {"working": "working on its task", "blocked": "stuck", "idle": "finished", "done": "finished"},
    None: {"working": "working", "blocked": "waiting for you", "idle": "ready", "done": "done"},
}


# ------------------------------------------------------------------------------------------------- the herdr CLI's argv shapes
def workspace_create(cwd: str, env: list) -> list:
    return ["workspace", "create", "--cwd", cwd, "--label", WORKSPACE_LABEL, "--no-focus", *env]


def tab_create(workspace_id: str, cwd: str, label: str, env: list) -> list:
    return ["tab", "create", "--workspace", workspace_id, "--cwd", cwd, "--label", label[:LABEL_MAX], "--no-focus", *env]


def pane_split(pane_id: str, direction: str, ratio: float, cwd: str, env: list) -> list:
    """The new pane splits ``pane_id``, which keeps ``ratio`` of the space."""
    return ["pane", "split", pane_id, "--direction", direction, "--ratio", f"{ratio:g}", "--cwd", cwd, "--no-focus", *env]


def pane_report_metadata(pane_id: str, meta: dict) -> list:
    """No ``--ttl-ms``: the report lasts as long as the pane."""
    labels = [x for status, text in sorted(meta["state_labels"].items()) for x in ("--state-label", f"{status}={text}")]
    return ["pane", "report-metadata", pane_id, "--source", SOURCE, "--agent", meta["agent"], "--display-agent", meta["display_agent"],
            "--title", meta["title"], *labels]


def created_pane(out: str) -> dict:
    """The new pane from a create or split command's JSON: ``result.root_pane`` (workspace and tab create) or ``result.pane``
    (split)."""
    result = json.loads(out)["result"]
    pane = result.get("root_pane") or result.get("pane")
    if not isinstance(pane, dict) or not pane.get("pane_id"):
        raise ValueError("herdr's answer names no pane")
    return pane


# ------------------------------------------------------------------------------------------------- where a pane goes
def short_id(unit: str) -> str:
    return str(unit or "")[:SHORT_ID]


def unit_label(unit: str, label: Optional[str] = None) -> str:
    """A unit's tab label: the scene tab's name when it is known, else a short id."""
    return " ".join(str(label or "").split())[:LABEL_MAX] or short_id(unit)


@dataclass(frozen=True)
class Placement:
    verb: str                          # "workspace" | "tab" | "split"
    label: str = ""                    # the new tab's label
    of: str = ""                       # split: the pane split
    direction: str = ""
    ratio: float = 0.0


def _tab(rec: dict, live: dict) -> Optional[str]:
    return (live.get(rec.get("pane_id")) or {}).get("tab_id") or rec.get("tab_id")


def _latest(recs: list) -> Optional[dict]:
    return max(recs, key=lambda r: r.get("created_at") or 0) if recs else None


def unit_main(unit: str, sessions: list, snap: dict) -> Optional[dict]:
    """The unit's main pane in herdr now: the newest record of role main whose pane is live (a live session first)."""
    live = {p["pane_id"] for p in snap.get("panes") or []}
    mains = [s for s in sessions if unit and s.get("unit") == unit and s.get("role") == MAIN and s.get("pane_id") in live]
    return _latest([s for s in mains if s.get("state") == "live"]) or _latest(mains)


def swarm_of(binding: Optional[str]) -> Optional[str]:
    """The swarm a worker pane belongs to, from its binding name ``swarm:<swarm_id>:<worker_id>``."""
    parts = str(binding or "").split(":")
    return parts[1] if len(parts) == 3 and parts[0] == "swarm" else None


def place(role: Optional[str], unit: Optional[str], label: str, sessions: list, snap: dict, swarm: Optional[str] = None,
          planned: Optional[int] = None) -> Placement:
    """Where a new pane goes. ``label`` is the tab label for a pane that opens a tab (a main pane's unit label, an ad-hoc pane's
    name). Only panes herdr still shows count: a finished worker's pane that is still open stays in the column (Q13 is not built)."""
    if not any(w.get("label") == WORKSPACE_LABEL for w in snap.get("workspaces") or []):
        return Placement("workspace")
    if role != WORKER or not unit:
        return Placement("tab", label=label)
    live = {p["pane_id"]: p for p in snap.get("panes") or []}
    root = unit_main(unit, sessions, snap)
    column = [s for s in sessions if s.get("unit") == unit and s.get("role") == WORKER and s.get("pane_id") in live
              and (root is None or _tab(s, live) == _tab(root, live))]
    last = _latest(column)
    if last is not None:
        mine = [s for s in column if swarm and swarm_of(s.get("swarm_binding")) == swarm]
        even = planned and mine and int(planned) > len(mine)
        return Placement("split", of=last["pane_id"], direction="down", ratio=1 / (int(planned) - len(mine) + 1) if even else COLUMN_RATIO)
    if root is not None:
        return Placement("split", of=root["pane_id"], direction="right", ratio=MAIN_SHARE)
    return Placement("tab", label=label)


def metadata(agent: str, role: Optional[str], *, unit_name: str, name: str, task: str, display_agent: Optional[str] = None) -> dict:
    """What a pane reports (spec A4): ``display_agent`` "Lampway · <scene>" for a main agent, "Worker N · <task>" for a worker (the
    swarm names it), the pane's name otherwise; ``title`` the task, clipped; ``state_labels`` by role."""
    shown = display_agent or (f"Lampway · {unit_name}" if role == MAIN else name)
    title = " ".join(str(task or name or "").split())
    return {"agent": agent, "display_agent": shown[:TITLE_MAX], "title": title[:TITLE_MAX - 1] + "…" if len(title) > TITLE_MAX else title,
            "state_labels": dict(STATE_LABELS.get(role, STATE_LABELS[None]))}
