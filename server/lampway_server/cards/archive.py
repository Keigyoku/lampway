"""Which cards show (specs/mrmak/09-report-cards.md section 6.2): a card is archived when its status says so, or when it is not pinned, not a sample and untouched for
seven days; freshly touched work sorts first whatever its status; a search reaches into the archive. ``today`` is handed in, so the rule is tested with a fixed date."""
from __future__ import annotations

from datetime import date

ARCHIVE_DAYS = 7


def _day(s: str) -> date:
    return date.fromisoformat(str(s)[:10])


def is_archived(card: dict, today: str) -> bool:
    if card.get("status") == "archived":
        return True
    if card.get("pinned") or card.get("sample"):
        return False
    touched = card.get("updated") or card.get("created")
    return bool(touched) and (_day(today) - _day(touched)).days >= ARCHIVE_DAYS


def visible(cards: list, today: str, query: str = "", status: str = "", category: str = "") -> list:
    q = str(query or "").strip().lower()
    out = []
    for c in cards:
        if status and status != "all" and c.get("status") != status and not (status == "archived" and is_archived(c, today)):
            continue
        if category and c.get("category") != category:
            continue
        if q:
            if q not in " ".join(str(c.get(k) or "") for k in ("title", "description", "category", "id")).lower():
                continue
        elif status != "archived" and status != "all" and is_archived(c, today):
            continue
        out.append(c)
    return sorted(out, key=lambda c: (str(c.get("updated") or c.get("created") or ""), c.get("status") == "active", c.get("id")), reverse=True)


def brief(card: dict, today: str) -> dict:
    return {k: card.get(k) for k in ("id", "title", "description", "category", "status", "pinned", "created", "updated")} | {
        "archived": is_archived(card, today), "steps": [s.get("name") for s in card.get("steps") or []]}
