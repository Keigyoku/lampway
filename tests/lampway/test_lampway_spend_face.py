# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 13, the spend card: one card for every spend that waits for a click, the price on its button, the caps as
meters with the pending amount apart, who planned it, and one row per state a spend can end in, each with its fix."""

import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mixar.modules.lampway_tools import spend_face as F

ROOT = Path(__file__).resolve().parents[2]
SPEND = {"scope": "day", "providers": [
    {"provider": "higgsfield", "unit": "credits", "spent": 31.5, "day_cap": 200.0, "job_cap": 40.0, "click": "always", "above": None},
    {"provider": "openrouter", "unit": "USD", "spent": 0.31, "day_cap": 3.0, "job_cap": 1.0, "click": "above", "above": 0.25},
    {"provider": "studios", "unit": "credits", "spent": 0.0, "day_cap": None, "job_cap": None, "click": "always", "above": None}]}


def approval(**kw):
    a = {"id": "a1", "action": "higgsfield.job", "studio": "higgsfield", "label": "Higgsfield video: a 5-second loop of the lantern, 720p",
         "price": 18.0, "settings": {"unit": "credits"}, "requested_by": "agent", "state": "pending", "expires": 2e9, "job_id": ""}
    a.update(kw)
    return a


def test_spend_button_carries_the_price():
    card = F.card(approval(), SPEND, now=1e9)
    assert card["button"] == "Spend 18 credits" and card["price"] == "18 credits" and card["kind"] == "quoted"
    usd = F.card(approval(studio="openrouter", price=0.4, settings={"unit": "usd"}), SPEND, now=1e9)
    assert usd["button"] == "Spend $0.40" and usd["kind"] == "estimate"
    unknown = F.card(approval(studio="openrouter", price=0.0, settings={"unit": "usd"}, label="Image generation: price set by the model"), SPEND, now=1e9)
    assert unknown["button"] == "Spend, price set by the model" and unknown["kind"] == "unknown"


def test_agent_origin_is_shown():
    assert F.card(approval(requested_by="agent"), SPEND, now=1e9)["origin"] == "planned by the agent, only your click spends"
    assert F.card(approval(requested_by="worker-2"), SPEND, now=1e9)["origin"] == "planned by the agent, only your click spends"
    assert F.card(approval(requested_by="user"), SPEND, now=1e9)["origin"] == "planned by you"


def test_meters_show_pending_separately():
    job, session = F.card(approval(), SPEND, now=1e9)["meters"]
    assert job["text"] == "this job 18 of 40" and job["used"] == 0.0 and job["pending"] == pytest.approx(18 / 40)
    assert session["text"] == "spent today 31.5 + 18 of 200" and session["used"] == pytest.approx(31.5 / 200)
    assert session["pending"] == pytest.approx(18 / 200) and session["used_tone"] == "muted"
    hot = F.card(approval(), dict(SPEND, providers=[dict(SPEND["providers"][0], spent=185.0)]), now=1e9)["meters"][1]
    assert hot["used_tone"] == "stop", "over 90 percent the used segment is stop"
    none = F.card(approval(studio="tripo"), SPEND, now=1e9)["meters"]
    assert [m["text"] for m in none] == ["no per-job cap", "spent today 0, no daily cap"]


def test_refusal_states_render_their_fix():
    cases = {
        "openrouter: 1.5 is over the per-job cap of 1 (Providers dialog)": ("over_job_cap", "Refused before sending: over the per-job cap"),
        "higgsfield: 30 would pass today's cap of 40 (31.5 already spent today, local day; Providers dialog)": ("past_cap", "Past today's cap"),
        "the price shown was 21.0, not 18.0: nothing was confirmed": ("price_changed", "The price changed: the old approval is void"),
        "A script cannot confirm a credit spend: click Confirm in the Studios panel yourself": ("agent_tried", "Agents can plan, never confirm"),
        "approval a1 expired: ask for the plan again so the price is read back fresh": ("expired", "This quote expired"),
    }
    for message, (state, title) in cases.items():
        row = F.state_row(F.classify(message), approval(), message)
        assert row["state"] == state and row["title"] == title, (message, row)
        assert row["fixes"] and row["detail"], row
    changed = F.state_row("price_changed", approval(), "the price shown was 21.0, not 18.0: nothing was confirmed")
    assert changed["button"] == "Spend 21 credits", "the new price waits for you on a new button"
    spent = F.state_row("spent", approval(job_id="j9"), "")
    assert spent["title"] == "Spent: job j9" and "never resubmitted" in spent["detail"]
    odd = F.state_row(F.classify("the moon is wrong"), approval(), "the moon is wrong")
    assert odd["title"] == "This spend cannot go ahead: the moon is wrong"


def test_enter_does_not_spend(monkeypatch):
    """The card is a popup with no default: Enter has nothing to press. invoke_props_confirm is gone."""
    src = (ROOT / "src/scripts/mixar/modules/lampway_tools/ui/operators/studio_ops.py").read_text(encoding="utf-8")
    assert "invoke_props_confirm" not in src
    from unittest.mock import MagicMock
    monkeypatch.setitem(sys.modules, "mathutils.bvhtree", MagicMock())
    for name in ("Panel", "Operator", "UIList", "PropertyGroup", "Menu"):
        monkeypatch.setattr(sys.modules["bpy.types"], name, object, raising=False)
    monkeypatch.delitem(sys.modules, "mixar.modules.lampway_tools.ui.operators.studio_ops", raising=False)
    import importlib
    ops = importlib.import_module("mixar.modules.lampway_tools.ui.operators.studio_ops")
    calls = []
    wm = SimpleNamespace(invoke_popup=lambda op, width=0: calls.append(("popup", width)) or {"RUNNING_MODAL"},
                         invoke_props_confirm=lambda *a, **k: calls.append("confirm"), invoke_props_dialog=lambda *a, **k: calls.append("dialog"))
    op = ops.LAMPWAY_OT_studio_confirm()
    op.execute = lambda context: calls.append("execute")
    op.approval_id, op.price, op.label = "a1", 18.0, "x"
    op.invoke(SimpleNamespace(window_manager=wm), SimpleNamespace(type="RET", value="PRESS"))
    assert calls == [("popup", 520)]


def test_one_card_for_every_source():
    """Every place a spend waits opens the same operator by invoking it (the card); nothing confirms around it."""
    base = ROOT / "src/scripts/mixar/modules/lampway_tools"
    sites = []
    for path in sorted(base.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and any(isinstance(a, ast.Constant) and a.value == "lampway.studio_confirm" for a in node.args):
                sites.append(path.name)
            if isinstance(node, ast.Attribute) and node.attr == "studio_confirm" and isinstance(node.value, ast.Attribute) and node.value.attr == "lampway":
                sites.append(path.name + ":ops")
    assert set(F.SOURCES) <= {s.split(":")[0] for s in sites}, (F.SOURCES, sites)
    assert F.OPERATOR == "lampway.studio_confirm"
    confirms = sorted({p.name for p in base.rglob("*.py") if "().confirm(" in p.read_text(encoding="utf-8") and p.name != "studio_client.py"})
    assert confirms == ["studio_ops.py"], confirms   # the card's Spend (studio_confirm.execute) and the answer button are the only confirms


def test_the_drawn_card_rows():
    """Contract 13 P1: the rows the C++ card painter draws (layout.mixar_spend), packed the way it reads them."""
    rows = F.drawn_rows(F.card(approval(), SPEND, now=1e9))
    assert rows[0] == ("TITLE", "Higgsfield video: a 5-second loop of the lantern, 720p")
    assert ("PRICE", "18 credits\x1fquoted") in rows
    meters = [r for r in rows if r[0] == "METER"]
    assert meters[0] == ("METER", "this job 18 of 40\x1f0.0000\x1f0.4500\x1f0")
    assert meters[1][1].startswith("spent today 31.5 + 18 of 200\x1f0.1575\x1f0.0900\x1f")
    assert F.rule("waiting") == "WAITING" and F.rule("over_job_cap") == "REFUSED" and F.rule("agent_tried") == "AGENT"
    assert F.rule("spent") == "SPENT" and F.rule("price_changed") == "WAITING"


def test_the_servers_own_day_cap_refusal_is_read_as_past_the_cap(tmp_path):
    """Ruling 5 made the server refuse with "would pass today's cap"; the card matched only "session cap" / "day cap", so the real
    refusal read as unknown. The message here comes from the server's SpendPolicy itself, not a paraphrase."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
    from lampway_server.spendpolicy import SpendPolicy, SpendRefused
    policy = SpendPolicy(lambda: {"higgsfield": {"day_cap": 40.0, "click": "always"}})
    policy.record("higgsfield", 31.5)
    with pytest.raises(SpendRefused) as exc:
        policy.check("higgsfield", 30.0)
    assert F.classify(str(exc.value)) == "past_cap", str(exc.value)
