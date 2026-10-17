# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The first-run walk's step "What may your agent do?" (E2): after the routes and the provider, with the server's defaults pre-ticked; Finish writes the changes
through ``PUT /app/capabilities/{id}``. Offline the step is skipped and nothing is saved, as for the rest of the walk. The walk
(``lampway_tools/onboarding.py``) holds no bpy and its logic loads without the package, as server/tests/test_onboarding_walk.py loads it;
the popup (``ui/onboarding.py``) draws it. The routes-only walk is tests/lampway/test_lampway_onboarding.py."""

import importlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mixar.modules.lampway_tools import capabilities_face, onboarding as ob

ROOT = Path(__file__).resolve().parents[2]
ONBOARDING = ROOT / "src/scripts/mixar/modules/lampway_tools/onboarding.py"
UI = "mixar.modules.lampway_tools.ui.onboarding"

ROUTES = [{"id": "openrouter", "label": "OpenRouter", "enabled": False, "hosts": ["openrouter.ai"], "privacy_class": "conditional",
           "retention": "per model: zdr", "training": "per model: data_collection=deny"},
          {"id": "fal", "label": "fal.ai", "enabled": False, "hosts": ["fal.ai"], "privacy_class": "unknown", "retention": "unknown", "training": "unknown"}]


def cap(cid, risk="reads", enabled=False, label=None, does="Do the thing.", routes=(), **kw):
    return {"id": cid, "label": label or cid, "does": does, "risk": risk, "enabled": enabled, "in_force": enabled and all(r["on"] for r in routes),
            "why_not": "", "approval": "none", "options": [], "chosen_options": {}, "scope": "default", "default": enabled,
            "routes": [dict(r) for r in routes], **kw}


# The server's defaults (Q8): scene work, vision, history, skills and studio planning on; everything that runs code or leaves, off.
CAPS = [cap("scene.read", enabled=True), cap("scene.edit", "writes_project", True), cap("vision", enabled=True),
        cap("terminal", "runs_code", label="Run shell commands", options=["local", "docker"],
            does="Run shell commands; with the local backend they run on this computer as you."),
        cap("web.browse", "reaches_internet", label="Browse the web", routes=[{"id": "web:any", "on": False}]),
        cap("image.fal", "reaches_internet", label="Make images with fal", routes=[{"id": "fal", "on": False}]),
        cap("computer.use", "acts_outside", label="Control this computer's desktop", does="Move the mouse, type and read the screen of this computer."),
        cap("messaging.*", "acts_outside"), cap("mcp.*"),
        cap("studio.plan", "spends_plan", True)]


def walk(provider="mock", capabilities=CAPS, routes=ROUTES):
    return ob.Walk(routes=routes, provider=provider, capabilities=capabilities)


class Door:
    """The server's three doors the walk writes through, in the order they were used."""

    def __init__(self, fail_on=None):
        self.writes, self.fail_on = [], fail_on

    def set_route(self, route, enabled):
        self.writes.append(("route", route, enabled))

    def set_capability(self, cid, enabled=None, **kw):
        if cid == self.fail_on:
            raise RuntimeError("the server went away")
        assert kw == {}, "the walk writes the global choice only: no project, no approval, no options"
        self.writes.append(("capability", cid, enabled))

    def save_provider_settings(self, values):
        self.writes.append(("caps", sorted(values)))


# ------------------------------------------------------------------------------------------------------------- the steps
def test_the_step_comes_after_routes_and_the_provider_and_before_spending_caps():
    w = walk()
    assert w.steps == ("Language and keys", "What may leave this machine", "Where the agent thinks", "What may your agent do?", "Spending caps")
    assert w.kinds == ("language", "routes", "agent", "capabilities", "spending")
    assert ob.STEPS[1] == "What may leave this machine" and len(ob.STEPS) == 4, "the routes-only walk is still the walk without it"


def test_the_walk_goes_through_it_and_the_last_step_is_still_spending():
    w = walk()
    seen = []
    while True:
        seen.append((w.step, w.kind))
        if w.step == len(w.steps):
            break
        assert w.next() is None
    assert seen == [(1, "language"), (2, "routes"), (3, "agent"), (4, "capabilities"), (5, "spending")]
    assert w.next() is None and w.step == 5, "it does not run past the end"
    w.back()
    assert w.kind == "capabilities"


def test_the_providers_refusal_still_sends_the_user_back_to_the_routes():
    w = walk("chatgpt_plan", routes=[dict(ROUTES[0], id="chatgpt_plan", label="ChatGPT plan")])
    w.step = 3
    assert "go Back and switch it on" in w.next()


# ------------------------------------------------------------------------------------------------------------- the defaults
def test_the_servers_defaults_are_pre_ticked_and_families_are_left_to_their_own_setup():
    w = walk()
    ticked = {cid for cid, on in w.capability_chosen.items() if on}
    assert ticked == {"scene.read", "scene.edit", "vision", "studio.plan"}
    assert "messaging.*" not in w.capability_chosen and "mcp.*" not in w.capability_chosen, "a family has no platform to switch on yet"
    assert [r["id"] for r in w.capability_rows][:3] == ["scene.read", "scene.edit", "vision"], "the server's order is kept"
    assert w.capability_clicks == [], "mirroring the server is not a click"


def test_a_click_is_recorded_and_an_unknown_capability_is_refused():
    w = walk()
    w.click_capability("terminal", True)
    w.click_capability("scene.edit", False)
    assert w.capability_clicks == [("terminal", True), ("scene.edit", False)]
    assert w.capabilities_on() == ["scene.read", "vision", "terminal", "studio.plan"]
    with pytest.raises(KeyError):
        w.click_capability("nope", True)


def test_turning_on_code_or_outside_action_shows_its_plain_warning_only_while_ticked():
    w = walk()
    assert w.capability_warning("terminal") == "" and w.capability_warning("computer.use") == ""
    w.click_capability("terminal", True)
    w.click_capability("computer.use", True)
    assert w.capability_warning("terminal") == "Commands run on this computer as you."
    assert w.capability_warning("computer.use") == "This lets your agent move the mouse, type and read the screen of this computer."
    assert w.capability_warning("scene.edit") == "", "a default that only changes your scene needs no warning"
    w.click_capability("terminal", False)
    assert w.capability_warning("terminal") == ""


def test_a_ticked_capability_whose_route_is_off_says_which_step_opens_it():
    w = walk()
    assert w.capability_note("image.fal") == "", "unticked: nothing to say"
    w.click_capability("image.fal", True)
    assert w.capability_note("image.fal") == "Needs the fal route, which is off: switch it on in step 2"
    w.click_route("fal", True)
    assert w.capability_note("image.fal") == "", "the route chosen in step 2 counts, before anything is saved"
    w.click_capability("web.browse", True)
    assert w.capability_note("web.browse") == "Needs the web (any site) route, which this setup does not offer yet"


# ------------------------------------------------------------------------------------------------------------- finish
def test_finish_writes_only_what_the_user_changed_after_the_routes():
    w = walk()
    w.click_route("fal", True)
    w.click_capability("terminal", True)
    w.click_capability("scene.edit", False)
    door = Door()
    saved = w.finish(door)
    assert saved == ["preferences", "routes", "capabilities", "caps"]
    assert door.writes == [("route", "fal", True), ("capability", "scene.edit", False), ("capability", "terminal", True), ("caps", ["spend_policy"])]


def test_finish_with_the_defaults_untouched_writes_no_capability():
    door = Door()
    saved = walk().finish(door)
    assert [w for w in door.writes if w[0] == "capability"] == [] and saved == ["preferences", "routes", "capabilities", "caps"]


def test_a_failed_write_keeps_what_was_saved_and_a_retry_writes_only_the_rest():
    w = walk()
    w.click_capability("terminal", True)
    w.click_capability("web.browse", True)
    door = Door(fail_on="web.browse")
    with pytest.raises(RuntimeError):
        w.finish(door)
    assert [x for x in door.writes if x[0] == "capability"] == [("capability", "terminal", True)]
    retry = Door()
    w.finish(retry)
    assert [x for x in retry.writes if x[0] == "capability"] == [("capability", "web.browse", True)]


# ------------------------------------------------------------------------------------------------------------- offline and older servers
def test_offline_the_step_is_skipped_and_nothing_is_saved():
    w = ob.Walk(routes=None, provider="", capabilities=CAPS)
    assert not w.online and w.steps == ob.STEPS and w.capability_rows is None
    for _ in range(3):
        assert w.next() is None
    assert w.step == 4 and w.kind == "spending"
    assert w.finish(None) == ["preferences"]
    door = Door()
    assert w.finish(door) == ["preferences"] and door.writes == []


class OnlineDoor:
    def __init__(self, listing=None, error=None):
        self.listing, self.error = listing, error

    def egress(self):
        return {"routes": ROUTES}

    def provider_settings(self):
        return {"values": {"provider": "mock"}}

    def capabilities(self, project=None):
        if self.error:
            raise self.error
        return self.listing


def test_read_takes_the_listing_from_the_server():
    w = ob.Walk.read(OnlineDoor({"capabilities": CAPS, "proposals": []}))
    assert w.online and w.kind == "language" and len(w.steps) == 5 and w.capability_chosen["scene.read"] is True


@pytest.mark.parametrize("door", [
    SimpleNamespace(egress=lambda: {"routes": ROUTES}, provider_settings=lambda: {"values": {}}),   # a door that has no Capabilities call
    OnlineDoor(error=RuntimeError("the server answered HTTP 404")),                                    # an older server
    OnlineDoor(error=OSError("the server could not be reached")),
    OnlineDoor({"capabilities": [cap("messaging.*"), cap("mcp.*")]}),                                  # nothing a person can switch
    OnlineDoor({})])
def test_an_older_server_or_an_empty_answer_leaves_the_walk_as_it_was(door):
    w = ob.Walk.read(door)
    assert w.online, "the routes are still the server's"
    assert w.steps == ob.STEPS and w.capability_rows is None
    sink = Door()
    assert w.finish(sink) == ["preferences", "routes", "caps"], "the saved list is the routes-only walk's"
    assert not [x for x in sink.writes if x[0] == "capability"]


def test_a_server_that_is_down_reads_offline_as_before():
    class Down:
        def egress(self):
            raise OSError("refused")

    w = ob.Walk.read(Down())
    assert not w.online and w.steps == ob.STEPS


def test_the_walks_logic_loads_without_the_package():
    """server/tests/test_onboarding_walk.py loads onboarding.py by its path, with nothing of mixar on the import path."""
    spec = importlib.util.spec_from_file_location("lampway_onboarding_alone", ONBOARDING)
    alone = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(alone)
    w = alone.Walk(routes=ROUTES, provider="mock", capabilities=CAPS)
    w.click_capability("terminal", True)
    door = Door()
    assert w.finish(door) == ["preferences", "routes", "capabilities", "caps"] and ("capability", "terminal", True) in door.writes


# ------------------------------------------------------------------------------------------------------------- the popup
class Recorder:
    def __init__(self, log=None):
        self.log = [] if log is None else log
        self.enabled = True

    def row(self, **_kw):
        return Recorder(self.log)

    column = split = box = row

    def label(self, text="", icon="NONE", **_kw):
        self.log.append(("label", text, icon))

    def operator(self, idname, text="", icon="NONE", **_kw):
        props = SimpleNamespace()
        self.log.append(("op", idname, text, icon, props))
        return props

    def prop(self, data, name, text=None, **_kw):
        self.log.append(("prop", name, getattr(data, "cap_id", getattr(data, "route_id", None)), text))

    def separator(self, **_kw):
        pass


@pytest.fixture
def ui(monkeypatch):
    monkeypatch.setattr(sys.modules["bpy.types"], "Operator", object, raising=False)
    monkeypatch.setattr(sys.modules["bpy.types"], "PropertyGroup", object, raising=False)
    monkeypatch.delitem(sys.modules, UI, raising=False)
    mod = importlib.import_module(UI)
    yield mod
    mod.WALK["walk"] = None
    sys.modules.pop(UI, None)


def items(w):
    return [SimpleNamespace(cap_id=r["id"], enabled=w.capability_chosen[r["id"]]) for r in w.capability_rows]


def at_step(w, kind):
    while w.kind != kind:
        assert w.next() is None
    return w


def test_capability_catalog_does_not_pad_sparse_setup_pages(ui):
    routes = [dict(ROUTES[0], id=f"route-{i}") for i in range(29)]
    capabilities = [cap(f"action-{i}", "runs_code") for i in range(20)]
    w = at_step(walk(capabilities=capabilities, routes=routes), "spending")
    lay = Recorder()
    ui.draw_step(lay, w, [], items(w))
    assert not any(e[0] == "label" and e[1] == "" for e in lay.log), "A sparse page must not inherit capability-catalog padding"


def test_disabled_capabilities_reserve_only_the_rows_actually_drawn(ui):
    w = at_step(walk(capabilities=[cap(f"action-{i}", "runs_code") for i in range(20)]), "capabilities")
    drawn = ui.draw_capabilities(Recorder(), w, items(w))
    assert ui.capability_rows(w) == drawn, "Unticked warnings are not drawn and must not inflate the dialog"


def test_capability_navigation_stays_bounded_as_the_catalog_grows(ui):
    w = at_step(walk(capabilities=[cap(f"action-{i}", "runs_code", enabled=True,
                                     routes=[{"id": "fal", "on": False}]) for i in range(100)]), "capabilities")
    assert ui.draw_capabilities(Recorder(), w, items(w)) <= 28, "A growing catalog must not push navigation below the tested window"


def test_capability_pages_keep_every_choice_once_when_warnings_change(ui):
    caps = [cap(f"action-{i}", capabilities_face.RISK_ORDER[i % 6],
                routes=[{"id": "fal", "on": False}]) for i in range(100)]
    w = at_step(walk(capabilities=caps), "capabilities")
    pages = ui.capability_pages(w)
    expected = [c["id"] for g in capabilities_face.groups(w.capability_rows) for c in g["rows"]]
    before = [[c["id"] for c in page] for page in pages]
    assert sum(before, []) == expected and len(set(expected)) == 100
    for c in caps:
        w.click_capability(c["id"], True)
    assert [[c["id"] for c in page] for page in ui.capability_pages(w)] == before
    seen = []
    for index in range(len(pages)):
        ui.WALK["capability_page"] = index
        lay = Recorder()
        drawn = ui.draw_capabilities(lay, w, items(w))
        assert drawn <= 28 and ui.capability_rows(w) == drawn
        seen.extend(e[2] for e in lay.log if e[0] == "prop")
    assert seen == expected
    assert set(w.capabilities_on()) == set(expected)


def test_paging_changes_no_server_choices_and_stale_page_action_is_refused(ui, monkeypatch):
    w = at_step(walk(capabilities=[cap(f"action-{i}", "runs_code") for i in range(20)]), "capabilities")
    ui.WALK["walk"] = w
    initial = dict(w.capability_chosen)
    invokes = []
    monkeypatch.setattr(ui.bpy.ops.lampway, "onboarding", lambda *args: invokes.append(args) or {'FINISHED'})
    refreshes = []
    window = SimpleNamespace(screen=SimpleNamespace(areas=[]), global_areas=[], mixar_refresh_popups=lambda: refreshes.append(True))
    context = SimpleNamespace(window=window)
    op = ui.LAMPWAY_OT_onboarding_capability_page()
    op.direction = 1
    assert op.execute(context) == {'FINISHED'} and ui.WALK["capability_page"] == 1
    assert w.capability_chosen == initial and w.capability_clicks == []
    assert refreshes == [True] and invokes == [], 'Paging must rebuild the original dialog without opening another modal'
    w.next()
    assert op.execute(None) == {'CANCELLED'}
    assert ui.WALK["capability_page"] == 1 and refreshes == [True] and invokes == []


def test_the_rail_lists_every_step_of_this_walk(ui):
    w = at_step(walk(), "capabilities")
    lay = Recorder()
    ui.draw_rail(lay, w)
    assert [e[1] for e in lay.log if e[0] == "label"] == list(w.steps)
    assert len(w.steps) == 5


def test_the_step_draws_a_tick_for_each_capability_under_its_risk(ui):
    w = at_step(walk(), "capabilities")
    lay = Recorder()
    ui.draw_step(lay, w, [], items(w))
    labels = [e[1] for e in lay.log if e[0] == "label"]
    ticks = [e[2] for e in lay.log if e[0] == "prop"]
    assert ticks == [r["id"] for g in capabilities_face.groups(w.capability_rows) for r in g["rows"]], "one tick per capability, grouped by risk"
    assert labels.index("Looks only") < labels.index("Runs code") < labels.index("Reaches the internet") < labels.index("Acts outside Lampway")
    assert "Run shell commands" in labels and "Browse the web" in labels
    infos = [e for e in lay.log if e[0] == "op" and e[1] == "lampway.onboarding_capability_info"]
    assert [e[4].cap_id for e in infos] == ticks, "each has its sentence as the hover"


def test_a_ticked_risky_capability_shows_its_warning_in_the_step(ui):
    w = at_step(walk(), "capabilities")
    lay = Recorder()
    ui.draw_step(lay, w, [], items(w))
    assert "Commands run on this computer as you." not in [e[1] for e in lay.log if e[0] == "label"]
    w.click_capability("terminal", True)
    w.click_capability("image.fal", True)
    lay = Recorder()
    ui.draw_step(lay, w, [], items(w))
    labels = [(e[1], e[2]) for e in lay.log if e[0] == "label"]
    assert ("Commands run on this computer as you.", "ERROR") in labels
    assert any(t == "Needs the fal route, which is off: switch it on in step 2" for t, _ in labels)


def test_offline_the_step_never_shows_and_the_spending_step_is_the_last(ui):
    w = ob.Walk(routes=None, provider="", capabilities=CAPS)
    w.step = 3
    lay = Recorder()
    ui.draw_step(lay, w, [])
    assert ("label", "Lampway's server is not running: Start it", "ERROR") in lay.log
    assert w.steps[-1] == "Spending caps" and len(w.steps) == 4


def test_the_switch_callback_records_the_click_once(ui):
    w = walk()
    ui.WALK["walk"] = w
    item = SimpleNamespace(cap_id="terminal", enabled=True)
    ui._capability_switched(item, None)
    ui._capability_switched(item, None)   # a redraw that finds the same value is not a second click
    assert w.capability_clicks == [("terminal", True)]


def test_the_info_button_says_what_the_capability_does(ui):
    w = walk()
    ui.WALK["walk"] = w
    props = SimpleNamespace(cap_id="terminal")
    assert ui.LAMPWAY_OT_onboarding_capability_info.description(None, props).startswith("Run shell commands")
    assert "with the local backend" in ui.capability_text(w.capability_rows[3])


def test_the_dialog_is_titled_and_confirmed_by_this_walks_own_steps(ui):
    src = (ROOT / "src/scripts/mixar/modules/lampway_tools/ui/onboarding.py").read_text(encoding="utf-8")
    assert "ob.STEPS" not in src, "the popup reads the steps of the walk it holds, which may or may not have the capabilities step"


def test_the_door_the_popup_gives_the_walk_has_the_capabilities_calls(ui):
    door = ui._door()
    assert callable(door.capabilities) and callable(door.set_capability) and callable(door.set_route) and callable(door.egress)


def test_a_walk_begun_by_the_popup_pre_ticks_the_servers_defaults(ui, monkeypatch):
    class Collection(list):
        def clear(self):
            del self[:]

        def add(self):
            item = SimpleNamespace(route_id="", cap_id="", enabled=False)
            self.append(item)
            return item

    wm = SimpleNamespace(lampway_onboarding_routes=Collection(), lampway_onboarding_caps=Collection(), lampway_onboarding_provider="mock",
                         lampway_onboarding_job_cap=1.0, lampway_onboarding_day_cap=5.0, lampway_onboarding_above=0.25)
    monkeypatch.setattr(ui, "_door", lambda: OnlineDoor({"capabilities": CAPS}))
    w = ui._begin(SimpleNamespace(window_manager=wm))
    assert [i.cap_id for i in wm.lampway_onboarding_caps] == [r["id"] for r in w.capability_rows]
    assert {i.cap_id for i in wm.lampway_onboarding_caps if i.enabled} == {"scene.read", "scene.edit", "vision", "studio.plan"}
    assert w.capability_clicks == [] and w.step == 2
