"""Cards as one service the REST routes and the agent tool share (specs/mrmak/09-report-cards.md section 4): list, read, update, activity, build and open, over the
registry under the project root, the experiment ledger and the prompt run log. ``open`` hands back a URL on the content server's own origin (started on first use)."""
from __future__ import annotations

import os
import threading
from pathlib import Path

from ..ledger import Ledger
from ..prompts.runlog import RunLog
from . import activity as ACT
from . import archive as AR
from . import build as BLD
from .content import ContentServer
from .registry import CardError, Registry, local_day

ACTIONS = ("list", "read", "update", "activity", "build", "open")


def project_root() -> Path:
    return Path(os.environ.get("LAMPWAY_PROJECT_ROOT") or Path.home() / ".local/share/lampway/projects")


class Cards:
    def __init__(self, root=None, api_port: int = 8787, host: str = "127.0.0.1"):
        self._root, self.api_port, self.host = root, api_port, host
        self._content = None
        self._lock = threading.Lock()

    @property
    def root(self) -> Path:
        return Path(self._root or project_root())

    def reg(self) -> Registry:
        return Registry(self.root)

    def ledger(self) -> Ledger:
        return Ledger(self.root / "ledger" / "runs.jsonl")

    def list(self, query="", status="", category="") -> dict:
        today = local_day()
        cards = AR.visible(self.reg().all(), today, query=query, status=status, category=category)
        return {"cards": [AR.brief(c, today) for c in cards], "total": len(cards)}

    def read(self, card_id: str, step: int = 0) -> dict:
        return self.reg().read(card_id, step)

    def update(self, card_id: str, **fields) -> dict:
        out = self.reg().update(card_id, **{k: v for k, v in fields.items() if k in ("status", "pinned")})
        return AR.brief(out, local_day())

    def activity(self, date: str) -> dict:
        return ACT.activity(self.reg(), self.ledger(), date or local_day(), git_root=self.root)

    def build(self, card: str, kind: str, piece: str, round_="auto", title=None) -> dict:
        reg = self.reg()
        led = self.ledger()
        if not led.list(piece=piece):
            raise CardError(f"no runs recorded for {piece}: nothing to report")
        found = next((c for c in reg.all() if card in (c.get("id"), c.get("title"))), None)
        cid = found["id"] if found else reg.create({"title": card, "category": piece})["id"]
        path = BLD.build(reg, led, RunLog(led.path), cid, kind, piece, round_, title)
        return {"page": path, "card": AR.brief(reg.get(cid), local_day())}

    def content(self) -> ContentServer:
        with self._lock:
            if self._content is None:
                self._content = ContentServer(self.reg().dir, host=self.host, port=0, api_port=self.api_port)
                self._content.serve()
            return self._content

    def open(self, card_id: str, step: int = 0) -> dict:
        card = self.reg().get(card_id)
        steps = card.get("steps") or []
        if not steps:
            raise CardError("the card has no pages yet: build one")
        s = steps[max(0, min(int(step), len(steps) - 1))]
        return {"url": self.content().url(f"{card['folder']}/{s['path']}"), "step": s["name"]}
