# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Choices window's words and cues (specs/choices/choices_face.md): a diamond per purpose that reads in greyscale, the
one glow for a proposal waiting for you, each option's six facts on its row, a skipped option with its fix, the eye of a
private-content acknowledgement you can take back, and no write that reaches a route or a connection."""

import json
import subprocess
import sys
from pathlib import Path

from mixar.modules.lampway_tools import choices_face as F

ROOT = Path(__file__).resolve().parents[2]


def summary(pid="images.plates", cue="preferred", **kw):
    s = {"id": pid, "label": {"images.plates": "Plates", "track.body_3d": "Body tracking", "agent.main": "Main agent"}.get(pid, pid),
         "group": "images", "now": {"option": "openrouter:openai/gpt-image-2.5-flare", "label": "openai/gpt-image-2.5-flare",
                                    "scope": "global", "reason": cue}, "cue": cue}
    s.update(kw)
    return s


def option(oid="openrouter:openai/gpt-image-2.5-flare", **kw):
    o = {"id": oid, "label": "openai/gpt-image-2.5-flare", "provider": "openrouter", "model": "openai/gpt-image-2.5-flare",
         "runs": "openrouter.ai", "connection": {"id": "openrouter", "state": "connected"}, "route": {"id": "openrouter", "on": True},
         "cost": {"basis": "measured", "amount": 0.14, "unit": "USD", "per": "image", "measured_at": "2026-10-05"},
         "retention": "zdr", "acknowledged": None, "quality": [{"metric": "IoU", "value": 0.987}], "verdict": "ok", "rank": 0}
    o.update(kw)
    return o


def test_every_state_has_its_diamond_and_word():
    cues = {c: F.cue(summary(cue=c), waiting=set()) for c in ("preferred", "fallback", "override", "blocked", "unset")}
    assert len({c["glyph"] for c in cues.values()}) == 5
    assert cues["preferred"]["word"] == "preferred" and cues["unset"]["word"] == "not chosen yet"
    assert cues["fallback"]["word"].startswith("fallback")
    assert F.cue(summary(cue="fallback", why="studio:tripo is off"), waiting=set())["word"] == "fallback: studio:tripo is off"
    assert F.cue(summary(cue="who knows"), waiting=set())["word"] == "unknown state: who knows"


def test_one_glow_per_window():
    rows = [summary(pid=f"p{i}", cue=c) for i, c in enumerate(("preferred", "fallback", "override", "blocked", "unset"))]
    assert not any(F.cue(r, waiting=set())["glows"] for r in rows)
    lit = [r["id"] for r in rows if F.cue(r, waiting={"p3"})["glows"]]
    assert lit == ["p3"] and F.cue(rows[3], waiting={"p3"})["glyph"] == "conn_waiting"


def test_cue_family_in_greyscale():
    tokens = json.loads((ROOT / "scripts/lampway/facelift/theme/tokens.json").read_text(encoding="utf-8"))
    assert {s["state"] for s in tokens["cues"]["choice"]} == {
        "served by the preferred option", "served by a fallback", "served by an override", "nothing can run", "not chosen yet",
        "an agent proposal waits for you"}
    done = subprocess.run([sys.executable, str(ROOT / "scripts/lampway/facelift/theme/check_cues.py")], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout


def test_an_option_row_carries_its_six_facts():
    row = F.option_row(option())
    assert row["name"] == "openai/gpt-image-2.5-flare" and row["runs"] == {"icon": "LAMPWAY_WIRE", "text": "openrouter.ai"}
    assert row["connection"] == "conn_connected" and row["retention"] == "LAMPWAY_SHIELD"
    assert "$0.14 an image, measured 2026-10-05" in row["cost_tip"] and row["quality"] == "IoU 0.987"
    local = F.option_row(option(runs="this machine", retention="local", route=None, connection=None, cost={"basis": "free"}))
    assert local["runs"] == {"icon": "LAMPWAY_LAMP", "text": "this machine"} and local["retention"] == "LAMPWAY_LAMP"
    kept = F.option_row(option(retention="kept"))
    assert kept["retention"] == "eye" and "terms unread" in kept["retention_tip"]


def test_skipped_option_shows_its_fix():
    off = F.option_row(option(verdict="skipped", skipped={"constraint": "route", "text": "route studio:tripo is off"},
                              route={"id": "studio:tripo", "on": False}))
    assert off["skipped"] == "route studio:tripo is off" and off["fix"] == {"label": "Open in Privacy", "op": "lampway.privacy_open"}
    nc = F.option_row(option(label="Meshy", verdict="skipped", skipped={"constraint": "connection", "text": "Meshy is not connected"},
                             connection={"id": "studio:meshy", "state": "missing"}))
    assert nc["fix"] == {"label": "Connect Meshy", "op": "lampway.connections_open", "connection": "studio:meshy"}


def test_an_acknowledgement_shows_the_eye_and_can_be_taken_back():
    row = F.option_row(option(retention="kept", acknowledged="2026-10-06T10:00:00Z"))
    assert row["ack"] == {"glyph": "eye", "tip": "You allowed private content here on 2026-10-06 (terms unread): click to take it back"}
    assert F.option_row(option())["ack"] is None


def test_the_one_action_clears_the_state():
    assert F.action(summary(cue="preferred"), proposal=True)["label"] == "Accept for this project"
    assert F.action(summary(cue="unset"), proposal=False)["label"] == "Choose"
    fallback = summary(cue="fallback", why="studio:tripo is off")
    assert F.action(fallback, proposal=False, chain=[option(verdict="skipped", skipped={"constraint": "route", "text": "route studio:tripo is off"},
                                                            route={"id": "studio:tripo", "on": False})])["label"] == "Open in Privacy"
    assert F.action(summary(cue="preferred"), proposal=False) is None


def test_route_and_connections_are_read_only_here():
    src = (ROOT / "src/scripts/mixar/modules/lampway_tools/ui/choices.py").read_text(encoding="utf-8")
    for needle in ("egress/route", "set_route", "lampway.egress_route\"", "/app/connections", "put_secret", "connections_save_secret"):
        assert needle not in src, needle
