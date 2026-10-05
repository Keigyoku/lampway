"""Voice dictation (docs: "Use Voice when you prefer to dictate"): WebSocket /api/v1/dictation/ws, the protocol the client's voice
input speaks. Proven code first: an energy gate (RMS) so silence never costs a transcription, PCM framing as the client sends it
(16 kHz, 16-bit mono, 32000 B/s), WAV wrapping, a duration cap. The speech-to-text model is the SLOT: any ``transcribe(pcm) -> str``;
the default is an OpenRouter audio-input model on the shared spend ledger, injected here with a fake."""

import base64
import json
import math
import struct

import httpx
import pytest

from lampway_server import dictation
from lampway_server.app import create_app

RATE = 16000


def speech(seconds=1.0, amp=8000, hz=220):
    n = int(RATE * seconds)
    return b"".join(struct.pack("<h", int(amp * math.sin(2 * math.pi * hz * i / RATE))) for i in range(n))


def silence(seconds=1.0):
    return b"\x00\x00" * int(RATE * seconds)


class FakeSTT:
    def __init__(self, text="make the lamp brass"):
        self.text, self.calls = text, []

    async def transcribe(self, pcm, rate=RATE):
        self.calls.append((len(pcm), rate))
        return self.text


def open_ws(app, token):
    from starlette.testclient import TestClient
    client = TestClient(app, base_url="http://127.0.0.1:8787")
    client.__enter__()
    return client, client.websocket_connect("/api/v1/dictation/ws", headers={"Authorization": f"Bearer {token}", "host": "127.0.0.1:8787"})


@pytest.fixture
def stack(settings, provider):
    stt = FakeSTT()
    app = create_app(settings, provider=provider, transcriber=stt)
    from starlette.testclient import TestClient
    from tests.fake_client import FakeMixarClient
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        yield http, fake.access_token, stt, app


def connect(http, token):
    return http.websocket_connect("/api/v1/dictation/ws", headers={"Authorization": f"Bearer {token}", "host": "127.0.0.1:8787"})


def test_a_bad_bearer_never_upgrades(stack):
    http, token, _stt, _app = stack
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with connect(http, "garbage") as ws:
            ws.receive_json()


def test_prepare_and_ping_are_answered(stack):
    http, token, *_ = stack
    with connect(http, token) as ws:
        ws.send_json({"type": "prepare", "protocol_version": 1})
        prepared = ws.receive_json()
        assert prepared["type"] == "prepared" and 1 <= prepared["expires_in_seconds"] <= 300
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_a_spoken_clip_is_transcribed_on_stop_and_the_dictation_id_is_echoed(stack):
    http, token, stt, _ = stack
    with connect(http, token) as ws:
        ws.send_json({"type": "start", "protocol_version": 1, "dictation_id": "d-1", "buffered_audio_seconds": 0.0})
        ready = ws.receive_json()
        assert ready["type"] == "ready" and 1 <= ready["max_duration_seconds"] <= 600
        pcm = speech(1.0)
        for i in range(0, len(pcm), 6400):
            ws.send_bytes(pcm[i:i + 6400])
        ws.send_json({"type": "stop"})
        final = ws.receive_json()
    assert final == {"type": "final", "dictation_id": "d-1", "text": "make the lamp brass"}
    assert stt.calls == [(len(pcm), RATE)]


def test_silence_costs_nothing_the_gate_answers_an_empty_final_without_calling_the_model(stack):
    http, token, stt, _ = stack
    with connect(http, token) as ws:
        ws.send_json({"type": "start", "protocol_version": 1, "dictation_id": "d-2", "buffered_audio_seconds": 0})
        ws.receive_json()
        ws.send_bytes(silence(1.0))
        ws.send_json({"type": "stop"})
        final = ws.receive_json()
    assert final == {"type": "final", "dictation_id": "d-2", "text": ""} and stt.calls == []


def test_cancel_drops_the_audio_and_a_cap_ends_a_long_dictation(stack, monkeypatch):
    http, token, stt, _ = stack
    with connect(http, token) as ws:
        ws.send_json({"type": "start", "protocol_version": 1, "dictation_id": "d-3", "buffered_audio_seconds": 0})
        ws.receive_json()
        ws.send_bytes(speech(0.5))
        ws.send_json({"type": "cancel"})
        assert ws.receive_json() == {"type": "cancelled", "dictation_id": "d-3"}
    assert stt.calls == []
    monkeypatch.setattr(dictation, "MAX_DURATION_S", 1)
    with connect(http, token) as ws:
        ws.send_json({"type": "start", "protocol_version": 1, "dictation_id": "d-4", "buffered_audio_seconds": 0})
        ws.receive_json()
        ws.send_bytes(speech(2.0))
        msg = ws.receive_json()
    assert msg["type"] == "max_duration_reached" and msg["dictation_id"] == "d-4" and msg["text"] == "make the lamp brass"


def test_without_a_transcriber_start_is_an_error_the_client_can_show(settings, provider):
    from starlette.testclient import TestClient
    from tests.fake_client import FakeMixarClient
    app = create_app(settings, provider=provider, transcriber=False)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        with connect(http, fake.access_token) as ws:
            ws.send_json({"type": "start", "protocol_version": 1, "dictation_id": "d-5", "buffered_audio_seconds": 0})
            msg = ws.receive_json()
    assert msg["type"] == "error" and msg["dictation_id"] == "d-5" and "speech-to-text" in msg["message"]


def test_the_wav_wrapper_and_the_energy_gate():
    wav = dictation.pcm_to_wav(b"\x01\x00" * 100, RATE)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE" and struct.unpack("<IHHIIHH", wav[16:36])[1:4] == (1, 1, RATE) and len(wav) == 44 + 200
    assert dictation.is_speech(speech(0.3)) is True and dictation.is_speech(silence(0.3)) is False
    assert dictation.is_speech(b"") is False


@pytest.mark.anyio
async def test_the_openrouter_transcriber_sends_the_clip_as_input_audio_and_books_the_cost(tmp_path, anyio_backend):
    from lampway_server.agent.providers.openrouter import SpendLedger
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": " hello lampway "}}], "usage": {"cost": 0.0003}})
    ledger = SpendLedger(1.0, tmp_path / "spend.jsonl")
    stt = dictation.OpenRouterTranscriber("k" * 20, "google/gemini-3.8-flash", ledger, transport=httpx.MockTransport(handler))
    text = await stt.transcribe(speech(0.5), RATE)
    assert text == "hello lampway"
    part = next(p for p in seen["body"]["messages"][-1]["content"] if p["type"] == "input_audio")
    assert part["input_audio"]["format"] == "wav" and base64.b64decode(part["input_audio"]["data"])[:4] == b"RIFF"
    assert seen["body"]["model"] == "google/gemini-3.8-flash" and seen["body"]["max_tokens"] <= 2048
    assert abs(ledger.spent - 0.0003) < 1e-9 and ledger.by_label == {"dictation": pytest.approx(0.0003)}
    ledger2 = SpendLedger(0.0001, tmp_path / "spend2.jsonl")
    ledger2.add(0.5, "x")
    from lampway_server.agent.providers.openrouter import SpendCeilingReached
    with pytest.raises(SpendCeilingReached):
        await dictation.OpenRouterTranscriber("k" * 20, "m", ledger2, transport=httpx.MockTransport(handler)).transcribe(speech(0.5), RATE)
