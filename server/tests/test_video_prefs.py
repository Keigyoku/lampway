"""Per-purpose video models in the provider settings: bulk (HeyGen 768p), loop (Seedance 1.5 Pro, first = last frame), motion (Seedance 2.0 Mini with a
reference video), plus the per-job cost cap. Validated like the image purposes; saved and merged per purpose."""

import pytest
from starlette.testclient import TestClient

from lampway_server import provider_prefs as PP
from lampway_server.app import create_app

from .fake_client import FakeMixarClient


def test_the_defaults_follow_the_coordinators_choice(settings):
    v = PP.view(settings)["values"]["video_purposes"]
    assert v["bulk"]["model"] == "heygen/heygen-video-1" and v["bulk"]["resolution"] == "768p"
    assert v["loop"]["model"] == "bytedance/seedance-1-5-pro" and v["loop"]["image_mode"] == "first_last_frame"
    assert v["motion"]["model"] == "bytedance/seedance-2.0-mini"
    assert PP.view(settings)["values"]["video_max_job_usd"] == 2.0
    assert set(PP.view(settings)["choices"]["video_purposes"]) == {"bulk", "loop", "motion"}


def test_a_video_purpose_is_saved_merged_and_validated(settings, monkeypatch):
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(settings.state_dir))
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        ok = fake.put("/app/provider-settings", json={"values": {"video_purposes": {"bulk": {"resolution": "480p", "duration": 5}}, "video_max_job_usd": 1.5}})
        assert ok.status_code == 200, ok.text
        v = ok.json()["values"]
        assert v["video_purposes"]["bulk"]["resolution"] == "480p" and v["video_purposes"]["bulk"]["model"] == "heygen/heygen-video-1"
        assert v["video_max_job_usd"] == 1.5
        for bad in ({"poster": {"model": "x"}}, {"bulk": {"duration": 0}}, {"bulk": {"model": "no spaces!"}}, {"bulk": {"colour": "red"}}, {"loop": {"image_mode": "wild"}}):
            assert fake.put("/app/provider-settings", json={"values": {"video_purposes": bad}}).status_code == 400, bad
        for bad_cap in (0, -1, 500, "x"):
            assert fake.put("/app/provider-settings", json={"values": {"video_max_job_usd": bad_cap}}).status_code == 400, bad_cap
