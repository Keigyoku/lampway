"""Audit F13 (2026-10-06): every tool a refusal names exists. A refusal's message and its help are what an agent acts on next; one
named `lampway_normalize_rigged` before it was built, others named tools that were renamed (lampway_asset_* -> lampway_vault_*).
The scan reads every raise and every help / error / next / hint value in the client's tool modules and the server, and checks
each `lampway_*` word against the registry."""
import ast
from pathlib import Path
import re

from lampway_server.agent.tools import TOOL_NAMES

ROOT = Path(__file__).resolve().parents[2]
NAME = re.compile(r"\blampway_[a-z0-9_]+\b")
SCANNED = (ROOT / "src/scripts/mixar/modules/lampway_tools", ROOT / "server/lampway_server")


def _named_in_refusals():
    for base in SCANNED:
        for p in base.rglob("*.py"):
            if "tests" in p.parts:
                continue
            tree = ast.parse(p.read_text(encoding="utf-8"))
            for n in ast.walk(tree):
                targets = [n.exc] if isinstance(n, ast.Raise) and n.exc is not None else []
                if isinstance(n, ast.Dict):
                    targets += [v for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant) and k.value in ("help", "error", "next", "hint")]
                for t in targets:
                    for s in (c.value for c in ast.walk(t) if isinstance(c, ast.Constant) and isinstance(c.value, str)):
                        for name in NAME.findall(s):
                            yield name, f"{p.relative_to(ROOT)}:{t.lineno}"


def test_every_tool_a_refusal_names_is_in_the_registry():
    missing = sorted({(name, where) for name, where in _named_in_refusals() if name not in TOOL_NAMES})
    assert not missing, missing


def test_the_scan_sees_a_refusal_naming_a_tool():
    assert any(name == "lampway_layered_material" for name, _ in _named_in_refusals())
