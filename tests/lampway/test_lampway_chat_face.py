# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 04, the chat face: prices as chips that say what kind of number they are (DESIGN.md 8), and one line by the
composer that says where the next message goes and what it carries (never its content)."""

import re
from pathlib import Path

import pytest

from mixar.modules.lampway_tools import price_chips as P
from mixar.modules.lampway_tools import route_line as R

ROOT = Path(__file__).resolve().parents[2]
CHAT_CC = ROOT / "src/source/blender/editors/space_mixie_chat"

ROUTES = {"routes": [{"id": "chatgpt_plan", "label": "ChatGPT plan", "enabled": True, "hosts": ["chatgpt.com", "auth.openai.com"]},
                     {"id": "openrouter", "label": "OpenRouter", "enabled": False, "hosts": ["openrouter.ai"]}]}


def test_plan_step_price_kinds():
    est = P.chip({"price": {"kind": "estimate", "amount": 0.07, "unit": "USD", "source": "openrouter"}, "runs_where": "openrouter"},
                 hosts={"openrouter": "openrouter.ai"})
    assert est["kind"] == "estimate" and est["text"] == "≈ $0.07 est., openrouter.ai"
    quote = P.chip({"price": {"kind": "quote", "amount": 13.5, "unit": "credits", "source": "Tripo", "at": "2026-10-06T14:32:00"},
                    "runs_where": "studio:tripo"})
    assert quote["kind"] == "quote" and quote["text"] == "13.5 credits, read back from Tripo 14:32"
    local = P.chip({"runs_where": "local"})
    assert local["kind"] == "local" and local["text"] == "local, no cost" and local["glyph"] == "LAMPWAY_LAMP"
    billed = P.chip({"price": {"kind": "spent", "amount": 0.05, "unit": "USD"}})
    assert billed["kind"] == "spent" and billed["text"] == "$0.05 billed"
    assert P.chip({}) is None, "a step with no price and no place carries no chip"


@pytest.mark.parametrize("kind", ["estimate"])
def test_an_estimate_always_reads_as_one(kind):
    """The falsifier: an estimate rendered without its approximately sign is a quote in disguise."""
    text = P.chip({"price": {"kind": kind, "amount": 1.0, "unit": "USD"}})["text"]
    assert text.startswith("≈ ") and " est." in text


def test_composer_route_line():
    on = R.route_line("chatgpt_plan", ROUTES, {"text": True, "names": True, "transforms": True, "images": 0})
    assert on["send_ok"] and on["host"] == "chatgpt.com"
    assert on["tooltip"] == ("Your next message goes to chatgpt.com on your plan: text, object names and transforms. "
                             "No images attached.")
    off = R.route_line("openrouter", ROUTES, {"text": True})
    assert not off["send_ok"] and off["host"] == ""
    assert off["tooltip"] == "Your next message cannot leave: the agent's provider is off in Privacy"
    two = R.route_line("chatgpt_plan", ROUTES, {"text": True, "images": 2})
    assert two["tooltip"].endswith("text and 2 images.")
    local = R.route_line("mock", ROUTES, {"text": True})
    assert local["send_ok"] and local["host"] == "this machine" and "stays on this machine" in local["tooltip"]
    unknown = R.route_line("chatgpt_plan", None, {"text": True})
    assert unknown["send_ok"] and unknown["host"] == "" and "not answering" in unknown["tooltip"]
    unset = R.route_line("", ROUTES, {"text": True})
    assert unset["host"] == "", "a provider nobody named is not 'this machine'"


def _body(src, name):
    start = src.index(name)
    return src[start:src.index("\n}\n", start)]


def test_theme_spacing_is_not_forced():
    """Contract 04 test 1: the bubble spacing and the label height are the theme's (Mixar forced 8 and 13 over it)."""
    theme = (CHAT_CC / "mixie_chat_ui_theme.cc").read_text(encoding="utf-8")
    assert "ts->chat_bubble_spacing" in _body(theme, "float chat_ui_get_bubble_spacing()")
    assert "ts->chat_label_height" in _body(theme, "float chat_ui_get_label_height()")


class _Items(list):
    def add(self):
        from types import SimpleNamespace
        item = SimpleNamespace(item_id="", text="", status="PENDING", price_text="")
        self.append(item)
        return item


def test_a_plan_step_carries_its_price_chip(monkeypatch):
    """The todo slot (the plan's steps) writes each step's chip words where the C++ row reads them (price_text)."""
    from types import SimpleNamespace
    from mixar.modules.space_mixie_chat.core import slot_processor as SP
    from mixar.modules.lampway_tools import statusbar_state as S
    S.update(egress={"routes": [{"id": "openrouter", "label": "OpenRouter", "enabled": True, "hosts": ["openrouter.ai"]}]})
    monkeypatch.setattr(SP, "_fast_set", lambda item, key, value: setattr(item, key, value), raising=False)
    proc = SP.SlotEventProcessor.__new__(SP.SlotEventProcessor)
    proc._start_loader_timer = lambda: None
    bubble = SimpleNamespace(todo_items=_Items())
    proc._apply_todo_slot(bubble, [
        {"id": "1", "text": "Block out the lantern", "status": "done", "runs_where": "local"},
        {"id": "2", "text": "Texture the glass", "status": "pending", "runs_where": "openrouter",
         "price": {"kind": "estimate", "amount": 0.07, "unit": "USD", "source": "openrouter"}},
        {"id": "3", "text": "Name the parts", "status": "pending"}])
    S.reset()
    assert [i.price_text for i in bubble.todo_items] == ["local, no cost", "≈ $0.07 est., openrouter.ai", ""]


def test_the_route_line_reaches_the_composer():
    """The status timer writes the route line where the island's Send reads it (WindowManager props)."""
    from types import SimpleNamespace
    from mixar.modules.lampway_tools import chat_route
    from mixar.modules.lampway_tools import statusbar_state as S
    wm = SimpleNamespace(lampway_chat_route_host="", lampway_chat_route_tip="", lampway_chat_send_ok=True)
    scene = SimpleNamespace(mixie_chat_pending_attachments=[1, 2])
    S.update(egress=ROUTES, provider="chatgpt_plan")
    chat_route.sync(wm, scene)
    assert (wm.lampway_chat_route_host, wm.lampway_chat_send_ok) == ("chatgpt.com", True)
    assert wm.lampway_chat_route_tip.endswith("text, object names, transforms and 2 images.")
    S.update(provider="openrouter")
    chat_route.sync(wm, scene)
    assert (wm.lampway_chat_route_host, wm.lampway_chat_send_ok) == ("", False)
    S.fail("down")
    chat_route.sync(wm, scene)
    assert wm.lampway_chat_send_ok is True, "a stopped server never blocks Send (the send fails on its own, loudly)"
    S.reset()


def test_send_refuses_before_the_server_is_asked():
    from types import SimpleNamespace
    from mixar.modules.lampway_tools import chat_route
    off = SimpleNamespace(window_manager=SimpleNamespace(lampway_chat_send_ok=False))
    assert chat_route.refusal(off) == "Your next message cannot leave: the agent's provider is off in Privacy"
    assert chat_route.refusal(SimpleNamespace(window_manager=SimpleNamespace(lampway_chat_send_ok=True))) is None
    ops = (ROOT / "src/scripts/mixar/modules/space_mixie_chat/ui/operators/chat_ops.py").read_text(encoding="utf-8")
    body = ops[ops.index("class MIXIE_CHAT_OT_send_message"):]
    body = body[body.index("    def execute(self, context):"):]
    assert body.index("chat_route.refusal(context)") < body.index("get_metrics()"), "the refusal comes first"


def test_generate_prompts_carry_an_estimate():
    """Contract 04 test 4: the two GENERATE prompts carry an estimate chip; a type with a known cost reads '≈ … est.',
    one without says it is priced first (never a number nobody computed)."""
    from mixar.modules.lampway_tools import chat_route
    costs = {"image_gen": 30}
    assert chat_route.estimates(costs.get) == "image_gen=\u2248 30 credits est."
    src = (CHAT_CC / "mixie_chat_empty_state.cc").read_text(encoding="utf-8")
    draw = src[src.index("void mixie_chat_draw_empty_state("):]
    assert 'STREQ(g_empty_prompt_modes[i], "GENERATE")' in draw and "empty_state_draw_chip(" in draw
    assert [m for m in re.findall(r'"(AGENT|GENERATE)"', src[src.index("g_empty_prompt_modes"):src.index("g_empty_prompt_generate_types")])].count("GENERATE") == 2


def test_each_agent_turn_gets_its_who_line():
    """Contract 04's who line: the first agent message after a user message is stamped with the time it arrived and the
    route it came by (the sync stamps it when it first sees it, so the time is the arrival within a poll)."""
    from types import SimpleNamespace

    from mixar.modules.lampway_tools import chat_route as CR
    msgs = [SimpleNamespace(sender="USER", lampway_who=""), SimpleNamespace(sender="AGENT", lampway_who=""),
            SimpleNamespace(sender="AGENT", lampway_who=""), SimpleNamespace(sender="USER", lampway_who=""),
            SimpleNamespace(sender="AGENT", lampway_who="09:00\x1fchatgpt.com")]
    CR.stamp_who(msgs, "14:32", "chatgpt.com")
    assert [m.lampway_who for m in msgs] == ["", "14:32\x1fchatgpt.com", "", "", "09:00\x1fchatgpt.com"]
    assert CR.stamp_who([SimpleNamespace(sender="AGENT", lampway_who="")], "10:01", "")[0].lampway_who == "10:01\x1fthis machine"


def test_the_step_log_collapses_to_what_happened_and_where():
    """Contract 04's calm pass: the collapsed step log says how many steps are done, any that failed, and where they ran (the
    agent's tools are scripts in this Blender: local). Steps carry no timing, so no duration is claimed."""
    from mixar.modules.space_mixie_chat.core import steps_format as SF
    assert SF.format_steps_summary(["READ", "COMMAND", "TOOL"], statuses=["DONE", "DONE", "DONE"]) == "3 steps done, local"
    assert SF.format_steps_summary(["READ", "COMMAND"], statuses=["DONE", "FAILED"]) == "1 step done, 1 failed, local"
    assert SF.format_steps_summary(["READ", "COMMAND", "TOOL"], statuses=["DONE", "RUNNING", "PENDING"]) == "1 of 3 steps done, local"
    assert SF.format_steps_summary(["READ"]) == "1 tool called", "a caller without statuses keeps the old words"
