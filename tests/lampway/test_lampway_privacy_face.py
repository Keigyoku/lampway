# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 12, the privacy face: route chips with one vocabulary everywhere a provider is named, route rows whose switch
needs a confirm row before data may leave, a refusal with its ways forward, a log that never renders content, and the
magenta wire reserved for data leaving."""

import re
import sys
from pathlib import Path

import pytest

from mixar.modules.lampway_tools import privacy_face as P

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def server_routes():
    """The server's route table, as GET /app/egress reports it (one source for the test and the client)."""
    sys.path.insert(0, str(ROOT / "server"))
    try:
        from lampway_server import egress as E
        return [{"id": r.id, "label": r.label, "enabled": False, "retention": r.retention, "training": r.training,
                 "privacy_class": r.privacy_class, "hosts": list(r.hosts), "last_used": None} for r in E.ROUTES.values()]
    finally:
        sys.path.remove(str(ROOT / "server"))


SECTION_4 = ("openrouter", "chatgpt_plan", "claude_plan", "custom_llm", "studio:tripo", "studio:meshy", "studio:hi3d",
             "studio:hyper3d", "higgsfield", "heygen", "fal", "compute:boat", "compute:modal", "compute:runpod")


def test_route_chip_vocabulary(server_routes):
    local = P.chip("local", server_routes)
    assert local == {"icon": "LAMPWAY_LAMP", "text": "this machine", "tone": "muted", "tooltip": "Runs on this machine: nothing leaves"}
    by = {r["id"]: r for r in server_routes}
    for rid in (*SECTION_4, "github"):
        c = P.chip(rid, server_routes)
        want = by[rid]["hosts"][0] if by[rid]["hosts"] else by[rid]["label"]
        assert c["icon"] == "LAMPWAY_WIRE" and c["text"] == want and c["tone"] == "muted", (rid, c)
        assert by[rid]["label"] in c["tooltip"], c
    unknown = P.chip("nowhere", server_routes)
    assert unknown["text"] == "unknown route" and unknown["tone"] == "stop" and unknown["icon"] == "LAMPWAY_WIRE"


def test_the_github_route_exists_and_is_off(server_routes):
    """Contract 12's calm pass: a `github` route for contract 16's download, off by default like every route."""
    gh = next(r for r in server_routes if r["id"] == "github")
    assert set(gh["hosts"]) >= {"github.com", "objects.githubusercontent.com"} and gh["enabled"] is False


def test_route_rows_switch_states_and_hover(server_routes):
    routes = [dict(r, enabled=r["id"] == "fal") for r in server_routes]
    rows = {r["id"]: r for r in P.route_rows(routes, pending="openrouter")}
    assert rows["fal"]["switch"] == "on" and rows["openrouter"]["switch"] == "confirm" and rows["heygen"]["switch"] == "off"
    assert rows["openrouter"]["confirm"] == "Let data leave for openrouter.ai?"
    assert rows["openrouter"]["shield"] == "LAMPWAY_SHIELD_HALF" and rows["heygen"]["shield"] == "LAMPWAY_SHIELD_UNKNOWN"
    assert rows["model_download"]["shield"] == "LAMPWAY_SHIELD"
    assert "openrouter.ai" in rows["openrouter"]["tooltip"] and "never used" in rows["openrouter"]["tooltip"]


def test_refusal_shows_three_ways():
    log = [{"t": 1.0, "event": "send", "route": "fal", "kind": "image"},
           {"t": 2.0, "event": "refused", "route": "fal", "kind": "image", "asset_ids": ["a1"], "content_class": "private",
            "reason": "this asset is private and fal.ai keeps what it is sent: use a verified route, run it locally, or flip the per-asset override (logged)"}]
    card = P.last_refusal(log)
    assert card["title"] == "a private asset on a route that may keep it"
    assert [w["label"] for w in card["ways"]] == ["Use OpenRouter, zero retention", "Run it here instead", "Allow this asset once (logged)"]
    override = card["ways"][2]
    assert override["action"] == "override" and override["asset_id"] == "a1" and override["route"] == "fal" and override["tone"] == "stop"
    off = P.last_refusal([{"t": 3.0, "event": "refused", "route": "heygen", "reason": "route off"}])
    assert off["title"] == "heygen is off" and [w["action"] for w in off["ways"]] == ["route_on"]
    assert P.last_refusal(log[:1]) is None
    here = card["ways"][1]
    assert here["action"] == "local" and here["op"] == "lampway.choices_open" and here["group"] == "images", \
        "Run it here instead opens Choices on the job's kind, where a local option can be put first"
    video = P.last_refusal([dict(log[1], kind="video")])["ways"][1]
    assert video["group"] == "video"


def test_log_view_never_renders_content():
    marker = "SECRET-CONTENT-MARKER"
    row = {"t": 1700000000.0, "event": "send", "route": "openrouter", "provider": "openrouter.ai", "kind": "image", "bytes": 1200,
           "content_class": "public", "retention": "per model", "prompt": marker, "body": marker, "url": "https://x/?q=" + marker,
           "headers": {"Authorization": marker}, "query": marker}
    out = P.log_rows([row])
    assert marker not in repr(out)
    r = out[0]
    assert r["event"] == "send" and r["glyph"] == "LAMPWAY_WIRE" and r["route"] == "openrouter" and r["what"] == "image, 1200 bytes"
    assert r["bed"] == "wire_bed" and "openrouter.ai" in r["tooltip"] and "per model" in r["tooltip"]
    assert P.log_rows([dict(row, event="refused")])[0]["bed"] == "stop_bed"


def test_wire_colour_is_reserved():
    """The magenta wire is data leaving and nothing else: no theme slot of the Blender theme maps to it (the status bar's
    wire is a colour-baked glyph), and only the travelling dot's two glyphs are painted in it."""
    theme = (ROOT / "scripts/lampway/facelift/theme/build_theme.py").read_text(encoding="utf-8")
    users = re.findall(r'"(\w+)":\s*"(wire|wire_bed)(?:@[0-9A-Fa-f]+)?"', theme)
    assert users == [], users
    icons = (ROOT / "scripts/dev/brand_art/lampway_icons.py").read_text(encoding="utf-8")
    painted = sorted(set(re.findall(r'"([\w-]+)":\s*"wire(?:_bed)?"', icons)))
    assert painted == ["wire-dot-a", "wire-dot-b"], painted
