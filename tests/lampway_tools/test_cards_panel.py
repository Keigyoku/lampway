# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The project cards in Blender (specs/mrmak/09-report-cards.md section 6, test 11): the Cards panel in the Asset Vault draws the cached list into a recording layout with no
network call; refresh, pin and open go through the server off the main thread; opening a card hands its URL to the browser and never renders HTML inside Blender."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE = '''
import bpy, json
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from types import SimpleNamespace
from mixar.modules.cards.core import state as ST
from mixar.modules.cards.ui.panels import cards_panels as CP
from mixar.modules.lampway_tools import library_client as LC
calls, opened = [], []
CARDS = {"cards": [{"id": "boots1", "title": "Boots1", "status": "active", "pinned": True, "updated": "2026-10-05", "archived": False, "steps": ["Round 4", "Motion tests"],
                    "category": "Boots1", "description": "", "created": "2026-10-03"},
                   {"id": "helm", "title": "Helm", "status": "done", "pinned": False, "updated": "2026-10-01", "archived": False, "steps": [], "category": "", "description": "", "created": "2026-10-01"}],
         "total": 2}
def fake(method, path, body=None, timeout=60):
    calls.append([method, path, body])
    if path.startswith("/app/cards?") or path == "/app/cards":
        return {"data": CARDS}
    if path.endswith("/open?step=0"):
        return {"data": {"url": "http://127.0.0.1:41234/view/g/2026-10-03_boots1/round-4.html", "step": "Round 4"}}
    return {"data": {"id": "boots1", "status": "active", "pinned": False}}
LC._request = fake
ST.PUMP.spawn = lambda job: job()
import webbrowser
webbrowser.open = lambda url, *a, **k: opened.append(url) or True
class Rec:
    def __init__(self, log): self.log, self.enabled = log, True
    def row(self, align=False): return Rec(self.log)
    def column(self, align=False): return Rec(self.log)
    def box(self): return Rec(self.log)
    def separator(self, **kw): pass
    def label(self, text="", icon="NONE"): self.log.append(("label", text, icon))
    def operator(self, idname, text="", icon="NONE", emboss=True, depress=False):
        self.log.append(("op", idname, text)); return SimpleNamespace()
'''


def test_the_panel_draws_the_cached_cards_and_the_operators_talk_to_the_server(tmp_path):
    r = run(tmp_path, PRE + '''
log0 = []
CP.draw_cards(Rec(log0))
before = list(calls)
bpy.ops.lampway.cards_refresh()
ST.PUMP.tick()
calls_refresh = list(calls)
calls.clear()
log = []
CP.draw_cards(Rec(log))
draw_calls = list(calls)
bpy.ops.lampway.cards_pin(card_id="boots1", pinned=False)
bpy.ops.lampway.cards_open(card_id="boots1", step=0)
ST.PUMP.tick()
print("RESULT", json.dumps({"empty": [e[1] for e in log0 if e[0] == "label"], "before": before, "refresh": calls_refresh, "draw_calls": draw_calls,
                            "labels": [e[1] for e in log if e[0] == "label"], "ops": [e[1] for e in log if e[0] == "op"], "after": calls, "opened": opened}))
''')
    assert r.rc == 0, r.out[-2500:]
    assert "Error registering class" not in r.out
    d = r.results[0]
    assert d["before"] == [] and "No cards yet: build one with lampway_cards" in d["empty"]
    assert d["refresh"] == [["GET", "/app/cards?status=all", None]]
    assert d["draw_calls"] == [], "draw makes no network call"
    assert "Boots1" in d["labels"] and "Round 4, Motion tests" in d["labels"] and "done" in d["labels"]
    assert d["ops"].count("lampway.cards_open") == 2 and "lampway.cards_pin" in d["ops"]
    assert ["POST", "/app/cards/boots1", {"pinned": False}] in d["after"]
    assert d["opened"] == ["http://127.0.0.1:41234/view/g/2026-10-03_boots1/round-4.html"]
