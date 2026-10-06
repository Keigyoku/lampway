"""The card registry (specs/mrmak/09-report-cards.md sections 5-6): ``<project root>/cards/cards.json`` = ``{"entities": [...]}``, one card per piece or task, its report
pages as steps (tabs). Every write is a read-modify-write under an exclusive file lock (threads and processes alike) with an atomic replace, and it merges into the parsed
dict, so fields this code does not know, on a card or at the root, survive every write. A write bumps ``updated`` to the local day."""
from __future__ import annotations

import contextlib
import json
import os
import re
import threading
import time
from html.parser import HTMLParser
from pathlib import Path

try:
    import fcntl
except ImportError:                                   # pragma: no cover
    fcntl = None

STATUSES = ("active", "done", "archived")
STEP_EXT = (".html", ".md", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm")
MAX_STEPS, MAX_DESCRIPTION, READ_CAP, STEP_MAX_BYTES = 24, 400, 12000, 3 * 1024 * 1024
_TLOCK = threading.Lock()


class CardError(ValueError):
    pass


def local_day() -> str:
    return time.strftime("%Y-%m-%d")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:48] or "card"


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        self._skip += tag in ("script", "style")

    def handle_endtag(self, tag):
        self._skip -= tag in ("script", "style") and self._skip > 0

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


class Registry:
    def __init__(self, project_root, today=local_day):
        self.root = Path(project_root)
        self.dir = self.root / "cards"
        self.path = self.dir / "cards.json"
        self.today = today

    # ---- the file
    @contextlib.contextmanager
    def _locked(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        with _TLOCK, open(self.dir / ".cards.lock", "a+") as fh:
            if fcntl:
                fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl:
                    fcntl.flock(fh, fcntl.LOCK_UN)

    def _load(self) -> dict:
        if not self.path.exists():
            return {"entities": []}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data.setdefault("entities", [])
        return data

    def _save(self, data: dict) -> None:
        tmp = self.path.with_name(f".cards.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def _find(self, data: dict, card_id: str) -> dict:
        card = next((c for c in data["entities"] if c.get("id") == card_id), None)
        if card is None:
            raise CardError(f"no card {card_id!r}: list them with lampway_cards {{action: list}}")
        return card

    # ---- cards
    def create(self, card: dict) -> dict:
        title = str(card.get("title") or "").strip()
        if not title:
            raise CardError("a card needs a title")
        if len(str(card.get("description") or "")) > MAX_DESCRIPTION:
            raise CardError(f"the description is at most {MAX_DESCRIPTION} characters")
        with self._locked():
            data = self._load()
            base, ids = _slug(title), {c.get("id") for c in data["entities"]}
            cid = base if base not in ids else next(f"{base}-{n}" for n in range(2, 10000) if f"{base}-{n}" not in ids)
            day = self.today()
            folder = f"{day}_{cid}"
            if any(c.get("folder") == folder for c in data["entities"]):
                raise CardError(f"the folder {folder} already belongs to another card")
            new = {**card, "id": cid, "title": title, "description": str(card.get("description") or ""), "type": card.get("type", "report"),
                   "category": card.get("category", ""), "created": day, "updated": day, "folder": folder, "steps": [], "default_step": 0,
                   "status": "active", "pinned": False}
            data["entities"].append(new)
            (self.dir / folder).mkdir(parents=True, exist_ok=True)
            self._save(data)
            return dict(new)

    def update(self, card_id: str, **fields) -> dict:
        if "status" in fields and fields["status"] not in STATUSES:
            raise CardError("status is active, done or archived")
        if "pinned" in fields and not isinstance(fields["pinned"], bool):
            raise CardError("pinned is true or false")
        with self._locked():
            data = self._load()
            card = self._find(data, card_id)
            card.update({k: v for k, v in fields.items() if k in ("status", "pinned", "title", "description", "category")})
            card["updated"] = self.today()
            self._save(data)
            return dict(card)

    def get(self, card_id: str) -> dict:
        return dict(self._find(self._load(), card_id))

    def all(self) -> list:
        return [dict(c) for c in self._load()["entities"]]

    def set_step(self, card_id: str, name: str, rel: str, viewer: str = "html") -> dict:
        """Add a page as a step, or replace the step of that name: a rebuilt round stays one tab."""
        if Path(rel).is_absolute() or ".." in Path(rel).parts or Path(rel).suffix.lower() not in STEP_EXT:
            raise CardError(f"a step is a relative html, md, txt, image or video path inside the card folder; got {rel!r}")
        with self._locked():
            data = self._load()
            card = self._find(data, card_id)
            steps = [s for s in card.get("steps") or [] if s.get("name") != name]
            if len(steps) >= MAX_STEPS:
                raise CardError(f"a card holds at most {MAX_STEPS} steps: start a new card for this task")
            steps.append({"name": name, "path": rel, "viewer": viewer})
            card["steps"] = steps
            card["updated"] = self.today()
            self._save(data)
            return dict(card)

    def card_dir(self, card: dict) -> Path:
        return self.dir / card["folder"]

    def read(self, card_id: str, step: int = 0) -> dict:
        card = self.get(card_id)
        steps = card.get("steps") or []
        if not steps:
            return {"id": card_id, "text": "", "note": "the card has no pages yet: build one"}
        s = steps[max(0, min(int(step), len(steps) - 1))]
        p = self.card_dir(card) / s["path"]
        if not p.is_file():
            return {"id": card_id, "step": s["name"], "text": "", "note": "folder missing: rebuild or remove the card"}
        if p.stat().st_size > STEP_MAX_BYTES:
            raise CardError(f"{s['name']} is over 3 MB: open it in a browser")
        raw = p.read_text(encoding="utf-8", errors="replace")
        if p.suffix.lower() == ".html":
            parser = _Text()
            parser.feed(raw)
            raw = re.sub(r"\n\s*\n+", "\n", "".join(parser.out)).strip()
        return {"id": card_id, "step": s["name"], "text": raw[:READ_CAP], "truncated": len(raw) > READ_CAP}
