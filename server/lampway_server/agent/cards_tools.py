"""The agent's ``lampway_cards`` tool (specs/mrmak/09-report-cards.md section 4): list, read, update, activity, build and open project cards, run here on the server over
the same service as the /app/cards routes. Building writes report pages under <project root>/cards only; nothing is spent."""
import asyncio
import json

from ..cards.registry import CardError
from ..cards.service import ACTIONS, Cards
from .providers.base import ToolSpec

NAMES = {"lampway_cards"}
CARDS = Cards()


def specs() -> list:
    return [ToolSpec("lampway_cards", "Project cards: one card per piece or task with its report pages as tabs, generated from the ledger and the prompt run log. action list "
                     "(query, status active|done|archived|all, category), read (id, step: the page as plain text), update (id, status, pinned), activity (date YYYY-MM-DD: the "
                     "cards, ledger rows and spend of that day), build (card: an id or a new title, kind design_versions|motion_tests|receipt, piece, round auto or a number), "
                     "open (id, step: a URL on the cards' own local origin for the user's browser). Pages never invent a review: the decision text is the user's.",
                     {"type": "object", "additionalProperties": False, "required": ["action"],
                      "properties": {"action": {"type": "string"}, "id": {"type": "string"}, "query": {"type": "string"}, "status": {"type": "string"}, "category": {"type": "string"},
                                     "pinned": {"type": "boolean"}, "step": {"type": "integer"}, "date": {"type": "string"}, "card": {"type": "string"},
                                     "kind": {"type": "string"}, "piece": {"type": "string"}, "round": {"type": "string"}, "title": {"type": "string"}}})]


def _run(cards: Cards, a: dict) -> dict:
    act = a.get("action")
    if act not in ACTIONS:
        raise CardError(f"action is one of {list(ACTIONS)}")
    if act == "list":
        return cards.list(a.get("query") or "", a.get("status") or "", a.get("category") or "")
    if act == "read":
        return cards.read(str(a["id"]), int(a.get("step") or 0))
    if act == "update":
        return cards.update(str(a["id"]), **{k: a[k] for k in ("status", "pinned") if k in a})
    if act == "activity":
        return cards.activity(str(a.get("date") or ""))
    if act == "build":
        return cards.build(str(a.get("card") or a.get("piece") or ""), str(a.get("kind") or ""), str(a.get("piece") or ""), a.get("round") or "auto", a.get("title"))
    return cards.open(str(a["id"]), int(a.get("step") or 0))


async def call(cards, name: str, arguments: dict) -> tuple:
    try:
        out = await asyncio.to_thread(_run, cards or CARDS, arguments if isinstance(arguments, dict) else {})
    except KeyError as exc:
        return f"lampway_cards needs {exc}", True
    except (CardError, ValueError) as exc:
        return str(exc), True
    return json.dumps({"ok": True, **out}, default=str), False
