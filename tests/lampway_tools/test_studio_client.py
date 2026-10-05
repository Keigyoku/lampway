# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The online Studios in the Client: the REST client, the confirm that only a human click can make, the landing of a job's files.
REAL binary. The server is a stand-in thread that records what the Client sends."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
import tempfile

PRE = '''
import bpy, json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
SEEN = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def _rec(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else None
        SEEN.append({"m": self.command, "p": self.path, "auth": self.headers.get("Authorization"), "body": body})
        return body
    def do_GET(self):
        self._rec()
        if self.path.endswith("/files/a.glb"): return self._send(200, b"GLBDATA", "application/octet-stream")
        if self.path == "/app/studio": return self._send(200, {"actions": [{"id": "tripo.mesh", "label": "Smart Mesh", "needs_approval": True, "expected_price": 100}],
            "approvals": [{"id": "ap1", "action": "tripo.mesh", "label": "Smart Mesh", "price": 100, "state": "pending", "settings": {}}], "jobs": [], "engine": {"shelf": True}})
        self._send(200, {"id": "j1", "state": "done", "files": []})
    def do_POST(self):
        body = self._rec()
        if self.path.endswith("/confirm") and body.get("price") != 100: return self._send(409, {"detail": "the price shown was 100, not %s" % body.get("price")})
        self._send(200, {"state": "needs_approval", "id": "j1"})
srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
from mixar.modules.lampway_tools import studio_client as SC
client = SC.StudioClient(f"http://127.0.0.1:{srv.server_port}", lambda: "tok123")
'''


def run(body, **kw):
    return run_script(PRE + body, env={"LAMPWAY_HOME": tempfile.mkdtemp(prefix="lw_home_")}, **kw)


def test_the_client_speaks_the_studio_routes_with_the_users_bearer():
    r = run('''
home = client.home()
plan = client.plan("tripo.mesh", {"front": "a.png"})
conf = client.confirm("ap1", 100)
try:
    client.confirm("ap1", 99); wrong = None
except SC.StudioError as e: wrong = str(e)
client.reject("ap1"); client.job("j1"); client.acknowledge_hung("j1")
blob = client.download("j1", "a.glb")
print("RESULT", json.dumps({"home": home["actions"][0]["id"], "wrong": wrong, "blob": blob.decode(), "seen": [(s["m"], s["p"], s["auth"]) for s in SEEN],
                            "plan_body": SEEN[1]["body"], "conf_body": SEEN[2]["body"]}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["home"] == "tripo.mesh" and "price shown was 100" in o["wrong"] and o["blob"] == "GLBDATA"
    paths = [(m, p) for m, p, a in o["seen"]]
    assert paths == [("GET", "/app/studio"), ("POST", "/app/studio/plan"), ("POST", "/app/studio/approvals/ap1/confirm"),
                     ("POST", "/app/studio/approvals/ap1/confirm"), ("POST", "/app/studio/approvals/ap1/reject"), ("GET", "/app/studio/jobs/j1"),
                     ("POST", "/app/studio/jobs/j1/acknowledge-hung"), ("GET", "/app/studio/jobs/j1/files/a.glb")]
    assert all(a == "Bearer tok123" for _, _, a in o["seen"]) and o["plan_body"] == {"action": "tripo.mesh", "args": {"front": "a.png"}}
    assert o["conf_body"] == {"price": 100}


CONFIRM = '''
from mixar.modules.lampway_tools.ui.operators import studio_ops
calls = []
studio_ops.CLIENT_FACTORY = lambda: type("C", (), {"confirm": lambda s, i, p: calls.append((i, p)) or {"id": "j9"}, "home": lambda s: {"actions": [], "approvals": [], "jobs": []}})()
def attempt():
    try:
        return sorted(bpy.ops.lampway.studio_confirm("EXEC_DEFAULT", approval_id="ap1", price=100))
    except RuntimeError as e:
        return ["REFUSED", str(e)[:200]]
'''


def test_only_a_human_click_confirms_not_an_agent_script_a_worker_or_the_bridge():
    r = run(CONFIRM + '''
from mixar.modules.space_mixie_chat.core.executor import get_executor
from mixar.modules.lampway_tools import bridge
via_agent = get_executor().execute("import bpy\\n__RESULT__ = {'r': str(bpy.ops.lampway.studio_confirm('EXEC_DEFAULT', approval_id='ap1', price=100))}", push_undo=False)
agent_calls = list(calls)
g = {}
bridge.exec_code("import bpy\\ntry:\\n    out = str(bpy.ops.lampway.studio_confirm('EXEC_DEFAULT', approval_id='ap1', price=100))\\nexcept RuntimeError as e:\\n    out = 'REFUSED ' + str(e)[:120]", g)
bridge_calls = list(calls)
direct = attempt()
print("RESULT", json.dumps({"agent_ok": via_agent.success, "agent_err": str(via_agent.error)[:200], "agent_calls": agent_calls, "bridge_out": g.get("out"),
                            "bridge_calls": bridge_calls, "direct": direct, "calls": calls}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["agent_calls"] == [] and o["bridge_calls"] == [], "a script, whoever runs it, never reaches the server"
    assert "REFUSED" in (o["bridge_out"] or "") or "CANCELLED" in (o["bridge_out"] or "")
    assert o["calls"] == [["ap1", 100]] and o["direct"] == ["FINISHED"], "a direct (UI) invocation confirms once"


def test_a_confirm_for_a_different_price_than_the_card_shows_is_refused_by_the_server_and_reported_not_swallowed():
    r = run('''
from mixar.modules.lampway_tools.ui.operators import studio_ops
studio_ops.CLIENT_FACTORY = lambda: client
try:
    bpy.ops.lampway.studio_confirm("EXEC_DEFAULT", approval_id="ap1", price=99); res = "FINISHED"
except RuntimeError as e: res = str(e)[:200]
print("RESULT", json.dumps({"res": res, "msg": bpy.context.scene.lampway_tools.last_message}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert "price shown was 100" in o["res"] and "price shown was 100" in o["msg"]


def test_a_jobs_glb_lands_in_the_studio_collection_with_the_job_prefix():
    r = run('''
import tempfile, os
bpy.ops.mesh.primitive_cube_add(); cube = bpy.context.active_object; cube.name = "src_cube"
path = os.path.join(tempfile.mkdtemp(), "a.glb")
bpy.ops.export_scene.gltf(filepath=path, use_selection=True)
bpy.data.objects.remove(cube)
from mixar.modules.lampway_tools import studio_landing as SL
res = SL.import_file(path, prefix="j1_")
coll = bpy.data.collections.get("Studio")
print("RESULT", json.dumps({"res": res, "in_collection": sorted(o.name for o in coll.objects) if coll else None,
                            "names": sorted(o.name for o in bpy.data.objects if o.name.startswith("j1_"))}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["res"]["objects"] and all(n.startswith("j1_") for n in o["res"]["objects"]) and o["in_collection"] == sorted(o["res"]["objects"])
    assert o["names"] == sorted(o["res"]["objects"])


def test_the_studios_panel_registers_and_refresh_fills_the_state():
    r = run(CONFIRM + '''
from mixar.modules.lampway_tools import studio_state
studio_ops.CLIENT_FACTORY = lambda: client
res = sorted(bpy.ops.lampway.studio_refresh())
print("RESULT", json.dumps({"res": res, "pending": [a["id"] for a in studio_state.STATE["approvals"] if a["state"] == "pending"],
                            "actions": [a["id"] for a in studio_state.STATE["actions"]],
                            "panel": any(c.__name__ == "LAMPWAY_PT_studios" for c in bpy.types.Panel.__subclasses__())}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["res"] == ["FINISHED"] and o["pending"] == ["ap1"] and o["actions"] == ["tripo.mesh"] and o["panel"] is True


PROVIDERS = '''
from mixar.modules.lampway_tools.ui.operators import studio_ops
from mixar.modules.lampway_tools import studio_state
VIEW = {"values": {"provider": "chatgpt_plan", "chatgpt_model": "gpt-6.1-sol", "chatgpt_effort": "medium", "swarm_provider": "claude_cli",
        "claude_swarm_model": "claude-sonnet-5-5", "openrouter_swarm_model": "deepseek/deepseek-v4.1-flash", "image_backend": "openrouter",
        "openrouter_image_model": "openai/gpt-image-2.5-sunburst", "openrouter_image_size": "2880x2880", "openrouter_image_quality": "high",
        "image_purposes": {"plates": {"model": "openai/gpt-image-2.5-flare", "size": "2880x2880"}, "mask": {"model": "google/gemini-3.1-flash-image"},
                           "concept": {"model": "black-forest-labs/flux-3-image", "resolution": "2K"}, "tile": {"model": "openai/gpt-image-2.5-flare", "size": "2048x2048"}}},
        "source": {}, "choices": {"main_providers": ["mock", "chatgpt_plan", "openrouter"], "swarm_providers": ["", "claude_cli", "openrouter"],
        "efforts": ["", "low", "medium", "high"], "image_backends": ["tripo", "openrouter"], "image_qualities": ["", "high"]}}
SAVED = []
class FakeServer:
    def provider_settings(self): return VIEW
    def save_provider_settings(self, values):
        SAVED.append(values)
        if values.get("openrouter_image_size") == "4K": raise studio_ops.studio_client.StudioError("openrouter_image_size: size must be WIDTHxHEIGHT")
        return VIEW
studio_ops.CLIENT_FACTORY = lambda: FakeServer()
'''


def test_the_provider_dialog_loads_the_server_values_and_saves_only_what_changed():
    r = run(PROVIDERS + '''
bpy.ops.lampway.providers_open("INVOKE_DEFAULT") if False else None
op_ok = bpy.ops.lampway.providers_save("EXEC_DEFAULT", main_provider="openrouter", chatgpt_effort="medium", swarm_provider="claude_cli",
                                       image_backend="openrouter", image_model="openai/gpt-image-2.5-flare", image_size="2048x1152", image_quality="high",
                                       plates_size="2160x3840", plates_model="openai/gpt-image-2.5-flare", concept_resolution="4K", mask_model="sourceful/riverflow-v2.5-pro")
try:
    bpy.ops.lampway.providers_save("EXEC_DEFAULT", image_size="4K"); bad = None
except RuntimeError as e: bad = str(e)[:160]
print("RESULT", json.dumps({"ok": sorted(op_ok), "saved": SAVED, "bad": bad, "msg": bpy.context.scene.lampway_tools.last_message,
                            "choices": studio_state.PROVIDERS.get("choices", {}).get("image_backends")}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["ok"] == ["FINISHED"]
    assert o["saved"][0] == {"provider": "openrouter", "openrouter_image_model": "openai/gpt-image-2.5-flare", "openrouter_image_size": "2048x1152",
                             "image_purposes": {"plates": {"size": "2160x3840"}, "concept": {"resolution": "4K"}, "mask": {"model": "sourceful/riverflow-v2.5-pro"}}}, \
        "only the fields that differ from what the server has are sent (the unchanged plates model is not)"
    assert "WIDTHxHEIGHT" in o["bad"] and "WIDTHxHEIGHT" in o["msg"]


def test_a_credit_price_is_sent_exactly_and_a_question_is_answered_only_by_a_click():
    r = run(CONFIRM + '''
class C:
    def __init__(self): self.sent = []
    def confirm(self, i, p, answer=None): self.sent.append((i, p, answer)); return {"id": "j"}
    def home(self): return {"actions": [], "approvals": [], "jobs": []}
c = C(); studio_ops.CLIENT_FACTORY = lambda: c
a = sorted(bpy.ops.lampway.studio_confirm("EXEC_DEFAULT", approval_id="ap1", price=9.6))
b = sorted(bpy.ops.lampway.studio_answer("EXEC_DEFAULT", approval_id="q1", answer=False))
from mixar.modules.lampway_tools import bridge
g = {}
bridge.exec_code("import bpy\\ntry:\\n    bpy.ops.lampway.studio_answer('EXEC_DEFAULT', approval_id='q2', answer=True); out = 'ran'\\nexcept RuntimeError as e:\\n    out = 'REFUSED'", g)
print("RESULT", json.dumps({"a": a, "b": b, "sent": c.sent, "scripted": g["out"]}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["a"] == ["FINISHED"] and o["b"] == ["FINISHED"]
    assert o["sent"] == [["ap1", 9.6, None], ["q1", 0, False]], "9.6 credits are not truncated to 9; an answer carries price 0"
    assert o["scripted"] == "REFUSED", "a script cannot answer the user's question either"


def test_the_higgsfield_sign_in_button_opens_the_servers_page_and_the_panel_shows_a_question_card():
    r = run(CONFIRM + '''
from mixar.modules.lampway_tools import studio_state
opened = []
studio_ops.OPEN_URL = lambda url: opened.append(url) or True
studio_ops.CLIENT_FACTORY = lambda: type("C", (), {"base": lambda s: "http://127.0.0.1:18790"})()
res = sorted(bpy.ops.lampway.higgsfield_signin("EXEC_DEFAULT"))
studio_state.STATE.update(approvals=[{"id": "q1", "state": "pending", "label": "Higgsfield asks: Use unlimited?", "price": 0,
                                      "settings": {"unit": "answer", "question": "Use your unlimited allowance?", "options": [True, False]}}])
cards = studio_state.questions()
print("RESULT", json.dumps({"res": res, "opened": opened, "q": [c["id"] for c in cards], "pending_spends": [a["id"] for a in studio_state.pending()]}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["res"] == ["FINISHED"] and o["opened"] == ["http://127.0.0.1:18790/app/higgsfield"]
    assert o["q"] == ["q1"] and o["pending_spends"] == [], "a question is not a spend: it has its own Yes / No buttons"


def test_the_providers_dialog_carries_the_video_purposes_and_the_cap():
    r = run(PROVIDERS + '''
VIEW["values"]["video_purposes"] = {"bulk": {"model": "heygen/heygen-video-1", "resolution": "768p", "duration": 10},
    "loop": {"model": "bytedance/seedance-1-5-pro", "resolution": "720p", "duration": 5}, "motion": {"model": "bytedance/seedance-2.0-mini", "resolution": "480p", "duration": 5}}
VIEW["values"]["video_max_job_usd"] = 2.0
SAVED.clear()
bpy.ops.lampway.providers_save("EXEC_DEFAULT", video_bulk_resolution="480p", video_bulk_duration="5", video_loop_model="bytedance/seedance-2.0-fast", video_max_job_usd=1.5)
print("RESULT", json.dumps({"saved": SAVED}))
''')
    assert r.rc == 0, r.out[-2500:]
    assert r.results[0]["saved"][0] == {"video_purposes": {"bulk": {"resolution": "480p", "duration": 5}, "loop": {"model": "bytedance/seedance-2.0-fast"}},
                                        "video_max_job_usd": 1.5}


def test_the_providers_dialog_carries_the_spend_policy_per_provider():
    r = run(PROVIDERS + '''
VIEW["values"]["spend_policy"] = {"openrouter": {"click": "off", "job_cap": 2.0}, "higgsfield": {"click": "always"}, "studios": {"click": "always"}, "hyper3d": {"click": "always"}}
SAVED.clear()
bpy.ops.lampway.providers_save("EXEC_DEFAULT", openrouter_click="above", openrouter_above="0.5", openrouter_job_cap="1", openrouter_session_cap="3",
                               higgsfield_job_cap="200", studios_click="always")
bpy.ops.lampway.providers_save("EXEC_DEFAULT", openrouter_job_cap="none")
try:
    bpy.ops.lampway.providers_save("EXEC_DEFAULT", hyper3d_session_cap="lots"); bad = None
except RuntimeError as e: bad = str(e)[:160]
print("RESULT", json.dumps({"saved": SAVED, "bad": bad}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["saved"][0] == {"spend_policy": {"openrouter": {"click": "above", "above": 0.5, "job_cap": 1.0, "session_cap": 3.0}, "higgsfield": {"job_cap": 200.0}}}, "only what differs is sent"
    assert o["saved"][1] == {"spend_policy": {"openrouter": {"job_cap": None}}} and "hyper3d_session_cap" in (o["bad"] or "")
