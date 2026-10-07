# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Capabilities page's words and state (docs/reports/agent-modes-spec.md E2, "The interface"): rows grouped by risk, each with its
label, its sentence, its routes with their state, its approval and options; one plain warning when a capability that runs code or acts
outside Lampway is turned on; a capability whose routes are off says so and points at Routes; an agent's proposal is a card the user
accepts or declines. ``capabilities_face`` has no bpy and no network; ``capabilities_state`` reads off the main thread and applies on it.

The rows are the shape ``GET /app/capabilities`` sends (server/lampway_server/capabilities/__init__.py ``Store.view``)."""

import threading

import pytest

from mixar.modules.lampway_tools import capabilities_face as F
from mixar.modules.lampway_tools import capabilities_state as S
from mixar.modules.lampway_tools import studio_client


def row(cid="scene.read", **kw):
    r = {"id": cid, "label": cid, "does": "Do the thing.", "risk": "reads", "enabled": False, "in_force": False, "why_not": f"{cid} is off",
         "approval": "none", "options": [], "chosen_options": {}, "scope": "default", "default": False, "routes": []}
    r.update(kw)
    if "in_force" not in kw:   # the server's rule (Store.effective): chosen on, and every route it needs on
        r["in_force"] = bool(r["enabled"] and all(x["on"] for x in r["routes"]))
        r["why_not"] = "" if r["in_force"] else r["why_not"]
    return r


TERMINAL = dict(label="Run shell commands", does="Run shell commands; with the local backend they run on this computer as you.",
                risk="runs_code", approval="ask_each_time", options=["local", "docker", "ssh", "modal"])
BROWSE = dict(label="Browse the web", does="Open and read any web page; every host it reaches is logged.", risk="reaches_internet",
              routes=[{"id": "web:any", "on": False}])


@pytest.fixture(autouse=True)
def fresh_state():
    S.reset()
    yield
    S.reset()


# ------------------------------------------------------------------------------------------------------------- the words
def test_rows_are_grouped_by_risk_in_the_servers_order_and_keep_their_own_order():
    rows = [row("terminal", risk="runs_code"), row("scene.read"), row("web.browse", risk="reaches_internet"), row("scene.edit", risk="writes_project"),
            row("vision"), row("panes.drive", risk="acts_outside"), row("studio.plan", risk="spends_plan"), row("code.execute", risk="runs_code")]
    out = F.groups(rows)
    assert [g["risk"] for g in out] == ["reads", "writes_project", "runs_code", "reaches_internet", "acts_outside", "spends_plan"]
    assert [r["id"] for r in out[0]["rows"]] == ["scene.read", "vision"], "catalogue order inside a group"
    assert [r["id"] for r in out[2]["rows"]] == ["terminal", "code.execute"]
    assert all(g["title"] and g["title"] != g["risk"] for g in out), "a group is named in words, never by its code"


def test_an_empty_group_is_not_drawn_and_a_risk_nobody_named_is_not_lost():
    out = F.groups([row("a", risk="reads"), row("b", risk="some_new_risk")])
    assert [g["risk"] for g in out] == ["reads", "some_new_risk"]
    assert out[1]["title"], "an unknown risk still has a heading"


def test_the_line_says_on_off_or_waiting_for_a_route():
    on = F.line(row("scene.read", enabled=True))
    assert (on["state"], on["word"], on["enabled"]) == ("on", "On", True)
    off = F.line(row("terminal", **TERMINAL))
    assert (off["state"], off["word"], off["enabled"]) == ("off", "Off", False)
    waiting = F.line(row("web.browse", enabled=True, in_force=False, why_not="web.browse needs the route web:any, which is off", **BROWSE))
    assert (waiting["state"], waiting["word"]) == ("waiting", "Waiting for a route")


def test_a_capability_whose_routes_are_off_says_so_and_points_at_routes():
    for enabled in (True, False):
        v = F.line(row("web.browse", enabled=enabled, in_force=False, **BROWSE))
        assert v["route_note"] == "Needs the web (any site) route, which is off", enabled
        assert v["route_fix"] == {"label": "Open Routes", "op": "lampway.privacy_open"}
        assert v["routes"] == [{"id": "web:any", "name": "web (any site)", "on": False}]
    two = F.line(row("x", routes=[{"id": "web_search", "on": False}, {"id": "fal", "on": False}]))
    assert two["route_note"] == "Needs the web search, fal routes, which are off"
    mixed = F.line(row("x", routes=[{"id": "web_search", "on": True}, {"id": "fal", "on": False}]))
    assert mixed["route_note"] == "Needs the fal route, which is off", "only the routes that are off are named"


def test_routes_that_are_on_say_nothing_and_a_capability_with_none_has_no_fix():
    on = F.line(row("web.search", enabled=True, routes=[{"id": "web_search", "on": True}]))
    assert on["route_note"] == "" and on["route_fix"] is None and on["state"] == "on"
    plain = F.line(row("scene.read"))
    assert plain["routes"] == [] and plain["route_note"] == "" and plain["route_fix"] is None


def test_the_sentence_and_the_scope_come_through():
    v = F.line(row("terminal", scope="project", **TERMINAL))
    assert v["does"].startswith("Run shell commands") and v["label"] == "Run shell commands"
    assert v["scope_tag"] == "this project"
    assert F.line(row("terminal", scope="global", **TERMINAL))["scope_tag"] == ""
    assert F.line(row("terminal", scope="default", **TERMINAL))["scope_tag"] == ""


def test_the_approval_setting_names_each_choice_and_marks_the_current():
    v = F.line(row("terminal", **dict(TERMINAL, enabled=True, approval="ask_once_per_session")))
    assert [(c["value"], c["on"]) for c in v["approval"]["choices"]] == [("none", False), ("ask_each_time", False), ("ask_once_per_session", True)]
    assert [c["label"] for c in v["approval"]["choices"]] == ["Never asks", "Asks every time", "Asks once per session"]


@pytest.mark.parametrize("risk, shown", [("reads", False), ("spends_plan", False), ("writes_project", True), ("runs_code", True),
                                          ("reaches_internet", True), ("acts_outside", True)])
def test_the_approval_setting_is_offered_where_an_action_can_be_asked_about(risk, shown):
    """Reading and planning are never asked about (a spend is the studio gate's, law 3); an action that writes, runs, reaches out or acts is."""
    assert F.line(row("x", risk=risk, enabled=True))["approval"]["shown"] is shown


def test_options_default_to_the_first_and_show_the_chosen_one():
    v = F.line(row("terminal", enabled=True, **TERMINAL))
    assert v["options"]["key"] == "backend" and v["options"]["label"] == "Where commands run"
    assert [(c["value"], c["on"]) for c in v["options"]["choices"]] == [("local", True), ("docker", False), ("ssh", False), ("modal", False)]
    v = F.line(row("terminal", enabled=True, chosen_options={"backend": "docker"}, **TERMINAL))
    assert [c["value"] for c in v["options"]["choices"] if c["on"]] == ["docker"]
    assert F.line(row("scene.read"))["options"] is None


# ------------------------------------------------------------------------------------------------------------- the warning
def test_the_terminal_on_this_computer_says_so_in_the_users_words():
    t = row("terminal", **TERMINAL)
    assert F.needs_confirm(t)
    assert F.warning(t) == "Commands run on this computer as you."
    assert F.warning(row("terminal", chosen_options={"backend": "local"}, **TERMINAL)) == "Commands run on this computer as you."


def test_another_backend_is_not_told_it_runs_here():
    """The local sentence is true only for the local backend: any other says what the capability does in the server's words."""
    w = F.warning(row("terminal", chosen_options={"backend": "docker"}, **TERMINAL))
    assert "this computer as you" not in w or "with the local backend" in w
    assert w.startswith("This lets your agent run shell commands")


@pytest.mark.parametrize("cid, risk, does, said", [
    ("code.execute", "runs_code", "Run code in a sandbox.", "This lets your agent run code in a sandbox."),
    ("computer.use", "acts_outside", "Move the mouse, type and read the screen of this computer.",
     "This lets your agent move the mouse, type and read the screen of this computer."),
    ("swarm", "runs_code", "Start up to six Lampway workers, each in its own headless Lampway.",
     "This lets your agent start up to six Lampway workers, each in its own headless Lampway.")])
def test_a_capability_that_runs_code_or_acts_outside_names_what_it_allows(cid, risk, does, said):
    r = row(cid, risk=risk, does=does)
    assert F.needs_confirm(r) and F.warning(r) == said


@pytest.mark.parametrize("risk", ["reads", "writes_project", "reaches_internet", "spends_plan"])
def test_the_other_risks_turn_on_in_one_click_with_no_warning(risk):
    r = row("x", risk=risk)
    assert not F.needs_confirm(r) and F.warning(r) == ""


# ------------------------------------------------------------------------------------------------------------- the summary
def test_the_summary_names_what_the_agent_can_do_now_in_short_words():
    rows = [row("scene.read", enabled=True), row("scene.edit", enabled=True), row("vision", enabled=True),
            row("web.browse", enabled=True, in_force=False, **{k: v for k, v in BROWSE.items() if k != "label"}),
            row("web.search", enabled=True, routes=[{"id": "web_search", "on": True}]), row("terminal", enabled=True, **TERMINAL),
            row("memory")]
    assert F.summary(rows) == "Agent can: scene, images, web, terminal", "in force only, once each, in the catalogue's order"


def test_the_summary_says_nothing_when_nothing_is_on_and_names_a_family_member():
    assert F.summary([row("terminal", **TERMINAL)]) == "Agent can: nothing"
    assert F.summary([]) == "Agent can: nothing"
    assert F.summary([row("messaging.telegram", enabled=True)]) == "Agent can: messaging"


# ------------------------------------------------------------------------------------------------------------- proposals
def proposal(pid="cap_1", cid="web.browse", enabled=True, **kw):
    p = {"pid": pid, "id": cid, "change": {"enabled": enabled}, "reason": "the docs are online", "origin": "agent", "state": "open", "t": 1.0}
    p.update(kw)
    return p


def test_a_proposal_is_a_card_with_what_and_why_in_the_agents_shape():
    rows = [row("web.browse", **BROWSE)]
    [card] = F.proposal_cards([proposal()], rows)
    assert card["pid"] == "cap_1" and card["id"] == "web.browse" and card["put"] == {"enabled": True}
    assert card["line"] == "The agent asks to turn on Browse the web: the docs are online"
    assert card["warning"] == "", "browsing is not code or acting outside: the route is its gate"
    [off] = F.proposal_cards([proposal(enabled=False, reason="")], [row("web.browse", enabled=True, **BROWSE)])
    assert off["line"] == "The agent asks to turn off Browse the web"


def test_a_proposal_to_run_code_carries_the_same_plain_warning():
    [card] = F.proposal_cards([proposal(cid="terminal")], [row("terminal", **TERMINAL)])
    assert card["warning"] == "Commands run on this computer as you."
    [safe] = F.proposal_cards([proposal(cid="terminal", enabled=False)], [row("terminal", enabled=True, **TERMINAL)])
    assert safe["warning"] == "", "turning something off warns of nothing"


def test_only_open_unanswered_proposals_show():
    rows = [row("web.browse", **BROWSE), row("terminal", **TERMINAL)]
    ps = [proposal("a"), proposal("b", cid="terminal"), proposal("c", state="accepted"), proposal("d", cid="terminal", state="declined")]
    assert [c["pid"] for c in F.proposal_cards(ps, rows)] == ["a", "b"]
    assert [c["pid"] for c in F.proposal_cards(ps, rows, dismissed={"a"})] == ["b"]


def test_a_proposal_the_state_already_satisfies_is_not_asked_again():
    """The server has no route that closes a proposal: after an accept (or a click elsewhere) the card goes by the state it asked for."""
    rows = [row("web.browse", enabled=True, **BROWSE)]
    assert F.proposal_cards([proposal(enabled=True)], rows) == []
    assert len(F.proposal_cards([proposal(enabled=False)], rows)) == 1


def test_a_proposal_for_a_capability_the_listing_does_not_have_still_shows_by_its_id():
    [card] = F.proposal_cards([proposal(cid="messaging.telegram")], [row("messaging.*")])
    assert card["line"].startswith("The agent asks to turn on messaging.telegram")


def test_a_family_members_card_is_warned_by_its_family():
    """messaging.telegram has no row of its own in the listing; the card must not turn on less than it says."""
    [card] = F.proposal_cards([proposal(cid="messaging.telegram")],
                              [row("messaging.*", risk="acts_outside", does="Send and receive messages on a messaging platform.")])
    assert card["warning"] == "This lets your agent send and receive messages on a messaging platform."


# ------------------------------------------------------------------------------------------------------------- the state
def listing(*rows, proposals=()):
    return {"capabilities": list(rows), "proposals": list(proposals)}


def test_a_listing_is_kept_and_a_failure_keeps_the_last_good_one():
    S.update(listing(row("scene.read", enabled=True), proposals=[proposal()]))
    assert S.STATE["ok"] and [r["id"] for r in S.STATE["rows"]] == ["scene.read"] and S.STATE["proposals"][0]["pid"] == "cap_1"
    assert S.STATE["as_of"] > 0 and S.STATE["error"] == ""
    S.fail("the server could not be reached: refused")
    assert not S.STATE["ok"] and S.STATE["error"] == "the server could not be reached: refused"
    assert [r["id"] for r in S.STATE["rows"]] == ["scene.read"], "the last good listing stays on screen, marked stale"


def test_an_older_server_is_told_by_its_404():
    S.fail("the server answered HTTP 404")
    assert S.STATE["missing"] is True
    S.update(listing())
    assert S.STATE["missing"] is False
    S.fail("the server answered HTTP 500")
    assert S.STATE["missing"] is False


def test_a_written_row_replaces_its_listing_row_at_once():
    S.update(listing(row("terminal", **TERMINAL), row("scene.read")))
    S.merge_row(row("terminal", enabled=True, **TERMINAL))
    assert [r["enabled"] for r in S.STATE["rows"]] == [True, False]
    S.merge_row({"id": "scene.read", "enabled": True, "approval": "none", "options": {}, "scope": "global"})   # a family member's short answer
    assert S.STATE["rows"][1]["enabled"] is True and S.STATE["rows"][1]["label"] == "scene.read", "a short answer merges, it never blanks the row"


def test_dismissing_a_card_hides_it_here_only():
    S.update(listing(row("web.browse", **BROWSE), proposals=[proposal("a"), proposal("b")]))
    assert [c["pid"] for c in S.cards()] == ["a", "b"]
    S.dismiss("a")
    assert [c["pid"] for c in S.cards()] == ["b"]


def test_a_read_runs_off_the_main_thread_and_applies_only_when_taken():
    started = []
    asked = []

    class Door:
        def capabilities(self, project=None):
            asked.append((threading.current_thread() is threading.main_thread(), project))
            return listing(row("scene.read", enabled=True))

    assert S.request(Door, "/p", spawn=lambda fn: started.append(fn)) is True
    assert S.STATE["rows"] == [] and not asked, "nothing read, nothing applied on the caller's thread"
    assert S.request(Door, "/p", spawn=lambda fn: started.append(fn)) is False, "one read in flight at a time"
    t = threading.Thread(target=started[0])
    t.start()
    t.join()
    assert asked == [(False, "/p")]
    assert S.STATE["rows"] == [], "the worker only leaves the answer in the inbox: the page changes on the main thread"
    assert S.take() is True
    assert [r["id"] for r in S.STATE["rows"]] == ["scene.read"] and S.STATE["ok"]
    assert S.take() is False, "an answer is applied once"
    assert S.request(Door, "/p", spawn=lambda fn: None) is True, "the next read may start once the last was taken"


@pytest.mark.parametrize("boom", [studio_client.StudioError("the server could not be reached: refused"), ValueError("not json")])
def test_a_read_that_fails_is_a_stated_error_never_a_dead_worker(boom):
    class Door:
        def capabilities(self, project=None):
            raise boom

    S.request(Door, "", spawn=lambda fn: fn())
    assert S.take() is True
    assert not S.STATE["ok"] and str(boom) in S.STATE["error"]
    assert S.request(Door, "", spawn=lambda fn: None) is True, "a failed read frees the next one"


def test_the_project_switch_needs_a_project():
    S.STATE["project"] = ""
    assert S.write_project() is None, "this file has no Lampway project: a write goes to every project"
    S.STATE["project"] = "/p"
    S.STATE["project_only"] = False
    assert S.write_project() is None
    S.STATE["project_only"] = True
    assert S.write_project() == "/p"
