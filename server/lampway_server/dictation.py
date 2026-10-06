"""Voice dictation: the WebSocket the client's voice input speaks (/api/v1/dictation/ws).

Protocol (JSON text frames plus binary PCM frames, 16 kHz 16-bit mono little-endian):
  prepare -> prepared{expires_in_seconds}; ping -> pong; start{dictation_id} -> ready{max_duration_seconds};
  binary frames are audio; stop -> final{dictation_id, text}; cancel -> cancelled{dictation_id};
  past the cap -> max_duration_reached{dictation_id, text}; no speech-to-text configured -> error{dictation_id, message}.

Proven code first: the energy gate (RMS of the PCM) means silence is answered with an empty final WITHOUT a model call, and the
duration cap bounds memory and spend. The speech-to-text model is only the slot behind ``transcribe(pcm, rate) -> str``; the
default is an OpenRouter audio-input model on the shared spend ledger (label "dictation").
"""

import base64
import io
import json
import math
import struct
import wave

import httpx

RATE = 16000
MAX_DURATION_S = 120
GATE_RMS = 250.0            # int16 units; room noise sits well below, speech well above
PREPARE_TTL_S = 120
MAX_TOKENS = 1024
PROMPT = ("Transcribe this audio exactly. Reply with only the spoken words, no commentary. "
          "If there is no intelligible speech, reply with nothing.")


def pcm_to_wav(pcm: bytes, rate: int = RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buf.getvalue()


def is_speech(pcm: bytes) -> bool:
    n = len(pcm) // 2
    if n == 0:
        return False
    samples = struct.unpack(f"<{n}h", pcm[:n * 2])
    return math.sqrt(sum(s * s for s in samples) / n) >= GATE_RMS


class OpenRouterTranscriber:
    def __init__(self, api_key: str, model: str, ledger, *, transport=None):
        self._key, self.model, self.ledger, self._transport = api_key, model, ledger, transport

    def __repr__(self) -> str:
        return f"OpenRouterTranscriber(model={self.model!r})"

    async def transcribe(self, pcm: bytes, rate: int = RATE) -> str:
        from .agent.providers.openrouter import BASE_URL, REFERER, TITLE, redact
        self.ledger.check()
        wav = base64.b64encode(pcm_to_wav(pcm, rate)).decode()
        body = {"model": self.model, "max_tokens": MAX_TOKENS, "usage": {"include": True}, "messages": [
            {"role": "user", "content": [{"type": "text", "text": PROMPT},
                                         {"type": "input_audio", "input_audio": {"data": wav, "format": "wav"}}]}]}
        from . import egress as EG
        with EG.context(content_class="private", kind="request", observe_private=True):          # his voice: HC24, declared and observed (CH1)
            async with httpx.AsyncClient(transport=self._transport, timeout=60.0) as client:
                resp = await client.post(f"{BASE_URL}/chat/completions", json=body, headers={
                    "Authorization": f"Bearer {self._key}", "HTTP-Referer": REFERER, "X-Title": TITLE})
        if resp.status_code >= 400:
            raise RuntimeError(redact(f"speech-to-text answered HTTP {resp.status_code}: {resp.text[:300]}", self._key))
        data = resp.json()
        cost = (data.get("usage") or {}).get("cost")
        if isinstance(cost, (int, float)):
            self.ledger.add(cost, "dictation")
        try:
            return (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            return ""


def default_transcriber(settings):
    """The OpenRouter transcriber when a key resolves, else None (start then answers an error the client shows)."""
    from .agent.providers import spend_ledger
    from .agent.providers.openrouter import KeyMissing, resolve_api_key
    try:
        key = resolve_api_key()
    except KeyMissing:
        return None
    from . import choices as CH
    try:                                                         # HC1: the agent.dictation choice (the environment's model is its session layer)
        model = CH.resolve("agent.dictation", CH.Job(needs={"runs_on": ["openrouter"]})).model
    except CH.NoChoice:
        model = (CH.preferred("agent.dictation") or f"openrouter:{settings.openrouter_stt_model}").split(":", 1)[1]   # the route gate refuses at the send, as before
    return OpenRouterTranscriber(key, model or settings.openrouter_stt_model, spend_ledger(settings))


async def run(websocket, auth, transcriber, bearer_from) -> None:
    token = bearer_from(websocket)
    if not token or auth.verify_access(token) is None:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    dictation_id, buf = None, bytearray()
    cap = MAX_DURATION_S * RATE * 2

    async def finish(kind):
        pcm = bytes(buf[:cap])
        try:
            text = (await transcriber.transcribe(pcm, RATE)) if is_speech(pcm) else ""
        except Exception as exc:  # noqa: BLE001 - the client gets the reason, the socket stays usable
            from .agent.providers.openrouter import redact
            await websocket.send_json({"type": "error", "dictation_id": dictation_id, "message": redact(f"{type(exc).__name__}: {exc}")})
            return
        msg = {"type": kind, "dictation_id": dictation_id, "text": text}
        await websocket.send_json(msg)

    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        if message.get("bytes") is not None:
            if dictation_id is None:
                continue
            buf.extend(message["bytes"])
            if len(buf) >= cap:
                await finish("max_duration_reached")
                dictation_id, buf = None, bytearray()
            continue
        try:
            msg = json.loads(message.get("text") or "")
        except ValueError:
            continue
        kind = msg.get("type") if isinstance(msg, dict) else None
        if kind == "prepare":
            await websocket.send_json({"type": "prepared", "expires_in_seconds": PREPARE_TTL_S})
        elif kind == "ping":
            await websocket.send_json({"type": "pong"})
        elif kind == "start":
            dictation_id = str(msg.get("dictation_id") or "")
            buf = bytearray()
            if transcriber is None:
                await websocket.send_json({"type": "error", "dictation_id": dictation_id,
                                           "message": "No speech-to-text is configured: set an OpenRouter key (OPENROUTER_API_KEY)."})
                dictation_id = None
            else:
                await websocket.send_json({"type": "ready", "dictation_id": dictation_id, "max_duration_seconds": MAX_DURATION_S})
        elif kind == "stop" and dictation_id is not None:
            await finish("final")
            dictation_id, buf = None, bytearray()
        elif kind == "cancel" and dictation_id is not None:
            await websocket.send_json({"type": "cancelled", "dictation_id": dictation_id})
            dictation_id, buf = None, bytearray()
