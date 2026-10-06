"""decisions_model: a small judge that picks ONE of a closed set of options (flagged-frame review before the user sees it, caption triage).

Routing law (captain 2026-10-05): the eligible-model list is computed LIVE from OpenRouter's model list and its ZDR endpoint list (GET /api/v1/endpoints/zdr),
never hard-coded. Private content goes only to a ZDR endpoint, with ``provider: {"zdr": true, "data_collection": "deny"}``, and never to a ``:free`` model; with none
eligible the call is refused and nothing is sent. The candidates below are a preference list, not an allow-list of what is eligible. Response shapes are
[UNVERIFIED] until a live run with a key (``needs_key``)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import httpx

from . import egress as E
from .agent.providers.openrouter import BASE_URL, REFERER, TITLE, redact

CANDIDATES = ("inception/mercury-decide:free", "cloudflare/clef", "liquid/d1", "perplexity/pplx-decider-v1-27b", "upstage/solar-decide")
PRIVATE_ROUTING = {"zdr": True, "data_collection": "deny"}
GOLDENS = Path(__file__).with_name("decisions_goldens.json")


def load_goldens(path=None) -> list:
    return json.loads(Path(path or GOLDENS).read_text(encoding="utf-8"))


def _ids(payload, *keys) -> set:
    out = set()
    for row in (payload or {}).get("data", []) or []:
        for k in keys:
            if isinstance(row, dict) and isinstance(row.get(k), str):
                out.add(row[k])
                break
    return out


class Decider:
    def __init__(self, api_key: str, transport=None, base_url: str = BASE_URL, max_tokens: int = 200):
        self._key, self._transport, self._base, self._max = api_key, transport, base_url, max_tokens

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=60, headers={"Authorization": f"Bearer {self._key}", "HTTP-Referer": REFERER, "X-Title": TITLE})

    def eligible(self, content_class: str) -> list:
        with E.context(route="openrouter", kind="request", content_class=content_class), self._client() as c:
            live = _ids(c.get(f"{self._base}/models").json(), "id")
            zdr = _ids(c.get(f"{self._base}/endpoints/zdr").json(), "model_id", "id", "model") if content_class == "private" else None
        out = [m for m in CANDIDATES if m in live]
        if content_class == "private":
            out = [m for m in out if m in zdr and not m.endswith(":free")]
        return out

    def decide(self, question: str, options: list, content_class: str = "private", evidence: str = "", model: Optional[str] = None) -> dict:
        models = self.eligible(content_class) if model is None else [model]
        if not models:
            return {"choice": None, "refused": "no ZDR endpoint is eligible for private content (none of the candidates is on the live ZDR list); nothing was sent"}
        model = models[0]
        body = {"model": model, "max_tokens": self._max, "usage": {"include": True}, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": 'Answer with JSON {"choice": <one of the options, verbatim>, "reason": <one short sentence>}.'},
                             {"role": "user", "content": f"{question}\nOptions: {json.dumps(options)}" + (f"\nEvidence: {evidence}" if evidence else "")}]}
        if content_class == "private":
            body["provider"] = dict(PRIVATE_ROUTING)
        with E.context(route="openrouter", kind="request", content_class=content_class,
                       constraints=dict(PRIVATE_ROUTING) if content_class == "private" else {}), self._client() as c:
            r = c.post(f"{self._base}/chat/completions", json=body)
        if r.status_code >= 400:
            return {"choice": None, "model": model, "refused": redact(f"OpenRouter answered HTTP {r.status_code}", self._key)}
        data = r.json()
        try:
            parsed = json.loads(data["choices"][0]["message"]["content"])
            choice = parsed.get("choice")
        except (KeyError, IndexError, ValueError, TypeError, AttributeError):
            return {"choice": None, "model": model, "refused": "the answer was not the requested JSON"}
        cost = (data.get("usage") or {}).get("cost")
        if choice not in options:
            return {"choice": None, "model": model, "refused": f"the answer is outside the options: {redact(str(choice)[:40], self._key)}", "cost_usd": cost}
        return {"choice": choice, "reason": redact(str(parsed.get("reason", ""))[:200], self._key), "model": model, "cost_usd": cost}


def evaluate(decider: Decider, goldens: list, content_class: str = "private") -> dict:
    """Each eligible candidate against the goldens: correct / total / accuracy (a refusal or a wrong answer is not correct)."""
    report = {}
    for m in decider.eligible(content_class):
        ok = sum(1 for g in goldens if decider.decide(g["question"], g["options"], content_class, g.get("evidence", ""), model=m)["choice"] == g["expected"])
        report[m] = {"correct": ok, "total": len(goldens), "accuracy": round(ok / len(goldens), 4) if goldens else 0.0}
    return {"models": report, "content_class": content_class}
