"""The Client's unserved job types backed by the tools that now exist (STATUS O13, specs/mixar_docs/job_services.md): retopology, hunyuan_uv, hunyuan_part,
tripo_rig, tripo_segment, tripo_smart_segment, image_to_3d, hunyuan_rapid and model_3d (with an image) run the Lampway tools in a headless Lampway (free, local,
no spend); the rest stay unbacked with the reason named. The runner is injected; one real run happens when LAMPWAY_BIN is set."""

import base64
import json
import os
from pathlib import Path

import pytest

from lampway_server import job_backends as JB
from lampway_server.jobqueue import FilesOutput
from lampway_server.services import WIRE_KEYS, ServiceRegistry

GLB = b"glTF" + b"\x00" * 16


class FakeRun:
    def __init__(self):
        self.calls = []

    def __call__(self, op, input_path, params):
        self.calls.append({"op": op, "input": Path(input_path).name, "bytes": Path(input_path).read_bytes(), "params": params})
        if op == "parts":
            return {"files": [(GLB, "part_01.glb"), (GLB, "part_02.glb")], "part_names": ["part_01", "part_02"]}
        return {"files": [(GLB, "result.glb")], "report": {"faces": 10}}


def test_the_local_services_register_with_catalog_rows_and_the_rest_are_unbacked_with_reasons():
    reg = ServiceRegistry()
    JB.register_local(reg, FakeRun())
    backed = set(reg.keys())
    assert backed == {"retopology", "hunyuan_uv", "hunyuan_part", "tripo_rig", "tripo_segment", "tripo_smart_segment", "image_to_3d", "hunyuan_rapid", "model_3d"}, backed
    assert not any(reg.get(k).spend for k in backed), "local tools spend nothing"
    unbacked = set(WIRE_KEYS) - backed - {"image_gen", "video_gen", "video_upscale"}
    assert unbacked <= set(JB.UNBACKED_REASONS) and all(JB.UNBACKED_REASONS[k] for k in unbacked)


def test_a_retopology_job_decodes_the_mesh_runs_the_tool_and_returns_a_glb():
    run = FakeRun()
    reg = ServiceRegistry()
    JB.register_local(reg, run)
    out = reg.get("retopology").backend("lampway_quadriflow", {"input_name": "chest", "file_bytes_b64": base64.b64encode(GLB).decode(), "file_filename": "chest.glb",
                                                               "params": {"face_level": "low"}})
    assert isinstance(out, FilesOutput) and out.kind == "GLB" and out.files[0][0] == GLB and out.extra["provider"] == "lampway-local", out
    assert run.calls[0]["op"] == "retopo" and run.calls[0]["input"] == "chest.glb" and run.calls[0]["bytes"] == GLB and run.calls[0]["params"]["target_faces"] == 2000


def test_parts_return_several_files_with_their_names_and_rig_takes_the_rig_payload():
    run = FakeRun()
    reg = ServiceRegistry()
    JB.register_local(reg, run)
    parts = reg.get("tripo_segment").backend("lampway_shells", {"file_bytes_b64": base64.b64encode(GLB).decode(), "file_filename": "x.glb"})
    assert len(parts.files) == 2 and parts.extra["part_names"] == ["part_01", "part_02"]
    rig = reg.get("tripo_rig").backend("lampway_auto_rig", {"rig": {"input_name": "hero", "file_bytes_b64": base64.b64encode(GLB).decode(), "file_filename": "hero.glb"}})
    assert run.calls[-1]["op"] == "rig" and rig.files


def test_image_to_3d_takes_the_image_and_model_3d_without_an_image_is_refused():
    run = FakeRun()
    reg = ServiceRegistry()
    JB.register_local(reg, run)
    reg.get("image_to_3d").backend("lampway_extrude", {"image_bytes_b64": base64.b64encode(b"\x89PNG").decode(), "image_filename": "front.png"})
    assert run.calls[-1]["op"] == "image_to_3d" and run.calls[-1]["input"] == "front.png"
    with pytest.raises(ValueError, match="text-to-3D needs a model"):
        reg.get("model_3d").backend("lampway_extrude", {"prompt": "a chair"})
    with pytest.raises(ValueError, match="no mesh"):
        reg.get("retopology").backend("lampway_quadriflow", {"params": {}})


def test_without_a_lampway_binary_nothing_registers():
    reg = ServiceRegistry()
    assert JB.default_registry(env={}).keys() == [] and JB.blender_binary(env={}) is None


@pytest.mark.skipif(not os.environ.get("LAMPWAY_BIN") or not Path(os.environ.get("LAMPWAY_BIN", "")).exists(), reason="no Lampway binary: set LAMPWAY_BIN for the real run")
def test_a_real_headless_retopology_returns_a_quad_mesh(tmp_path):
    run = JB.BlenderRun(os.environ["LAMPWAY_BIN"], tmp_path)
    src = run.make_test_glb(tmp_path / "sphere.glb")
    out = run("retopo", str(src), {"target_faces": 300})
    assert out["files"] and out["files"][0][0][:4] == b"glTF" and out["report"]["faces"] > 100, out.get("report")


def test_the_app_registers_the_local_services_only_when_lampway_blender_names_the_binary(settings, provider, monkeypatch, tmp_path):
    from lampway_server.app import create_app
    exe = tmp_path / "lampway"; exe.write_text("#!/bin/sh\n"); exe.chmod(0o755)
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path / "root"))
    monkeypatch.delenv("LAMPWAY_BLENDER", raising=False)
    plain = create_app(settings, provider=provider, job_backends={})
    assert plain.state.jobs.registry.keys() == []
    monkeypatch.setenv("LAMPWAY_BLENDER", str(exe))
    lit = create_app(settings, provider=provider, job_backends={})
    assert "retopology" in lit.state.jobs.registry.keys() and "retopology" not in lit.state.jobs.service_report()["unbacked"]


def test_the_agent_tool_names_why_each_unbacked_service_is_unbacked():
    from lampway_server.agent import ledger_tools as LGT

    class Jobs:
        def service_report(self):
            return {"services": [], "unbacked": ["pbr_gen", "world_labs"]}
    out = json.loads(LGT.job_services(Jobs()))
    assert set(out["unbacked_reasons"]) == {"pbr_gen", "world_labs"} and "model" in out["unbacked_reasons"]["world_labs"]
