"""The MCP client for Higgsfield: streamable HTTP JSON-RPC (initialize + the session id, tools/list cached, tools/call), the bearer from
the ONE auth instance, a 401 answered by a refresh and a retry, SSE or JSON responses, tool errors as errors, a transport timeout as its
own error (callers never resubmit on it), and no token in any error text."""

import json

import httpx
import pytest

from lampway_server import higgsfield_auth as HA
from lampway_server import higgsfield_mcp as HM

from .fake_higgsfield import FakeHiggsfield


@pytest.fixture
def hf():
    return FakeHiggsfield()


@pytest.fixture
def signed_in(tmp_path, hf):
    auth = HA.HiggsfieldAuth(tmp_path / "s", http=httpx.Client(transport=hf.transport()))
    a = auth.start_login()
    auth.complete_login(hf.authorize(a.url))
    return auth


@pytest.fixture
def mcp(signed_in, hf):
    return HM.HiggsfieldMCP(signed_in, transport=hf.transport())


def test_initialize_opens_a_session_and_calls_carry_its_id(mcp, hf):
    out = mcp.call("balance", {})
    assert out == {"subscription_plan_type": "plus", "credits": 100.0}
    assert hf.calls == [("balance", {})]


def test_tools_list_is_cached(mcp, hf):
    names = [t["name"] for t in mcp.tools()]
    assert {"generate_video", "media_upload", "media_confirm", "jobs_wait", "models_explore"} <= set(names)
    mcp.tools()
    assert mcp.has_tool("generate_video") and not mcp.has_tool("nope")


def test_a_401_refreshes_the_token_once_and_retries(mcp, hf, signed_in):
    mcp.call("balance", {})
    hf.unauthorised_once = True
    before = len(hf.token_requests)
    assert mcp.call("balance", {})["credits"] == 100.0
    assert len(hf.token_requests) == before + 1 and hf.token_requests[-1]["grant_type"] == "refresh_token"


def test_a_tool_error_is_raised_with_the_servers_words(mcp):
    with pytest.raises(HM.ToolError, match="unknown tool"):
        mcp.call("no_such_tool", {})


def test_an_sse_response_is_read(signed_in, hf):
    def sse(request):
        resp = hf.handle(request)
        if request.method == "POST" and json.loads(request.content).get("method") == "tools/call" and resp.status_code == 200:
            body = "event: message\ndata: " + resp.text + "\n\n"
            return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})
        return resp
    client = HM.HiggsfieldMCP(signed_in, transport=httpx.MockTransport(sse))
    assert client.call("balance", {})["subscription_plan_type"] == "plus"


def test_not_signed_in_says_where_to_sign_in(tmp_path, hf):
    auth = HA.HiggsfieldAuth(tmp_path / "x", http=httpx.Client(transport=hf.transport()))
    with pytest.raises(HA.NotSignedIn, match="/app/higgsfield"):
        HM.HiggsfieldMCP(auth, transport=hf.transport()).call("balance", {})


def test_a_transport_timeout_is_its_own_error_and_leaks_no_token(signed_in, hf):
    def boom(request):
        if request.method == "POST" and b"tools/call" in request.content:
            raise httpx.ReadTimeout("read timed out")
        return hf.handle(request)
    client = HM.HiggsfieldMCP(signed_in, transport=httpx.MockTransport(boom))
    with pytest.raises(HM.TransportTimeout) as e:
        client.call("generate_video", {"model": "seedance1_5"})
    assert "hf-access" not in str(e.value) and "NOT resubmitted" in str(e.value)
