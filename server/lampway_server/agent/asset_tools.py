"""The agent's asset-search tool (specs/mixar_docs/asset_search.md): look in the user's enrolled library BEFORE modelling something new, by text and/or a reference image, and decide: `place` (one confident match
with a margin over the second), `ask` (plausible matches: a thumbnail picker for the user) or `none`. Read-only: nothing lands in the scene and nothing is generated. The margin rule is [UNVERIFIED]."""
import asyncio
import json
from pathlib import Path

from ..assetsearch import MAX_TOP_K
from .providers.base import ToolSpec

NAMES = {"lampway_asset_search"}
MARGIN = 0.1                                   # [UNVERIFIED] the lead the best match needs over the second to be placed without asking


def specs() -> list:
    return [ToolSpec("lampway_asset_search", "Search the user's enrolled asset library by meaning before modelling anything new. `query` (text) and/or `image` (a project-relative reference picture; matched by colour "
                     "unless an embedding model is configured), `top_k` 1..50, `threshold` 0..1 (how eager reuse is, default 0.5), `libraries` to restrict. Returns results (identity name|library|blend_file, name, library, "
                     "score, thumbnail_path, kind) and a decision: place (one confident match), ask (show the user the candidates), none. only_library: an unmatched object stays unmatched, never replaced by a "
                     "generation or a substitute. Read-only: placing is a separate step.",
                     {"type": "object", "additionalProperties": False, "properties": {"query": {"type": "string"}, "image": {"type": "string"}, "top_k": {"type": "integer"}, "threshold": {"type": "number"},
                                                                                        "libraries": {"type": "array", "items": {"type": "string"}}, "only_library": {"type": "boolean"}}})]


def _read_image(root, rel) -> bytes:
    import os
    full = Path(rel) if Path(rel).is_absolute() else Path(root) / rel
    real_root, real = Path(os.path.realpath(root)), Path(os.path.realpath(full))
    if real != real_root and real_root not in real.parents:
        raise ValueError(f"{rel} is outside the project root")
    if not real.is_file():
        raise ValueError(f"{rel} is not a file")
    return real.read_bytes()


def _search(index, root, a: dict) -> dict:
    query, image = (a.get("query") or "").strip(), a.get("image")
    if not query and not image:
        raise ValueError("give a text query or a reference image")
    top_k = 10 if a.get("top_k") is None else int(a["top_k"])
    if not 1 <= top_k <= MAX_TOP_K:
        raise ValueError(f"top_k is 1..{MAX_TOP_K}")
    threshold = 0.5 if a.get("threshold") is None else float(a["threshold"])
    if not 0 <= threshold <= 1:
        raise ValueError("threshold is 0..1")
    try:
        rows = index.search(query, _read_image(root, image) if image else None, top_k, a.get("libraries") or None)
    except LookupError:
        raise ValueError("no trained model: train the asset library first")
    results = [{"identity": f"{r['metadata']['name']}|{r['metadata']['library']}|{r['metadata']['blend_file']}", "name": r["metadata"]["name"], "library": r["metadata"]["library"],
                "score": r["similarity_score"], "thumbnail_path": None, "kind": r["metadata"]["type"]} for r in rows]
    if not results:
        decision = "none"
    elif results[0]["score"] >= threshold and (len(results) == 1 or results[0]["score"] - results[1]["score"] >= MARGIN or results[1]["score"] < threshold):
        decision = "place"
    else:
        decision = "ask"
    out = {"ok": True, "results": results, "decision": decision, "threshold": threshold}
    if a.get("only_library") and decision == "none":
        out["note"] = "only_library: nothing in the library matches, and no generation or substitute is offered; tell the user it is missing"
    return out


async def call(index, root, name: str, arguments: dict) -> tuple:
    if index is None:
        return "the asset library is not available on this server", True
    try:
        return json.dumps(await asyncio.to_thread(_search, index, root, arguments or {})), False
    except ValueError as exc:
        return str(exc), True
