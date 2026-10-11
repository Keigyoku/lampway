# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Capabilities page and its operators (E2, "The interface"): drawn in the Choices window beside the link to Routes. Outside Blender
``bpy`` is a mock, so the operators run against a fake client and the drawing against a recording layout, and the rules that no run
could show (no network in a draw, every write behind the human gate, no route switched from here) are pinned in the source.

The words are ``capabilities_face`` (tests/lampway/test_lampway_capabilities_face.py); this file is what the page does with them."""

import ast
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mixar.modules.lampway_tools import capabilities_state as S
from mixar.modules.lampway_tools import human_gate, studio_client

ROOT = Path(__file__).resolve().parents[2]
UI_PATH = ROOT / "src/scripts/mixar/modules/lampway_tools/ui/capabilities.py"
MOD = "mixar.modules.lampway_tools.ui.capabilities"

WRITE_OPS = ("capability_switch", "capability_approval", "capability_option", "capability_proposal_accept", "capability_proposal_decline")


def row(cid="scene.read", **kw):
    r = {"id": cid, "label": cid, "does": "Do the thing.", "risk": "reads", "enabled": False, "in_force": False, "why_not": f"{cid} is off",
         "approval": "none", "options": [], "chosen_options": {}, "scope": "default", "default": False, "routes": []}
    r.update(kw)
    if "in_force" not in kw:
        r["in_force"] = bool(r["enabled"] and all(x["on"] for x in r["routes"]))
    return r


TERMINAL = dict(label="Run shell commands", does="Run shell commands; with the local backend they run on this computer as you.",
                risk="runs_code", approval="ask_each_time", options=["local", "docker", "ssh", "modal"])
BROWSE = dict(label="Browse the web", does="Open and read any web page; every host it reaches is logged.", risk="reaches_internet",
              routes=[{"id": "web:any", "on": False}])
SCENE = dict(label="Change the scene", does="Use Lampway's tools on the open scene.", risk="writes_project")


class Recorder:
    """A layout that writes down what it was asked to draw. An operator call returns the object whose properties the draw then sets."""

    def __init__(self, log=None):
        self.log = [] if log is None else log
        self.enabled = True
        self.alert = False

    def _child(self, kind, **kw):
        self.log.append((kind, kw))
        return Recorder(self.log)

    def row(self, **kw):
        return self._child("row", **kw)

    column = box = split = row

    def label(self, text="", icon="NONE", icon_value=0, **kw):
        self.log.append(("label", text, icon))

    def operator(self, idname, text="", icon="NONE", **kw):
        props = SimpleNamespace()
        self.log.append(("op", idname, text, icon, props, kw))
        return props

    def separator(self, **kw):
        pass

    def labels(self):
        return [e[1] for e in self.log if e[0] == "label"]

    def ops(self, idname=None):
        return [e for e in self.log if e[0] == "op" and (idname is None or e[1] == idname)]


class Door:
    """The server, as far as the page can tell: it records each PUT and answers with the row it would hold."""

    def __init__(self, fail=""):
        self.calls, self.fail = [], fail

    def capabilities(self, project=None):
        raise AssertionError("the page read the network")

    def set_capability(self, cid, enabled=None, approval=None, options=None, project=None):
        self.calls.append({"id": cid, "enabled": enabled, "approval": approval, "options": options, "project": project})
        if self.fail:
            raise studio_client.StudioError(self.fail)
        old = next(r for r in S.STATE["rows"] if r["id"] == cid)
        new = dict(old)
        if enabled is not None:
            new["enabled"] = enabled
        if approval is not None:
            new["approval"] = approval
        if options is not None:
            new["chosen_options"] = options
        return new


@pytest.fixture
def ui(monkeypatch):
    monkeypatch.setattr(sys.modules["bpy.types"], "Operator", object, raising=False)
    monkeypatch.delitem(sys.modules, MOD, raising=False)
    mod = importlib.import_module(MOD)
    S.reset()
    mod.refreshed = []   # a write asks for a fresh read (the routes it needs may have changed); the read itself is not run here
    monkeypatch.setattr(mod, "request_refresh", lambda: mod.refreshed.append(1))
    yield mod
    S.reset()
    sys.modules.pop(MOD, None)


@pytest.fixture
def door(ui, monkeypatch):
    d = Door()
    monkeypatch.setattr(ui, "CLIENT_FACTORY", lambda: d)
    monkeypatch.setattr(human_gate, "script_running", lambda: False)
    return d


def press(cls, **props):
    """Press an operator as the user: its properties, a context whose scene keeps the last message, report() written down."""
    op = cls()
    for k, v in props.items():
        setattr(op, k, v)
    said = []
    op.report = lambda kind, message: said.append((next(iter(kind)), message))
    ctx = SimpleNamespace(scene=SimpleNamespace(lampway_tools=SimpleNamespace(last_message="")))
    return op.execute(ctx), said


def load(*rows, proposals=(), ok=True, project="", project_only=False):
    S.update({"capabilities": list(rows), "proposals": list(proposals)})
    S.STATE.update(ok=ok, project=project, project_only=project_only)


# ------------------------------------------------------------------------------------------------------------- the writes
def test_turning_on_something_that_runs_code_opens_its_warning_and_writes_nothing(ui, door):
    load(row("terminal", **TERMINAL))
    result, said = press(ui.LAMPWAY_OT_capability_switch, cap_id="terminal", enabled=True, confirm=False)
    assert door.calls == [] and S.STATE["pending"] == "terminal" and result == {"FINISHED"}
    assert S.STATE["rows"][0]["enabled"] is False


def test_the_confirm_button_turns_it_on_and_closes_the_warning(ui, door):
    load(row("terminal", **TERMINAL))
    press(ui.LAMPWAY_OT_capability_switch, cap_id="terminal", enabled=True, confirm=False)
    result, said = press(ui.LAMPWAY_OT_capability_switch, cap_id="terminal", enabled=True, confirm=True)
    assert door.calls == [{"id": "terminal", "enabled": True, "approval": None, "options": None, "project": None}]
    assert S.STATE["pending"] == "" and S.STATE["rows"][0]["enabled"] is True, "the row shows the server's answer at once"
    assert result == {"FINISHED"} and said[-1][0] == "INFO"
    assert ui.refreshed, "and the page reads again, because a route it needs may have changed"


def test_a_confirm_for_a_row_whose_warning_is_not_open_does_not_write(ui, door):
    """The confirm flag alone is not a second click: the warning for THIS capability must be the one that is open."""
    load(row("terminal", **TERMINAL), row("computer.use", risk="acts_outside", label="Control this computer's desktop"))
    press(ui.LAMPWAY_OT_capability_switch, cap_id="computer.use", enabled=True, confirm=False)
    press(ui.LAMPWAY_OT_capability_switch, cap_id="terminal", enabled=True, confirm=True)
    assert door.calls == [] and S.STATE["pending"] == "terminal"


@pytest.mark.parametrize("risk", ["reads", "writes_project", "reaches_internet", "spends_plan"])
def test_the_other_risks_turn_on_in_one_click(ui, door, risk):
    load(row("x", risk=risk))
    press(ui.LAMPWAY_OT_capability_switch, cap_id="x", enabled=True, confirm=False)
    assert [c["enabled"] for c in door.calls] == [True] and S.STATE["pending"] == ""


def test_turning_anything_off_is_one_click_and_needs_no_warning(ui, door):
    load(row("terminal", enabled=True, **TERMINAL))
    press(ui.LAMPWAY_OT_capability_switch, cap_id="terminal", enabled=False, confirm=False)
    assert door.calls == [{"id": "terminal", "enabled": False, "approval": None, "options": None, "project": None}]
    assert S.STATE["rows"][0]["enabled"] is False


def test_a_cancel_closes_the_warning(ui, door):
    load(row("terminal", **TERMINAL))
    press(ui.LAMPWAY_OT_capability_switch, cap_id="terminal", enabled=True, confirm=False)
    press(ui.LAMPWAY_OT_capability_cancel)
    assert S.STATE["pending"] == "" and door.calls == []


def test_this_project_only_makes_the_write_carry_the_project(ui, door):
    load(row("scene.read"), project="/work/p", project_only=True)
    press(ui.LAMPWAY_OT_capability_switch, cap_id="scene.read", enabled=True, confirm=False)
    assert door.calls[0]["project"] == "/work/p"
    S.STATE["project_only"] = False
    press(ui.LAMPWAY_OT_capability_switch, cap_id="scene.read", enabled=False, confirm=False)
    assert door.calls[1]["project"] is None


def test_the_project_switch_toggles_only_when_the_file_has_a_project(ui, door):
    load(row("scene.read"), project="/work/p")
    press(ui.LAMPWAY_OT_capability_project_only)
    assert S.STATE["project_only"] is True
    press(ui.LAMPWAY_OT_capability_project_only)
    assert S.STATE["project_only"] is False
    S.STATE["project"] = ""
    result, said = press(ui.LAMPWAY_OT_capability_project_only)
    assert S.STATE["project_only"] is False and said[-1][0] == "ERROR", "no project: it says so and stays off"
    assert door.calls == [], "the switch is a view choice: it writes nothing"


def test_the_approval_and_the_option_are_written_on_their_own(ui, door):
    load(row("terminal", enabled=True, chosen_options={"backend": "local", "image": "x"}, **TERMINAL))
    press(ui.LAMPWAY_OT_capability_approval, cap_id="terminal", approval="ask_once_per_session")
    assert door.calls[0] == {"id": "terminal", "enabled": None, "approval": "ask_once_per_session", "options": None, "project": None}
    press(ui.LAMPWAY_OT_capability_option, cap_id="terminal", key="backend", value="docker")
    assert door.calls[1]["options"] == {"backend": "docker", "image": "x"}, "one option changes, the others stay"
    assert door.calls[1]["enabled"] is None and door.calls[1]["approval"] is None


def test_a_refusal_from_the_server_stays_beside_its_row_and_changes_nothing(ui, door):
    door.fail = "only your click in Capabilities can change what an agent may do: an agent may propose a change"
    load(row("scene.read"))
    result, said = press(ui.LAMPWAY_OT_capability_switch, cap_id="scene.read", enabled=True, confirm=False)
    assert result == {"CANCELLED"} and said[-1][0] == "ERROR"
    assert S.STATE["refusal"]["scene.read"] == door.fail and S.STATE["rows"][0]["enabled"] is False
    door.fail = ""
    press(ui.LAMPWAY_OT_capability_switch, cap_id="scene.read", enabled=True, confirm=False)
    assert "scene.read" not in S.STATE["refusal"], "the next good write clears it"


def test_a_row_the_page_does_not_have_is_refused_not_guessed(ui, door):
    load(row("scene.read"))
    result, said = press(ui.LAMPWAY_OT_capability_switch, cap_id="terminal", enabled=True, confirm=True)
    assert result == {"CANCELLED"} and door.calls == [] and "Refresh" in said[-1][1]


@pytest.mark.parametrize("name", [n for n in WRITE_OPS])
def test_a_script_cannot_press_any_write(ui, door, monkeypatch, name):
    """The agent's executor, a worker and the live bridge run inside human_gate.scripting(): none of them can change what an agent may do."""
    monkeypatch.setattr(human_gate, "script_running", lambda: True)
    load(row("terminal", **TERMINAL), proposals=[{"pid": "p1", "id": "terminal", "change": {"enabled": True}, "reason": "", "origin": "agent",
                                                    "state": "open", "t": 1.0}])
    cls = getattr(ui, "LAMPWAY_OT_" + name)
    props = {"cap_id": "terminal", "enabled": True, "confirm": True, "approval": "none", "key": "backend", "value": "docker", "pid": "p1",
             "scope": "global"}
    result, said = press(cls, **{k: v for k, v in props.items() if k in cls.__annotations__})
    assert result == {"CANCELLED"} and said[-1][0] == "ERROR" and "user's click" in said[-1][1]
    assert door.calls == [] and S.STATE["pending"] == "" and S.STATE["dismissed"] == set()


# ------------------------------------------------------------------------------------------------------------- proposals
PROPOSAL = {"pid": "p1", "id": "terminal", "change": {"enabled": True}, "reason": "to run the build", "origin": "agent", "state": "open", "t": 1.0}


def test_accepting_a_proposal_sends_its_change_and_removes_its_card(ui, door):
    load(row("terminal", **TERMINAL), proposals=[PROPOSAL], project="/work/p")
    assert [c["pid"] for c in S.cards()] == ["p1"]
    result, said = press(ui.LAMPWAY_OT_capability_proposal_accept, pid="p1", scope="project")
    assert door.calls == [{"id": "terminal", "enabled": True, "approval": None, "options": None, "project": "/work/p"}]
    assert S.cards() == [] and result == {"FINISHED"}


def test_accepting_for_all_projects_carries_no_project(ui, door):
    load(row("terminal", **TERMINAL), proposals=[PROPOSAL], project="/work/p")
    press(ui.LAMPWAY_OT_capability_proposal_accept, pid="p1", scope="global")
    assert door.calls[0]["project"] is None


def test_accepting_for_a_project_needs_the_file_to_have_one(ui, door):
    load(row("terminal", **TERMINAL), proposals=[PROPOSAL], project="")
    result, said = press(ui.LAMPWAY_OT_capability_proposal_accept, pid="p1", scope="project")
    assert result == {"CANCELLED"} and door.calls == [] and "no Lampway project" in said[-1][1]
    assert [c["pid"] for c in S.cards()] == ["p1"], "the card stays"


def test_a_failed_accept_keeps_the_card(ui, door):
    door.fail = "the server could not be reached: refused"
    load(row("terminal", **TERMINAL), proposals=[PROPOSAL])
    result, said = press(ui.LAMPWAY_OT_capability_proposal_accept, pid="p1", scope="global")
    assert result == {"CANCELLED"} and [c["pid"] for c in S.cards()] == ["p1"]


def test_declining_hides_the_card_and_asks_the_server_nothing(ui, door):
    """The server has no route that declines a proposal: a decline is the Client's own memory, and the report says so."""
    load(row("terminal", **TERMINAL), proposals=[PROPOSAL])
    result, said = press(ui.LAMPWAY_OT_capability_proposal_decline, pid="p1")
    assert result == {"FINISHED"} and S.cards() == [] and door.calls == []


# ------------------------------------------------------------------------------------------------------------- the drawing
def drawn(ui, *rows, **kw):
    load(*rows, **kw)
    layout = Recorder()
    ui.draw_capabilities(layout)
    return layout


def test_the_page_opens_with_what_the_agent_can_do_and_a_refresh(ui):
    lay = drawn(ui, row("scene.read", enabled=True), row("terminal", **TERMINAL))
    assert lay.labels()[0] == "Agent can: scene"
    assert lay.ops("lampway.capabilities_refresh")


def test_rows_are_grouped_under_their_risk_in_words(ui):
    lay = drawn(ui, row("scene.read", enabled=True), row("terminal", **TERMINAL), row("web.browse", **BROWSE))
    labels = lay.labels()
    assert labels.index("Looks only") < labels.index("Runs code") < labels.index("Reaches the internet")
    assert "reads" not in labels and "runs_code" not in labels


def test_each_row_has_its_switch_its_label_its_sentence_and_its_state(ui):
    lay = drawn(ui, row("terminal", **TERMINAL), row("scene.read", enabled=True, label="See the scene as data", does="Inspect the scene."))
    switches = {e[4].cap_id: e for e in lay.ops("lampway.capability_switch")}
    assert switches["terminal"][4].enabled is True and switches["terminal"][3] == "CHECKBOX_DEHLT"
    assert switches["scene.read"][4].enabled is False and switches["scene.read"][3] == "CHECKBOX_HLT"
    named = [e[2] for e in lay.ops("lampway.choices_info")]
    assert "Run shell commands" in named and "See the scene as data" in named
    text = " ".join(lay.labels())
    assert "Inspect the scene." in text and "with the local backend they run on this computer as you." in text.replace("\n", " ")
    assert "On" in lay.labels() and "Off" in lay.labels()


def test_a_capability_whose_route_is_off_says_so_and_points_at_routes(ui):
    lay = drawn(ui, row("web.browse", enabled=True, **BROWSE))
    assert "Waiting for a route" in lay.labels()
    assert "Needs the web (any site) route, which is off" in lay.labels()
    [fix] = lay.ops("lampway.privacy_open")
    assert fix[2] == "Open Routes"


def test_approval_and_options_show_only_for_an_enabled_row(ui):
    off = drawn(ui, row("terminal", **TERMINAL))
    assert not off.ops("lampway.capability_approval") and not off.ops("lampway.capability_option")
    on = drawn(ui, row("terminal", **dict(TERMINAL, enabled=True, approval="ask_each_time")))
    approvals = {e[4].approval: e for e in on.ops("lampway.capability_approval")}
    assert set(approvals) == {"none", "ask_each_time", "ask_once_per_session"}
    assert approvals["ask_each_time"][5].get("depress") is True and approvals["none"][5].get("depress") is False
    options = {e[4].value: e for e in on.ops("lampway.capability_option")}
    assert set(options) == {"local", "docker", "ssh", "modal"} and {e[4].key for e in options.values()} == {"backend"}
    assert options["local"][5].get("depress") is True
    quiet = drawn(ui, row("scene.read", enabled=True))
    assert not quiet.ops("lampway.capability_approval"), "reading is never asked about"


def test_an_open_confirm_row_names_what_it_allows_and_has_two_buttons(ui):
    load(row("terminal", **TERMINAL))
    S.STATE["pending"] = "terminal"
    lay = Recorder()
    ui.draw_capabilities(lay)
    assert "Commands run on this computer as you." in lay.labels()
    go = [e for e in lay.ops("lampway.capability_switch") if getattr(e[4], "confirm", False)]
    assert len(go) == 1 and go[0][4].cap_id == "terminal" and go[0][4].enabled is True and go[0][5].get("depress") is True
    assert lay.ops("lampway.capability_cancel")


def test_the_project_switch_shows_its_state_and_why_it_is_off(ui):
    lay = drawn(ui, row("scene.read"), project="/work/p", project_only=True)
    [sw] = lay.ops("lampway.capability_project_only")
    assert sw[5].get("depress") is True and sw[2] == "This project only"
    none = drawn(ui, row("scene.read"), project="")
    assert "This file has no Lampway project: changes here apply to every project" in none.labels()


def test_a_row_set_for_this_project_says_so(ui):
    lay = drawn(ui, row("scene.read", enabled=True, scope="project"))
    assert "this project" in lay.labels()


def test_a_proposal_card_says_what_it_asks_warns_and_offers_accept_or_decline(ui):
    lay = drawn(ui, row("terminal", **TERMINAL), proposals=[PROPOSAL], project="/work/p")
    labels = lay.labels()
    assert "The agent asks to turn on Run shell commands: to run the build" in labels
    assert labels.count("Commands run on this computer as you.") == 1, "the warning is on the card, once"
    accepts = {e[4].scope: e[4].pid for e in lay.ops("lampway.capability_proposal_accept")}
    assert accepts == {"project": "p1", "global": "p1"}
    assert [e[4].pid for e in lay.ops("lampway.capability_proposal_decline")] == ["p1"]


def test_a_card_without_a_project_offers_one_accept(ui):
    lay = drawn(ui, row("terminal", **TERMINAL), proposals=[PROPOSAL], project="")
    assert [e[4].scope for e in lay.ops("lampway.capability_proposal_accept")] == ["global"]


def test_a_server_that_has_no_capabilities_is_told_so(ui):
    S.fail("the server answered HTTP 404")
    lay = Recorder()
    ui.draw_capabilities(lay)
    assert any("no Capabilities yet" in t for t in lay.labels()) and not lay.ops("lampway.capability_switch")


def test_a_stopped_server_is_said_and_the_last_listing_stays_marked_stale(ui):
    lay = Recorder()
    ui.draw_capabilities(lay)
    assert "Lampway's server is not running: start it, then Refresh" in lay.labels()
    load(row("scene.read", enabled=True))
    S.fail("the server could not be reached: refused")
    lay = Recorder()
    ui.draw_capabilities(lay)
    assert any(t.startswith("as of ") and t.endswith("server stopped") for t in lay.labels()) and lay.ops("lampway.capability_switch")


def test_a_refusal_is_drawn_beside_its_row(ui):
    load(row("scene.read"))
    S.STATE["refusal"]["scene.read"] = "the server could not be reached: refused"
    lay = Recorder()
    ui.draw_capabilities(lay)
    assert "the server could not be reached: refused" in lay.labels()


def test_drawing_never_touches_the_network(ui, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a draw reached for the network")

    monkeypatch.setattr(ui, "CLIENT_FACTORY", boom)
    monkeypatch.setattr(S, "request", boom)
    load(row("terminal", enabled=True, **TERMINAL), row("web.browse", **BROWSE), proposals=[PROPOSAL], project="/p")
    S.STATE["pending"] = "terminal"
    ui.draw_capabilities(Recorder())


# ------------------------------------------------------------------------------------------------------------- the refresh
def test_refresh_asks_the_state_to_read_off_the_main_thread(monkeypatch):
    monkeypatch.setattr(sys.modules["bpy.types"], "Operator", object, raising=False)
    monkeypatch.delitem(sys.modules, MOD, raising=False)
    mod = importlib.import_module(MOD)
    S.reset()
    asked = []
    monkeypatch.setattr(S, "request", lambda factory, project="", spawn=None: asked.append((factory, project)) or True)
    S.STATE["project"] = "/work/p"
    mod.request_refresh()
    assert asked == [(mod.CLIENT_FACTORY, "/work/p")]
    S.reset()
    sys.modules.pop(MOD, None)


# ------------------------------------------------------------------------------------------------------------- the source
def _tree():
    return ast.parse(UI_PATH.read_text(encoding="utf-8"))


def _classes(tree):
    return [n for n in tree.body if isinstance(n, ast.ClassDef)]


def _bases(c):
    return {getattr(b, "id", "") for b in c.bases}


def test_the_gate_is_in_the_one_place_every_write_goes_through():
    tree = _tree()
    base = next(c for c in _classes(tree) if c.name == "_Write")
    execute = next(f for f in base.body if isinstance(f, ast.FunctionDef) and f.name == "execute")
    first = execute.body[0]
    assert isinstance(first, ast.If) and "script_running" in ast.unparse(first.test), "the human gate is the first thing a write does"
    for c in _classes(tree):
        if "_Write" in _bases(c):
            assert not any(isinstance(f, ast.FunctionDef) and f.name == "execute" for f in c.body), f"{c.name} must not bypass the gate"


def test_no_draw_reaches_the_network_or_starts_a_read():
    tree = _tree()
    forbidden = {"CLIENT_FACTORY", "request_refresh", "request", "capabilities", "set_capability", "_call", "Thread", "urlopen"}
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith(("draw", "_draw"))]:
        names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
        assert not (names & forbidden), (fn.name, names & forbidden)
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not (imported & {"urllib", "requests", "socket", "threading", "http"}), "the page's transport is the client and the state"


def test_the_page_never_switches_a_route():
    src = UI_PATH.read_text(encoding="utf-8")
    for needle in ("egress/route", "set_route", 'lampway.egress_route"', "/app/connections", "put_secret"):
        assert needle not in src, needle


def test_every_operator_is_registered_and_every_registered_class_exists():
    tree = _tree()
    defined = {c.name for c in _classes(tree) if any(isinstance(s, ast.Assign) and any(getattr(t, "id", "") == "bl_idname" for t in s.targets)
                                                      for s in c.body)}
    listed = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "classes")
    registered = {e.id for e in listed.value.elts}
    assert defined == registered, (defined ^ registered)
    ids = [s.value.value for c in _classes(tree) for s in c.body
           if isinstance(s, ast.Assign) and getattr(s.targets[0], "id", "") == "bl_idname"]
    assert len(ids) == len(set(ids)) and all(i.startswith("lampway.capabilit") for i in ids)


def test_every_operator_has_a_docstring_because_blender_shows_it_as_the_tooltip():
    for c in _classes(_tree()):
        if "_Write" in _bases(c) or "Operator" in _bases(c):
            assert ast.get_docstring(c), c.name
