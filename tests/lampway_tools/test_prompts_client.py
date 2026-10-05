import tempfile
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The prompt library in the Client: a template picker with a variable form generated from the schema, a rendered preview, "edit as my own" (fork to user scope
with the next version), the user's 1-5 rating, and the Video Gen / Image Gen surfaces carrying template + variables on the job. REAL binary; the server is a
stand-in thread that records what the Client sends."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

TEMPLATE = {"id": "anim-walk-side-track", "version": "1.0.0", "title": "Walk cycle: side tracking shot", "media": "video", "purpose": "anim-walk", "scope": "builtin",
            "description": "d", "versions": ["1.0.0"],
            "body": {"subject": "S {{design_lock}}", "action": "A {{cadence_spm}} {{direction}} {{fast}}", "camera": "C", "style": "St", "constraints": "Co"},
            "variables": {"design_lock": {"type": "string", "default": "bronze armour", "description": "the design"},
                          "cadence_spm": {"type": "integer", "default": 110, "min": 60, "max": 160, "description": "steps per minute"},
                          "direction": {"type": "enum", "default": "right", "enum": ["left", "right"], "description": "way"},
                          "fast": {"type": "boolean", "default": False, "description": "faster"}},
            "negatives": ["no cuts"], "inputs": {}, "defaults": {"model": "heygen/heygen-video-1"}, "model_adapters": {}, "gates": [], "provenance": {"source": "t"}}

PRE = '''
import bpy, json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
TEMPLATE = json.loads(%r)
SEEN = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def _rec(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else None
        SEEN.append({"m": self.command, "p": self.path, "auth": self.headers.get("Authorization"), "body": body})
        return body
    def do_GET(self):
        self._rec()
        if self.path.startswith("/app/prompts/anim"): return self._send(200, TEMPLATE)
        self._send(200, {"templates": [{k: TEMPLATE[k] for k in ("id", "version", "title", "description", "purpose", "media", "scope")}], "errors": []})
    def do_POST(self):
        b = self._rec()
        if self.path == "/app/prompts/render":
            v = b.get("variables") or {}
            if v.get("cadence_spm", 0) > 160: return self._send(400, {"detail": "cadence_spm: 200 is above the max 160"})
            return self._send(200, {"prompt": "RENDERED " + json.dumps(v, sort_keys=True), "template": "anim-walk-side-track@1.0.0", "variables": v, "params": {"model": "heygen/heygen-video-1"}, "warnings": [], "negatives": ["no cuts"], "inputs_required": []})
        self._send(200, {"ok": True})
    def do_PUT(self):
        self._rec(); self._send(200, {"saved": "/x/y.json", "scope": "user"})
srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
from mixar.modules.lampway_tools import studio_client as SC
from mixar.modules.lampway_tools.ui.operators import studio_ops, prompt_ops
studio_ops.CLIENT_FACTORY = lambda: SC.StudioClient(f"http://127.0.0.1:{srv.server_port}", lambda: "tok123")
P = bpy.context.scene.lampway_tools
''' % json.dumps(TEMPLATE)


def run(body, **kw):
    return run_script(PRE + body, env={"LAMPWAY_HOME": tempfile.mkdtemp(prefix="lw_home_")}, **kw)


def test_the_picker_lists_templates_and_loading_one_builds_the_form_from_the_schema():
    r = run('''
r1 = sorted(bpy.ops.lampway.prompts_refresh())
P.prompt_template = "anim-walk-side-track"
r2 = sorted(bpy.ops.lampway.prompt_load())
rows = [{"name": v.name, "kind": v.kind, "value": v.value, "min": v.vmin, "max": v.vmax, "choices": v.choices, "help": v.help} for v in P.prompt_vars]
print("RESULT", json.dumps({"r1": r1, "r2": r2, "rows": rows, "paths": [(s["m"], s["p"], s["auth"]) for s in SEEN]}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["r1"] == ["FINISHED"] and o["r2"] == ["FINISHED"] and ("GET", "/app/prompts", "Bearer tok123") in [tuple(x) for x in o["paths"]]
    rows = {x["name"]: x for x in o["rows"]}
    assert set(rows) == {"design_lock", "cadence_spm", "direction", "fast"}
    assert rows["cadence_spm"]["kind"] == "integer" and rows["cadence_spm"]["value"] == "110" and rows["cadence_spm"]["min"] == 60 and rows["cadence_spm"]["max"] == 160
    assert rows["direction"]["kind"] == "enum" and rows["direction"]["choices"] == "left|right" and rows["fast"]["kind"] == "boolean" and rows["fast"]["value"] == "false"


def test_the_preview_renders_through_the_server_with_typed_values_and_a_refusal_is_shown():
    r = run('''
bpy.ops.lampway.prompts_refresh(); P.prompt_template = "anim-walk-side-track"; bpy.ops.lampway.prompt_load()
next(v for v in P.prompt_vars if v.name == "cadence_spm").value = "120"
next(v for v in P.prompt_vars if v.name == "fast").value = "true"
bpy.ops.lampway.prompt_preview()
ok = P.prompt_preview
next(v for v in P.prompt_vars if v.name == "cadence_spm").value = "200"
try:
    bpy.ops.lampway.prompt_preview(); refused = None
except RuntimeError as e: refused = str(e)[:200]
sent = [s["body"] for s in SEEN if s["p"] == "/app/prompts/render"]
print("RESULT", json.dumps({"ok": ok, "refused": refused, "msg": P.last_message, "sent": sent}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert '"cadence_spm": 120' in o["ok"] and '"fast": true' in o["ok"] and '"direction": "right"' in o["ok"]
    assert o["sent"][0]["variables"]["cadence_spm"] == 120 and isinstance(o["sent"][0]["variables"]["cadence_spm"], int) and o["sent"][0]["id"] == "anim-walk-side-track"
    assert "above the max 160" in o["refused"] and "above the max 160" in o["msg"]


def test_edit_as_my_own_forks_to_the_user_scope_with_the_next_version():
    r = run('''
bpy.ops.lampway.prompts_refresh(); P.prompt_template = "anim-walk-side-track"; bpy.ops.lampway.prompt_load()
bpy.ops.lampway.prompt_fork()
put = next(s for s in SEEN if s["m"] == "PUT")
print("RESULT", json.dumps({"put": put["body"]["template"], "msg": P.last_message}))
''')
    assert r.rc == 0, r.out[-2500:]
    t = r.results[0]["put"]
    assert t["id"] == "anim-walk-side-track" and t["version"] == "1.0.1" and t["title"].startswith("My ") and "scope" not in t and "versions" not in t
    assert t["body"] == TEMPLATE["body"] and t["provenance"]["note"].startswith("forked from anim-walk-side-track@1.0.0")


def test_using_a_template_attaches_it_to_the_job_only_while_the_prompt_is_unchanged_and_rating_is_sent():
    r = run('''
from mixar.modules.lampway_tools import prompt_attach as PA
bpy.ops.lampway.prompts_refresh(); P.prompt_template = "anim-walk-side-track"; bpy.ops.lampway.prompt_load()
bpy.ops.lampway.prompt_preview(); bpy.ops.lampway.prompt_use()
same = {"prompt": P.prompt_preview}; PA.attach_to(same, P.prompt_preview, bpy.context.scene)
edited = {"prompt": "my own words"}; PA.attach_to(edited, "my own words", bpy.context.scene)
P.prompt_job_id = "job-9"; P.prompt_rating = 4; P.prompt_note = "good stride"
bpy.ops.lampway.prompt_rate()
rate = next(s for s in SEEN if s["p"] == "/app/prompts/rate")
print("RESULT", json.dumps({"same": same.get("template"), "edited": edited.get("template"), "rate": rate["body"]}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["same"]["id"] == "anim-walk-side-track" and o["same"]["variables"]["cadence_spm"] == 110 and o["edited"] is None
    assert o["rate"] == {"job_id": "job-9", "rating": 4, "note": "good stride"}


def test_the_prompts_panel_and_the_surface_hooks_exist():
    r = run('''
import inspect
from mixar.modules.moodboard.ui.operators import video_gen_ops, imagegen_ops
print("RESULT", json.dumps({"panel": any(c.__name__ == "LAMPWAY_PT_prompts" for c in bpy.types.Panel.__subclasses__()),
    "video": "prompt_attach" in inspect.getsource(video_gen_ops), "image": inspect.getsource(imagegen_ops).count("prompt_attach")}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["panel"] is True and o["video"] is True and o["image"] >= 2
