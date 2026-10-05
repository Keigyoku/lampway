"""The Higgsfield service layer over the MCP client: the catalogue from models_explore, uploads (media_upload -> PUT -> media_confirm),
get_cost before any spend, generation requests in the roles each model takes, motion transfer (Genjutsu and Kling), jobs_wait polling that
survives a transport timeout without resubmitting, the unlim_choice question surfaced and never auto-answered, and downloads into the project."""

import httpx
import pytest

from lampway_server import higgsfield as HF
from lampway_server import higgsfield_auth as HA
from lampway_server import higgsfield_mcp as HM

from .fake_higgsfield import FakeHiggsfield


@pytest.fixture
def hf():
    return FakeHiggsfield()


@pytest.fixture
def svc(tmp_path, hf):
    auth = HA.HiggsfieldAuth(tmp_path / "s", http=httpx.Client(transport=hf.transport()))
    a = auth.start_login()
    auth.complete_login(hf.authorize(a.url))
    mcp = HM.HiggsfieldMCP(auth, transport=hf.transport())
    return HF.Higgsfield(mcp, http_transport=hf.transport(), poll_s=0.0, wait_timeout_s=5.0)


PNG = b"\x89PNG\r\n\x1a\n" + b"x"
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"v"


def test_the_catalogue_is_normalised_from_models_explore(svc):
    rows = svc.models("video")
    seed = next(r for r in rows if r["id"] == "seedance1_5")
    assert seed["durations"] == [4, 8, 12] and seed["resolutions"] == ["480p", "720p", "1080p"] and seed["roles"] == ["start_image", "end_image"]
    assert seed["supports_audio"] is True and next(r for r in rows if r["id"] == "seedance_2_0")["supports_unlim"] is True
    assert "gpt_image_2_5" in [r["id"] for r in svc.models("image")]
    assert svc.balance() == {"plan": "plus", "credits": 623.86}


def test_the_catalogue_follows_the_paging_cursor_to_the_end(svc, hf):
    """models_explore pages (20 by default, has_more + next_page_token + after): the first page alone held 20 of the 53 video models."""
    hf.max_page = 20
    rows = svc.models("video")
    assert len(rows) == 53 and len({r["id"] for r in rows}) == 53 and "hf_mult_motion_control" in [r["id"] for r in rows] and "kling3_0_motion_control" in [r["id"] for r in rows]
    explores = [a for t, a in hf.calls if t == "models_explore"]
    assert [a.get("after") for a in explores] == [None, "20", "40"] and not hf.schema_errors and all(a.get("limit") for a in explores)


def test_the_live_catalogue_shapes_are_read(svc):
    """parameters is a LIST of {name, options, min, max}; a duration is a list, a range or a parameter's span; wan2_6 names its resolution `quality`."""
    by = {r["id"]: r for r in svc.models("video")}
    assert by["seedance_2_5"]["durations"] == list(range(4, 31)) and by["cinematic_studio_3_0"]["durations"] == list(range(4, 16))
    assert by["cinematic_studio_video"]["durations"] == [5, 10] and by["minimax_hailuo"]["durations"] == [6, 10]
    assert by["wan2_6"]["resolutions"] == ["720p", "1080p"] and by["wan2_6"]["resolution_key"] == "quality"
    assert by["seedance_2_5"]["resolution_key"] == "resolution" and by["video_background_remover"]["resolutions"] == []
    assert by["kling3_0_motion_control"]["roles"] == ["image_references", "video_references"]


def test_the_generation_tools_take_one_params_argument(svc, hf):
    """The live schemas: generate_video / generate_image take ONE argument ``params`` holding model, prompt, duration, ..., get_cost, use_unlim. The
    fake refuses (isError) any request the recorded schema would, so a flat call raises here exactly as it did live."""
    svc.cost("generate_video", {"model": "seedance1_5", "prompt": "x", "duration": 8, "resolution": "720p", "generate_audio": False})
    svc.cost("generate_image", {"model": "gpt_image_2_5", "prompt": "x", "aspect_ratio": "1:1", "count": 1})
    sub = svc.submit("generate_video", {"model": "seedance1_5", "prompt": "x", "duration": 8})
    assert sub["job_ids"] and hf.schema_errors == []
    with pytest.raises(HM.ToolError, match="missing required 'params'"):
        svc.mcp.call("generate_video", {"model": "seedance1_5", "prompt": "x"})
    assert [t for t, _ in hf.schema_errors] == ["generate_video"]


def test_uploads_put_the_bytes_then_confirm_and_return_a_media_id(svc, hf):
    mid = svc.upload(PNG, "image", "ref.png", "image/png")
    assert hf.puts[0][1] == PNG and hf.puts[0][0].endswith(mid)
    tools = [c[0] for c in hf.calls]
    assert tools.index("media_upload") < tools.index("media_confirm")
    assert hf.calls[tools.index("media_upload")][1] == {"files": [{"filename": "ref.png", "content_type": "image/png"}]}, "media_upload has no `type`: the extension decides"
    assert hf.calls[tools.index("media_confirm")][1] == {"type": "image", "media_ids": [mid]} and hf.media[mid]["confirmed_as"] == "image"
    assert hf.schema_errors == []


def test_cost_runs_get_cost_and_submits_nothing(svc, hf):
    out = svc.cost("generate_video", {"model": "seedance1_5", "prompt": "x", "duration": 8, "resolution": "720p"})
    assert out == pytest.approx(9.6)
    assert hf.jobs == {} and hf.calls[-1][1]["get_cost"] is True


def test_a_start_and_end_frame_request_uses_the_roles_the_model_takes(svc, hf):
    a = svc.upload(PNG, "image", "a.png", "image/png")
    args = svc.video_args("seedance1_5", "a loop", {"duration": 8, "resolution": "720p", "aspect_ratio": "16:9", "image_mode": "first_last_frame"},
                          images=[a])
    assert args["medias"] == [{"value": a, "role": "start_image"}, {"value": a, "role": "end_image"}], "one image in first_last_frame mode is a LOOP"
    assert args["model"] == "seedance1_5" and args["duration"] == 8 and "use_unlim" not in args
    with pytest.raises(HF.HiggsfieldError, match="start_image"):
        svc.video_args("hf_mult_motion_control", "x", {"image_mode": "first_last_frame"}, images=[a])


def test_motion_transfer_maps_the_character_image_and_the_driving_video_to_the_models_roles(svc, hf):
    img, vid = svc.upload(PNG, "image", "c.png", "image/png"), svc.upload(MP4, "video", "d.mp4", "video/mp4")
    args = svc.video_args("hf_mult_motion_control", "dance", {"duration": 5, "resolution": "720p"}, images=[img], videos=[vid])
    assert {"value": img, "role": "image_references"} in args["medias"] and {"value": vid, "role": "video_references"} in args["medias"]
    assert args["resolution"] == "720p" and args["model"] == "hf_mult_motion_control"


def test_submit_returns_job_ids_and_wait_polls_to_the_result_urls(svc, hf):
    r = svc.submit("generate_video", {"model": "seedance1_5", "prompt": "x", "duration": 8, "resolution": "720p"})
    assert r["question"] is None and len(r["job_ids"]) == 1
    done = svc.wait(r["job_ids"])
    assert [d["status"] for d in done] == ["completed"] and done[0]["url"].endswith(".mp4")
    assert svc.download(done[0]["url"]) is not None


def test_an_unlim_choice_is_surfaced_as_a_question_and_never_answered_by_us(svc, hf):
    hf.unlim_question = True
    r = svc.submit("generate_video", {"model": "seedance_2_0", "prompt": "x", "duration": 10, "resolution": "720p"})
    assert r["job_ids"] == [] and r["question"]["question"].startswith("Use your unlimited")
    assert hf.jobs == {} and all("use_unlim" not in a for _, a in hf.calls)
    r2 = svc.submit("generate_video", {"model": "seedance_2_0", "prompt": "x", "duration": 10, "resolution": "720p", "use_unlim": False})
    assert len(r2["job_ids"]) == 1 and hf.calls[-1][1]["use_unlim"] is False


def test_a_submit_timeout_is_never_retried_and_a_wait_timeout_just_polls_again(svc, hf):
    hf.fail_next_generate = "timeout"
    with pytest.raises(HM.TransportTimeout):
        svc.submit("generate_video", {"model": "seedance1_5", "prompt": "x"})
    assert sum(1 for t, a in hf.calls if t == "generate_video" and not a.get("get_cost")) == 1 and hf.jobs == {}, "exactly one attempt, no resubmit"
    r = svc.submit("generate_video", {"model": "seedance1_5", "prompt": "x"})
    real = svc.mcp.call
    flaky = {"n": 0}

    def call(name, args=None):
        if name == "jobs_wait" and flaky["n"] == 0:
            flaky["n"] += 1
            raise HM.TransportTimeout("slow")
        return real(name, args)
    svc.mcp.call = call
    assert svc.wait(r["job_ids"])[0]["status"] == "completed"
    assert sum(1 for t, _ in hf.calls if t == "generate_video" and True) == 2


def test_a_failed_job_is_reported_with_its_status(svc, hf):
    hf.job_status = ["failed"]
    r = svc.submit("generate_video", {"model": "seedance1_5", "prompt": "x"})
    out = svc.wait(r["job_ids"])
    assert out[0]["status"] == "failed" and out[0]["url"] is None


def test_the_wait_is_bounded(svc, hf):
    hf.job_status = ["in_progress"]
    svc.wait_timeout_s = 0.05
    r = svc.submit("generate_video", {"model": "seedance1_5", "prompt": "x"})
    with pytest.raises(HF.HiggsfieldError, match="still running"):
        svc.wait(r["job_ids"])
