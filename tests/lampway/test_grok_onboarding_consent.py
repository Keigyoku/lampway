# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""First-run choices cannot replace the server's dedicated worker consent review."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from test_lampway_onboarding_capabilities import ui, cap, walk, at_step, items, Recorder, Door

DESCRIPTOR = {"consent_version": 1, "effects_sha256": "a" * 64,
              "effects": ["Worker-only temporary native view."], "ready": False}

@pytest.mark.parametrize("enabled", [False, True])
def test_dedicated_review_shows_saved_state_without_tick_and_keeps_warning(ui, enabled):
    w = at_step(walk(capabilities=[cap("grok.worker_compat", "runs_code", enabled,
                                     worker_compat=deepcopy(DESCRIPTOR))]), "capabilities")
    lay = Recorder()
    drawn = ui.draw_capabilities(lay, w, items(w))
    assert not any(e[0] == "prop" for e in lay.log), "Dedicated consent cannot use a generic tick"
    labels = [e[1] for e in lay.log if e[0] == "label"]
    assert ("On" if enabled else "Off") in labels
    assert "Review and consent separately in Agent preferences." in labels
    if enabled:
        assert w.capability_warning("grok.worker_compat") in labels
    assert drawn == ui.capability_rows(w)
    assert w.capability_chosen == {"grok.worker_compat": enabled} and not w.capability_clicks

@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("descriptor", [DESCRIPTOR, {}, None])
def test_callback_cannot_stage_generic_write_for_server_dedicated_review(ui, enabled, descriptor):
    w = walk(capabilities=[cap("grok.worker_compat", "runs_code", enabled, worker_compat=descriptor),
                           cap("terminal", "runs_code")])
    ui.WALK["walk"] = w
    item = SimpleNamespace(cap_id="grok.worker_compat", enabled=not enabled)
    ui._capability_switched(item, None)
    ui._capability_switched(item, None)
    assert item.enabled is enabled and w.capability_chosen["grok.worker_compat"] is enabled
    assert w.capability_clicks == []
    ui._capability_switched(SimpleNamespace(cap_id="terminal", enabled=True), None)
    door = Door()
    assert w.finish(door) == ["preferences", "routes", "capabilities", "caps"]
    assert [r for r in door.writes if r[0] == "capability"] == [("capability", "terminal", True)]


def test_descriptor_signal_not_client_id_default_and_metadata_keeps_pages_stable(ui):
    caps = [cap(f"worker-{i}", "runs_code", worker_compat=deepcopy(DESCRIPTOR),
                routes=[{"id": "fal", "on": False}]) for i in range(100)]
    w = at_step(walk(capabilities=caps), "capabilities")
    before = [[c["id"] for c in page] for page in ui.capability_pages(w)]
    for c in caps:
        w.click_capability(c["id"], True)
    assert [[c["id"] for c in page] for page in ui.capability_pages(w)] == before
    seen = []
    for index in range(len(before)):
        ui.WALK["capability_page"] = index
        lay = Recorder()
        drawn = ui.draw_capabilities(lay, w, items(w))
        assert drawn == ui.capability_rows(w) and drawn <= 28
        assert not any(e[0] == "prop" for e in lay.log)
        seen.extend(e[4].cap_id for e in lay.log if e[0] == "op" and e[1] == "lampway.onboarding_capability_info")
    assert seen == sum(before, []) and len(set(seen)) == 100
    legacy = walk(capabilities=[cap("grok.worker_compat", "runs_code")])
    lay = Recorder()
    ui.WALK["capability_page"] = 0
    ui.draw_capabilities(lay, legacy, items(legacy))
    assert any(e[0] == "prop" for e in lay.log), "The server descriptor owns the review requirement"

@pytest.mark.parametrize("enabled", [False, True])
def test_initialization_keeps_server_choice_and_records_no_dedicated_click(ui, monkeypatch, enabled):
    from test_lampway_onboarding_capabilities import OnlineDoor

    class Collection(list):
        def add(self):
            item = SimpleNamespace(route_id="", cap_id="", enabled=False)
            self.append(item)
            return item

    wm = SimpleNamespace(lampway_onboarding_routes=Collection(), lampway_onboarding_caps=Collection(),
                         lampway_onboarding_provider="mock", lampway_onboarding_job_cap=1.0,
                         lampway_onboarding_day_cap=5.0, lampway_onboarding_above=0.25)
    caps = [cap("grok.worker_compat", "runs_code", enabled, worker_compat=deepcopy(DESCRIPTOR))]
    monkeypatch.setattr(ui, "_door", lambda: OnlineDoor({"capabilities": caps}))
    w = ui._begin(SimpleNamespace(window_manager=wm))
    assert wm.lampway_onboarding_caps[0].enabled is enabled
    assert w.capability_chosen == {"grok.worker_compat": enabled}
    assert w.capability_clicks == [] and w.step == 2
    door = Door()
    w.finish(door)
    assert not any(r[0] == "capability" for r in door.writes)
