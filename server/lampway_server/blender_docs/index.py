# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Adapt Blender Lab's pinned lookup/search to the compact T3 reply contract."""
from functools import lru_cache
import json
from pathlib import Path
import re

from .vendor import api_lookup, rst_doc_search, rst_parse_docs

DATA = Path(__file__).with_name("data")


@lru_cache(maxsize=1)
def manifest():
    return normalize_manifest(json.loads((DATA / "manifest.json").read_text(encoding="utf-8")))


def normalize_manifest(raw):
    """Keep the runtime interface stable across publication format versions.

    Version 2 serializes paths, digests and SPDX identifiers as typed records,
    rather than making public API filenames look like credential assignments.
    No source hash, licence or revision changes during normalization.
    """
    if raw.get("format_version", 1) == 1:
        return raw
    if raw["format_version"] != 2:
        raise ValueError("unsupported offline documentation manifest format")
    def rows_to_mapping(rows, key, value):
        result = {}
        for row in rows:
            if row[key] in result:
                raise ValueError("duplicate offline documentation manifest " + key)
            result[row[key]] = row[value]
        return result
    return {**raw,
            "files_sha256": rows_to_mapping(raw["files_sha256"], "path", "sha256"),
            "source_licenses": rows_to_mapping(raw["source_licenses"], "scope", "identifier"),
            "api_generator_sha256": raw["api_generator"]["sha256"]}


def truncate(value, full=False):
    if full or len(value) <= 200:
        return value
    return value[:200] + f"... (truncated, {len(value)} chars total; full=true)"


def _signature(content):
    match = re.search(r"^\s*\.\.\s+(\w+)::\s*(.*)$", content, re.MULTILINE)
    return (match.group(1), match.group(2)) if match else ("module", "")


def get(identifier, limit, full):
    raw = api_lookup.lookup(identifier)
    # Blender's class RST nests attributes inside the class directive. Lab's
    # stripped tail lookup misses Object.location when given just location;
    # retry with the containing class name using its existing tree engine.
    if not raw["found"] and raw["kind"] == "partial":
        parent = raw["parent"]
        path = api_lookup._resolve_inside(str(DATA / "api"), parent)
        tail = identifier[len(parent)+1:]
        block = rst_parse_docs.find_definition_in_doctree(
            rst_parse_docs.doctree_for_path(path), parent.rsplit(".", 1)[-1] + "." + tail)
        if block:
            raw = {"found": True, "kind": "definition", "content": block}
    if not raw["found"]:
        return {"identifier": identifier, "results": []}, 0, 0
    if raw["kind"] == "namespace":
        children = [{"name": name, "kind": "namespace"} for name in raw["submodules"]]
        return {"identifier": identifier, "kind": "namespace", "signature": "", "doc": "", "children": children[:limit]}, min(limit, len(children)), len(children)
    content = raw.get("content", "")
    # Upstream's exact lookup compresses very large files at 32 KB. T3 full=true
    # promises the full text, so read that same jailed pinned RST for exact hits.
    if raw["kind"] == "exact":
        path = api_lookup._resolve_inside(str(DATA / "api"), identifier)
        if path:
            content = Path(path).read_text(encoding="utf-8")
    kind, signature = _signature(content)
    children = []
    if raw["kind"] == "exact":
        path = api_lookup._resolve_inside(str(DATA / "api"), identifier)
        if path:
            names = rst_parse_docs.list_doctree_definitions(rst_parse_docs.doctree_for_path(path))
            children = [{"name": identifier + "." + name, "kind": "definition"} for name in names]
    return {"identifier": identifier, "kind": kind, "signature": signature,
            "doc": truncate(content, full), "children": children[:limit],
            "children_count": min(limit, len(children)), "children_total": len(children)}, 1, 1


def get_manual(identifier, full):
    root = (DATA / "manual").resolve()
    path = (root / (identifier + ".rst")).resolve()
    if root not in path.parents or not path.is_file():
        return {"identifier": identifier, "results": []}, 0, 0
    content = path.read_text(encoding="utf-8")
    title = Path(identifier).name
    lines = content.splitlines()
    for i, line in enumerate(lines[:-1]):
        if line.strip() and len(lines[i+1].strip()) >= 3 and set(lines[i+1].strip()) <= set("=-*^~+#"):
            title = line.strip()
            break
    return {"identifier": identifier, "kind": "manual", "signature": title,
            "doc": truncate(content, full), "children": []}, 1, 1


def search(query, scope, limit, context, full):
    # Request the entire hit count before returning the compact limited rows.
    # The helper applies its proven TF-IDF/path/title ranking to the pinned RST.
    raw = rst_doc_search.search(query, scope, max_results=1_000_000, context=0)
    hits = raw["hits"]
    rows = []
    for rank, hit in enumerate(hits[:limit], 1):
        path = hit["path"]
        title = hit.get("breadcrumb") or Path(path).stem
        text = hit["text"]
        # context is lines, whereas Blender Lab's option is paragraphs. Pull
        # surrounding lines from the same source file around its matching text.
        if context:
            source = (DATA / path).read_text(encoding="utf-8").splitlines()
            tokens = query.lower().split()
            indices = [i for i, line in enumerate(source) if all(t in line.lower() for t in tokens)]
            if indices:
                i = indices[0]
                text = "\n".join(source[max(0, i-context):i+context+1])
        identifier = Path(path).stem if scope == "api" else path.removeprefix("manual/").removesuffix(".rst")
        rows.append({"rank": rank, "identifier": identifier, "title": truncate(title, full), "snippet": truncate(text, full)})
    return {"results": rows}, len(rows), len(hits)
