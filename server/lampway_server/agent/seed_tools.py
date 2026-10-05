"""The agent's seed-catalogue tool (seeds.py). Paths are jailed to the project root; the agent records as ``agent`` always: it can propose a verdict, never pick."""

import asyncio
import json

from ..seeds import Catalog, SeedError
from . import server_tools as ST
from .providers.base import ToolSpec

NAMES = {"lampway_seed_catalog"}


def specs() -> list:
    return [ToolSpec("lampway_seed_catalog", "The catalogue of every Tripo seed (generation variants, banked rerolls) with stage, model, settings, proportion score and verdict. verb: list "
                     "(piece, by score|created) | show (id) | ingest_variants (file = variants.json from tripo.fetch, piece) | ingest_harvest (file = harvest.json from tripo.regen.harvest, piece) "
                     "| ingest_scores (file = scores.json from the proportion tools; matched by directory/stem) | verdict (id prefix, verdict pick|reroll|reject|usable|fix, note). "
                     "No signed URL is ever stored. You may propose usable/fix/reroll/reject; only the captain picks a seed.",
                     {"type": "object", "additionalProperties": False, "required": ["verb"], "properties": {
                         "verb": {"type": "string"}, "piece": {"type": "string"}, "file": {"type": "string"}, "id": {"type": "string"}, "verdict": {"type": "string"},
                         "note": {"type": "string"}, "by": {"type": "string"}, "settings": {"type": "object"}, "model_version": {"type": "string"}}})]


async def call(name: str, arguments: dict) -> tuple:
    a = arguments if isinstance(arguments, dict) else {}
    cat = Catalog()
    verb = str(a.get("verb") or "")
    try:
        if verb == "list":
            return json.dumps({"table": cat.list(a.get("piece"), a.get("by") or "score")}), False
        if verb == "show":
            return json.dumps(cat.show(str(a.get("id") or ""))), False
        if verb in ("ingest_variants", "ingest_harvest", "ingest_scores"):
            path = ST.jail(str(a.get("file") or ""))
            if verb == "ingest_scores":
                out = await asyncio.to_thread(cat.ingest_scores, path)
            elif verb == "ingest_harvest":
                out = await asyncio.to_thread(cat.ingest_harvest, path, str(a.get("piece") or ""), a.get("model_version"))
            else:
                out = await asyncio.to_thread(cat.ingest_variants, path, str(a.get("piece") or ""), None, a.get("settings"), a.get("model_version"))
            return json.dumps(out), False
        if verb == "verdict":
            return json.dumps(await asyncio.to_thread(cat.verdict, str(a.get("id") or ""), str(a.get("verdict") or ""), str(a.get("note") or ""), "", "agent")), False
    except (SeedError, ST.BadToolCall, ValueError, KeyError) as exc:
        return str(exc), True
    return f"unknown seed_catalog verb {verb!r}: list | show | ingest_variants | ingest_harvest | ingest_scores | verdict", True
