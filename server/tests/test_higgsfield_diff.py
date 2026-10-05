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
    assert report["video_models"] > 20 and "seedance1_5" in report["video_model_ids"] and report["unparsed_models"] == [], "every page of the catalogue"
    assert report["mismatches"] == 0, report["args"]
    assert all(v["takes_params_wrapper"] for k, v in report["args"].items() if k in ("generate_video", "generate_image"))


def test_a_server_whose_generation_tools_take_flat_arguments_is_a_mismatch(mcp):
    client, hf = mcp
    flat = {"type": "object", "properties": {"model": {"type": "string"}, "prompt": {"type": "string"}}}
    client._tools = [dict(t, inputSchema=flat) if t["name"] == "generate_video" else t for t in client.tools()]
    report = HD.diff(client)
    assert "params" in report["args"]["generate_video"]["missing_from_schema"] and report["mismatches"] > 0


def test_a_missing_tool_and_an_unparseable_catalogue_are_reported_not_hidden(mcp):
    client, hf = mcp
    client._tools = [t for t in client.tools() if t["name"] != "jobs_wait"]
    original = hf.tool_models_explore
    hf.tool_models_explore = lambda a: {"weird": [{"name": "no id"}]}
    report = HD.diff(client)
    assert "jobs_wait" in report["tools_missing"] and report["video_models"] == 0 and report["catalogue_note"]


def test_dump_records_the_live_tool_definitions_and_raw_responses(mcp, tmp_path):
    client, hf = mcp
    out = tmp_path / "fx"
    HD.dump(client, out)
    import json
    tools = json.loads((out / "tools_list.json").read_text())
    assert {t["name"] for t in tools} == set(HD.EXPECTED_TOOLS)
    assert json.loads((out / "balance.json").read_text())["credits"] == 623.86
    assert json.loads((out / "models_video.json").read_text())["items"] and json.loads((out / "models_image.json").read_text())["items"]
    assert {t for t, _ in hf.calls} <= {"balance", "models_explore"}
