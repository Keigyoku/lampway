# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Connections window's words and cues (specs/connections/connections_face.md): one glyph per state that reads in
greyscale, the one glow only for a sign-in waiting on your browser, the route as its own fact, the one action that
clears a state, and nothing of a secret in anything drawn."""

import ast
import json
import subprocess
import sys
from pathlib import Path

from mixar.modules.lampway_tools import connections_face as C

ROOT = Path(__file__).resolve().parents[2]


def view(cid="studio:meshy", state="missing", **kw):
    v = {"id": cid, "label": {"studio:meshy": "Meshy", "openrouter": "OpenRouter", "chatgpt_plan": "ChatGPT plan"}.get(cid, cid),
         "group": "Studios", "kind": "key", "state": state, "qualifiers": [], "route": {"id": cid, "on": False},
         "active_source": {"mode": "manual", "label": "keyring"}, "identity": {}, "checked_at": None, "check_age_s": None,
         "fingerprint": {}, "next_step": "Meshy is not connected: connect it in Connections"}
    v.update(kw)
    return v


def test_every_state_has_its_glyph_and_word():
    states = ("connected", "not_checked", "signed_out", "expired", "missing", "error")
    glyphs = {C.cue(view(state=s))["glyph"] for s in states}
    assert len(glyphs) == len(states), glyphs
    assert C.cue(view(state="connected", qualifiers=["warning"]))["glyph"] == "conn_warning"
    assert C.cue(view(state="missing"))["word"] == "not connected"
    odd = C.cue(view(state="haunted"))
    assert odd["word"] == "unknown state: haunted" and odd["glyph"] == "conn_error"


def test_route_off_is_not_a_colour_on_the_glyph():
    """'connected, route off' reads as two facts: the glyph is connected's, the route is its own column."""
    on, off = view(state="connected", route={"id": "openrouter", "on": True}), view(state="connected", route={"id": "openrouter", "on": False}, qualifiers=["route_off"])
    assert C.cue(on) == C.cue(off)
    assert C.route_cell(on)["icon"] == "LAMPWAY_WIRE" and C.route_cell(off)["icon"] == ""
    assert "route off" in C.route_cell(off)["tooltip"]


def test_one_glow_per_window():
    every = [view(cid=f"c{i}", state=s) for i, s in enumerate(("connected", "not_checked", "signed_out", "expired", "missing", "error"))]
    assert not any(C.glows(v, waiting=set()) for v in every)
    assert [v["id"] for v in every if C.glows(v, waiting={"c2"})] == ["c2"]


def test_the_one_action_clears_the_state():
    assert C.action(view(state="connected"))["label"] == "Test"
    assert C.action(view(state="not_checked"))["label"] == "Test"
    assert C.action(view(state="signed_out", kind="oauth", label="ChatGPT plan"))["label"] == "Sign in with ChatGPT plan"
    assert C.action(view(state="expired", kind="oauth"))["op"] == "lampway.connections_sign_in"
    assert C.action(view(state="missing", kind="key"))["label"] == "Paste a key"


def test_list_groups_in_order_and_hover_carries_source_and_age():
    views = [view(cid="openrouter", group="Agents", state="connected", check_age_s=125, active_source={"mode": "env", "label": "environment"}),
             view(cid="studio:meshy", group="Studios")]
    groups = C.groups(views)
    assert [g for g, _ in groups] == ["Agents", "Studios"]
    row = groups[0][1][0]
    assert row["name"] == "OpenRouter" and "environment" in row["tooltip"] and "checked 2 min ago" in row["tooltip"]


def test_draw_words_carry_no_secret():
    """The face reads only the view's allow-listed fields: a planted secret in any other field is never in its words."""
    sentinel = "sk-or-v1-SENTINEL"
    v = view(state="connected", secret=sentinel, value=sentinel, identity={"masked": "c•••@g•••.com", "token": sentinel},
             fingerprint={"last4": "7f3a", "sha8": "deadbeef", "raw": sentinel})
    out = json.dumps([C.cue(v), C.route_cell(v), C.action(v), C.groups([v]), C.detail(v)], ensure_ascii=False)
    assert sentinel not in out
    assert "•••• 7f3a" in out


def test_the_window_never_switches_a_route():
    src = (ROOT / "src/scripts/mixar/modules/lampway_tools/ui/connections.py").read_text(encoding="utf-8")
    assert "egress/route" not in src and "set_route" not in src and "lampway.egress_route" not in src


def test_cue_family_in_greyscale():
    tokens = json.loads((ROOT / "scripts/lampway/facelift/theme/tokens.json").read_text(encoding="utf-8"))
    states = {s["state"] for s in tokens["cues"]["connection"]}
    assert {"connected", "connected, warning", "not checked", "signed out", "expired", "missing", "error",
            "sign-in waiting for your browser"} == states
    done = subprocess.run([sys.executable, str(ROOT / "scripts/lampway/facelift/theme/check_cues.py")], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout


def test_the_secret_field_is_a_password_that_is_never_saved():
    tree = ast.parse((ROOT / "src/scripts/mixar/modules/lampway_tools/ui/connections.py").read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "StringProperty"
             and any(k.arg == "subtype" and getattr(k.value, "value", "") == "PASSWORD" for k in n.keywords)]
    assert calls, "no PASSWORD field"
    for c in calls:
        opts = next(k.value for k in c.keywords if k.arg == "options")
        assert "SKIP_SAVE" in {e.value for e in opts.elts}, ast.dump(c)


def test_sign_out_and_forget_only_where_they_mean_something():
    assert C.detail(view(state="missing", kind="key"))["foot"] == []
    assert C.detail(view(state="connected", kind="oauth", active_source={"mode": "signin"}))["foot"] == ["sign_out"]
    assert C.detail(view(state="connected", kind="key", active_source={"mode": "manual", "label": "keyring"}))["foot"] == ["forget"]
    assert C.detail(view(state="connected", kind="key", active_source={"mode": "env", "label": "environment"}))["foot"] == []
