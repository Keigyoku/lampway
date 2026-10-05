"""The edit and upscale purposes of lampway_video_gen: each resolves its default model, and the upscale factor and creativity reach the plan."""
import asyncio
import json
from pathlib import Path

from lampway_server.agent import video_tools as VT
from lampway_server.config import DEFAULT_VIDEO_PURPOSES


def _system(tmp_path, seen):
    class System:
        settings = type("S", (), {"video_purposes": DEFAULT_VIDEO_PURPOSES, "video_max_job_usd": 2.0})()
        uploads = type("U", (), {"put": staticmethod(lambda kind, data, name="": {"s3_key": "k-" + name})})()
        jobs = None
        prompts = None
        root = tmp_path

        def plan(self, service, model, payload):
            seen.append((model, payload))
            return {"plan": {"ok": True, "model": model, "params": payload["params"]}, "provider": "openrouter"}
    return System()


def test_the_upscale_purpose_picks_flux_video_upscale_and_passes_the_factor_and_creativity(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"x")
    seen = []
    out, err = asyncio.run(VT.call(_system(tmp_path, seen), "lampway_video_gen", {"purpose": "upscale", "prompt": "sharper", "videos": ["clip.mp4"], "upscale_factor": 2, "creativity": 1}))
    assert not err and json.loads(out)["ok"]
    model, payload = seen[0]
    assert model == "black-forest-labs/flux-video-upscale" and payload["params"]["upscale_factor"] == 2 and payload["params"]["creativity"] == 1
    assert payload["reference_video_s3_keys"] == ["k-clip.mp4"]


def test_the_edit_purpose_picks_flux_video_edit_with_the_source_video(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"x")
    seen = []
    out, err = asyncio.run(VT.call(_system(tmp_path, seen), "lampway_video_gen", {"purpose": "edit", "prompt": "replace the prop with a lantern", "videos": ["clip.mp4"]}))
    assert not err and seen[0][0] == "black-forest-labs/flux-video-edit" and seen[0][1]["reference_video_s3_keys"] == ["k-clip.mp4"]
    assert "upscale_factor" not in seen[0][1]["params"]
