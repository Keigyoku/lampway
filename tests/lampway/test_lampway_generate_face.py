# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 08, the generation face: before any generation is sent the Image and Video tabs say its estimate (marked as
one), the caps it falls under, the route it takes and what content goes with it; an unknown price is never waved
through; a route that is off refuses in the tab and asks nothing of the network; the prompt library is a list with
versions, runs, ratings and prices."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mixar.modules.lampway_tools import generate_face as G

ROOT = Path(__file__).resolve().parents[2]
EGRESS_ON = {"routes": [{"id": "openrouter", "label": "OpenRouter", "enabled": True, "hosts": ["openrouter.ai"]},
                        {"id": "higgsfield", "label": "Higgsfield", "enabled": True, "hosts": ["higgsfield.ai"]}]}
EGRESS_OFF = {"routes": [{"id": "openrouter", "label": "OpenRouter", "enabled": False, "hosts": ["openrouter.ai"]}]}
POLICY = {"click": "above", "above": 0.25, "job_cap": 1.0, "day_cap": 3.0, "spent": 0.31}


def answer(amount=0.067, kind="estimate", needs_click=False, refused=None, policy=POLICY, provider="openrouter"):
    price = None if amount is None else {"kind": kind, "amount": amount, "unit": "USD", "source": "model listing", "basis": "b"}
    return {"provider": provider, "route": provider, "price": price, "basis": "b", "policy": dict(policy),
            "needs_click": needs_click, "refused": refused}


def test_estimate_is_labelled_as_one():
    est = G.face("openai/gpt-5-image-mini", answer(0.067, "estimate"), EGRESS_ON)
    assert "≈" in est["estimate"] and "est." in est["estimate"] and "$0.067" in est["estimate"]
    assert est["estimate_kind"] == "estimate" and "not read back" in est["estimate_tip"]
    quote = G.face("openai/gpt-5-image-mini", answer(0.40, "quote"), EGRESS_ON)
    assert "≈" not in quote["estimate"] and "est." not in quote["estimate"] and "$0.40" in quote["estimate"]
    assert "≈" not in quote["button"]


def test_unknown_price_needs_a_click():
    """No estimate: Spend, 'price unknown', even under click-above-$0.25 - whether the server said so or is silent."""
    said = G.face("heygen/heygen-video-1", answer(None, needs_click=True), EGRESS_ON)
    silent = G.face("heygen/heygen-video-1", None, EGRESS_ON)
    for face in (said, silent):
        assert face["button_kind"] == "spend" and face["button"].startswith("Spend") and "price unknown" in face["button"]
        assert face["estimate"] == "price unknown" and face["estimate_kind"] == "unknown"
    assert "never waved through" in said["policy"]


def test_generate_label_carries_the_number():
    assert G.face("m", answer(0.067), EGRESS_ON)["button"] == "Generate, ≈ $0.07"
    assert G.face("m", answer(0.21), EGRESS_ON)["button_kind"] == "generate"
    spend = G.face("m", answer(0.40, needs_click=True), EGRESS_ON)
    assert spend["button_kind"] == "spend" and spend["button"] == "Spend $0.40"
    assert "over" in spend["policy"] and "$0.25" in spend["policy"]


def test_the_results_row_says_the_last_run_billed_against_its_estimate():
    """Section 5: the last run's line, from the server's run log; none before the first run, and none while it is silent."""
    line = "3 images, $0.20 billed against a $0.21 estimate, rated 4"
    assert G.face("m", dict(answer(0.21), last_run=line), EGRESS_ON)["last_run"] == line
    assert G.face("m", dict(answer(0.21), last_run=line, last_run_short="$0.20 billed / $0.21 est."), EGRESS_ON)["last_run_short"] == "$0.20 billed / $0.21 est."
    assert G.face("m", answer(0.21), EGRESS_ON)["last_run"] == ""
    assert G.face("m", None, EGRESS_ON)["last_run"] == ""
    pump = (ROOT / "src/scripts/mixar/modules/lampway_tools/ui/generate_pump.py").read_text()
    strings = pump.split("STRINGS = ")[1].split(")")[0]
    assert '"last_run"' in strings and '"last_run_short"' in strings, "the pump writes both to wm.lampway_gen_*"
    native = (ROOT / "src/source/blender/editors/space_agent_bubble/agent_ui_tabmedia_estimate.cc").read_text()
    assert '"lampway_gen_last_run"' in native and '"lampway_gen_last_run_short"' in native and "face.last_run_short" in native, \
        "the column draws the line, or its short form when the line does not fit"


def test_meters_say_the_job_against_its_cap_and_the_session_against_its_ceiling():
    face = G.face("m", answer(0.067), EGRESS_ON)
    assert face["cap_job"] == "≈ $0.07 of cap $1.00 per job" and face["cap_job_fill"] == pytest.approx(0.067)
    assert face["cap_job_level"] == "ok"
    assert face["cap_session"] == "spent today $0.31 + 0.07 of $3.00" and face["cap_session_fill"] == pytest.approx((0.31 + 0.067) / 3.0)
    assert G.face("m", answer(0.85), EGRESS_ON)["cap_job_level"] == "warn"
    assert G.face("m", answer(1.2, refused="openrouter: 1.2 is over the per-job cap of 1"), EGRESS_ON)["cap_job_level"] == "over"
    assert G.face("m", answer(0.1, policy=dict(POLICY, job_cap=None, day_cap=None)), EGRESS_ON)["cap_job"] == "no per-job cap"


def test_route_and_content_say_where_it_goes_and_what_goes():
    face = G.face("m", answer(0.067), EGRESS_ON, references=0)
    assert face["route"] == "openrouter.ai" and face["route_ok"] is True and face["content"] == "prompt only, no asset"
    assert G.face("m", answer(0.067), EGRESS_ON, references=2)["content"] == "prompt and 2 reference images"
    assert G.face("higgsfield/kling-3", answer(None, needs_click=True, provider="higgsfield"), EGRESS_ON)["route"] == "higgsfield.ai"


class FakeClient:
    def __init__(self, reply=None):
        self.calls = []
        self.reply = reply or answer()

    def generate_estimate(self, service, model, params, references):
        self.calls.append((service, model, params, references))
        return self.reply


def test_route_off_refuses_in_the_tab():
    """openrouter off: Generate is disabled with the fix shown, and the estimate is never asked for."""
    client = FakeClient()
    got = G.ask(client, "image_gen", "openai/gpt-5-image-mini", {"number_of_images": 1}, 0, EGRESS_OFF)
    assert got is None and client.calls == []
    face = G.face("openai/gpt-5-image-mini", got, EGRESS_OFF)
    assert face["button_kind"] == "refused" and face["route_ok"] is False
    assert face["refusal"] == "openrouter is off: switch it on in Privacy to let data leave"
    assert "not answering" not in face["cap_job"] + face["estimate_tip"], "nothing was asked: the server's silence is not the reason"
    assert face["cap_job"] == "caps not asked: openrouter is off"
    image = "MixieMoodboardTabImageGenProps"
    wm = SimpleNamespace(lampway_gen_button_kind="refused", lampway_gen_refusal=face["refusal"], lampway_gen_owner=image)
    assert G.refusal(SimpleNamespace(window_manager=wm), image) == face["refusal"]
    assert G.refusal(SimpleNamespace(window_manager=wm), "MixieMoodboardTabImageTo3DProps") is None, "the 3D tab is not judged by the image face"
    wm.lampway_gen_button_kind = "generate"
    assert G.refusal(SimpleNamespace(window_manager=wm), image) is None
    on = G.ask(client, "image_gen", "openai/gpt-5-image-mini", {"number_of_images": 1}, 0, EGRESS_ON)
    assert on["price"]["amount"] == 0.067 and len(client.calls) == 1


def test_a_cap_refusal_from_the_server_disables_generate_with_its_reason():
    face = G.face("m", answer(1.2, refused="openrouter: 1.2 is over the per-job cap of 1 (Providers dialog)"), EGRESS_ON)
    assert face["button_kind"] == "refused" and "per-job cap" in face["refusal"]


def test_the_generate_operator_refuses_before_it_dispatches():
    """The island's Generate and Enter both go through mixie.moodboard_prompt_generate: it asks the face first."""
    src = (ROOT / "src/scripts/mixar/modules/moodboard/ui/operators/prompt_generate_ops.py").read_text(encoding="utf-8")
    execute = src[src.index("    def execute(self, context):"):]
    assert execute.index("generate_face.refusal(context, self.owner_type)") < execute.index("resolve_prompt_generate(")


# ------------------------------------------------------------------------------------------------- the prompt library
class Recorder:
    def __init__(self, log=None):
        self.log = [] if log is None else log

    def _child(self, *a, **_kw):
        return Recorder(self.log)

    row = column = split = _child

    def label(self, text="", icon="NONE", **_kw):
        self.log.append(("label", text))

    def operator(self, idname, text="", icon="NONE", **_kw):
        op = SimpleNamespace()
        self.log.append(("op", idname, text, op))
        return op


@pytest.fixture
def library():
    sys.path.insert(0, str(ROOT / "server"))
    try:
        from lampway_server.prompts.library import Library
        templates = Library(user_dir=None).list()
    finally:
        sys.path.remove(str(ROOT / "server"))
    return templates


def test_library_rows_show_versions_and_prices(library, monkeypatch):
    """Every built-in the server ships is a row: name, version and mean price on the row; runs and rating on hover."""
    from mixar.modules.lampway_tools import prompt_library
    tile = next(t for t in library if t["id"] == "seamless-tile")
    stats = [{"template": f"seamless-tile@{tile['version']}", "runs": 12, "rated": 5, "mean_rating": 4.2, "mean_cost": 0.067}]
    rows = prompt_library.rows([{k: t[k] for k in ("id", "version", "title", "media")} for t in library], stats)
    assert len(rows) == len(library) and {r["media"] for r in rows} == {"image", "video"}
    row = next(r for r in rows if r["id"] == "seamless-tile")
    assert row["price"] == "≈ $0.067" and "12 runs" in row["hover"] and "rated 4.2" in row["hover"]
    assert all(r["price"] == "no runs yet" for r in rows if r["id"] != "seamless-tile")

    for name in ("Panel", "Operator", "UIList", "PropertyGroup", "Menu"):
        monkeypatch.setattr(sys.modules["bpy.types"], name, object, raising=False)
    monkeypatch.delitem(sys.modules, "mixar.modules.lampway_tools.ui.panels.prompt_library_list", raising=False)
    import importlib
    ui = importlib.import_module("mixar.modules.lampway_tools.ui.panels.prompt_library_list")
    drawn = []
    for r in rows:
        item = SimpleNamespace(template_id=r["id"], title=r["title"], version=r["version"], media=r["media"], price=r["price"], hover=r["hover"])
        layout = Recorder()
        ui.LAMPWAY_UL_prompt_library.draw_item(None, None, layout, None, item, 0, None, "", 0)
        texts = [e[1] if e[0] == "label" else e[2] for e in layout.log]
        assert r["title"] in texts and f"v{r['version']}" in texts and r["price"] in texts, texts
        hover_ops = [e[3] for e in layout.log if e[0] == "op" and e[1] == "lampway.prompt_row_info"]
        assert hover_ops and hover_ops[0].hover == r["hover"]
        drawn.append(r["id"])
    assert len(drawn) == len(library)


def test_the_prompts_panel_leads_with_the_list_and_previews_whole(monkeypatch):
    """The panel's first control after refresh is the library list with its Image / Video filter; the rendered preview is
    a popover holding the whole text, not eight cut labels."""
    from unittest.mock import MagicMock
    monkeypatch.setitem(sys.modules, "mathutils.bvhtree", MagicMock())
    for name in ("Panel", "Operator", "UIList", "PropertyGroup", "Menu"):
        monkeypatch.setattr(sys.modules["bpy.types"], name, object, raising=False)
    monkeypatch.delitem(sys.modules, "mixar.modules.lampway_tools.ui.panels.lampway_panels", raising=False)
    import importlib
    panels = importlib.import_module("mixar.modules.lampway_tools.ui.panels.lampway_panels")
    log = []

    class L(Recorder):
        def prop(self, data, name, text=None, expand=False, **_kw):
            self.log.append(("prop", name, expand))

        def template_list(self, list_id, *a, **_kw):
            self.log.append(("list", list_id))

        def popover(self, panel, text="", **_kw):
            self.log.append(("popover", panel, text))

        def separator(self, **_kw):
            pass

        def _child(self, *a, **_kw):
            return L(self.log)

        row = column = split = box = _child

    preview = "Seamless square tile of brass sheet, light patina, even studio light, " * 6
    p = SimpleNamespace(prompt_vars=[SimpleNamespace(name="metal", value="brass")], prompt_preview=preview, last_message="",
                        prompt_library=[1, 2], prompt_library_filter="ALL")
    panels.LAMPWAY_PT_prompts.draw(SimpleNamespace(layout=L(log)), SimpleNamespace(scene=SimpleNamespace(lampway_tools=p)))
    kinds = [e[0] for e in log]
    assert ("prop", "prompt_library_filter", True) in log and ("list", "LAMPWAY_UL_prompt_library") in log
    assert kinds.index("list") < next(i for i, e in enumerate(log) if e[0] == "prop" and e[1] == "value")
    assert ("popover", "LAMPWAY_PT_prompt_preview") == next(e for e in log if e[0] == "popover")[:2]
    assert not [e for e in log if e[0] == "label" and e[1] and e[1] in preview], "the preview is not cut into labels"
    lines = []
    panels.LAMPWAY_PT_prompt_preview.draw(SimpleNamespace(layout=L(lines)), SimpleNamespace(scene=SimpleNamespace(lampway_tools=p)))
    assert " ".join(e[1] for e in lines if e[0] == "label").split() == preview.split()


def test_spend_opens_the_spend_card_for_the_approval_it_caused():
    """Contract 08: Spend opens contract 13's card. The tab cannot know the approval id before the server makes it: Spend notes
    the approvals already waiting, and the first new spend approval after it is the one whose card opens, once."""
    before = [{"id": "old", "state": "pending", "settings": {"unit": "usd"}}]
    G.await_card(before)
    assert G.next_card(before) is None
    later = before + [{"id": "q", "state": "pending", "settings": {"unit": "answer"}},
                      {"id": "new", "state": "pending", "settings": {"unit": "usd"}, "price": 0.4, "label": "Video"}]
    assert G.next_card(later)["id"] == "new"
    assert G.next_card(later) is None, "once"
