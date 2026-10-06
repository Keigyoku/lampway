"""The slot register (specs/wiki/slot_register.md): a typed, dated, append-only record of every model or Studio slot Lampway mentions. Each row says the slot's
evidence class (the wiki's availability table: paper | repo | demo_shell | caption_demo | official_docs | local_measured), whether a driver exists, the
eligibility the USER stated, the last price read back and when. ``list`` answers 'what can actually run now': a slot is runnable only when a driver
exists in the catalog, its evidence is not a research class, and it was not expired.

The catalog is the Studio action catalog (studios/actions.py) plus the provider routes this server ships outside it (the image and video jobs, the fal
gateway): a row claiming ``driver_exists`` for anything else is refused. The seed (the Studio families from the catalog and the wiki's research leads, each
with its source line) is code, dated, never written; recorded rows go to <project root>/ledger/slots.jsonl, one JSON per line, never edited: a correction
is a new row and the latest row per slot wins. Stale: a row whose read-back (else its record date) is older than STALE_DAYS [UNVERIFIED policy]."""

import datetime as _dt
import json
import os
import threading
from pathlib import Path
from typing import Optional

try:
    import fcntl
except ImportError:                                  # pragma: no cover
    fcntl = None

EVIDENCE = ("paper", "repo", "demo_shell", "caption_demo", "official_docs", "local_measured")
RESEARCH = ("paper", "repo", "demo_shell")
BYS = ("captain", "agent", "rule")
STALE_DAYS = 30
SEED_DATE = "2026-10-05"
_LOCK = threading.Lock()

# The routes outside the Studio catalog that are drivers all the same: the server runs them.
PROVIDER_ROUTES = {
    "higgsfield.video_gen": ("higgsfield", "official_docs", "server videogen.py + higgsfield*.py (Higgsfield MCP; no generation run live)"),
    "openrouter.image_gen": ("openrouter", "official_docs", "server imagegen.py (OpenRouter images endpoint)"),
    "openrouter.video_gen": ("openrouter", "official_docs", "server videogen.py (OpenRouter video route)"),
    "fal.gateway": ("fal", "official_docs", "server fal.py (fake transport only; the live leg waits for the user's key)"),
}

# The wiki's research leads: never runnable here; no third-party code is run for any of them. Sources are wiki file:line.
RESEARCH_LEADS = (
    ("arbor", "paper", "wiki concepts/geometry-research-and-product-availability.md:22 (constraint-guided inference: a research lead)"),
    ("kaininja", "demo_shell", "wiki concepts/geometry-research-and-product-availability.md:22; sources/videos/video-tZnL7_V_ki0.md:25 (described as unreleased)"),
    ("worldsculpt", "paper", "wiki concepts/geometry-research-and-product-availability.md:22 (object/box conditioning: a research lead)"),
    ("hktex", "paper", "wiki concepts/geometry-research-and-product-availability.md:22 (UV-free texture representation: a research lead)"),
    ("trellis", "repo", "wiki entities/trellis.md:11 (github microsoft/TRELLIS: a developer route)"),
    ("trellis2", "repo", "wiki entities/trellis.md:11,13 (github microsoft/TRELLIS.2: Linux, substantial GPU memory)"),
    ("hunyuan3d_2_1", "repo", "wiki entities/hunyuan3d.md:13 (official 2.1 repository: an open-model route)"),
    ("rodin.partial_edit", "caption_demo", "wiki entities/rodin.md:19 (imported-mesh region edit: a creator account, locality unproven)"),
    ("modddif.geometry_editor", "official_docs", "wiki entities/modddif.md:15 (Geometry Editor docs: selection then Move/Rotate/Scale; no driver)"),
    ("3daistudio.painter_v2", "official_docs", "wiki entities/3d-ai-studio.md:13 (Painter V2 beta documentation; no driver)"),
)


class SlotError(ValueError):
    pass


def catalog() -> dict:
    """slot id -> (family, default evidence, source) for every slot this server has a driver for."""
    from .studios.actions import ACTIONS
    out = {}
    for aid in ACTIONS:
        fam = aid.split(".", 1)[0]
        rest = ".rest." in aid or fam in ("meshy", "hi3d", "hyper3d")
        out[aid] = (fam, "official_docs" if rest else "local_measured",
                    "server studios/rest/shapes.py (the docs' list price, dated; fake transport only)" if rest else
                    "server studios/actions.py + the owner's shelf drivers (measured on his account; never run live from Lampway)")
    out.update(PROVIDER_ROUTES)
    return out


def seed() -> list:
    rows = []
    for slot, (fam, ev, src) in sorted(catalog().items()):
        rows.append({"slot": slot, "family": fam, "kind": "studio", "evidence": ev, "driver_exists": True, "eligibility": None, "price_read_back": None,
                     "read_back_at": None, "source": src, "by": "rule", "recorded_at": SEED_DATE})
    for slot, ev, src in RESEARCH_LEADS:
        rows.append({"slot": slot, "family": slot.split(".", 1)[0], "kind": "research", "evidence": ev, "driver_exists": False, "eligibility": None,
                     "price_read_back": None, "read_back_at": None, "source": src, "by": "rule", "recorded_at": SEED_DATE})
    return rows


def default_path() -> Path:
    return Path(os.environ.get("LAMPWAY_PROJECT_ROOT") or Path.home() / ".local/share/lampway/projects") / "ledger" / "slots.jsonl"


def _date(s) -> Optional[_dt.date]:
    if not s:
        return None
    try:
        return _dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        raise SlotError(f"{s!r} is not an ISO date (YYYY-MM-DD)") from None


class SlotRegister:
    def __init__(self, path, today: Optional[str] = None):
        self.path = Path(path)
        self.today = _date(today) if today else _dt.date.today()

    def _rows(self) -> list:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
        return out

    def _append(self, row: dict) -> None:
        with _LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                if fcntl:
                    fcntl.flock(fh, fcntl.LOCK_EX)
                fh.write(json.dumps(row, sort_keys=True) + "\n")

    def _decorate(self, row: dict) -> dict:
        r = dict(row)
        when = _date(r.get("read_back_at")) or _date(r.get("recorded_at"))
        r["stale"] = bool(when is None or (self.today - when).days > STALE_DAYS)
        r["stale_policy_days"] = STALE_DAYS
        r["runnable"] = bool(r.get("driver_exists") and r["slot"] in catalog() and r.get("evidence") not in RESEARCH and not r.get("expired"))
        return r

    def _history(self) -> dict:
        hist = {}
        for r in seed() + self._rows():
            hist.setdefault(r["slot"], []).append(r)
        return hist

    def list(self, family: str = "", runnable_only: bool = False) -> list:
        out = [self._decorate(h[-1]) for _slot, h in sorted(self._history().items())]
        if family:
            out = [r for r in out if r.get("family") == family]
        return [r for r in out if r["runnable"]] if runnable_only else out

    def show(self, slot: str) -> dict:
        h = self._history().get(slot)
        if not h:
            raise SlotError(f"no slot {slot!r} in the register; list shows them all")
        return {**self._decorate(h[-1]), "history": h}

    def record(self, slot: str, row: dict) -> dict:
        slot = str(slot or "").strip()
        if not slot:
            raise SlotError("record needs a slot id (e.g. tripo.mesh)")
        row = dict(row or {})
        ev = row.get("evidence")
        if ev not in EVIDENCE:
            raise SlotError(f"evidence is one of {EVIDENCE}")
        by = row.get("by", "agent")
        if by not in BYS:
            raise SlotError(f"by is one of {BYS}")
        cat = catalog()
        drv = bool(row.get("driver_exists"))
        if drv and slot not in cat:
            raise SlotError(f"no catalog action named {slot!r}: driver_exists=true needs a Studio action (studios/actions.py) or a server route ({', '.join(PROVIDER_ROUTES)})")
        if drv and ev in RESEARCH:
            raise SlotError(f"evidence {ev!r} is a research class: a research lead has no driver here (record it with driver_exists=false)")
        if row.get("eligibility") and by != "captain":
            raise SlotError("eligibility is the user's statement (which plan, which features): only by=captain records it")
        price = row.get("price_read_back")
        if price is not None and (not isinstance(price, int) or isinstance(price, bool) or price < 0):
            raise SlotError("price_read_back is a whole number of credits read back from the driver, or null")
        if price is not None and not row.get("read_back_at"):
            raise SlotError("a price needs read_back_at: the date the driver read it back")
        _date(row.get("read_back_at"))
        if not str(row.get("source") or "").strip():
            raise SlotError("source is required: a URL or file:line")
        fam = cat[slot][0] if slot in cat else slot.split(".", 1)[0]
        out = {"slot": slot, "family": fam, "kind": "studio" if slot in cat else "research", "evidence": ev, "driver_exists": drv,
               "eligibility": row.get("eligibility"), "price_read_back": price, "read_back_at": row.get("read_back_at"), "source": str(row["source"]),
               "by": by, "recorded_at": self.today.isoformat()}
        self._append(out)
        return out

    def expire(self, slot: str, by: str = "agent") -> dict:
        cur = self.show(slot)
        row = {k: cur.get(k) for k in ("slot", "family", "kind", "evidence", "driver_exists", "eligibility", "source")}
        row.update({"price_read_back": None, "read_back_at": None, "expired": True, "by": by if by in BYS else "agent", "recorded_at": self.today.isoformat()})
        self._append(row)
        return row
