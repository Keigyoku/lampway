"""The vision judge (STATUS O38): frames or a native video judged by a vision model through OpenRouter, a STRICT JSON verdict (PASS | FAIL | INCONCLUSIVE with
timestamped findings and limitations), per-purpose judge prompts (locomotion, air, combat, moment), a receipt per judgment, and the law that INCONCLUSIVE is never
upgraded. Routing follows decisions_model's law: the eligible list is live (OpenRouter /models with the modality, /endpoints/zdr), private content goes only to a
ZDR endpoint with data_collection=deny and never to a ':free' model. Fake transport only; provider shapes are [UNVERIFIED] until a live run with a key."""

import json

import httpx
import pytest

from lampway_server import egress as E
from lampway_server import vision_judge as V

KEY = "sk-or-v1-" + "ab12" * 16
MODELS = {"data": [
    {"id": "google/gemini-3.8-flash", "architecture": {"input_modalities": ["text", "image", "video"]}},
    {"id": "z-ai/glm-5.3-flash", "architecture": {"input_modalities": ["text", "image"]}},
    {"id": "free/vision:free", "architecture": {"input_modalities": ["text", "image"]}},
    {"id": "text/only", "architecture": {"input_modalities": ["text"]}}]}
ZDR = {"data": [{"model_id": "google/gemini-3.8-flash"}, {"model_id": "z-ai/glm-5.3-flash"}, {"model_id": "free/vision:free"}, {"model_id": "text/only"}]}
GOOD = {"verdict": "FAIL", "findings": [{"timestamp": 1.5, "observation": "the stance foot slides"}], "limitations": ["frames only"],
        "criteria": [{"name": "gait", "verdict": "FAIL"}]}


def fake(answer=GOOD, seen=None, cost=0.002):
    def handler(req: httpx.Request):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELS)
        if req.url.path.endswith("/endpoints/zdr"):
            return httpx.Response(200, json=ZDR)
        body = json.loads(req.content)
        if seen is not None:
            seen.append(body)
        text = answer if isinstance(answer, str) else json.dumps(answer)
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}], "usage": {"cost": cost}})
    return httpx.MockTransport(handler)


def frames(tmp_path, n=3, name="frames"):
    d = tmp_path / name
    d.mkdir()
    for i in range(n):
        (d / f"{i:04d}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([i]) * 64)
    return d


def judge(tmp_path, transport, **kw):
    return V.VisionJudge(KEY, transport=transport, receipts=tmp_path / "receipts")


def test_the_eligible_list_is_live_needs_the_modality_and_keeps_private_on_zdr_never_free(tmp_path):
    j = judge(tmp_path, fake())
    assert j.eligible("private", "image") == ["google/gemini-3.8-flash", "z-ai/glm-5.3-flash"]
    assert j.eligible("private", "video") == ["google/gemini-3.8-flash"], "native video only to a model that declares video input"
    assert "free/vision:free" in j.eligible("public", "image") and "text/only" not in j.eligible("public", "image")


def test_a_private_judgment_carries_zdr_the_purpose_prompt_and_the_frames_in_order(tmp_path):
    seen = []
    r = judge(tmp_path, fake(seen=seen)).judge(frames(tmp_path), "locomotion", reference=frames(tmp_path, 2, "ref"))
    body = seen[0]
    assert body["provider"] == {"zdr": True, "data_collection": "deny"} and body["model"] == "google/gemini-3.8-flash"
    parts = body["messages"][-1]["content"]
    text = " ".join(p["text"] for p in parts if p["type"] == "text")
    assert "INCONCLUSIVE is not PASS" in text and "gait and ground contact" in text and "Media 1..3: candidate" in text and "Media 4..5: reference" in text
    assert [p["type"] for p in parts if p["type"] != "text"] == ["image_url"] * 5
    assert r["verdict"] == "FAIL" and r["status"] == "complete" and r["findings"][0]["timestamp"] == 1.5 and r["cost_usd"] == 0.002


@pytest.mark.parametrize("raw", ["Looks great to me!", json.dumps({"findings": []}), json.dumps({"verdict": "great", "findings": [], "limitations": []}),
                                 json.dumps({"verdict": "PASS", "findings": "fine", "limitations": []}),
                                 json.dumps({"verdict": "PASS", "findings": [{"observation": "no time"}], "limitations": []}),
                                 "```json\n{}\n```\n```json\n{}\n```"])
def test_anything_but_the_strict_verdict_is_inconclusive_never_pass(tmp_path, raw):
    r = judge(tmp_path, fake(answer=raw)).judge(frames(tmp_path), "judge")
    assert r["status"] == "failed" and r["verdict"] == "INCONCLUSIVE" and r["schema_errors"], r


def test_inconclusive_is_never_upgraded(tmp_path):
    up = dict(GOOD, verdict="PASS", criteria=[{"name": "gait", "verdict": "PASS"}, {"name": "landing", "verdict": "INCONCLUSIVE"}])
    r = judge(tmp_path, fake(answer=up)).judge(frames(tmp_path), "air")
    assert r["verdict"] == "INCONCLUSIVE" and r["model_verdict"] == "PASS" and "landing" in r["downgraded_by"], r
    down = dict(GOOD, verdict="FAIL", criteria=[{"name": "gait", "verdict": "PASS"}])
    assert judge(tmp_path / "b", fake(answer=down)).judge(frames(tmp_path, name="f2"), "air")["verdict"] == "FAIL"


def test_the_receipt_is_idempotent_and_media_drift_is_refused(tmp_path):
    seen = []
    j = judge(tmp_path, fake(seen=seen))
    f = frames(tmp_path)
    r1 = j.judge(f, "combat")
    r2 = j.judge(f, "combat")
    assert len(seen) == 1 and r2["noop"] is True and r2["receipt"] == r1["receipt"]
    rec = json.loads(open(r1["receipt"]).read())
    assert rec["raw_model_text"] and rec["identity"]["media"][0]["sha256"] and "base64" not in json.dumps(rec["request"])
    (f / "0000.png").write_bytes(b"changed")
    r3 = j.judge(f, "combat")
    assert len(seen) == 2 and r3["receipt"] != r1["receipt"], "changed media is a new identity, judged afresh"


def test_reconcile_reads_the_raw_text_and_ignores_an_edited_verdict(tmp_path):
    r = judge(tmp_path, fake(answer=dict(GOOD, verdict="INCONCLUSIVE", criteria=[]))).judge(frames(tmp_path), "moment")
    rec = json.loads(open(r["receipt"]).read())
    rec["verdict"] = "PASS"; rec["output"]["verdict"] = "PASS"
    assert V.reconcile(rec)["verdict"] == "INCONCLUSIVE"


def test_no_eligible_model_or_a_route_switched_off_sends_nothing(tmp_path, monkeypatch):
    global ZDR
    seen = []
    monkeypatch.setitem(ZDR, "data", [])
    r = judge(tmp_path, fake(seen=seen)).judge(frames(tmp_path), "judge")
    assert r["status"] == "refused" and "ZDR" in r["refused"] and seen == []
    monkeypatch.setitem(ZDR, "data", [{"model_id": "google/gemini-3.8-flash"}])
    strict = E.Egress(tmp_path / "egress")
    E.set_active(strict)
    try:
        r = judge(tmp_path / "x", fake(seen=seen)).judge(frames(tmp_path, name="f3"), "judge")
    finally:
        E.set_active(E.Egress.permissive(tmp_path / "egress-p"))
    assert r["status"] == "refused" and "openrouter is off" in r["refused"] and seen == []


def test_an_oversized_request_and_a_mixed_or_empty_media_folder_are_refused(tmp_path):
    big = tmp_path / "big"; big.mkdir()
    (big / "a.png").write_bytes(b"\x89PNG" + b"0" * (15 * 1024 * 1024))
    with pytest.raises(ValueError, match="19,000,000"):
        judge(tmp_path, fake()).judge(big, "judge")
    mixed = tmp_path / "mixed"; mixed.mkdir()
    (mixed / "a.png").write_bytes(b"x"); (mixed / "b.mp4").write_bytes(b"x")
    with pytest.raises(ValueError, match="only images"):
        judge(tmp_path, fake()).judge(mixed, "judge")
    with pytest.raises(ValueError, match="purpose"):
        judge(tmp_path, fake()).judge(frames(tmp_path), "vibes")


def test_the_spend_ledger_is_checked_before_and_charged_after(tmp_path):
    from lampway_server.agent.providers.openrouter import SpendLedger
    led = SpendLedger(1.0)
    j = V.VisionJudge(KEY, transport=fake(cost=0.25), receipts=tmp_path / "r", ledger=led)
    j.judge(frames(tmp_path), "judge")
    assert led.spent == pytest.approx(0.25)
    spent = SpendLedger(0.1); spent.add(0.2, "x")
    r = V.VisionJudge(KEY, transport=fake(), receipts=tmp_path / "r2", ledger=spent).judge(frames(tmp_path, name="f9"), "judge")
    assert r["status"] == "refused" and "ceiling" in r["refused"]


def test_the_agent_tool_plans_by_default_and_names_the_missing_key(tmp_path, monkeypatch):
    import asyncio
    from lampway_server.agent import orphan_server_tools as OST
    from lampway_server.agent import tools as T
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LAMPWAY_OPENROUTER_KEY_FILE", raising=False)
    frames(tmp_path)
    assert "lampway_vision_judge" in OST.NAMES and "lampway_vision_judge" in {t.name for t in T.TOOLS}
    text, err = asyncio.run(OST.call(None, "lampway_vision_judge", {"media": "frames", "purpose": "air"}))
    plan = json.loads(text)
    assert not err and plan["dry_run"] and plan["media"] == 3 and "air triplets" in plan["prompt"], plan
    text, err = asyncio.run(OST.call(None, "lampway_vision_judge", {"media": "frames", "purpose": "air", "dry_run": False}))
    assert err and "OPENROUTER_API_KEY" in text, text
    text, err = asyncio.run(OST.call(None, "lampway_vision_judge", {"media": "../outside", "purpose": "air"}))
    assert err
