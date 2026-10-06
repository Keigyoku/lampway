"""Studio REST drivers (specs/studios/{meshy,hyper3d,hi3d,tripo}.md): Meshy, Hyper3D (Rodin), Hi3D (Hitem3D) and Tripo's REST API behind the Studio action registry. Every request shape is [UNVERIFIED] against the
live services and frozen in a LOCAL FAKE SERVER here (the live legs are needs_key). The spend laws: a plan reads the list price and the balance and spends nothing; only the user's confirmed (armed) run creates a
task; a create whose outcome is unknown is NEVER resent; the key never leaves; downloads are hygienic."""
import asyncio
import base64
import http.server
import io
import json
import os
import threading
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from lampway_server.studios import actions as ACT
from lampway_server.studios import toon
from lampway_server.studios.rest import client as RC
from lampway_server.studios.rest import driver as DRV
from lampway_server.studios.rest import shapes as SH
from lampway_server.studios.service import StudioService

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
GLB = b"glTF" + b"\x00" * 60


class Fake(http.server.BaseHTTPRequestHandler):
    log = []
    knobs = {}

    def log_message(self, *a):
        pass

    def _send(self, code, obj=None, raw=None, headers=None):
        body = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("content-length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def _handle(self, method):
        body = self._body()
        path = self.path.split("?")[0]
        Fake.log.append({"method": method, "path": self.path, "auth": self.headers.get("authorization"), "ctype": self.headers.get("content-type"), "len": len(body), "body": body[:4000]})
        k, port = Fake.knobs, self.server.server_port
        base = f"http://127.0.0.1:{port}"
        if path.startswith("/dl/"):
            if k.get("big"):
                return self._send(200, raw=b"x" * 64, headers={"content-length": str(10 ** 12)}) if False else self._big()
            return self._send(200, raw=GLB)
        # ------------------------------------------------------------------ meshy
        if path == "/openapi/v1/balance":
            return self._send(200, {"balance": k.get("balance", 500)} if not k.get("after") else {"balance": k["after"]})
        if method == "POST" and path.startswith("/openapi/"):
            if k.get("create_status"):
                return self._send(k["create_status"], {"message": "NoMorePendingTasks"})
            if k.get("drop_create"):
                self.connection.close()
                return
            return self._send(200, {"result": "mt-1"})
        if method == "GET" and path.startswith("/openapi/") and "/mt-1" in path:
            if k.get("fail"):
                return self._send(200, {"status": "FAILED", "task_error": {"message": "mesh too thin"}})
            n = k.setdefault("polls", 0)
            k["polls"] = n + 1
            if k.get("poll_error") and n < k["poll_error"]:
                return self._send(503, {"message": "busy"})
            if n < k.get("pending", 1):
                return self._send(200, {"status": "IN_PROGRESS", "progress": 40})
            return self._send(200, {"status": "SUCCEEDED", "progress": 100, "model_urls": {"glb": base + "/dl/model.glb", "fbx": base + "/dl/model.fbx"}, "consumed_credits": 30})
        # ------------------------------------------------------------------ hyper3d
        if path == "/api/v2/check_balance":
            return self._send(200, {"balance": k.get("balance", 12.5)})
        if method == "POST" and path in ("/api/v2/rodin", "/api/v2/rodin_texture_only", "/api/v2/bang"):
            return self._send(200, {"uuid": "hu-1", "consumed": 0.5, "jobs": {"subscription_key": "sub-1", "uuids": ["hj-1"]}})
        if method == "POST" and path == "/api/v2/status":
            n = k.setdefault("hpolls", 0)
            k["hpolls"] = n + 1
            return self._send(200, {"jobs": [{"uuid": "hj-1", "status": "Generating" if n < 1 else ("Failed" if k.get("fail") else "Done")}]})
        if method == "POST" and path == "/api/v2/download":
            return self._send(200, {"list": [{"url": base + "/dl/rodin.glb", "name": "rodin.glb"}]})
        # ------------------------------------------------------------------ hi3d
        if method == "POST" and path == "/open-api/v1/auth/token":
            return self._send(200, {"data": {"accessToken": "hi3d-token"}})
        if path == "/open-api/v1/balance":
            return self._send(200, {"data": {"balance": k.get("balance", 1000)}})
        if method == "POST" and path in ("/open-api/v1/submit-task", "/open-api/v1/split/create-task"):
            return self._send(200, {"data": {"task_id": "h3-1"}})
        if method == "GET" and path in ("/open-api/v1/query-task", "/open-api/v1/split/query-task"):
            n = k.setdefault("h3polls", 0)
            k["h3polls"] = n + 1
            return self._send(200, {"data": {"state": "processing" if n < 1 else ("failed" if k.get("fail") else "success"), "url": base + "/dl/hi3d.glb"}})
        # ------------------------------------------------------------------ tripo rest v3
        if path == "/v3/account/balance":
            return self._send(200, {"code": 0, "data": {"balance": k.get("balance", 321)}})
        if method == "POST" and path == "/v3/files":
            return self._send(200, {"code": 0, "data": {"file_token": "ft-1"}})
        if method == "POST" and path.startswith("/v3/") and path != "/v3/tasks/list":
            return self._send(200, {"code": 0, "data": {"task_id": "tk-1"}})
        if method == "GET" and path == "/v3/tasks/tk-1":
            n = k.setdefault("tpolls", 0)
            k["tpolls"] = n + 1
            return self._send(200, {"code": 0, "data": {"status": "running" if n < 1 else ("failed" if k.get("fail") else "success"), "output": {"model": base + "/dl/tripo.glb"}, "consumed_credit": 30}})
        return self._send(404, {"error": "no route " + path})

    def _big(self):
        self.send_response(200)
        self.send_header("content-length", str(2 * 1024 ** 3))
        self.end_headers()


@pytest.fixture
def srv(monkeypatch):
    Fake.log, Fake.knobs = [], {}
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{s.server_port}"
    for name in ("MESHY", "HYPER3D", "HI3D", "TRIPO"):
        monkeypatch.setenv(f"LAMPWAY_STUDIO_REST_BASE_{name}", base)
    monkeypatch.setenv("MESHY_API_KEY", "msy_SECRETKEY0123456789")
    monkeypatch.setenv("HYPER3D_API_KEY", "hy_SECRETKEY0123456789")
    monkeypatch.setenv("HITEM3D_CLIENT_ID", "cid-SECRET")
    monkeypatch.setenv("HITEM3D_CLIENT_SECRET", "csec-SECRET0123456789")
    monkeypatch.setenv("TRIPO_API_KEY", "tsk_SECRETKEY0123456789")
    monkeypatch.setenv("LAMPWAY_STUDIO_POLL_S", "0")
    monkeypatch.delenv("LAMPWAY_STUDIO_ARMED", raising=False)
    yield base
    s.shutdown()


def drive(argv, armed=False, env_extra=None):
    out = io.StringIO()
    env = dict(os.environ)
    if armed:
        env["LAMPWAY_STUDIO_ARMED"] = "1"
    env.update(env_extra or {})
    with redirect_stdout(out):
        rc = DRV.main(argv, env=env)
    return rc, out.getvalue(), toon.parse(out.getvalue())


def fix(args, files):
    """Rewrite file-name values (and lists of them) to absolute paths in the fixture folder."""
    f = lambda v: str(files / v) if isinstance(v, str) and (files / v).is_file() else v  # noqa: E731
    return {k: ([f(x) for x in v] if isinstance(v, list) else f(v)) for k, v in args.items()}


def creates():
    return [r for r in Fake.log if r["method"] == "POST" and not r["path"].endswith(("/auth/token", "/status", "/download", "/v3/files"))]


@pytest.fixture
def files(tmp_path):
    (tmp_path / "plate.png").write_bytes(PNG)
    (tmp_path / "back.png").write_bytes(PNG)
    (tmp_path / "piece.glb").write_bytes(GLB)
    return tmp_path


CASES = {
    "meshy.image_to_3d": ({"image": "plate.png", "texture": True, "texture_resolution": "2k"}, 30),
    "meshy.multi_image_to_3d": ({"images": ["plate.png", "back.png"], "texture": True, "texture_resolution": "4k"}, 30),
    "meshy.text_to_3d": ({"prompt": "a bronze helmet", "mode": "preview"}, 20),
    "meshy.remesh": ({"model": "piece.glb", "topology": "quad", "target_polycount": 20000}, 5),
    "meshy.uv_unwrap": ({"model": "piece.glb"}, 5),
    "meshy.retexture": ({"model": "piece.glb", "text_style_prompt": "worn bronze", "texture_resolution": "2k"}, 10),
    "hyper3d.texture_only": ({"model": "piece.glb", "image": "plate.png", "material": "PBR", "resolution": "Basic"}, 0.5),
    "hyper3d.generate": ({"images": ["plate.png"], "tier": "Gen-2.5-Medium", "mesh_mode": "Quad", "accept_up_to_credits": 5}, None),
    "hyper3d.bang": ({"model": "piece.glb", "image": "plate.png", "strength": 5, "accept_up_to_credits": 5}, None),
    "hi3d.image_to_3d": ({"images": ["plate.png"], "model": "hi3dv3.0", "resolution": "2048quality", "pbr": True}, 65),
    "hi3d.texture_only": ({"model": "piece.glb", "image": "plate.png", "pbr": True}, 15),
    "hi3d.split": ({"model": "piece.glb", "mode": "general", "level": "medium"}, 20),
    "tripo.rest.image_to_model": ({"image": "plate.png", "accept_up_to_credits": 40}, None),
    "tripo.rest.texture": ({"model": "piece.glb", "quality": "detailed"}, 20),
    "tripo.rest.decimate": ({"model": "piece.glb", "version": "2.0", "face_limit": 20000}, 30),
}


@pytest.mark.parametrize("action", sorted(CASES))
def test_a_plan_reads_the_list_price_and_the_balance_spends_nothing_and_marks_unknown_prices(srv, files, action):
    args, price = CASES[action]
    rc, text, p = drive([action, "--plan", "--args", json.dumps(fix(args, files))])
    assert rc == 0 and p.error is None, text
    assert p.kv["dry_run"] == "verified" and p.kv["unit"] == "credits" and (("list price" in str(p.kv["price_source"])) if price is not None else ("unknown" in str(p.kv["price_source"])))
    assert (p.kv["price_credits"] == price) if price is not None else (p.kv["price_credits"] is None and p.kv["price_ceiling_credits"] == args["accept_up_to_credits"])
    assert p.kv["balance_credits"] is not None and creates() == []
    assert not any(r["method"] == "POST" and "/auth" not in r["path"] and r["path"] != "/v3/files" for r in Fake.log)


def test_an_unpublished_price_is_never_waved_through_without_the_users_ceiling(srv, files):
    rc, text, p = drive(["hyper3d.generate", "--plan", "--args", json.dumps({"images": [str(files / "plate.png")]})])
    assert rc != 0 and "not published" in text and "accept_up_to_credits" in text and creates() == []


def test_an_unarmed_run_refuses_and_sends_nothing_and_an_armed_run_creates_polls_downloads_and_reports_the_credits(srv, files):
    args = json.dumps({"image": str(files / "plate.png"), "texture": True, "texture_resolution": "2k"})
    rc, text, p = drive(["meshy.image_to_3d", "--run", "--out", str(files / "out"), "--args", args], armed=False)
    assert rc != 0 and "guard is not armed" in text and creates() == []
    rc, text, p = drive(["meshy.image_to_3d", "--run", "--out", str(files / "out"), "--args", args], armed=True)
    assert rc == 0 and p.error is None, text
    assert p.kv["status"] == "SUCCEEDED" and p.kv["consumed_credits"] == 30 and p.kv["balance_before"] == 500 and p.kv["task_id"] == "mt-1"
    rows = p.tables["files"]
    assert len(rows) == 2 and all(Path(r["path"]).read_bytes() == GLB for r in rows) and all(len(str(r["sha256"])) == 64 for r in rows)
    assert len(creates()) == 1 and creates()[0]["auth"] == "Bearer msy_SECRETKEY0123456789"
    body = json.loads(creates()[0]["body"])
    assert body["image_url"].startswith("data:image/png;base64,") and body["should_texture"] is True and body["texture_resolution"] == "2k" and body["ai_model"] == "meshy-7.1"
    assert "SECRETKEY" not in text and "http" not in text                                           # no key and no signed URL in what is printed


def test_a_create_whose_outcome_is_unknown_is_never_resent_and_the_error_says_so(srv, files):
    Fake.knobs["drop_create"] = True
    args = json.dumps({"image": str(files / "plate.png")})
    rc, text, p = drive(["meshy.image_to_3d", "--run", "--out", str(files / "o"), "--args", args], armed=True)
    assert rc != 0 and "outcome is unknown" in text and "not resent" in text.lower()
    assert len(creates()) == 1


def test_a_full_queue_is_not_created_and_not_retried_and_a_failed_task_reports_the_providers_reason(srv, files):
    Fake.knobs["create_status"] = 429
    args = json.dumps({"image": str(files / "plate.png")})
    rc, text, p = drive(["meshy.image_to_3d", "--run", "--out", str(files / "o"), "--args", args], armed=True)
    assert rc != 0 and "queue is full" in text and "nothing was created" in text and len(creates()) == 1
    Fake.knobs.clear()
    Fake.log.clear()
    Fake.knobs["fail"] = True
    rc, text, p = drive(["meshy.image_to_3d", "--run", "--out", str(files / "o2"), "--args", args], armed=True)
    assert rc != 0 and "mesh too thin" in text and not (files / "o2").exists() or not list((files / "o2").glob("*"))


def test_polling_survives_transient_errors_and_gives_up_naming_the_task_so_it_is_never_resubmitted(srv, files):
    Fake.knobs["poll_error"] = 2
    args = json.dumps({"image": str(files / "plate.png")})
    rc, text, p = drive(["meshy.image_to_3d", "--run", "--out", str(files / "o"), "--args", args], armed=True)
    assert rc == 0 and p.kv["status"] == "SUCCEEDED" and len(creates()) == 1
    Fake.knobs.clear(); Fake.log.clear()
    Fake.knobs["poll_error"] = 10 ** 6
    rc, text, p = drive(["meshy.image_to_3d", "--run", "--out", str(files / "o3"), "--args", args], armed=True)
    assert rc != 0 and "mt-1" in text and "poll it later" in text and len(creates()) == 1


@pytest.mark.parametrize("studio,key_vars,action,args", [
    ("meshy", ("MESHY_API_KEY",), "meshy.uv_unwrap", {"model": "piece.glb"}),
    ("hyper3d", ("HYPER3D_API_KEY",), "hyper3d.texture_only", {"model": "piece.glb", "image": "plate.png"}),
    ("hi3d", ("HITEM3D_CLIENT_ID", "HITEM3D_CLIENT_SECRET"), "hi3d.split", {"model": "piece.glb"}),
    ("tripo", ("TRIPO_API_KEY",), "tripo.rest.decimate", {"model": "piece.glb"}),
])
def test_a_missing_key_is_needs_key_before_any_request_and_a_key_file_must_be_owner_only(srv, files, monkeypatch, studio, key_vars, action, args):
    full = {k: (str(files / v) if k in ("model", "image") else v) for k, v in args.items()}
    for k in key_vars:
        monkeypatch.delenv(k)
    n = len(Fake.log)
    rc, text, p = drive([action, "--plan", "--args", json.dumps(full)])
    assert rc != 0 and "needs_key" in text and len(Fake.log) == n
    kf = files / "key"
    kf.write_text("hy_FILEKEY0123456789\n" if studio != "hi3d" else "id\nsecret\n")
    kf.chmod(0o644)
    monkeypatch.setenv(key_vars[0] + "_FILE", str(kf))
    rc, text, p = drive([action, "--plan", "--args", json.dumps(full)])
    assert rc != 0 and "owner-only" in text
    kf.chmod(0o600)
    if studio != "hi3d":
        rc, text, p = drive([action, "--plan", "--args", json.dumps(full)])
        assert rc == 0 and "FILEKEY" not in text


def test_the_base_url_override_is_loopback_only(monkeypatch, files):
    monkeypatch.setenv("LAMPWAY_STUDIO_REST_BASE_MESHY", "https://evil.example/")
    monkeypatch.setenv("MESHY_API_KEY", "msy_x" * 6)
    with pytest.raises(RC.StudioError, match="loopback"):
        RC.RestStudio(SH.STUDIOS["meshy"], dict(os.environ))
    monkeypatch.delenv("LAMPWAY_STUDIO_REST_BASE_MESHY")
    assert RC.RestStudio(SH.STUDIOS["meshy"], dict(os.environ)).base == "https://api.meshy.ai"


def test_downloads_are_hygienic_https_only_unless_loopback_override_a_size_cap_and_no_part_files(srv, files, monkeypatch):
    st = RC.RestStudio(SH.STUDIOS["meshy"], dict(os.environ))
    d = files / "dl"
    got = st.download("http://127.0.0.1:%d/dl/model.glb" % int(srv.rsplit(":", 1)[1]), d, "model.glb")
    assert (d / "model.glb").read_bytes() == GLB and not list(d.glob("*.part")) and len(got["sha256"]) == 64
    monkeypatch.delenv("LAMPWAY_STUDIO_REST_BASE_MESHY")
    plain = RC.RestStudio(SH.STUDIOS["meshy"], dict(os.environ))
    with pytest.raises(RC.StudioError, match="https only"):
        plain.download("http://assets.meshy.ai/x.glb", d, "x.glb")
    with pytest.raises(RC.StudioError, match="userinfo"):
        plain.download("https://u:p" "@assets.meshy.ai/x.glb", d, "x.glb")
    Fake.knobs["big"] = True
    with pytest.raises(RC.StudioError, match="512 MB"):
        st.download("http://127.0.0.1:%d/dl/big.glb" % int(srv.rsplit(":", 1)[1]), d, "big.glb")
    assert not list(d.glob("big*"))


@pytest.mark.parametrize("action,args,auth_checks", [
    ("hyper3d.texture_only", {"model": "piece.glb", "image": "plate.png", "material": "PBR", "resolution": "Basic"}, ["/api/v2/rodin_texture_only", "/api/v2/status", "/api/v2/download"]),
    ("hi3d.image_to_3d", {"images": ["plate.png"], "model": "hi3dv3.0", "resolution": "2048quality", "pbr": True}, ["/open-api/v1/auth/token", "/open-api/v1/submit-task", "/open-api/v1/query-task"]),
    ("tripo.rest.texture", {"model": "piece.glb", "quality": "detailed"}, ["/v3/files", "/v3/models/texture", "/v3/tasks/tk-1"]),
])
def test_each_other_studios_lifecycle_runs_end_to_end_with_its_own_auth_and_ids(srv, files, action, args, auth_checks):
    full = fix(args, files)
    rc, text, p = drive([action, "--run", "--out", str(files / "o"), "--args", json.dumps(full)], armed=True)
    assert rc == 0 and p.error is None, text
    paths = [r["path"].split("?")[0] for r in Fake.log]
    for need in auth_checks:
        assert need in paths, (need, paths)
    assert p.tables["files"] and all((Path(r["path"])).exists() for r in p.tables["files"]) and "SECRET" not in text
    if action.startswith("hi3d"):
        tok = next(r for r in Fake.log if r["path"].endswith("/auth/token"))
        assert tok["auth"].startswith("Basic ") and base64.b64decode(tok["auth"][6:]).decode() == "cid-SECRET:csec-SECRET0123456789"
        assert next(r for r in Fake.log if r["path"].endswith("/submit-task"))["auth"] == "Bearer hi3d-token"


def test_parameters_are_validated_before_any_request(srv, files):
    for action, args, msg in (("meshy.image_to_3d", {"image": str(files / "plate.png"), "texture_resolution": "16k"}, "texture_resolution"),
                              ("meshy.multi_image_to_3d", {"images": []}, "1 to 4"),
                              ("hyper3d.bang", {"model": str(files / "piece.glb"), "image": str(files / "plate.png"), "strength": 99}, "strength"),
                              ("meshy.remesh", {"model": str(files / "nope.glb")}, "not a file"),
                              ("hi3d.image_to_3d", {"images": [str(files / "plate.png")], "model": "hi9"}, "model")):
        n = len(Fake.log)
        rc, text, p = drive([action, "--plan", "--args", json.dumps(args)])
        assert rc != 0 and msg in text and len(Fake.log) == n, (action, text)
    rc, text, p = drive(["meshy.nope", "--plan", "--args", "{}"])
    assert rc != 0 and "no such action" in text


# ------------------------------------------------------------------------------------------- the Studio service
def make_exec():
    def execute(argv, env, timeout):
        i = argv.index("lampway_server.studios.rest.driver")
        out = io.StringIO()
        with redirect_stdout(out):
            rc = DRV.main(argv[i + 1:], env=env)
        return rc, out.getvalue()
    return execute


def test_the_actions_are_in_the_registry_need_approval_and_run_through_the_service_only_after_the_users_confirm(srv, files):
    for aid in CASES:
        assert aid in ACT.ACTIONS and ACT.ACTIONS[aid].needs_approval and ACT.ACTIONS[aid].studio == aid.split(".")[0]
    svc = StudioService(files, execute=make_exec())

    async def go():
        plan = await svc.plan("meshy.image_to_3d", {"image": "plate.png", "texture": True, "texture_resolution": "2k"}, "agent")
        assert plan["state"] == "needs_approval" and plan["approval"]["price"] == 30 and creates() == []
        assert plan["approval"]["settings"]["unit"] == "credits" and "list price" in plan["approval"]["settings"]["price_source"]
        with pytest.raises(Exception, match="only the user"):
            await svc.confirm(plan["approval"]["id"], 30, by="agent")
        with pytest.raises(Exception, match="not 31"):
            await svc.confirm(plan["approval"]["id"], 31, by="captain")
        job = await svc.confirm(plan["approval"]["id"], 30, by="captain")
        done = await svc.wait(job["id"])
        return plan, done
    plan, done = asyncio.run(go())
    assert done["state"] == "done" and done["kv"]["consumed_credits"] == 30 and len(creates()) == 1 and done["tables"]["files"]
    refused = asyncio.run(svc.plan("meshy.image_to_3d", {"image": "nope.png"}, "agent")) if False else None
    with pytest.raises(ACT.ActionError, match="not a file"):
        asyncio.run(svc.plan("meshy.image_to_3d", {"image": "nope.png"}, "agent"))


def test_an_unpublished_price_through_the_service_needs_the_users_ceiling_which_becomes_the_approved_price(srv, files):
    svc = StudioService(files, execute=make_exec())
    r = asyncio.run(svc.plan("hyper3d.generate", {"images": ["plate.png"]}, "agent"))
    assert r["state"] == "refused" and "not published" in r["reason"]
    r = asyncio.run(svc.plan("hyper3d.generate", {"images": ["plate.png"], "accept_up_to_credits": 5}, "agent"))
    assert r["state"] == "needs_approval" and r["approval"]["price"] == 5 and r["approval"]["settings"]["ceiling_credits"] == 5
