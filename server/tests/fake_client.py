"""A fake Mixar desktop client.

It speaks the frames the real client sends, as read from the client source
(see audit/protocol.json): the form login (auth.py:319-334), the PKCE desktop
SSO (sso.py:146-215), the REST headers (client.py:177-211), the agent
WebSocket handshake (socket_connection.py:266-342), the agent.chat command
(agent_rpc/client.py:38-41 + chat_payloads.py), and the blender.execute_script
reply envelope (executor_result.py:30-66). It never contains an LLM.
"""

import base64
import hashlib
import json
import secrets
import uuid
from urllib.parse import parse_qs, urlparse

INSTANCE_CAPABILITIES = [
    "agent_history_v1", "agent_history_v2", "script_execution", "forest_runtime_v1",
    "terrain_raycast_v1", "inspection_preview_v1", "notifications", "local_llm",
    "liveness", "mcp_operations_v1", "mixar_ui_v1", "addon_project_v1",
    "addon_project_tests_v1", "addon_project_verify_v1", "context_folder_v1",
    "exec_envelope_v3", "task_binding_v1", "operation_receipts_v1",
    "native_artifacts_v1", "document_epoch_v1", "runtime_questions_v1",
]

LOOPBACK_PORT = 51731


def pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


def decode_jwt_claims(token):
    encoded = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))


class FakeMixarClient:
    def __init__(self, http, *, password, username="owner@lampway.local"):
        self.http = http
        self.username = username
        self.password = password
        self.device_id = hashlib.sha256(b"mixar-device-v1:fake-machine").hexdigest()[:32]
        self.instance_id = str(uuid.uuid4())
        self.access_token = None
        self.refresh_token = None
        self._req = 0

    # ------------------------------------------------------------------ REST
    def rest_headers(self, token=None):
        headers = {
            "Accept": "application/json",
            "X-Client-Version": "5.2.0",
            "x-telemetry-consent": "1",
            "X-Mixar-Locale": "en_US",
        }
        token = token or self.access_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def get(self, path, **kwargs):
        headers = {**self.rest_headers(), **kwargs.pop("headers", {})}
        return self.http.get(path, headers=headers, **kwargs)

    def put(self, path, **kwargs):
        headers = {**self.rest_headers(), **kwargs.pop("headers", {})}
        return self.http.put(path, headers=headers, **kwargs)

    def post(self, path, **kwargs):
        headers = {**self.rest_headers(), **kwargs.pop("headers", {})}
        return self.http.post(path, headers=headers, **kwargs)

    def delete(self, path, **kwargs):
        headers = {**self.rest_headers(), **kwargs.pop("headers", {})}
        return self.http.delete(path, headers=headers, **kwargs)

    def _store(self, data):
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        return data

    def login_form(self):
        """Dev-bypass route: POST /api/v1/auth/login, x-www-form-urlencoded (auth.py:319-334)."""
        response = self.http.post(
            "/api/v1/auth/login",
            headers={"Content-Type": "application/x-www-form-urlencoded", "accept": "application/json"},
            data={"username": self.username, "password": self.password, "device_id": self.device_id},
        )
        return response

    def login_pkce(self, *, password=None, state=None, port=LOOPBACK_PORT):
        """Browser SSO as the client drives it (sso.py:154-215), the browser hop
        replaced by following the server's redirect by hand. Returns the token
        exchange response."""
        verifier, challenge = pkce_pair()
        state = state or base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
        page = self.http.get(
            "/app/desktop-login",
            params={"port": port, "code_challenge": challenge,
                    "code_challenge_method": "S256", "state": state, "source": "desktop"},
            follow_redirects=False,
        )
        if page.status_code == 200:
            # A password-guarded page: submit the form.
            page = self.http.post(
                "/app/desktop-login",
                data={"port": port, "code_challenge": challenge,
                      "code_challenge_method": "S256", "state": state,
                      "source": "desktop",
                      "password": self.password if password is None else password},
                follow_redirects=False,
            )
        self.last_login_page = page
        if page.status_code not in (302, 303):
            return page
        location = urlparse(page.headers["location"])
        assert location.scheme == "http" and location.netloc == f"127.0.0.1:{port}", page.headers["location"]
        query = parse_qs(location.query)
        self.callback_state = query.get("state", [None])[0]
        code = query["code"][0]
        return self.exchange_code(code, verifier)

    def exchange_code(self, code, verifier):
        return self.http.post(
            "/api/v1/auth/desktop/token",
            content=json.dumps({"code": code, "code_verifier": verifier, "device_id": self.device_id}),
            headers={"Content-Type": "application/json", "accept": "application/json"},
        )

    def refresh(self, idempotency_key=None, refresh_token=None):
        return self.http.post(
            "/api/v1/auth/refresh",
            content=json.dumps({"refresh_token": refresh_token or self.refresh_token}),
            headers={"Content-Type": "application/json", "accept": "application/json",
                     "Idempotency-Key": idempotency_key or str(uuid.uuid4())},
        )

    def login(self):
        response = self.login_form()
        assert response.status_code == 200, response.text
        return self._store(response.json())

    # ------------------------------------------------------------- WebSocket
    def next_id(self, prefix):
        self._req += 1
        return f"{prefix}_{self._req}"

    def connect_ws(self, token=None):
        token = token or self.access_token
        headers = {"x-telemetry-consent": "1", "X-Mixar-Locale": "en_US"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # Starlette's TestClient opens WebSockets against "testserver" whatever the base_url; name the host the server
        # answers to (the host guard refuses the rest).
        headers = {**headers, "host": "127.0.0.1:8787"}
        return self.http.websocket_connect(f"/api/agent/ws/{self.instance_id}", headers=headers)

    def handshake_frame(self):
        return {
            "jsonrpc": "2.0",
            "method": "system.handshake",
            "id": self.next_id("handshake"),
            "params": {
                "blender_version": "5.2.0",
                "addon_version": "5.2.0",
                "capabilities": list(INSTANCE_CAPABILITIES),
                "machine": {"memory_bytes": 34359738368, "gpu_memory_bytes": None, "platform": "linux"},
                "device_id": self.device_id,
            },
        }

    def handshake(self, ws):
        frame = self.handshake_frame()
        ws.send_json(frame)
        reply = ws.receive_json()
        assert reply["id"] == frame["id"], reply
        return reply

    def request(self, ws, method, params=None, prefix="req"):
        frame = {"jsonrpc": "2.0", "method": method, "id": self.next_id(prefix)}
        if params is not None:
            frame["params"] = params
        ws.send_json(frame)
        return frame["id"]

    def command(self, ws, method, payload):
        """agent_rpc.client.command: params = {command_id, payload}."""
        command_id = str(uuid.uuid4())
        self.last_request_id = self.request(ws, "agent." + method, {"command_id": command_id, "payload": payload})
        return command_id

    def chat_payload(self, message, session_id):
        return {
            "message": message,
            "instance_id": self.instance_id,
            "session_id": session_id,
            "plan_required": True,
            "execution_required": True,
            "approval_required": True,
            "rules": {"project": [], "global": []},
            "folder_context": {"folders": []},
        }

    @staticmethod
    def execute_script_result(script, *, success=True, output="", created=None, error=None):
        """The envelope executor_result.to_dict produces (only present keys)."""
        result = {"success": success}
        if output:
            result["output"] = output
        if created:
            result["created_objects"] = list(created)
        if error:
            result["error"] = error
        return result

    def run_turn(self, ws, command_id, *, on_script, max_frames=500):
        """Drive one turn: answer blender.execute_script requests through
        ``on_script(params) -> result dict``; collect everything else. Stops at
        agent.turn.ended for this command (turn_id == command_id)."""
        frames = []
        for _ in range(max_frames):
            frame = ws.receive_json()
            frames.append(frame)
            if "error" in frame:
                raise AssertionError(f"server answered an error during turn {command_id}: {frame!r}")
            if frame.get("method") == "blender.execute_script" and frame.get("id"):
                ws.send_json({"jsonrpc": "2.0", "id": frame["id"], "result": on_script(frame["params"])})
            if frame.get("method") == "agent.turn.ended" and frame["params"].get("turn_id") == command_id:
                return frames
        raise AssertionError(f"turn {command_id} never ended; frames={frames!r}")
