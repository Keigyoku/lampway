"""The read-only live check after sign-in: tools/list, balance and models_explore only (nothing is generated), diffed against what the SPEC and our
code assume, so a wrong shape shows up before the first real clip."""

import httpx
import pytest

from lampway_server import higgsfield_auth as HA
from lampway_server import higgsfield_diff as HD
from lampway_server import higgsfield_mcp as HM

from .fake_higgsfield import FakeHiggsfield


@pytest.fixture
def mcp(tmp_path):
    hf = FakeHiggsfield()
    auth = HA.HiggsfieldAuth(tmp_path / "s", http=httpx.Client(transport=hf.transport()))
    a = auth.start_login()
    auth.complete_login(hf.authorize(a.url))
    return HM.HiggsfieldMCP(auth, transport=hf.transport()), hf


def test_the_diff_reads_only_and_reports_tools_and_shapes(mcp):
    client, hf = mcp
    report = HD.diff(client)
    assert {"generate_video", "media_upload", "jobs_wait"} <= set(report["tools_present"]) and report["tools_missing"] == []
    assert {t for t, _ in hf.calls} <= {"balance", "models_explore"}, "read-only: no generation tool was called"
    assert report["balance"] == {"plan": "plus", "credits": 623.86}
    assert report["video_models"] >= 3 and "seedance1_5" in report["video_model_ids"] and report["unparsed_models"] == []


def test_a_missing_tool_and_an_unparseable_catalogue_are_reported_not_hidden(mcp):
    client, hf = mcp
    client._tools = [t for t in client.tools() if t["name"] != "motion_control"]
    original = hf.tool_models_explore
    hf.tool_models_explore = lambda a: {"weird": [{"name": "no id"}]}
    report = HD.diff(client)
    assert "motion_control" in report["tools_missing"] and report["video_models"] == 0 and report["catalogue_note"]
