# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""C1: only the new wrapper tools opt into typed, TOON MCP replies."""
import asyncio
import base64
import json
from copy import deepcopy
from types import SimpleNamespace

import jsonschema
import pytest

from lampway_server import mcp as M
from lampway_server.agent.providers.base import ToolSpec
from .test_mcp_operation_lease import Agent, GatedClient


class EnvelopeClient(GatedClient):
    """Main's fake client gates every response before returning envelope data."""

    def __init__(self, answer):
        super().__init__(scene_session="scene")
        self.answer = answer
        self.frames = []

    async def request(self, method, params, timeout=None):
        self.frames.append((method, deepcopy(params)))
        reply = await super().request(method, params, timeout)
        if method == "blender.execute_script" and reply.get("success"):
            return dict(self.answer)
        return reply


@pytest.fixture
def wrapper(monkeypatch):
    spec = ToolSpec("lampway_inspect", "Read the scene", {
        "type": "object", "additionalProperties": False,
        "properties": {"view": {"type": "string"}, "name": {"type": "string"}, "full": {"type": "boolean"}}})
    monkeypatch.setattr(M, "offered_tools", lambda: [spec])
    monkeypatch.setattr(M, "script_for", lambda name, args: "one safe script")
    answer = {"success": True, "ok": True, "view": "mesh", "scene": "Scene",
              "count": 0, "total": 0, "data": {"holes": []}, "skipped": [],
              "help": ["lampway_inspect view=help name=mesh"]}

    client = EnvelopeClient(answer)
    server = M.McpServer(SimpleNamespace(sockets={"app": client}), Agent())
    yield server, answer
    assert client.leases == {}, "every wrapper success/failure must release its scene"



def call(server, arguments=None, session="scene"):
    client = server.hub.sockets.get("app")
    before = len(client.frames) if client is not None else 0
    result = asyncio.run(server.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                                       "params": {"name": "lampway_inspect", "arguments": arguments or {}}}, "app", session))["result"]
    frames = client.frames[before:] if client is not None else []
    if len(frames) > 1:
        assert [method for method, _ in frames] == [
            "mcp.begin_operation", "blender.execute_script", "mcp.end_operation"]
        begin, script, end = [params for _, params in frames]
        assert script["script"] == "one safe script"
        assert script["tool_name"] == "lampway_inspect"
        assert begin["session_id"] == session
        assert script["session_id"] == script["agent_ctx"]["chat_session_id"] == end["session_id"] == client.scene_session
        assert begin["operation_id"] == script["agent_ctx"]["mcp_operation_id"] == end["operation_id"]
        assert script["agent_ctx"]["turn_id"] == "mcp"
        assert script["agent_ctx"]["call_id"] == result["_meta"]["call_id"]
        assert client.leases == {}
    return result


def test_new_tools_offer_output_schema(wrapper):
    server, _ = wrapper
    schema = server.tools_payload()[0].get("outputSchema")
    assert schema is not None, "new wrapper tools need their outputSchema"
    jsonschema.Draft202012Validator.check_schema(schema)


def test_toon_text_and_structured_data_are_equivalent(wrapper):
    server, _ = wrapper
    result = call(server)
    assert "structuredContent" in result, "C1 needs JSON alongside TOON"
    from lampway_server.compute.toon_out import decode
    assert decode(result["content"][0]["text"]) == result["structuredContent"]
    jsonschema.validate(result["structuredContent"], server.tools_payload()[0]["outputSchema"])
    assert result["structuredContent"]["data"]["holes"] == []
    assert "holes: []" in result["content"][0]["text"]
    assert result["content"][0]["text"].splitlines()[-1].strip().endswith("name=mesh")


def test_unknown_argument_is_structured_refusal_before_blender(wrapper):
    server, _ = wrapper
    result = call(server, {"surprise": "not sent"})
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "unknown_argument"
    assert not server.journal
    assert server.hub.sockets["app"].calls == []
    jsonschema.validate(result["structuredContent"], server.tools_payload()[0]["outputSchema"])


def test_unknown_argument_precedes_disconnected_app_refusal(wrapper):
    server, _ = wrapper
    server.hub.sockets.clear()
    result = call(server, {"typo": True})
    assert result["structuredContent"]["code"] == "unknown_argument"
    assert not server.journal


def test_client_refusal_is_error_even_when_script_succeeded(wrapper):
    server, answer = wrapper
    answer.clear()
    answer.update(success=True, ok=False, error="no mesh named Missing", code="not_found",
                  help=["lampway_inspect view=objects match=<name>"])
    result = call(server)
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "not_found"


def test_client_image_is_appended_then_deleted(wrapper, tmp_path, monkeypatch):
    server, answer = wrapper
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    from PIL import Image
    image = tmp_path / "capture.png"
    Image.new("RGB", (4, 4)).save(image)
    original = image.read_bytes()
    answer["image_path"] = "capture.png"
    result = call(server)
    assert len(result["content"]) == 2
    block = result["content"][1]
    assert block["mimeType"] == "image/png"
    assert base64.b64decode(block["data"]) == original
    assert not image.exists()


def test_image_outside_project_is_refused_and_not_deleted(wrapper, tmp_path, monkeypatch):
    server, answer = wrapper
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "private.png"
    outside.write_bytes(b"must not read")
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(root))
    answer["image_path"] = "../private.png"
    result = call(server)
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "path_outside_project"
    assert outside.read_bytes() == b"must not read"


def test_oversized_image_is_refused_without_base64(wrapper, tmp_path, monkeypatch):
    server, answer = wrapper
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    image = tmp_path / "capture.png"
    image.write_bytes(b"x" * 750001)
    answer["image_path"] = "capture.png"
    result = call(server)
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "image_too_large"
    assert not any(block["type"] == "image" for block in result["content"])


def test_symlink_escape_is_refused_without_reading_target(wrapper, tmp_path, monkeypatch):
    server, answer = wrapper
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "private.png"
    outside.write_bytes(b"must not read")
    (root / "escape.png").symlink_to(outside)
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(root))
    answer["image_path"] = "escape.png"
    result = call(server)
    assert result["structuredContent"]["code"] == "path_outside_project"
    assert outside.read_bytes() == b"must not read"


def test_long_data_strings_disclose_truncation_and_full_restores_them(wrapper):
    server, answer = wrapper
    answer["data"]["doc"] = "x" * 2847
    result = call(server)
    assert result["structuredContent"]["data"]["doc"].endswith("... (truncated, 2847 chars total; full=true)")


def test_large_float_and_lossless_integer_share_exact_typed_reply(wrapper):
    server, answer = wrapper
    answer['data']['number'] = 4.370708124762165e16
    answer['data']['integer'] = 43707081247621648
    result = call(server)
    from lampway_server.compute.toon_out import decode
    assert decode(result['content'][0]['text']) == result['structuredContent']
    assert result['structuredContent']['data']['integer'] == 43707081247621648


def test_full_disables_server_string_truncation(wrapper):
    server, answer = wrapper
    answer['data']['doc'] = 'x' * 2847
    result = call(server, {'full': True})
    assert result['structuredContent']['data']['doc'] == 'x' * 2847


def test_image_path_swap_cannot_read_outside(wrapper, tmp_path, monkeypatch):
    from lampway_server import mcp_envelope as E
    from PIL import Image
    from pathlib import Path
    server, answer = wrapper
    root = tmp_path / 'project'
    root.mkdir()
    capture = root / 'capture.png'
    outside = tmp_path / 'outside.png'
    Image.new('RGB', (4, 4), 'red').save(capture)
    Image.new('RGB', (4, 4), 'blue').save(outside)
    original = capture.read_bytes()
    private = outside.read_bytes()
    monkeypatch.setenv('LAMPWAY_PROJECT_ROOT', str(root))
    read_bytes = Path.read_bytes
    def swap_before_read(path):
        if path == capture:
            capture.unlink()
            capture.symlink_to(outside)
        return read_bytes(path)
    monkeypatch.setattr(Path, 'read_bytes', swap_before_read)
    answer['image_path'] = 'capture.png'
    result = call(server)
    blocks = [b for b in result['content'] if b['type'] == 'image']
    assert not blocks or base64.b64decode(blocks[0]['data']) == original
    assert outside.exists()
    assert not blocks or base64.b64decode(blocks[0]['data']) != private


def test_signature_without_png_chunks_is_refused(wrapper, tmp_path, monkeypatch):
    server, answer = wrapper
    monkeypatch.setenv('LAMPWAY_PROJECT_ROOT', str(tmp_path))
    (tmp_path / 'capture.png').write_bytes(b'\x89PNG\r\n\x1a\n')
    answer['image_path'] = 'capture.png'
    result = call(server)
    assert result['isError'] is True
    assert result['structuredContent']['code'] == 'bad_image'
    assert not any(b['type'] == 'image' for b in result['content'])


def test_offline_docs_are_typed_without_a_connected_app(fake):
    fake.login()
    result = fake.post('/api/v1/mcp', json={'jsonrpc': '2.0', 'id': 91, 'method': 'tools/call',
        'params': {'name': 'lampway_blender_docs', 'arguments': {'view': 'get', 'identifier': 'bpy.types.Object.location'}}}).json()['result']
    from lampway_server.compute.toon_out import decode
    assert not result['isError'], result
    assert decode(result['content'][0]['text']) == result['structuredContent']
    assert result['structuredContent']['count'] == 1
    assert result['structuredContent']['data']['identifier'] == 'bpy.types.Object.location'


def test_image_swap_at_final_open_refuses_symlink(wrapper, tmp_path, monkeypatch):
    import os
    from PIL import Image
    server, answer = wrapper
    root = tmp_path / 'project'
    root.mkdir()
    capture = root / 'capture.png'
    outside = tmp_path / 'outside.png'
    Image.new('RGB', (4, 4), 'red').save(capture)
    Image.new('RGB', (4, 4), 'blue').save(outside)
    private = outside.read_bytes()
    monkeypatch.setenv('LAMPWAY_PROJECT_ROOT', str(root))
    original_open = os.open
    def swap(path, flags, *args, **kwargs):
        if path == 'capture.png':
            capture.unlink()
            capture.symlink_to(outside)
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'supports_dir_fd', os.supports_dir_fd | {swap})
    monkeypatch.setattr(os, 'open', swap)
    answer['image_path'] = 'capture.png'
    result = call(server)
    assert result['isError'] is True
    assert result['structuredContent']['code'] == 'path_outside_project'
    assert outside.read_bytes() == private
    assert not any(b['type'] == 'image' for b in result['content'])


def test_image_parent_swap_refuses_symlink(wrapper, tmp_path, monkeypatch):
    import os
    from PIL import Image
    server, answer = wrapper
    root = tmp_path / 'project'
    root.mkdir()
    sub = root / 'captures'
    sub.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    Image.new('RGB', (4, 4), 'red').save(sub / 'capture.png')
    Image.new('RGB', (4, 4), 'blue').save(outside / 'capture.png')
    private = (outside / 'capture.png').read_bytes()
    monkeypatch.setenv('LAMPWAY_PROJECT_ROOT', str(root))
    original_open = os.open
    def swap(path, flags, *args, **kwargs):
        if path == 'captures':
            sub.rename(root / 'retained')
            sub.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'supports_dir_fd', os.supports_dir_fd | {swap})
    monkeypatch.setattr(os, 'open', swap)
    answer['image_path'] = 'captures/capture.png'
    result = call(server)
    assert result['isError'] is True
    assert result['structuredContent']['code'] == 'path_outside_project'
    assert (outside / 'capture.png').read_bytes() == private


def test_image_growth_after_stat_still_has_bounded_read(wrapper, tmp_path, monkeypatch):
    import os
    server, answer = wrapper
    monkeypatch.setenv('LAMPWAY_PROJECT_ROOT', str(tmp_path))
    capture = tmp_path / 'capture.png'
    capture.write_bytes(b'x' * 750001)
    original_fstat, original_read = os.fstat, os.read
    sizes, received = [], []
    def stale_size(fd):
        stat = original_fstat(fd)
        return SimpleNamespace(st_mode=stat.st_mode, st_size=1, st_dev=stat.st_dev, st_ino=stat.st_ino)
    def read(fd, size):
        sizes.append(size)
        data = original_read(fd, size)
        received.append(len(data))
        return data
    monkeypatch.setattr(os, 'fstat', stale_size)
    monkeypatch.setattr(os, 'read', read)
    answer['image_path'] = 'capture.png'
    result = call(server)
    assert result['isError'] is True
    assert result['structuredContent']['code'] == 'image_too_large'
    assert max(sizes) <= 65536
    assert sum(received) == 750001
    assert capture.exists()


def test_unsupported_secure_image_platform_refuses_explicitly(wrapper, tmp_path, monkeypatch):
    import os
    server, answer = wrapper
    monkeypatch.setenv('LAMPWAY_PROJECT_ROOT', str(tmp_path))
    monkeypatch.setattr(os, 'supports_dir_fd', set())
    answer['image_path'] = 'capture.png'
    result = call(server)
    assert result['isError'] is True
    assert result['structuredContent']['code'] == 'image_platform_unsupported'


def test_render_gate_executor_error_preserves_typed_code(wrapper):
    server, answer = wrapper
    answer.clear()
    answer.update(success=False, error='Render still running', error_type='render_in_progress', render_kind='scene_image')
    result = call(server)
    assert result['isError'] is True
    assert result['structuredContent']['code'] == 'render_in_progress'


def test_invalid_result_does_not_consume_its_capture(wrapper, tmp_path, monkeypatch):
    from PIL import Image
    server, answer = wrapper
    monkeypatch.setenv('LAMPWAY_PROJECT_ROOT', str(tmp_path))
    image=tmp_path/'capture.png'
    Image.new('RGB',(4,4)).save(image)
    answer['image_path']='capture.png'
    answer['count']='invalid count'
    result=call(server)
    assert result['structuredContent']['code']=='invalid_result'
    assert image.exists()


def test_wrapper_without_session_uses_the_scene_returned_by_begin(wrapper):
    server, _ = wrapper
    result = call(server, session="")
    assert not result["isError"], result
    assert result["structuredContent"]["data"]["holes"] == []


def test_wrapper_script_failure_still_releases_lease_and_returns_typed_error(wrapper):
    server, _ = wrapper
    client = server.hub.sockets["app"]
    client.fail_script = True
    result = call(server)
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "execution_failed"
    assert "the socket dropped mid-script" in result["structuredContent"]["error"]
    jsonschema.validate(result["structuredContent"], server.tools_payload()[0]["outputSchema"])
    # A retry can lease the same scene: the failure left no stale owner behind.
    client.fail_script = False
    retried = call(server)
    assert not retried["isError"] and retried["structuredContent"]["data"]["holes"] == []
    assert len(client.frames) == 6


def test_wrapper_refused_scene_lease_preserves_typed_code_and_never_sends_script(wrapper):
    server, _ = wrapper
    client = server.hub.sockets["app"]
    result = call(server, session="another-scene")
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "document_changed"
    assert client.calls == ["mcp.begin_operation"] and client.leases == {}
    jsonschema.validate(result["structuredContent"], server.tools_payload()[0]["outputSchema"])


@pytest.mark.parametrize('mismatch', ['operation', 'session'])
def test_envelope_fake_refuses_scripts_outside_the_acquired_lease(wrapper, mismatch):
    """Plant each client authorization violation; a fake must not hand out data."""
    server, _ = wrapper
    client = server.hub.sockets['app']
    operation = '00000000-0000-4000-8000-000000000001'

    async def unauthorized_script():
        begun = await client.request('mcp.begin_operation', {
            'operation_id': operation, 'session_id': client.scene_session})
        assert begun['success']
        try:
            return await client.request('blender.execute_script', {
                'session_id': 'another-scene' if mismatch == 'session' else client.scene_session,
                'agent_ctx': {'chat_session_id': client.scene_session,
                              'mcp_operation_id': 'forged-operation' if mismatch == 'operation' else operation}})
        finally:
            await client.request('mcp.end_operation', {
                'operation_id': operation, 'session_id': client.scene_session})

    reply = asyncio.run(unauthorized_script())
    assert reply['success'] is False and reply['error_type'] == 'mcp_operation_expired'
    assert 'data' not in reply
    assert client.calls == ['mcp.begin_operation', 'blender.execute_script', 'mcp.end_operation']
    assert client.leases == {}
